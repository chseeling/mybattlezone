from panda3d.core import ClockObject


class TankCommand:
    def __init__(self, throttle=0.0, turn=0.0, fire=False, barrel_tilt=0.0,
                 desired_world_pos=None, desired_heading=None, desired_barrel_tilt=None):
        self.throttle = throttle
        self.turn = turn
        self.fire = fire
        self.barrel_tilt = barrel_tilt
        self.desired_world_pos = desired_world_pos
        self.desired_heading = desired_heading
        self.desired_barrel_tilt = desired_barrel_tilt


class TankController:
    def command(self, app, avatar, dt, task_time):
        return TankCommand()


class RemoteTankController(TankController):
    def __init__(self, timeout_seconds=0.35):
        self.timeout_seconds = timeout_seconds
        self.current_command = TankCommand()
        self.last_update_time = None

    def submit_command(self, command, timestamp=None):
        if timestamp is None:
            timestamp = ClockObject.getGlobalClock().getFrameTime()
        self.current_command = command
        self.last_update_time = timestamp

    def submit_input(self, throttle=0.0, turn=0.0, fire=False, barrel_tilt=0.0):
        self.submit_command(TankCommand(throttle=throttle, turn=turn, fire=fire, barrel_tilt=barrel_tilt))

    def command(self, app, avatar, dt, task_time):
        if self.last_update_time is None:
            return TankCommand()

        now = ClockObject.getGlobalClock().getFrameTime()
        if now - self.last_update_time > self.timeout_seconds:
            self.current_command = TankCommand()
            return self.current_command

        command = self.current_command
        self.current_command = TankCommand(
            throttle=command.throttle,
            turn=command.turn,
            fire=False,
            barrel_tilt=command.barrel_tilt,
            desired_world_pos=command.desired_world_pos,
            desired_heading=command.desired_heading,
            desired_barrel_tilt=command.desired_barrel_tilt
        )
        return command
