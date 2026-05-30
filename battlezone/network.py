import json
import secrets
import socket

from panda3d.core import ClockObject, Point3

from battlezone.protocol import (
    NETWORK_CLIENT_TIMEOUT,
    NETWORK_COMMAND_HISTORY_LIMIT,
    NETWORK_COMMAND_RETRY_RATE,
    NETWORK_JOIN_RATE,
    NETWORK_PENDING_COMMAND_LIMIT,
    NETWORK_PROTOCOL_VERSION,
    NETWORK_SEND_RATE,
    NETWORK_SNAPSHOT_RATE,
)


class UdpTankInputBridge:
    def __init__(
            self,
            app,
            mode,
            host,
            port,
            tank_id,
            tank_ids,
            claimable_tank_ids,
            command_type,
            human_input_reader=None):
        self.app = app
        self.mode = mode
        self.host = host
        self.port = port
        self.tank_id = tank_id
        self.tank_ids = set(tank_ids)
        self.claimable_tank_ids_set = set(claimable_tank_ids)
        self.command_type = command_type
        self.human_input_reader = human_input_reader
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setblocking(False)
        self.client_addr = None
        self.client_addrs = {}
        self.client_last_seen = {}
        self.client_join_status = {}
        self.client_controller_types = {}
        self.client_player_ids = {}
        self.client_ready_states = {}
        self.client_join_order = []
        self.client_claim_tokens = {}
        self.client_claim_generations = {}
        self.client_last_input_sequences = {}
        self.processed_host_command_acks = {}
        self.processed_host_command_addrs = {}
        self.processed_host_command_order = []
        self.tank_claim_generation_counters = {}
        self.next_player_number = 1
        self.join_accepted = False
        self.join_rejected_reason = ""
        self.manual_claim_released = False
        self.player_id = ""
        self.claim_token = ""
        self.ownership_generation = 0
        self.client_sequence = 0
        self.client_command_sequence = 0
        self.pending_client_commands = {}
        self.pending_client_command_order = []
        self.last_join_send_time = -999
        self.last_send_time = 0
        self.last_snapshot_time = 0
        self.snapshot_frame_count = 0
        self.snapshot_packet_count = 0
        self.rejected_join_count = 0
        self.rejected_input_count = 0
        self.rejected_sequence_count = 0
        self.last_fire_down = False
        self.last_packet_time = None
        self.last_packet_count = 0

        if self.mode == "host":
            self.socket.bind((self.host, self.port))
        elif self.mode == "client":
            self.socket.bind(("", 0))
            self.server_addr = (self.host, self.port)

    def close(self):
        self.send_client_leave()
        self.socket.close()

    def status(self):
        if self.mode == "host":
            connected = self.connected_tank_ids()
            peer = ",".join(connected) if connected else "WAIT"
            return "NET SERVER {}".format(peer)
        if self.mode == "client":
            if self.join_accepted:
                state = "ACCEPTED"
            elif self.join_rejected_reason:
                state = "REJECTED"
            else:
                state = "JOINING"
            return "NET CLIENT {} {}".format(self.tank_id, state)
        return ""

    def connected_tank_ids(self):
        return sorted(self.client_addrs.keys(), key=lambda tank_id: int(tank_id))

    def network_tank_ids(self):
        return set(self.tank_ids)

    def claimable_tank_ids(self):
        return sorted(self.claimable_tank_ids_set, key=lambda tank_id: int(tank_id))

    def tank_is_claimable(self, tank_id):
        return tank_id in self.claimable_tank_ids_set

    def update(self, task_time):
        if self.mode == "host":
            self.receive_host_packets(task_time)
            self.expire_host_clients(task_time)
            self.send_host_snapshot(task_time)
        elif self.mode == "client":
            self.receive_client_packets(task_time)
            self.expire_client_claim(task_time)
            self.send_client_join(task_time)
            self.send_client_input(task_time)
            self.resend_pending_client_commands(task_time)

    def receive_host_packets(self, task_time):
        while True:
            try:
                payload, addr = self.socket.recvfrom(4096)
            except (BlockingIOError, ConnectionResetError, OSError):
                return

            try:
                message = json.loads(payload.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                continue

            message_type = message.get("type")
            if message_type == "join":
                self.handle_host_join(message, addr, task_time)
                continue
            if message_type == "leave":
                self.handle_host_leave(message, addr)
                continue
            if message_type == "start":
                self.handle_host_start(message, addr)
                continue
            if message_type == "restart":
                self.handle_host_restart(message, addr)
                continue
            if message_type == "enemy_fire":
                self.handle_host_enemy_fire(message, addr)
                continue
            if message_type == "investigation":
                self.handle_host_investigation(message, addr)
                continue
            if message_type == "terrain":
                self.handle_host_terrain(message, addr)
                continue
            if message_type == "command":
                self.handle_host_command(message, addr)
                continue

            if message_type != "input":
                continue

            tank_id = str(message.get("tank_id", self.tank_id))
            if tank_id not in self.network_tank_ids():
                continue
            if not self.accept_host_tank_intent(tank_id, addr, message, task_time):
                continue

            self.last_packet_time = task_time
            self.last_packet_count += 1
            self.app.submit_remote_tank_command(tank_id, self.command_from_message(message))

    def handle_host_join(self, message, addr, task_time):
        tank_id = str(message.get("tank_id", self.tank_id))
        if tank_id not in self.network_tank_ids():
            self.rejected_join_count += 1
            self.app.record_server_event("join rejected tank {} invalid".format(tank_id))
            self.send_host_join_ack(addr, tank_id, False, "invalid tank")
            return
        if not self.tank_is_claimable(tank_id):
            self.rejected_join_count += 1
            self.app.record_server_event("join rejected tank {} reserved".format(tank_id))
            self.send_host_join_ack(addr, tank_id, False, "tank not claimable")
            return

        if not self.accept_host_client_claim(tank_id, addr, task_time, message.get("controller")):
            self.rejected_join_count += 1
            self.app.record_server_event("join rejected tank {} already claimed".format(tank_id))
            self.send_host_join_ack(addr, tank_id, False, "tank already claimed")
            return

        self.app.record_server_event("join accepted tank {} {}".format(tank_id, self.client_controller_types.get(tank_id, "CLIENT")))
        if tank_id == "0":
            self.app.return_to_lobby_after_game_over("tank 0 joined")
        self.app.wake_network_arena_if_hibernating("tank {} joined".format(tank_id))
        self.app.assign_lobby_terrain_authority_if_needed()
        self.send_host_join_ack(addr, tank_id, True, "")

    def next_host_player_id(self):
        player_id = "player{}".format(self.next_player_number)
        self.next_player_number += 1
        return player_id

    def next_host_claim_generation(self, tank_id):
        generation = self.tank_claim_generation_counters.get(tank_id, 0) + 1
        self.tank_claim_generation_counters[tank_id] = generation
        return generation

    def build_host_claim_token(self, tank_id, generation):
        return "{}:{}:{}".format(tank_id, generation, secrets.token_hex(8))

    def accept_host_client_claim(self, tank_id, addr, task_time, controller=None):
        existing_addr = self.client_addrs.get(tank_id)
        if existing_addr is not None:
            if existing_addr != addr:
                return False
            self.client_last_seen[tank_id] = task_time
            if controller:
                self.client_controller_types[tank_id] = str(controller).upper()
            return True

        self.client_addr = addr
        self.client_addrs[tank_id] = addr
        self.client_last_seen[tank_id] = task_time
        self.client_join_status[tank_id] = "accepted"
        if controller:
            self.client_controller_types[tank_id] = str(controller).upper()
        self.client_player_ids[tank_id] = self.next_host_player_id()
        self.client_ready_states[tank_id] = True
        self.client_join_order.append(self.client_player_ids[tank_id])
        generation = self.next_host_claim_generation(tank_id)
        self.client_claim_generations[tank_id] = generation
        self.client_claim_tokens[tank_id] = self.build_host_claim_token(tank_id, generation)
        self.client_last_input_sequences[tank_id] = -1
        self.app.set_remote_control_tank(tank_id)
        return True

    def build_claim_identity_result(self, tank_id, claim="claimed"):
        return {
            "claim": claim,
            "tank_id": tank_id,
            "player_id": self.client_player_ids.get(tank_id, ""),
            "claim_token": self.client_claim_tokens.get(tank_id, ""),
            "ownership_generation": self.client_claim_generations.get(tank_id, 0)
        }

    def switch_host_client_claim(self, current_tank_id, target_tank_id, addr):
        if current_tank_id == target_tank_id:
            return True, "", self.build_claim_identity_result(current_tank_id, "already-current")
        if self.client_addrs.get(current_tank_id) != addr:
            return False, "current claim mismatch", {}
        if not self.tank_is_claimable(target_tank_id):
            return False, "target tank not claimable", {}
        if self.client_addrs.get(target_tank_id) is not None:
            return False, "target tank already claimed", {"target_tank_id": target_tank_id}

        player_id = self.client_player_ids.get(current_tank_id, "")
        controller = self.client_controller_types.get(current_tank_id, "CLIENT")
        ready = self.client_ready_states.get(current_tank_id, True)
        last_seen = self.client_last_seen.get(current_tank_id, ClockObject.getGlobalClock().getFrameTime())

        self.client_addrs.pop(current_tank_id, None)
        self.client_last_seen.pop(current_tank_id, None)
        self.client_join_status.pop(current_tank_id, None)
        self.client_controller_types.pop(current_tank_id, None)
        self.client_player_ids.pop(current_tank_id, None)
        self.client_ready_states.pop(current_tank_id, None)
        self.client_claim_tokens.pop(current_tank_id, None)
        self.client_claim_generations.pop(current_tank_id, None)
        self.client_last_input_sequences.pop(current_tank_id, None)
        self.app.submit_remote_tank_input(current_tank_id, throttle=0.0, turn=0.0, fire=False, barrel_tilt=0.0)
        self.app.clear_remote_control_tank(current_tank_id)

        self.client_addrs[target_tank_id] = addr
        self.client_last_seen[target_tank_id] = last_seen
        self.client_join_status[target_tank_id] = "accepted"
        self.client_controller_types[target_tank_id] = controller
        self.client_player_ids[target_tank_id] = player_id or self.next_host_player_id()
        self.client_ready_states[target_tank_id] = ready
        if self.client_player_ids[target_tank_id] not in self.client_join_order:
            self.client_join_order.append(self.client_player_ids[target_tank_id])
        generation = self.next_host_claim_generation(target_tank_id)
        self.client_claim_generations[target_tank_id] = generation
        self.client_claim_tokens[target_tank_id] = self.build_host_claim_token(target_tank_id, generation)
        self.client_last_input_sequences[target_tank_id] = -1
        if self.app.terrain_authority_tank_id == current_tank_id and self.app.terrain_authority_player_id == self.client_player_ids[target_tank_id]:
            self.app.terrain_authority_tank_id = target_tank_id
        self.app.set_remote_control_tank(target_tank_id)
        self.app.record_server_event("claim switch tank {} to {}".format(current_tank_id, target_tank_id))
        return True, "", self.build_claim_identity_result(target_tank_id, "switched")

    def host_claim_identity_matches(self, tank_id, addr, message, require_token=True):
        if self.client_addrs.get(tank_id) != addr:
            return False
        if not require_token:
            return True
        token = str(message.get("claim_token", ""))
        if token != self.client_claim_tokens.get(tank_id, ""):
            return False
        try:
            generation = int(message.get("ownership_generation", -1))
        except (TypeError, ValueError):
            return False
        return generation == self.client_claim_generations.get(tank_id)

    def accept_host_tank_intent(self, tank_id, addr, message, task_time):
        if not self.host_claim_identity_matches(tank_id, addr, message):
            self.rejected_input_count += 1
            return False
        try:
            client_sequence = int(message.get("client_sequence"))
        except (TypeError, ValueError):
            self.rejected_input_count += 1
            return False
        if client_sequence <= self.client_last_input_sequences.get(tank_id, -1):
            self.rejected_sequence_count += 1
            return False
        self.client_last_seen[tank_id] = task_time
        self.client_last_input_sequences[tank_id] = client_sequence
        controller = message.get("controller")
        if controller:
            self.client_controller_types[tank_id] = str(controller).upper()
        return True

    def release_host_client_claim(self, tank_id, addr=None, reason="released"):
        existing_addr = self.client_addrs.get(tank_id)
        if existing_addr is None:
            return False
        if addr is not None and existing_addr != addr:
            return False

        player_id = self.client_player_ids.get(tank_id, "")
        self.client_addrs.pop(tank_id, None)
        self.client_last_seen.pop(tank_id, None)
        self.client_join_status.pop(tank_id, None)
        self.client_controller_types.pop(tank_id, None)
        self.client_player_ids.pop(tank_id, None)
        self.client_ready_states.pop(tank_id, None)
        if player_id in self.client_join_order:
            self.client_join_order.remove(player_id)
        self.client_claim_tokens.pop(tank_id, None)
        self.client_claim_generations.pop(tank_id, None)
        self.client_last_input_sequences.pop(tank_id, None)
        self.app.submit_remote_tank_input(tank_id, throttle=0.0, turn=0.0, fire=False, barrel_tilt=0.0)
        self.app.clear_remote_control_tank(tank_id)
        self.app.handle_lobby_player_disconnected(player_id)
        self.app.record_server_event("claim {} tank {}".format(reason, tank_id))
        self.app.hibernate_empty_network_arena("no human claims")
        return True

    def handle_host_leave(self, message, addr):
        tank_id = str(message.get("tank_id", self.tank_id))
        if tank_id not in self.network_tank_ids():
            return
        if not self.host_claim_identity_matches(tank_id, addr, message):
            return
        self.release_host_client_claim(tank_id, addr, "released")

    def handle_host_restart(self, message, addr):
        tank_id = str(message.get("tank_id", self.tank_id))
        if tank_id != "0":
            return
        if not self.host_claim_identity_matches(tank_id, addr, message):
            return
        self.app.restart_game()

    def handle_host_start(self, message, addr):
        tank_id = str(message.get("tank_id", self.tank_id))
        if tank_id not in self.network_tank_ids():
            return
        if not self.host_claim_identity_matches(tank_id, addr, message):
            return
        self.app.start_game()

    def handle_host_enemy_fire(self, message, addr):
        tank_id = str(message.get("tank_id", self.tank_id))
        if tank_id != "0":
            return
        if not self.host_claim_identity_matches(tank_id, addr, message):
            return
        self.app.set_enemy_shooting_suspended(bool(message.get("suspended", False)))

    def handle_host_investigation(self, message, addr):
        tank_id = str(message.get("tank_id", self.tank_id))
        if tank_id != "0":
            return
        if not self.host_claim_identity_matches(tank_id, addr, message):
            return
        active = bool(message.get("active", False))
        if active:
            if not self.app.investigation_mode:
                self.app.enter_investigation()
                self.app.record_server_event("investigation pause")
        elif self.app.investigation_mode:
            self.app.exit_investigation()
            self.app.record_server_event("investigation resume")

    def handle_host_terrain(self, message, addr):
        tank_id = str(message.get("tank_id", self.tank_id))
        if tank_id not in self.network_tank_ids():
            return
        if not self.host_claim_identity_matches(tank_id, addr, message):
            return

        action = str(message.get("action", "set"))
        index = message.get("environment_index")
        try:
            index = None if index is None else int(index)
        except (TypeError, ValueError):
            index = None
        player_id = self.client_player_ids.get(tank_id, "")
        self.app.request_lobby_terrain_change(player_id, tank_id, action, index)

    def command_ack_payload(self, tank_id, command_id, accepted, reason="", result=None):
        return {
            "type": "command_ack",
            "protocol": NETWORK_PROTOCOL_VERSION,
            "tank_id": str(tank_id),
            "command_id": str(command_id),
            "accepted": bool(accepted),
            "reason": str(reason or ""),
            "result": result or {}
        }

    def send_host_command_ack_payload(self, addr, payload):
        try:
            self.socket.sendto(json.dumps(payload).encode("utf-8"), addr)
        except OSError:
            pass

    def remember_host_command_ack(self, command_id, addr, ack_payload):
        self.processed_host_command_acks[command_id] = ack_payload
        self.processed_host_command_addrs[command_id] = addr
        self.processed_host_command_order.append(command_id)
        while len(self.processed_host_command_order) > NETWORK_COMMAND_HISTORY_LIMIT:
            stale_command_id = self.processed_host_command_order.pop(0)
            if stale_command_id not in self.processed_host_command_order:
                self.processed_host_command_acks.pop(stale_command_id, None)
                self.processed_host_command_addrs.pop(stale_command_id, None)

    def handle_host_command(self, message, addr):
        tank_id = str(message.get("tank_id", self.tank_id))
        command_id = str(message.get("command_id", ""))
        if tank_id not in self.network_tank_ids():
            return
        existing_ack = self.processed_host_command_acks.get(command_id)
        if existing_ack is not None:
            if self.processed_host_command_addrs.get(command_id) == addr:
                self.send_host_command_ack_payload(addr, existing_ack)
            return
        if not self.host_claim_identity_matches(tank_id, addr, message):
            return
        if not command_id:
            ack = self.command_ack_payload(tank_id, "", False, "missing command id")
            self.send_host_command_ack_payload(addr, ack)
            return

        accepted, reason, result = self.dispatch_host_command(tank_id, message, addr)
        ack = self.command_ack_payload(tank_id, command_id, accepted, reason, result)
        self.remember_host_command_ack(command_id, addr, ack)
        self.send_host_command_ack_payload(addr, ack)

    def dispatch_host_command(self, tank_id, message, addr=None):
        command = str(message.get("command", ""))
        payload = message.get("payload", {})
        if not isinstance(payload, dict):
            payload = {}

        if command == "start":
            self.app.start_game()
            return True, "", {}

        if command == "restart":
            if tank_id != "0":
                return False, "restart requires tank 0", {}
            self.app.restart_game()
            return True, "", {}

        if command == "ready":
            self.client_ready_states[tank_id] = True
            self.app.record_server_event("ready tank {}".format(tank_id))
            return True, "", {"ready": True, "tank_id": tank_id}

        if command == "unready":
            if not self.app.waiting_to_start:
                return False, "ready state is lobby-only", {}
            self.client_ready_states[tank_id] = False
            self.app.record_server_event("unready tank {}".format(tank_id))
            return True, "", {"ready": False, "tank_id": tank_id}

        if command == "release_claim":
            released = self.release_host_client_claim(tank_id, reason="released")
            reason = "" if released else "claim already released"
            return released, reason, {"released": released, "tank_id": tank_id}

        if command == "claim_tank":
            target_tank_id = str(payload.get("target_tank_id", tank_id))
            if target_tank_id not in self.network_tank_ids():
                return False, "invalid target tank", {}
            return self.switch_host_client_claim(tank_id, target_tank_id, addr)

        if command == "enemy_fire":
            if tank_id != "0":
                return False, "enemy fire toggle requires tank 0", {}
            self.app.set_enemy_shooting_suspended(bool(payload.get("suspended", False)))
            return True, "", {"suspended": self.app.enemy_shooting_suspended}

        if command == "investigation":
            if tank_id != "0":
                return False, "investigation requires tank 0", {}
            active = bool(payload.get("active", False))
            if active:
                if not self.app.investigation_mode:
                    self.app.enter_investigation()
                    self.app.record_server_event("investigation pause")
            elif self.app.investigation_mode:
                self.app.exit_investigation()
                self.app.record_server_event("investigation resume")
            return True, "", {"active": self.app.investigation_mode}

        if command == "terrain":
            action = str(payload.get("action", "set"))
            index = payload.get("environment_index")
            try:
                index = None if index is None else int(index)
            except (TypeError, ValueError):
                index = None
            player_id = self.client_player_ids.get(tank_id, "")
            accepted = self.app.request_lobby_terrain_change(player_id, tank_id, action, index)
            reason = "" if accepted else "terrain command rejected"
            return accepted, reason, {"environment_index": self.app.environment_index}

        return False, "unknown command {}".format(command or "?"), {}

    def connected_player_rows(self):
        by_player = {}
        for tank_id, player_id in self.client_player_ids.items():
            by_player[player_id] = {
                "player_id": player_id,
                "tank_id": tank_id,
                "controller": self.client_controller_types.get(tank_id, "CLIENT"),
                "team_id": "T{}".format(tank_id),
                "role": "driver",
                "ready": self.client_ready_states.get(tank_id, True)
            }
        rows = [by_player[player_id] for player_id in self.client_join_order if player_id in by_player]
        for player_id, row in by_player.items():
            if player_id not in self.client_join_order:
                rows.append(row)
        return rows

    def host_lobby_can_start(self):
        required_tanks = self.app.server_lobby_expected_client_tanks()
        connected_tanks = set(self.connected_tank_ids())
        if not required_tanks.issubset(connected_tanks):
            return False
        for tank_id in required_tanks:
            if not self.client_ready_states.get(tank_id, False):
                return False
        return True

    def host_lobby_tank_rows(self):
        claims = self.host_claim_snapshot()
        rows = []
        for tank_id in self.app.tank_ids_for_state():
            claim = claims.get(tank_id, {})
            claimed = bool(claim)
            claimable = tank_id in self.claimable_tank_ids_set
            if claimed:
                source = claim.get("controller", "CLIENT")
                status = "CLAIMED"
                player_id = claim.get("player_id", "")
            elif not claimable:
                source = "RESERVED"
                status = "RESERVED"
                player_id = ""
            elif tank_id == "0":
                source = "OPEN"
                status = "OPEN"
                player_id = ""
            else:
                source = "AI"
                status = "SERVER_AI"
                player_id = ""
            rows.append({
                "tank_id": tank_id,
                "team_id": "T{}".format(tank_id),
                "claimable": claimable,
                "claimed": claimed,
                "player_id": player_id,
                "controller": source,
                "status": status,
                "lives": self.app.tank_lives(tank_id)
            })
        return rows

    def host_lobby_snapshot(self):
        required_tanks = sorted(self.app.server_lobby_expected_client_tanks(), key=lambda tank_id: int(tank_id))
        players = self.connected_player_rows()
        ready_count = len([player for player in players if player.get("ready")])
        return {
            "state": self.app.arena_state_label(),
            "phase": "hibernate" if self.app.arena_is_hibernating() else ("lobby" if self.app.waiting_to_start else "running"),
            "start_policy": "tank0_required",
            "can_start": self.host_lobby_can_start(),
            "required_tanks": required_tanks,
            "team_model": "teams_of_one",
            "late_join": True,
            "ready_count": ready_count,
            "players": players,
            "tanks": self.host_lobby_tank_rows(),
            "terrain": {
                "environment_index": self.app.environment_index,
                "environment_name": self.app.selected_environment()["name"],
                "authority_player_id": self.app.terrain_authority_player_id,
                "authority_tank_id": self.app.terrain_authority_tank_id,
                "locked": self.app.terrain_selection_locked()
            }
        }

    def host_claim_snapshot(self):
        claims = {}
        for tank_id in self.connected_tank_ids():
            claims[tank_id] = {
                "player_id": self.client_player_ids.get(tank_id, ""),
                "controller": self.client_controller_types.get(tank_id, "CLIENT"),
                "ownership_generation": self.client_claim_generations.get(tank_id, 0),
                "last_input_sequence": self.client_last_input_sequences.get(tank_id, -1)
            }
        return claims

    def host_status_snapshot(self):
        return {
            "host": self.host,
            "port": self.port,
            "claimable_count": len(self.claimable_tank_ids_set),
            "connected_count": len(self.client_addrs),
            "terrain_authority_player_id": self.app.terrain_authority_player_id,
            "terrain_authority_tank_id": self.app.terrain_authority_tank_id,
            "terrain_locked": self.app.terrain_selection_locked(),
            "rx_input_packets": self.last_packet_count,
            "snapshot_frames": self.snapshot_frame_count,
            "snapshot_packets": self.snapshot_packet_count,
            "rejected_joins": self.rejected_join_count,
            "rejected_inputs": self.rejected_input_count,
            "rejected_sequences": self.rejected_sequence_count
        }

    def send_host_join_ack(self, addr, tank_id, accepted, reason):
        payload = {
            "type": "join_ack",
            "protocol": NETWORK_PROTOCOL_VERSION,
            "tank_id": tank_id,
            "accepted": bool(accepted),
            "reason": reason,
            "connected_tanks": self.connected_tank_ids(),
            "claimable_tanks": self.claimable_tank_ids()
        }
        if accepted:
            payload.update({
                "player_id": self.client_player_ids.get(tank_id, ""),
                "claim_token": self.client_claim_tokens.get(tank_id, ""),
                "ownership_generation": self.client_claim_generations.get(tank_id, 0)
            })
        try:
            self.socket.sendto(json.dumps(payload).encode("utf-8"), addr)
        except OSError:
            pass

    def send_host_snapshot(self, task_time):
        if not self.client_addrs:
            return
        if task_time - self.last_snapshot_time < 1.0 / NETWORK_SNAPSHOT_RATE:
            return
        self.last_snapshot_time = task_time

        payload = self.app.build_network_snapshot(task_time)
        packet = json.dumps(payload).encode("utf-8")
        stale_tanks = []
        self.snapshot_frame_count += 1
        for tank_id, addr in self.client_addrs.items():
            try:
                self.socket.sendto(packet, addr)
                self.snapshot_packet_count += 1
            except OSError:
                stale_tanks.append(tank_id)
        for tank_id in stale_tanks:
            self.release_host_client_claim(tank_id, reason="stale-send")

    def expire_host_clients(self, task_time):
        stale_tanks = [
            tank_id
            for tank_id, last_seen in self.client_last_seen.items()
            if task_time - last_seen > NETWORK_CLIENT_TIMEOUT
        ]
        for tank_id in stale_tanks:
            self.release_host_client_claim(tank_id, reason="timeout")

    def receive_client_packets(self, task_time):
        while True:
            try:
                payload, _addr = self.socket.recvfrom(16384)
            except BlockingIOError:
                return
            except (ConnectionResetError, OSError):
                self.mark_client_disconnected()
                return

            try:
                message = json.loads(payload.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                continue

            message_type = message.get("type")
            if message_type == "join_ack":
                self.handle_client_join_ack(message)
                continue
            if message_type == "command_ack":
                self.handle_client_command_ack(message)
                continue

            if message_type != "snapshot":
                continue

            self.last_packet_time = task_time
            self.last_packet_count += 1
            self.app.apply_network_snapshot(message)

    def handle_client_join_ack(self, message):
        if str(message.get("tank_id", self.tank_id)) != self.tank_id:
            return
        was_accepted = self.join_accepted
        previous_token = self.claim_token
        previous_generation = self.ownership_generation
        self.join_accepted = bool(message.get("accepted", False))
        self.join_rejected_reason = "" if self.join_accepted else str(message.get("reason", "join rejected"))
        if self.join_accepted:
            self.manual_claim_released = False
            new_player_id = str(message.get("player_id", ""))
            new_claim_token = str(message.get("claim_token", ""))
            try:
                new_ownership_generation = int(message.get("ownership_generation", 0))
            except (TypeError, ValueError):
                new_ownership_generation = 0
            self.player_id = new_player_id
            self.claim_token = new_claim_token
            self.ownership_generation = new_ownership_generation
            if (
                    not was_accepted or
                    previous_token != new_claim_token or
                    previous_generation != new_ownership_generation):
                self.client_sequence = 0
                self.client_command_sequence = 0
                self.pending_client_commands = {}
                self.pending_client_command_order = []
        else:
            self.player_id = ""
            self.claim_token = ""
            self.ownership_generation = 0
            self.client_sequence = 0
            self.client_command_sequence = 0
            self.pending_client_commands = {}
            self.pending_client_command_order = []
        self.app.network_join_accepted = self.join_accepted
        self.app.network_join_rejected_reason = self.join_rejected_reason
        self.app.network_manual_claim_released = False
        self.app.network_claimed_tank_id = self.tank_id
        self.app.network_connected_tanks = message.get("connected_tanks", [])
        self.app.network_claimable_tanks = message.get("claimable_tanks", self.app.network_claimable_tanks)
        self.app.network_player_id = self.player_id
        self.app.network_claim_token = self.claim_token
        self.app.network_ownership_generation = self.ownership_generation
        self.last_packet_time = ClockObject.getGlobalClock().getFrameTime()
        if self.app.is_network_client_controller():
            if self.join_accepted and hasattr(self.app, "apply_network_claim_identity"):
                self.app.apply_network_claim_identity(
                    self.tank_id,
                    self.player_id,
                    self.claim_token,
                    self.ownership_generation
                )
            else:
                self.app.update_network_client_presentation()

    def apply_client_claim_identity(self, result):
        tank_id = str(result.get("tank_id", self.tank_id))
        if tank_id not in self.network_tank_ids():
            return
        self.tank_id = tank_id
        self.join_accepted = True
        self.join_rejected_reason = ""
        self.manual_claim_released = False
        self.player_id = str(result.get("player_id", self.player_id))
        self.claim_token = str(result.get("claim_token", self.claim_token))
        try:
            self.ownership_generation = int(result.get("ownership_generation", self.ownership_generation))
        except (TypeError, ValueError):
            self.ownership_generation = 0
        self.client_sequence = 0
        self.client_command_sequence = 0
        self.pending_client_commands = {}
        self.pending_client_command_order = []
        if hasattr(self.app, "apply_network_claim_identity"):
            self.app.apply_network_claim_identity(
                tank_id,
                self.player_id,
                self.claim_token,
                self.ownership_generation
            )

    def prepare_client_claim_target(self, tank_id):
        tank_id = str(tank_id)
        if tank_id not in self.network_tank_ids():
            return False
        self.tank_id = tank_id
        self.manual_claim_released = False
        self.join_accepted = False
        self.join_rejected_reason = ""
        self.player_id = ""
        self.claim_token = ""
        self.ownership_generation = 0
        self.client_sequence = 0
        self.client_command_sequence = 0
        self.pending_client_commands = {}
        self.pending_client_command_order = []
        self.last_join_send_time = -999
        if hasattr(self.app, "apply_network_claim_identity"):
            self.app.apply_network_claim_identity(tank_id, "", "", 0, accepted=False)
        return True

    def handle_client_command_ack(self, message):
        command_id = str(message.get("command_id", ""))
        if not command_id:
            return
        pending = self.pending_client_commands.pop(command_id, None)
        if command_id in self.pending_client_command_order:
            self.pending_client_command_order.remove(command_id)
        command = ""
        if pending is not None:
            command = str(pending.get("message", {}).get("command", ""))
        if command and hasattr(self.app, "note_network_command_ack"):
            self.app.note_network_command_ack(
                command,
                bool(message.get("accepted", False)),
                str(message.get("reason", ""))
            )
        if bool(message.get("accepted", False)) and command == "release_claim":
            self.mark_client_disconnected(manual_release=True)
            return
        if bool(message.get("accepted", False)) and command == "claim_tank":
            self.apply_client_claim_identity(message.get("result", {}))
            self.last_packet_time = ClockObject.getGlobalClock().getFrameTime()
            return
        self.last_packet_time = ClockObject.getGlobalClock().getFrameTime()

    def send_client_join(self, task_time):
        if self.join_accepted:
            return
        if self.manual_claim_released:
            return
        if task_time - self.last_join_send_time < 1.0 / NETWORK_JOIN_RATE:
            return
        self.last_join_send_time = task_time

        payload = {
            "type": "join",
            "protocol": NETWORK_PROTOCOL_VERSION,
            "tank_id": self.tank_id,
            "controller": self.app.network_client_controller_label()
        }
        try:
            self.socket.sendto(json.dumps(payload).encode("utf-8"), self.server_addr)
        except OSError:
            self.mark_client_disconnected()

    def expire_client_claim(self, task_time):
        if not self.join_accepted:
            return
        if self.last_packet_time is None:
            return
        if task_time - self.last_packet_time <= NETWORK_CLIENT_TIMEOUT:
            return
        self.mark_client_disconnected()

    def send_client_leave(self):
        if self.mode != "client" or not hasattr(self, "server_addr"):
            return
        if not self.join_accepted:
            return

        payload = {
            "type": "leave",
            "protocol": NETWORK_PROTOCOL_VERSION,
            "tank_id": self.tank_id,
            "claim_token": self.claim_token,
            "ownership_generation": self.ownership_generation
        }
        try:
            self.socket.sendto(json.dumps(payload).encode("utf-8"), self.server_addr)
        except OSError:
            pass
        self.join_accepted = False

    def send_pending_client_command(self, command_id, task_time=None, force=False):
        if self.mode != "client" or not hasattr(self, "server_addr"):
            return
        pending = self.pending_client_commands.get(command_id)
        if pending is None:
            return
        if task_time is None:
            task_time = ClockObject.getGlobalClock().getFrameTime()
        if (
                not force and
                task_time - pending.get("last_send_time", -999) < 1.0 / NETWORK_COMMAND_RETRY_RATE):
            return

        try:
            self.socket.sendto(json.dumps(pending["message"]).encode("utf-8"), self.server_addr)
            pending["last_send_time"] = task_time
            pending["attempts"] = pending.get("attempts", 0) + 1
        except OSError:
            self.mark_client_disconnected()

    def resend_pending_client_commands(self, task_time):
        if not self.join_accepted:
            return
        for command_id in list(self.pending_client_command_order):
            self.send_pending_client_command(command_id, task_time)

    def prune_pending_client_commands(self):
        while len(self.pending_client_command_order) > NETWORK_PENDING_COMMAND_LIMIT:
            stale_command_id = self.pending_client_command_order.pop(0)
            self.pending_client_commands.pop(stale_command_id, None)

    def send_client_command(self, command, payload=None):
        if self.mode != "client" or not hasattr(self, "server_addr"):
            return None
        if not self.join_accepted:
            return None

        self.client_command_sequence += 1
        player_id = self.player_id or "tank{}".format(self.tank_id)
        command_id = "{}:{}:{}".format(player_id, self.ownership_generation, self.client_command_sequence)
        message = {
            "type": "command",
            "protocol": NETWORK_PROTOCOL_VERSION,
            "tank_id": self.tank_id,
            "player_id": self.player_id,
            "claim_token": self.claim_token,
            "ownership_generation": self.ownership_generation,
            "command_id": command_id,
            "command": str(command),
            "payload": payload or {}
        }
        self.pending_client_commands[command_id] = {
            "message": message,
            "last_send_time": -999,
            "attempts": 0
        }
        self.pending_client_command_order.append(command_id)
        self.prune_pending_client_commands()
        self.send_pending_client_command(command_id, force=True)
        return command_id

    def send_client_restart(self):
        self.send_client_command("restart")

    def send_client_start(self):
        self.send_client_command("start")

    def send_client_ready(self, ready=True):
        self.send_client_command("ready" if ready else "unready")

    def send_client_release_claim(self):
        self.send_client_command("release_claim")

    def send_client_claim_tank(self, target_tank_id):
        self.send_client_command("claim_tank", {"target_tank_id": str(target_tank_id)})

    def send_client_enemy_fire(self, suspended):
        self.send_client_command("enemy_fire", {"suspended": bool(suspended)})

    def send_client_investigation(self, active):
        self.send_client_command("investigation", {"active": bool(active)})

    def send_client_terrain(self, action, environment_index=None):
        payload = {
            "action": str(action)
        }
        if environment_index is not None:
            payload["environment_index"] = int(environment_index)
        self.send_client_command("terrain", payload)

    def send_client_input(self, task_time):
        if not self.join_accepted:
            return
        if task_time - self.last_send_time < 1.0 / NETWORK_SEND_RATE:
            return
        dt = 0.05 if self.last_send_time <= 0 else min(max(task_time - self.last_send_time, 0.0), 0.05)
        self.last_send_time = task_time

        command = self.capture_local_input(dt, task_time)
        self.client_sequence += 1
        payload = {
            "type": "input",
            "tank_id": self.tank_id,
            "protocol": NETWORK_PROTOCOL_VERSION,
            "player_id": self.player_id,
            "claim_token": self.claim_token,
            "ownership_generation": self.ownership_generation,
            "client_sequence": self.client_sequence,
            "controller": self.app.network_client_controller_label()
        }
        payload.update(self.command_to_message(command))
        try:
            self.socket.sendto(json.dumps(payload).encode("utf-8"), self.server_addr)
        except OSError:
            self.mark_client_disconnected()

    def mark_client_disconnected(self, manual_release=False):
        if self.mode != "client":
            return
        self.manual_claim_released = bool(manual_release)
        self.join_accepted = False
        self.join_rejected_reason = ""
        self.player_id = ""
        self.claim_token = ""
        self.ownership_generation = 0
        self.client_sequence = 0
        self.client_command_sequence = 0
        self.pending_client_commands = {}
        self.pending_client_command_order = []
        self.app.network_join_accepted = False
        self.app.network_join_rejected_reason = ""
        self.app.network_manual_claim_released = bool(manual_release)
        self.app.network_player_id = ""
        self.app.network_claim_token = ""
        self.app.network_ownership_generation = 0
        self.app.network_terrain_authority_player_id = ""
        self.app.network_terrain_authority_tank_id = ""
        self.app.network_terrain_locked = False
        self.app.network_claim_metadata = {}
        self.app.network_lobby_state = {}
        self.app.network_snapshot_received = False
        self.app.network_snapshot_shot_visible = {}
        if hasattr(self.app, "update_network_client_audio_state"):
            self.app.update_network_client_audio_state(True, False)
        if self.app.is_network_client_controller():
            self.app.update_network_client_presentation()

    def capture_local_input(self, dt=0.05, task_time=0.0):
        if (
                hasattr(self.app, "network_client_uses_autonomous_controller") and
                self.app.network_client_uses_autonomous_controller()):
            return self.app.network_autonomous_client_command(dt, task_time)
        return self.capture_human_input()

    def capture_human_input(self):
        if self.human_input_reader is not None:
            return self.human_input_reader(self)
        return self.command_type()

    def command_to_message(self, command):
        payload = {
            "throttle": command.throttle,
            "turn": command.turn,
            "fire": command.fire,
            "barrel_tilt": command.barrel_tilt
        }
        if command.desired_world_pos is not None:
            payload["desired_world_pos"] = [
                command.desired_world_pos[0],
                command.desired_world_pos[1],
                command.desired_world_pos[2]
            ]
        if command.desired_heading is not None:
            payload["desired_heading"] = command.desired_heading
        if command.desired_barrel_tilt is not None:
            payload["desired_barrel_tilt"] = command.desired_barrel_tilt
        return payload

    def command_from_message(self, message):
        desired_world_pos = message.get("desired_world_pos")
        if desired_world_pos is not None:
            desired_world_pos = Point3(*desired_world_pos)
        desired_heading = message.get("desired_heading")
        desired_barrel_tilt = message.get("desired_barrel_tilt")
        return self.command_type(
            throttle=float(message.get("throttle", 0.0)),
            turn=float(message.get("turn", 0.0)),
            fire=bool(message.get("fire", False)),
            barrel_tilt=float(message.get("barrel_tilt", 0.0)),
            desired_world_pos=desired_world_pos,
            desired_heading=None if desired_heading is None else float(desired_heading),
            desired_barrel_tilt=None if desired_barrel_tilt is None else float(desired_barrel_tilt)
        )


