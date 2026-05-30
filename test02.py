import os

from panda3d.core import loadPrcFile, loadPrcFileData, AntialiasAttrib, KeyboardButton, CollisionSphere, CollisionNode, CollisionBox, CollisionPolygon
from panda3d.core import CollisionTraverser, CollisionHandlerEvent

from direct.interval.IntervalGlobal import *

from battlezone.config import (
    DEFAULT_NETWORK_HOST,
    DEFAULT_NETWORK_PORT,
    DEFAULT_SERVER_LOG_INTERVAL,
    DEFAULT_SERVER_TUI_WINDOW,
    client_controller_default,
    client_low_render_default,
    configured_network_mode,
    configured_network_mode_label,
    configured_server_ui_mode,
    env_bool,
    should_silence_server_startup,
)
from battlezone.protocol import (
    NETWORK_CLIENT_TIMEOUT,
    NETWORK_COMMAND_HISTORY_LIMIT,
    NETWORK_COMMAND_RETRY_RATE,
    NETWORK_EFFECT_DELAY,
    NETWORK_JOIN_RATE,
    NETWORK_PENDING_COMMAND_LIMIT,
    NETWORK_PROTOCOL_VERSION,
    NETWORK_RENDER_DELAY,
    NETWORK_SEND_RATE,
    NETWORK_SMOOTHING_RATE,
    NETWORK_SNAPSHOT_RATE,
)

loadPrcFile("config/conf.prc")

if should_silence_server_startup():
    loadPrcFileData("battlezone-headless-server", "\n".join([
        "audio-library-name null",
        "notify-level-device fatal",
        "notify-level-display warning",
        "notify-output /tmp/panda-notify.log",
    ]))

import json
import math
import secrets
import socket
import time
import atexit
from math import pi, sin, cos
from random import random

from direct.showbase.ShowBase import ShowBase
from direct.task import Task

from panda3d.core import AmbientLight
from panda3d.core import Vec4, Mat4, Point2, Point3, Point4, BitMask32, AudioSound
from panda3d.core import LineSegs, NodePath, TransparencyAttrib, ColorBlendAttrib, TextNode, ClockObject, CardMaker
from panda3d.core import Geom, GeomNode, GeomTriangles, GeomVertexData, GeomVertexFormat, GeomVertexWriter
from panda3d.core import LVecBase4, LVecBase2d, InputDevice, WindowProperties, Camera, PerspectiveLens

from direct.gui.OnscreenText import OnscreenText
from direct.filter.CommonFilters import CommonFilters
from direct.interval.LerpInterval import LerpPosInterval



arrow_right = KeyboardButton.right()
arrow_left = KeyboardButton.left()
arrow_back = KeyboardButton.down()
arrow_forward = KeyboardButton.up()
shift_key = KeyboardButton.shift()
space_key = KeyboardButton.space()
control_key = KeyboardButton.control()
f_key = KeyboardButton.ascii_key('f')
GG = LVecBase4(0, 1, 0, 1)  # game green constant
PLAYER_TURN_ANG_VEL = 43.2
ENEMY_TURN_ANG_VEL = 21.6
camera_dict = {"turn_ang_vel": PLAYER_TURN_ANG_VEL, "translate_vel": 30.0}
tanks_dict = {"0": {},
              "1": {"init_pos": Point3(30, 50, 0),
                    "color_scale": Point4(0, 0.7, 0, 1.0),
                    "move_params": {"Ax": 25, "Ay": 18, "Bx": -0.15, "By": 0.25, "phix": 10, "phiy": 0},
                    "coll_rad": 1.4,
                    "barrel_tilt": 0.0,
                    "shooting": False
                    },
              "2": {"init_pos": Point3(0, 50, 0),
                    "color_scale": Point4(1, 0.6, 0.1, 1.0),
                    "move_params": {"Ax": 16, "Ay": 18, "Bx": 0.3, "By": 0.35, "phix": 20, "phiy": 3},
                    "coll_rad": 1.4,
                    "barrel_tilt": 0.0,
                    "shooting": False
                    },
              "3": {"init_pos": Point3(-30, 40, 0),
                    "color_scale": Point4(0.1, 0.6, 0.5, 1.0),
                    "move_params": {"Ax": 16, "Ay": 18, "Bx": 0.3, "By": 0.35, "phix": -10, "phiy": 7},
                    "coll_rad": 1.4,
                    "barrel_tilt": 0.0,
                    "shooting": False
                    }
              }

def all_non_player_tank_ids():
    return {
        tank_id
        for tank_id in tanks_dict
        if tank_id != "0"
    }


def configured_active_tanks():
    network_mode = os.environ.get("BATTLEZONE_NET_MODE", "").lower()
    default_tanks = ",".join(sorted(all_non_player_tank_ids(), key=lambda tank_id: int(tank_id)))
    if network_mode == "client":
        return all_non_player_tank_ids()

    requested = os.environ.get("BATTLEZONE_ACTIVE_TANKS", default_tanks)
    active = {
        tank_id.strip()
        for tank_id in requested.split(",")
        if tank_id.strip() in tanks_dict and tank_id.strip() != "0"
    }
    if active:
        return active
    print("Ignoring BATTLEZONE_ACTIVE_TANKS='{}'; using tanks {}".format(requested, default_tanks))
    return {
        tank_id.strip()
        for tank_id in default_tanks.split(",")
        if tank_id.strip() in tanks_dict and tank_id.strip() != "0"
    }


tanks_list = configured_active_tanks()
NUMET = len(tanks_list)  # number of active non-player tanks

def network_tank_ids():
    return {"0"} | set(tanks_list)

def configured_claimable_tanks():
    valid_tanks = network_tank_ids()
    default_tanks = ",".join(sorted(valid_tanks, key=lambda tank_id: int(tank_id)))
    requested = os.environ.get("BATTLEZONE_CLAIMABLE_TANKS", default_tanks)
    claimable = {
        tank_id.strip()
        for tank_id in requested.split(",")
        if tank_id.strip() in valid_tanks
    }
    if claimable:
        return claimable
    print("Ignoring BATTLEZONE_CLAIMABLE_TANKS='{}'; using tanks {}".format(requested, default_tanks))
    return set(valid_tanks)

CLAIMABLE_TANK_IDS = configured_claimable_tanks()

DEBUG = env_bool("BATTLEZONE_DEBUG")
NETWORK_MODE = configured_network_mode()
NETWORK_MODE_LABEL = configured_network_mode_label()
NETWORK_HOST = os.environ.get("BATTLEZONE_NET_HOST", DEFAULT_NETWORK_HOST)
NETWORK_PORT = int(os.environ.get("BATTLEZONE_NET_PORT", DEFAULT_NETWORK_PORT))
NETWORK_TANK_ID = os.environ.get("BATTLEZONE_NET_TANK", "1")
NETWORK_CLIENT_CONTROLLER = os.environ.get(
    "BATTLEZONE_NET_CONTROLLER",
    client_controller_default(NETWORK_TANK_ID)
).lower()
NETWORK_CLIENT_LOW_RENDER_DEFAULT = client_low_render_default(NETWORK_TANK_ID)
NETWORK_CLIENT_LOW_RENDER = env_bool("BATTLEZONE_NET_CLIENT_LOW_RENDER", NETWORK_CLIENT_LOW_RENDER_DEFAULT == "1")
NETWORK_CLIENT_LOW_RENDER_SIZE = (960, 540)
NETWORK_SERVER_LOW_RENDER = env_bool("BATTLEZONE_NET_SERVER_LOW_RENDER", True)
NETWORK_SERVER_LOW_RENDER_SIZE = (720, 405)
SERVER_UI_MODE = configured_server_ui_mode()
SERVER_TUI_WINDOW_MODE = os.environ.get("BATTLEZONE_SERVER_TUI_WINDOW", DEFAULT_SERVER_TUI_WINDOW).lower()
SERVER_WINDOW_MODE = os.environ.get("BATTLEZONE_SERVER_WINDOW", SERVER_TUI_WINDOW_MODE).lower()
SERVER_LOG_INTERVAL = float(os.environ.get("BATTLEZONE_SERVER_LOG_INTERVAL", DEFAULT_SERVER_LOG_INTERVAL))
AUDIO_FOCUS_MUTE_DEFAULT = "0" if (
    NETWORK_MODE == "client" and
    NETWORK_TANK_ID == "0" and
    NETWORK_CLIENT_CONTROLLER not in {"auto", "autonomous", "ai", "enemy"}
) else "1"
AUDIO_FOCUS_MUTE = env_bool("BATTLEZONE_AUDIO_FOCUS_MUTE", AUDIO_FOCUS_MUTE_DEFAULT == "1")
MOUNTAIN_BLOOM_ALPHA = 0.11
MOUNTAIN_BLOOM_THICKNESS = 7
MOUNTAIN_HALO_ALPHA = 0.025
MOUNTAIN_HALO_THICKNESS = 16
WORLD_LINE_THICKNESS = 2.4
GPU_BLOOM_BLEND = (0.08, 1.0, 0.08, 0.0)
GPU_BLOOM_MIN_TRIGGER = 0.075
GPU_BLOOM_MAX_TRIGGER = 0.75
GPU_BLOOM_DESATURATION = 0.0
GPU_BLOOM_INTENSITY = 0.62
GPU_BLOOM_SIZE = "medium"
RADAR_RADIUS = 0.18
RADAR_RANGE = 120
RADAR_MARGIN = 0.12
RADAR_SWEEP_SPEED = 120
RADAR_SWEEP_SLICE_DEGREES = 78
RADAR_SWEEP_SLICE_ALPHA = 0.16
RADAR_SCAN_WIDTH_DEGREES = 6
RADAR_BLIP_FADE_SECONDS = 1.6
RADAR_BLIP_IDLE_ALPHA = 0.03
HUD_VIEWPORTS = (
    {"name": "PANORAMA", "heading": 0, "slot": (0.00, 1.00, 0.76, 1.00), "fov": 270, "aspect": 48 / 7,
     "slices": 18},
    {"name": "REAR", "heading": 180, "slot": (0.333, 0.667, 0.02, 0.26), "fov": 48, "aspect": 4 / 3},
)
HUD_VIEW_PADDING = 0.012
PLAYER_MAX_LIVES = 3
AUTONOMOUS_TANK_MAX_LIVES = 10
PLAYER_HIT_COOLDOWN = 1.2
PLAYER_FLASH_SECONDS = 0.45
PLAYER_HIT_SHAKE_SECONDS = 0.32
PLAYER_HIT_SHAKE_YAW = 1.2
PLAYER_HIT_SHAKE_PITCH = 0.7
PLAYER_RESTART_GRACE_SECONDS = 1.0
PLAYER_COLLISION_RADIUS = 1.5
PLAYER_HIT_COLLISION_RADIUS = 1.45
PLAYER_HIT_COLLISION_CENTER_Z = -1.15
PLAYER_HIT_MAX_HEIGHT_ABOVE_GROUND = 2.15
PLAYER_NETWORK_HIT_RADIUS = 1.55
PLAYER_HIT_EFFECT_SECONDS = 1.2
PROJECTILE_COLLISION_RADIUS = 0.18
TANK_COLLISION_RADIUS = 1.6
AUTONOMOUS_TANK_MAX_SPEED = 9.0
AUTONOMOUS_TANK_TURNING_SPEED_FACTOR = 0.45
PLAYER_CAMERA_HEIGHT = 2.0
START_CAMERA_TERRAIN_CLEARANCE = 4.0
TERRAIN_SLOPE_SAMPLE_DISTANCE = 3.0
TERRAIN_SLOPE_RESPONSE = 0.75
ENEMY_CONTROLLER_MODE = "TACTICAL"
TACTICAL_AI_DEBUG_LABELS = True
TACTICAL_AI_AIM_TOLERANCE_DEGREES = 3.0
TACTICAL_AI_BARREL_TILT_TOLERANCE_DEGREES = 1.2
TACTICAL_AI_IDEAL_RANGE = 72.0
TACTICAL_AI_MIN_RANGE = 34.0
TACTICAL_AI_MAX_RANGE = 145.0
TACTICAL_AI_REPOSITION_SECONDS = 2.4
TACTICAL_AI_MANEUVER_INTERVAL_SECONDS = 4.2
TACTICAL_AI_MANEUVER_DURATION_SECONDS = 1.7
TACTICAL_AI_POST_SHOT_MANEUVER_SECONDS = 1.4
TACTICAL_AI_RISKY_SHOT_CLEAR_FRACTION = 0.58
TACTICAL_AI_FIRE_COOLDOWN = 3.6
TACTICAL_AI_AIM_DWELL_SECONDS = 0.55
TACTICAL_AI_SHOT_VERTICAL_JITTER = 0.22
TACTICAL_AI_SHOT_LATERAL_JITTER = 0.55
TACTICAL_AI_FIRE_COOLDOWN_VARIATION = 0.9
TACTICAL_AI_OPENING_FIRE_STAGGER = 1.6
TACTICAL_AI_MANEUVER_VARIATION = 1.1
TACTICAL_AI_AIM_DWELL_VARIATION = 0.28
AI_SHOT_SPREAD_YAW_DEGREES = 2.2
AI_SHOT_SPREAD_PITCH_DEGREES = 1.0
TANK_RESPAWN_ATTACK_COOLDOWN = 5.0
TANK_FIRE_COOLDOWN = 1.1
PLAYER_BARREL_TILT_MIN = -8.0
PLAYER_BARREL_TILT_MAX = 12.0
PLAYER_BARREL_TILT_RATE = 18.0
PLAYER_BARREL_AIM_REFERENCE_DISTANCE = 500.0
PLAYER_SHOT_START_Y = 20.0
PLAYER_SHOT_START_Z = -0.2
PLAYER_SHOT_BACKTRACE_DISTANCE = 20.0
PLAYER_SIGHT_MOVES_WITH_BARREL = True
SHOT_GROUND_BURST_RADIUS = 3.0
SHOT_GROUND_BURST_SECONDS = 0.22
INVESTIGATE_WINDOW_SECONDS = 4.0
INVESTIGATE_FATAL_WINDOW_SECONDS = 999999.0
INVESTIGATION_GHOST_SPEED = 51.0
INVESTIGATION_GHOST_HEIGHT = 5.0
INVESTIGATION_DRONE_ORBIT_RADIUS = 48.0
INVESTIGATION_DRONE_ORBIT_ALTITUDE = 18.0
INVESTIGATION_DRONE_ORBIT_SPEED = 18.0
SHOT_DEFLECTION_CLEARANCE = 0.25
MAIN_CAMERA_MASK = BitMask32.bit(0)
AUX_CAMERA_MASK = BitMask32.bit(1)
DRONE_CAMERA_MASK = BitMask32.bit(2)
DRONE_VIEW_SLOT = (0.72, 0.98, 0.02, 0.25)
ENVIRONMENT_PREVIEW_SLOT = (0.68, 0.98, 0.04, 0.34)
DRONE_BATTERY_MAX = 100
DRONE_DEPLOY_MIN_BATTERY = 35
DRONE_RETURN_BATTERY = 20
DRONE_DRAIN_PER_SECOND = 1.8
DRONE_RECHARGE_PER_SECOND = 18
DRONE_SPEED = 13
DRONE_RETURN_SPEED = 17
DRONE_MAX_RANGE = 220
DRONE_ALTITUDE = 12
DRONE_DOCK_LEFT_OFFSET = 7
DRONE_DOCK_REAR_OFFSET = 1.5
DRONE_DOCK_ALTITUDE = 3.2
DRONE_IDLE_SCAN_DEGREES = 28
DRONE_IDLE_SCAN_SPEED = 1.25
DRONE_SURVEY_ALTITUDE = 34
DRONE_SURVEY_SECONDS = 8
DRONE_WAYPOINT_REACHED = 12
DRONE_WAYPOINT_MIN_RANGE = 55
DRONE_WAYPOINT_MAX_RANGE = 135
DRONE_TARGET_SWEEP_RADIUS = 54
DRONE_TARGET_SWEEP_VARIATION = 18
DRONE_LOW_ALTITUDE = 8
DRONE_HIGH_ALTITUDE = 17
DRONE_TURN_RATE = 32
DRONE_CAMERA_TURN_RATE = 42
DRONE_CAMERA_PITCH_RATE = 22
DRONE_CAMERA_FORWARD_OFFSET = 2.2
DRONE_CAMERA_VERTICAL_OFFSET = -0.25
DRONE_CAMERA_FOV = 82
DRONE_CAMERA_SCENE_HEIGHT = 3.0
DRONE_CAMERA_TARGET_FOCUS_RANGE = 95
DRONE_CAMERA_MAX_TARGET_FOCUS = 0.62
DRONE_BLUE = LVecBase4(0.12, 0.38, 1.0, 1)
DRONE_CYAN = LVecBase4(0.0, 0.75, 1.0, 1)
DRONE_DIM_BLUE = LVecBase4(0.02, 0.12, 0.32, 1)
ENVIRONMENTS = (
    {
        "name": "SIMPLE RANGE",
        "description": "OPEN TEST GROUND",
        "terrain": {"amplitude": 2.1, "frequency": 0.018, "cross_frequency": 0.012},
        "obstacles": (
            {"name": "Block-1", "kind": "block", "pos": Point3(18, 38, 0), "scale": Point3(7, 7, 5),
             "radius": 6.0},
            {"name": "Pyramid-1", "kind": "pyramid", "pos": Point3(-16, 32, 0), "scale": Point3(9, 9, 7),
             "radius": 6.5},
            {"name": "Cone-1", "kind": "cone", "pos": Point3(4, 68, 0), "scale": Point3(8, 8, 8),
             "radius": 5.8},
        ),
    },
    {
        "name": "CITY BLOCK",
        "description": "STREETS AND CORNERS",
        "terrain": {"amplitude": 0.65, "frequency": 0.012, "cross_frequency": 0.009},
        "obstacles": (
            {"name": "City-Block-W1", "kind": "block", "pos": Point3(-48, 42, 0), "scale": Point3(12, 18, 8),
             "radius": 10.8},
            {"name": "City-Block-E1", "kind": "block", "pos": Point3(48, 42, 0), "scale": Point3(12, 18, 7),
             "radius": 10.8},
            {"name": "City-Block-W2", "kind": "block", "pos": Point3(-48, 78, 0), "scale": Point3(12, 18, 9),
             "radius": 10.8},
            {"name": "City-Block-E2", "kind": "block", "pos": Point3(48, 78, 0), "scale": Point3(12, 18, 6),
             "radius": 10.8},
            {"name": "City-North-Block", "kind": "block", "pos": Point3(0, 92, 0), "scale": Point3(20, 12, 8),
             "radius": 11.8},
            {"name": "City-Plaza-Monument", "kind": "pyramid", "pos": Point3(0, 30, 0), "scale": Point3(7, 7, 10),
             "radius": 5.5},
            {"name": "City-North-Tower", "kind": "cone", "pos": Point3(0, 116, 0), "scale": Point3(8, 8, 13),
             "radius": 6.0},
        ),
    },
)
RADAR_SWEEP_TRAILS = (
    (0, 0.55, 2),
    (28, 0.10, 1),
    (56, 0.04, 1),
)


def terrain_height(x, y, terrain):
    if not terrain:
        return 0.1

    amplitude = terrain.get("amplitude", 0)
    frequency = terrain.get("frequency", 0.015)
    cross_frequency = terrain.get("cross_frequency", frequency * 0.7)
    return 0.1 + amplitude * (
        0.55 * sin(x * frequency) +
        0.35 * cos(y * frequency * 0.83) +
        0.25 * sin((x + y) * cross_frequency)
    )


def procedural_grid(x_min, x_max, y_min, y_max, n, terrain=None, subdivisions=6):
    del_x = (x_max - x_min) / n
    del_y = (y_max - y_min) / n

    lines = LineSegs()
    # constant y lines
    y0 = y_min
    for i in range(0, n + 1):
        segment_count = n * subdivisions
        for segment in range(segment_count + 1):
            x = x_min + (x_max - x_min) * segment / segment_count
            z = terrain_height(x, y0, terrain)
            if segment == 0:
                lines.moveTo(x, y0, z)
            else:
                lines.draw_to(x, y0, z)
        y0 += del_y

    # constant x lines
    x0 = x_min
    for i in range(0, n + 1):
        segment_count = n * subdivisions
        for segment in range(segment_count + 1):
            y = y_min + (y_max - y_min) * segment / segment_count
            z = terrain_height(x0, y, terrain)
            if segment == 0:
                lines.moveTo(x0, y, z)
            else:
                lines.draw_to(x0, y, z)
        x0 += del_x

    return lines


def configure_bloom_layer(node_path, alpha):
    node_path.setTransparency(TransparencyAttrib.MAlpha, 10)
    node_path.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.MAdd), 10)
    node_path.setBin("transparent", 0)
    node_path.setDepthWrite(False, 10)
    node_path.setDepthTest(False, 10)
    node_path.setColorScale(alpha, alpha, alpha, alpha, 10)
    return node_path


def create_lineSegs_object(data, idx_start=1, name='lines_'):
    points = data['points']
    lines_def = data['lines']

    lines = LineSegs(name)
    for line_def in lines_def:
        # print(line_def)
        idx0 = line_def[0] - idx_start
        lines.moveTo(points[idx0][0], points[idx0][1], points[idx0][2])
        for idx1 in line_def[1:]:
            # print(idx1)
            idx1 = idx1 - idx_start
            lines.drawTo(points[idx1][0], points[idx1][1], points[idx1][2])
    return lines


def create_line_nodepath(data, idx_start=1, name='lines_', thickness=3):
    lines = create_lineSegs_object(data, idx_start, name)
    lines.setThickness(thickness)
    return NodePath(lines.create())

# n : number of repeats on cylinder
def map_mountains(points, n):
    # find range of x
    xmin = points[0][0]
    xmax = xmin
    for point in points[1:]:
        if xmin > point[0]:
            xmin = point[0]
        if xmax < point[0]:
            xmax = point[0]
    radius = (xmax - xmin) * n / 2.0 / math.pi

    # map to circle of radius rad
    points_mapped = []
    for point in points:
        z = point[2]
        theta = (point[0] - xmin) / radius
        x = math.cos(-theta)
        y = math.sin(-theta)
        z = point[2]
        points_mapped.append([x, y, z])
    return points_mapped

def procedural_sight(line_seg, lower_level, engaged):
    sight_width = 0.25
    sight_tick = 0.1
    x0 = -sight_width / 2
    z0 = sight_tick
    sight_lower = -0.23
    sight_upper = 0.23

    if line_seg is None:
        line_seg = LineSegs()

    if lower_level:
        sight_level = sight_lower
        m = 1
    else:
        sight_level = sight_upper
        m = -1
    if engaged:
        x_eng = 0.07
        z_eng = 0.07
    else:
        x_eng = 0
        z_eng = 0

    line_seg.moveTo(x0 + x_eng, 0, m * z0 + sight_level + m * z_eng)
    line_seg.draw_to(x0, 0, sight_level)
    line_seg.draw_to(x0 + sight_width, 0, 0 + sight_level)
    line_seg.draw_to(x0 + sight_width - x_eng, 0, m * z0 + sight_level + m * z_eng)
    # outer - central lines
    line_seg.moveTo(0, 0, 0 + sight_level)
    line_seg.draw_to(0, 0, 0 + sight_level - m * 0.25)

    return line_seg


def procedural_radar_frame(radius):
    lines = LineSegs("radar-frame")
    segments = 48
    lines.moveTo(radius, 0, 0)
    for i in range(1, segments + 1):
        theta = 2 * pi * i / segments
        lines.drawTo(radius * cos(theta), 0, radius * sin(theta))

    tick = radius * 0.35
    lines.moveTo(-tick, 0, 0)
    lines.drawTo(tick, 0, 0)
    lines.moveTo(0, 0, -tick)
    lines.drawTo(0, 0, tick)
    lines.moveTo(0, 0, radius * 0.58)
    lines.drawTo(-radius * 0.09, 0, radius * 0.42)
    lines.moveTo(0, 0, radius * 0.58)
    lines.drawTo(radius * 0.09, 0, radius * 0.42)
    return lines


def procedural_radar_blip(size):
    lines = LineSegs("radar-blip")
    lines.moveTo(0, 0, size)
    lines.drawTo(size, 0, 0)
    lines.drawTo(0, 0, -size)
    lines.drawTo(-size, 0, 0)
    lines.drawTo(0, 0, size)
    return lines


def procedural_radar_sweep(radius):
    lines = LineSegs("radar-sweep")
    lines.moveTo(0, 0, 0)
    lines.drawTo(0, 0, radius * 0.92)
    return lines


def procedural_block():
    lines = LineSegs("structure-block")
    corners = [
        (-0.5, -0.5, 0), (0.5, -0.5, 0), (0.5, 0.5, 0), (-0.5, 0.5, 0),
        (-0.5, -0.5, 1), (0.5, -0.5, 1), (0.5, 0.5, 1), (-0.5, 0.5, 1),
    ]
    edges = (
        (0, 1), (1, 2), (2, 3), (3, 0),
        (4, 5), (5, 6), (6, 7), (7, 4),
        (0, 4), (1, 5), (2, 6), (3, 7),
    )
    for start, end in edges:
        lines.moveTo(*corners[start])
        lines.drawTo(*corners[end])
    return lines


def procedural_pyramid():
    lines = LineSegs("structure-pyramid")
    base = [(-0.5, -0.5, 0), (0.5, -0.5, 0), (0.5, 0.5, 0), (-0.5, 0.5, 0)]
    apex = (0, 0, 1)
    for idx, point in enumerate(base):
        next_point = base[(idx + 1) % len(base)]
        lines.moveTo(*point)
        lines.drawTo(*next_point)
        lines.moveTo(*point)
        lines.drawTo(*apex)
    return lines


def procedural_cone(segments=20):
    lines = LineSegs("structure-cone")
    apex = (0, 0, 1)
    points = []
    for i in range(segments):
        theta = 2 * pi * i / segments
        points.append((0.5 * cos(theta), 0.5 * sin(theta), 0))

    for i, point in enumerate(points):
        next_point = points[(i + 1) % segments]
        lines.moveTo(*point)
        lines.drawTo(*next_point)
        if i % 4 == 0:
            lines.moveTo(*point)
            lines.drawTo(*apex)
    return lines


def procedural_recon_drone():
    lines = LineSegs("recon-drone")
    points = [
        (0, 1.4, 0), (-0.8, -0.6, 0), (0.8, -0.6, 0),
        (-1.2, 0, 0), (1.2, 0, 0), (0, 0, 0.45), (0, 0, -0.35),
    ]
    edges = (
        (0, 1), (1, 2), (2, 0), (3, 4), (5, 6)
    )
    for start, end in edges:
        lines.moveTo(*points[start])
        lines.drawTo(*points[end])
    return lines


def procedural_home_tank_marker():
    lines = LineSegs("home-tank-marker")
    body = [(-1, -0.7, 0), (1, -0.7, 0), (1, 0.7, 0), (-1, 0.7, 0)]
    turret = [(-0.35, -0.25, 0.45), (0.35, -0.25, 0.45), (0.35, 0.25, 0.45), (-0.35, 0.25, 0.45)]
    for shape in (body, turret):
        for idx, point in enumerate(shape):
            next_point = shape[(idx + 1) % len(shape)]
            lines.moveTo(*point)
            lines.drawTo(*next_point)
    lines.moveTo(0, 0.25, 0.45)
    lines.drawTo(0, 1.4, 0.45)
    return lines


def create_structure_faces(kind):
    vertex_format = GeomVertexFormat.getV3()
    vertex_data = GeomVertexData("structure-faces-" + kind, vertex_format, Geom.UHStatic)
    vertices = GeomVertexWriter(vertex_data, "vertex")
    tris = GeomTriangles(Geom.UHStatic)

    def add_vertex(point):
        vertices.addData3f(*point)

    def add_triangle(a, b, c):
        row = vertex_data.getNumRows()
        vertex_data.setNumRows(row + 3)
        add_vertex(a)
        add_vertex(b)
        add_vertex(c)
        tris.addVertices(row, row + 1, row + 2)

    def add_quad(a, b, c, d):
        add_triangle(a, b, c)
        add_triangle(a, c, d)

    if kind == "block":
        p = [
            (-0.5, -0.5, 0), (0.5, -0.5, 0), (0.5, 0.5, 0), (-0.5, 0.5, 0),
            (-0.5, -0.5, 1), (0.5, -0.5, 1), (0.5, 0.5, 1), (-0.5, 0.5, 1),
        ]
        for face in ((0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1),
                     (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)):
            add_quad(p[face[0]], p[face[1]], p[face[2]], p[face[3]])
    elif kind == "pyramid":
        base = [(-0.5, -0.5, 0), (0.5, -0.5, 0), (0.5, 0.5, 0), (-0.5, 0.5, 0)]
        apex = (0, 0, 1)
        add_quad(base[0], base[1], base[2], base[3])
        for idx, point in enumerate(base):
            add_triangle(point, base[(idx + 1) % len(base)], apex)
    elif kind == "cone":
        segments = 24
        center = (0, 0, 0)
        apex = (0, 0, 1)
        points = []
        for i in range(segments):
            theta = 2 * pi * i / segments
            points.append((0.5 * cos(theta), 0.5 * sin(theta), 0))
        for idx, point in enumerate(points):
            next_point = points[(idx + 1) % segments]
            add_triangle(center, next_point, point)
            add_triangle(point, next_point, apex)

    geom = Geom(vertex_data)
    geom.addPrimitive(tris)
    node = GeomNode("structure-faces-" + kind)
    node.addGeom(geom)
    return NodePath(node)


def add_obstacle_shot_solids(collision_node, obstacle):
    kind = obstacle["kind"]
    scale = obstacle["scale"]
    half_x = scale[0] * 0.5
    half_y = scale[1] * 0.5
    height = scale[2]

    def add_polygon(*points):
        collision_node.addSolid(CollisionPolygon(*points))
        collision_node.addSolid(CollisionPolygon(*reversed(points)))

    if kind == "block":
        collision_node.addSolid(CollisionBox(Point3(0, 0, height * 0.5),
                                             half_x,
                                             half_y,
                                             height * 0.5))
    elif kind == "pyramid":
        base = [
            Point3(-half_x, -half_y, 0), Point3(half_x, -half_y, 0),
            Point3(half_x, half_y, 0), Point3(-half_x, half_y, 0),
        ]
        apex = Point3(0, 0, height)
        add_polygon(*base)
        for idx, point in enumerate(base):
            add_polygon(point, base[(idx + 1) % len(base)], apex)
    elif kind == "cone":
        segments = 16
        center = Point3(0, 0, 0)
        apex = Point3(0, 0, height)
        points = []
        for i in range(segments):
            theta = 2 * pi * i / segments
            points.append(Point3(half_x * cos(theta), half_y * sin(theta), 0))
        for idx, point in enumerate(points):
            next_point = points[(idx + 1) % segments]
            add_polygon(center, next_point, point)
            add_polygon(point, next_point, apex)


def angular_distance_degrees(a, b):
    return abs((a - b + 180) % 360 - 180)


def signed_angular_delta_degrees(target, current):
    return (target - current + 180) % 360 - 180


def create_radar_sweep_slice(radius, arc_degrees, max_alpha, segments=18):
    vertex_format = GeomVertexFormat.getV3c4()
    vertex_data = GeomVertexData("radar-sweep-slice", vertex_format, Geom.UHStatic)
    vertex_data.setNumRows(segments * 3)

    vertices = GeomVertexWriter(vertex_data, "vertex")
    colors = GeomVertexWriter(vertex_data, "color")
    tris = GeomTriangles(Geom.UHStatic)

    for i in range(segments):
        old_t = i / segments
        new_t = (i + 1) / segments
        old_angle = math.radians(-arc_degrees + arc_degrees * old_t)
        new_angle = math.radians(-arc_degrees + arc_degrees * new_t)
        old_alpha = max_alpha * old_t * old_t
        new_alpha = max_alpha * new_t * new_t
        center_alpha = max_alpha * 0.08

        row = i * 3
        vertices.addData3f(0, 0, 0)
        colors.addData4f(0, center_alpha, 0, center_alpha)
        vertices.addData3f(radius * sin(old_angle), 0, radius * cos(old_angle))
        colors.addData4f(0, old_alpha, 0, old_alpha)
        vertices.addData3f(radius * sin(new_angle), 0, radius * cos(new_angle))
        colors.addData4f(0, new_alpha, 0, new_alpha)
        tris.addVertices(row, row + 1, row + 2)

    geom = Geom(vertex_data)
    geom.addPrimitive(tris)
    node = GeomNode("radar-sweep-slice")
    node.addGeom(geom)
    return NodePath(node)


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


class TankAvatar:
    def __init__(self, tank_id, node, locator=None, collision_radius=TANK_COLLISION_RADIUS):
        self.tank_id = tank_id
        self.node = node
        self.locator = locator
        self.collision_radius = collision_radius

    def get_pos(self):
        return self.node.getPos(render)

    def get_hpr(self):
        return self.node.getHpr(render)

    def is_hidden(self):
        return self.node.isHidden()


class TankController:
    def command(self, app, avatar, dt, task_time):
        return TankCommand()


class HumanTankController(TankController):
    def __init__(self):
        self.fire_requested = False

    def request_fire(self):
        self.fire_requested = True

    def command(self, app, avatar, dt, task_time):
        fire = self.fire_requested
        self.fire_requested = False
        if base.mouseWatcherNode is None:
            return TankCommand(fire=fire)

        is_down = base.mouseWatcherNode.is_button_down
        turn = 0.0
        throttle = 0.0
        barrel_tilt = 0.0
        is_adjusting_barrel = is_down(shift_key)
        if is_down(arrow_right):
            turn -= 1.0
        if is_down(arrow_left):
            turn += 1.0
        if is_adjusting_barrel:
            if is_down(arrow_back):
                barrel_tilt -= 1.0
            if is_down(arrow_forward):
                barrel_tilt += 1.0
        else:
            if is_down(arrow_back):
                throttle -= 1.0
            if is_down(arrow_forward):
                throttle += 1.0

        return TankCommand(throttle=throttle, turn=turn, fire=fire, barrel_tilt=barrel_tilt)


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


class UdpTankInputBridge:
    def __init__(self, app, mode, host, port, tank_id):
        self.app = app
        self.mode = mode
        self.host = host
        self.port = port
        self.tank_id = tank_id
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

    def claimable_tank_ids(self):
        return sorted(CLAIMABLE_TANK_IDS, key=lambda tank_id: int(tank_id))

    def tank_is_claimable(self, tank_id):
        return tank_id in CLAIMABLE_TANK_IDS

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
            if tank_id not in network_tank_ids():
                continue
            if not self.accept_host_tank_intent(tank_id, addr, message, task_time):
                continue

            self.last_packet_time = task_time
            self.last_packet_count += 1
            self.app.submit_remote_tank_command(tank_id, self.command_from_message(message))

    def handle_host_join(self, message, addr, task_time):
        tank_id = str(message.get("tank_id", self.tank_id))
        if tank_id not in network_tank_ids():
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
        if tank_id not in network_tank_ids():
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
        if tank_id not in network_tank_ids():
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
        if tank_id not in network_tank_ids():
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
        if tank_id not in network_tank_ids():
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
            if target_tank_id not in network_tank_ids():
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
            claimable = tank_id in CLAIMABLE_TANK_IDS
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
            "claimable_count": len(CLAIMABLE_TANK_IDS),
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
        if tank_id not in network_tank_ids():
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
        if tank_id not in network_tank_ids():
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
        if base.mouseWatcherNode is None:
            return TankCommand()

        is_down = base.mouseWatcherNode.is_button_down
        turn = 0.0
        throttle = 0.0
        barrel_tilt = 0.0
        fire_down = is_down(space_key) or is_down(control_key) or is_down(f_key)
        fire = fire_down and not self.last_fire_down
        self.last_fire_down = fire_down

        if is_down(arrow_right):
            turn -= 1.0
        if is_down(arrow_left):
            turn += 1.0

        if is_down(shift_key):
            if is_down(arrow_back):
                barrel_tilt -= 1.0
            if is_down(arrow_forward):
                barrel_tilt += 1.0
        else:
            if is_down(arrow_back):
                throttle -= 1.0
            if is_down(arrow_forward):
                throttle += 1.0

        return TankCommand(throttle=throttle, turn=turn, fire=fire, barrel_tilt=barrel_tilt)

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
        return TankCommand(
            throttle=float(message.get("throttle", 0.0)),
            turn=float(message.get("turn", 0.0)),
            fire=bool(message.get("fire", False)),
            barrel_tilt=float(message.get("barrel_tilt", 0.0)),
            desired_world_pos=desired_world_pos,
            desired_heading=None if desired_heading is None else float(desired_heading),
            desired_barrel_tilt=None if desired_barrel_tilt is None else float(desired_barrel_tilt)
        )


class SineAiTankController(TankController):
    def __init__(self, tank_id):
        self.tank_id = tank_id

    def command(self, app, avatar, dt, task_time):
        tank_state = tanks_dict[self.tank_id]
        if not tank_state["move"] or avatar.is_hidden():
            return TankCommand()

        move_params = tank_state["move_params"]
        Ax = move_params["Ax"]
        Ay = move_params["Ay"]
        Bx = move_params["Bx"]
        By = move_params["By"]
        phix = move_params["phix"]
        phiy = move_params["phiy"]

        x = Ax * sin(Bx * task_time) + phix
        y = Ay * sin(By * task_time) + phiy
        dx = Ax * Bx * cos(Bx * task_time)
        dy = Ay * By * cos(By * task_time)
        heading = math.degrees(math.atan2(dy, dx))
        desired_world = render.getRelativePoint(avatar.locator, Point3(x, y, 0))

        return TankCommand(
            desired_world_pos=desired_world,
            desired_heading=heading,
            fire=self.should_fire(app, avatar)
        )

    def should_fire(self, app, avatar):
        if tanks_dict[self.tank_id]["shooting"]:
            return False

        aim_jitter = 0.18
        shoot_at = avatar.node.getRelativePoint(
            app.camera,
            (
                (random() - 0.5) * aim_jitter,
                (random() - 0.5) * aim_jitter,
                (random() - 0.5) * aim_jitter
            )
        )
        shoot_at = LVecBase2d(shoot_at[0], shoot_at[1]).normalized()
        return shoot_at[0] > 0.99995


class TacticalAiTankController(TankController):
    def __init__(self, tank_id):
        self.tank_id = tank_id
        tank_number = int(tank_id)
        self.reposition_until = 0
        self.strafe_sign = 1 if tank_number % 2 else -1
        self.next_fire_time = 0
        self.aim_acquired_since = None
        self.opening_fire_delay = 0.65 + tank_number * 0.45 + random() * TACTICAL_AI_OPENING_FIRE_STAGGER
        self.opening_maneuver_delay = 0.8 + tank_number * 0.55 + random() * TACTICAL_AI_MANEUVER_VARIATION
        self.fire_cooldown = (
            TACTICAL_AI_FIRE_COOLDOWN +
            (random() - 0.5) * TACTICAL_AI_FIRE_COOLDOWN_VARIATION +
            tank_number * 0.12
        )
        self.aim_dwell_seconds = max(
            0.25,
            TACTICAL_AI_AIM_DWELL_SECONDS +
            (random() - 0.5) * TACTICAL_AI_AIM_DWELL_VARIATION
        )
        self.reposition_seconds = TACTICAL_AI_REPOSITION_SECONDS + (random() - 0.5) * TACTICAL_AI_MANEUVER_VARIATION
        self.maneuver_interval_seconds = (
            TACTICAL_AI_MANEUVER_INTERVAL_SECONDS +
            tank_number * 0.45 +
            random() * TACTICAL_AI_MANEUVER_VARIATION
        )
        self.maneuver_duration_seconds = (
            TACTICAL_AI_MANEUVER_DURATION_SECONDS +
            (random() - 0.5) * TACTICAL_AI_MANEUVER_VARIATION
        )
        self.post_shot_maneuver_seconds = (
            TACTICAL_AI_POST_SHOT_MANEUVER_SECONDS +
            random() * TACTICAL_AI_MANEUVER_VARIATION
        )
        self.respawn_attack_delay = TANK_RESPAWN_ATTACK_COOLDOWN + random() * TACTICAL_AI_OPENING_FIRE_STAGGER
        self.aim_jitter_interval = 0.55 + random() * 0.65
        self.next_maneuver_time = self.opening_maneuver_delay
        self.ideal_range = TACTICAL_AI_IDEAL_RANGE + (tank_number - 2) * 8.0 + (random() - 0.5) * 10.0
        self.min_range = TACTICAL_AI_MIN_RANGE + (tank_number - 2) * 3.0 + (random() - 0.5) * 5.0
        self.max_range = TACTICAL_AI_MAX_RANGE + (tank_number - 2) * 9.0 + (random() - 0.5) * 12.0
        self.base_strafe_weight = 0.62 + tank_number * 0.08 + (random() - 0.5) * 0.16
        self.aim_heading_jitter = 0.0
        self.aim_tilt_jitter = 0.0
        self.next_aim_jitter_time = 0.0
        self.debug_state = "INIT"

    def reset_for_match(self, task_time):
        self.reposition_until = task_time + random() * 0.35
        self.next_fire_time = task_time + self.opening_fire_delay
        self.next_maneuver_time = task_time + self.opening_maneuver_delay
        self.aim_acquired_since = None
        self.next_aim_jitter_time = task_time + random() * self.aim_jitter_interval
        self.strafe_sign = -self.strafe_sign

    def command(self, app, avatar, dt, task_time):
        tank_can_move = True if self.tank_id == "0" else tanks_dict[self.tank_id]["move"]
        if not tank_can_move or avatar.is_hidden():
            self.aim_acquired_since = None
            self.debug_state = "DOWN"
            return TankCommand()
        if self.tank_id != "0" and not app.primary_player_target_available():
            self.aim_acquired_since = None
            self.debug_state = "WAIT"
            return TankCommand()

        observation = app.build_tank_observation(self.tank_id)
        if observation["distance_to_player"] < 0.001:
            self.aim_acquired_since = None
            self.debug_state = "HOLD"
            return TankCommand()

        if task_time > self.reposition_until and (
            not observation["line_of_sight"] or
            observation["distance_to_player"] < self.min_range or
            observation["distance_to_player"] > self.max_range
        ):
            self.reposition_until = task_time + self.reposition_seconds
            self.strafe_sign *= -1
        elif task_time >= self.next_maneuver_time:
            self.reposition_until = task_time + self.maneuver_duration_seconds
            self.next_maneuver_time = (
                task_time +
                self.maneuver_interval_seconds
            )
            self.strafe_sign *= -1

        if task_time >= self.next_aim_jitter_time:
            self.aim_heading_jitter = (random() - 0.5) * TACTICAL_AI_SHOT_LATERAL_JITTER
            self.aim_tilt_jitter = (random() - 0.5) * TACTICAL_AI_SHOT_VERTICAL_JITTER
            self.next_aim_jitter_time = task_time + self.aim_jitter_interval

        aim_heading = observation["heading_to_player"] + self.aim_heading_jitter
        desired_barrel_tilt = observation["barrel_tilt_target"] + self.aim_tilt_jitter
        aim_error = signed_angular_delta_degrees(aim_heading, observation["tank_heading"])
        barrel_tilt_error = desired_barrel_tilt - app.tank_barrel_tilt(self.tank_id)
        aligned = abs(aim_error) <= TACTICAL_AI_AIM_TOLERANCE_DEGREES
        barrel_aligned = abs(barrel_tilt_error) <= TACTICAL_AI_BARREL_TILT_TOLERANCE_DEGREES
        range_is_good = (
            self.min_range <= observation["distance_to_player"] <= self.max_range
        )
        firing_lane = observation["line_of_sight"] or observation["risky_line_of_sight"]
        stable_firing_solution = firing_lane and range_is_good and aligned and barrel_aligned
        if stable_firing_solution:
            if self.aim_acquired_since is None:
                self.aim_acquired_since = task_time
        else:
            self.aim_acquired_since = None

        aim_dwell_complete = (
            self.aim_acquired_since is not None and
            task_time - self.aim_acquired_since >= self.aim_dwell_seconds
        )
        can_fire = (
            firing_lane and
            aligned and
            barrel_aligned and
            range_is_good and
            aim_dwell_complete and
            not observation["is_shooting"] and
            task_time >= self.next_fire_time
        )
        if can_fire:
            self.debug_state = "RFIRE" if observation["risky_line_of_sight"] and not observation["line_of_sight"] else "FIRE"
            self.next_fire_time = task_time + self.fire_cooldown
            self.reposition_until = max(
                self.reposition_until,
                task_time + self.post_shot_maneuver_seconds
            )
            self.next_maneuver_time = max(
                self.next_maneuver_time,
                task_time + self.post_shot_maneuver_seconds
            )
            self.strafe_sign *= -1
            desired_world = self.choose_reposition_target(observation, task_time)
            return TankCommand(
                desired_world_pos=desired_world,
                desired_heading=aim_heading,
                desired_barrel_tilt=desired_barrel_tilt,
                fire=True
            )

        if firing_lane and range_is_good and task_time >= self.reposition_until:
            self.debug_state = self.tactical_debug_state(
                observation,
                firing_lane,
                aligned,
                range_is_good,
                aim_dwell_complete,
                task_time
            )
            return TankCommand(
                desired_world_pos=Point3(observation["tank_pos"]),
                desired_heading=aim_heading,
                desired_barrel_tilt=desired_barrel_tilt,
                fire=False
            )

        desired_world = self.choose_reposition_target(observation, task_time)
        self.debug_state = self.tactical_debug_state(
            observation,
            firing_lane,
            aligned,
            range_is_good,
            aim_dwell_complete,
            task_time
        )
        return TankCommand(
            desired_world_pos=desired_world,
            desired_heading=aim_heading,
            desired_barrel_tilt=desired_barrel_tilt,
            fire=False
        )

    def tactical_debug_state(self, observation, firing_lane, aligned, range_is_good, aim_dwell_complete, task_time):
        if task_time < self.next_fire_time:
            return "COOL"
        if observation["is_shooting"]:
            return "SHOT"
        if not range_is_good:
            return "RANGE"
        if not firing_lane:
            return "HOLD"
        if observation["risky_line_of_sight"] and not observation["line_of_sight"]:
            return "RISK"
        if not aligned:
            return "AIM"
        if abs(observation.get("barrel_tilt_error", 0.0)) > TACTICAL_AI_BARREL_TILT_TOLERANCE_DEGREES:
            return "ELEV"
        if not aim_dwell_complete:
            return "LOCK"
        if task_time < self.reposition_until:
            return "MOVE"
        return "HOLD"

    def choose_reposition_target(self, observation, task_time):
        tank_pos = observation["tank_pos"]
        player_dx = observation["player_dx"]
        player_dy = observation["player_dy"]
        distance = max(0.001, observation["distance_to_player"])
        to_player_x = player_dx / distance
        to_player_y = player_dy / distance
        strafe_x = -to_player_y * self.strafe_sign
        strafe_y = to_player_x * self.strafe_sign

        range_error = distance - self.ideal_range
        forward_weight = max(-0.9, min(0.9, range_error / self.ideal_range))
        strafe_weight = self.base_strafe_weight if task_time < self.reposition_until else 0.35
        if observation["line_of_sight"]:
            strafe_weight *= 0.55
        else:
            forward_weight *= 0.35

        move_x = to_player_x * forward_weight + strafe_x * strafe_weight
        move_y = to_player_y * forward_weight + strafe_y * strafe_weight
        move_len = math.sqrt(move_x ** 2 + move_y ** 2)
        if move_len < 0.001:
            move_x = strafe_x
            move_y = strafe_y
            move_len = 1

        step = 18.0
        return Point3(
            tank_pos[0] + move_x / move_len * step,
            tank_pos[1] + move_y / move_len * step,
            tank_pos[2]
        )


class ServerTuiDashboard:
    def __init__(self, app):
        self.app = app
        self.screen = None
        self.curses = None
        self.enabled = False
        self.last_draw_time = 0
        self.colors = {}

        try:
            import curses
            self.curses = curses
            self.screen = curses.initscr()
            curses.noecho()
            curses.cbreak()
            self.screen.keypad(True)
            self.screen.nodelay(True)
            if curses.has_colors():
                curses.start_color()
                curses.use_default_colors()
                self.init_colors()
            self.enabled = True
            self.draw()
        except Exception as exc:
            self.enabled = False
            self.close()
            print("Server TUI disabled: {}".format(exc))

    def init_colors(self):
        curses = self.curses
        curses.init_pair(1, curses.COLOR_GREEN, -1)
        curses.init_pair(2, curses.COLOR_GREEN, -1)
        curses.init_pair(3, curses.COLOR_YELLOW, -1)
        curses.init_pair(4, curses.COLOR_RED, -1)
        curses.init_pair(5, curses.COLOR_BLACK, curses.COLOR_GREEN)
        self.colors = {
            "normal": curses.color_pair(1),
            "dim": curses.color_pair(2) | curses.A_DIM,
            "warn": curses.color_pair(3),
            "error": curses.color_pair(4),
            "active": curses.color_pair(5),
            "bold": curses.color_pair(1) | curses.A_BOLD,
        }

    def color(self, name):
        return self.colors.get(name, 0)

    def close(self):
        if self.curses is None or self.screen is None:
            return
        try:
            self.screen.nodelay(False)
            self.screen.keypad(False)
            self.curses.nocbreak()
            self.curses.echo()
            self.curses.endwin()
        except Exception:
            pass
        self.screen = None

    def update(self, task_time):
        if not self.enabled:
            return
        self.handle_input()
        if task_time - self.last_draw_time >= 0.25:
            self.draw()
            self.last_draw_time = task_time

    def handle_input(self):
        try:
            key = self.screen.getch()
        except Exception:
            return
        if key in (ord("q"), ord("Q")):
            self.app.record_server_event("operator requested clean quit")
            self.close()
            self.app.userExit()

    def addstr(self, y, x, text, attr=0):
        try:
            height, width = self.screen.getmaxyx()
            if y < 0 or y >= height or x >= width:
                return
            clipped = str(text)[:max(0, width - x - 1)]
            self.screen.addstr(y, x, clipped, attr)
        except Exception:
            pass

    def draw_box(self, y, x, height, width, title):
        if height < 3 or width < 8:
            return
        top = "+" + "-" * (width - 2) + "+"
        mid = "|" + " " * (width - 2) + "|"
        self.addstr(y, x, top, self.color("dim"))
        for row in range(1, height - 1):
            self.addstr(y + row, x, mid, self.color("dim"))
        self.addstr(y + height - 1, x, top, self.color("dim"))
        if title:
            self.addstr(y, x + 2, " {} ".format(title.upper()), self.color("bold"))

    def draw_kv_lines(self, y, x, lines, attr=None):
        attr = self.color("normal") if attr is None else attr
        for index, line in enumerate(lines):
            self.addstr(y + index, x, line, attr)

    def draw_table(self, y, x, headers, rows, widths):
        header_text = " ".join([
            str(header)[:width].ljust(width)
            for header, width in zip(headers, widths)
        ])
        self.addstr(y, x, header_text, self.color("bold"))
        self.addstr(y + 1, x, "-" * len(header_text), self.color("dim"))
        for row_index, row in enumerate(rows):
            parts = []
            for value, width in zip(row, widths):
                parts.append(str(value)[:width].ljust(width))
            text = " ".join(parts)
            attr = self.color("normal")
            status_text = " ".join([str(value) for value in row])
            if "ERR" in status_text or "BAD" in status_text:
                attr = self.color("error")
            elif "WARN" in status_text or "STALE" in status_text:
                attr = self.color("warn")
            elif "JOINED" in status_text:
                attr = self.color("bold")
            elif "RESERVED" in status_text:
                attr = self.color("dim")
            self.addstr(y + 2 + row_index, x, text, attr)

    def draw(self):
        if not self.enabled:
            return
        state = self.app.server_dashboard_state()
        try:
            self.screen.erase()
        except Exception:
            return

        height, width = self.screen.getmaxyx()
        if height < 24 or width < 78:
            self.addstr(0, 0, "BATTLEZONE SERVER TUI", self.color("bold"))
            self.addstr(2, 0, "Terminal too small. Use at least 78x24.", self.color("warn"))
            self.screen.refresh()
            return

        self.addstr(0, 2, "BATTLEZONE ARENA SERVER", self.color("bold"))
        self.addstr(0, max(42, width - 22), "q clean quit", self.color("dim"))

        left_w = min(42, width // 2 - 2)
        right_x = left_w + 3
        right_w = width - right_x - 2

        self.draw_box(2, 1, 9, left_w, "Arena")
        arena = state["arena"]
        self.draw_kv_lines(4, 3, [
            "MODE    {}".format(arena["mode"]),
            "STATE   {}".format(arena["state"]),
            "UPTIME  {}".format(arena["uptime"]),
            "ENV     {}".format(arena["environment"]),
            "AUTH    {}".format(arena["terrain_authority"]),
            "VIEW    {}".format(arena["view"]),
        ])

        self.draw_box(2, right_x, 8, right_w, "Network")
        network = state["network"]
        lobby = state["lobby"]
        self.draw_kv_lines(4, right_x + 2, [
            "UDP {}:{}  PROTO {}".format(network["host"], network["port"], network["protocol"]),
            "RX {}  SNAP {}/{}".format(network["rx_input_packets"], network["snapshot_packets"], network["snapshot_frames"]),
            "REJECT J{} I{} S{}".format(network["rejected_joins"], network["rejected_inputs"], network["rejected_sequences"]),
            "LOBBY P{} R{} START {} {}".format(lobby["player_count"], lobby["ready_count"], lobby["start"], lobby["team_model"]),
        ])

        self.draw_box(11, 1, 8, left_w, "Autonomy")
        autonomy = state["autonomy"]
        self.draw_kv_lines(13, 3, [
            "FALLBACK ACTIVE {}".format(autonomy["fallback_active_count"]),
            "HUMAN CLAIMS    {}".format(autonomy["human_claim_count"]),
            "ENEMY FIRE      {}".format(autonomy["enemy_fire"]),
            "TEAMS           {}".format(autonomy["team_model"]),
        ])

        self.draw_box(11, right_x, 8, right_w, "Claims")
        claim_rows = [
            (row["tank"], row["source"], row["player"], row["generation"], row["sequence"], row["heartbeat"])
            for row in state["claims"]
        ]
        self.draw_table(13, right_x + 2, ("TANK", "SRC", "PLAYER", "GEN", "SEQ", "AGE"), claim_rows[:4], (5, 8, 10, 5, 7, 6))

        tank_box_height = min(9, max(6, height - 29))
        self.draw_box(20, 1, tank_box_height, width - 2, "Tanks")
        tank_rows = [
            (row["tank"], row["team"], row["source"], row["lives"], row["state"], row["shot"])
            for row in state["tanks"]
        ]
        self.draw_table(22, 3, ("TANK", "TEAM", "SOURCE", "LIVES", "STATE", "SHOT"), tank_rows[:max(1, tank_box_height - 3)], (6, 7, 12, 7, 16, 8))

        event_y = 20 + tank_box_height + 1
        event_h = max(5, height - event_y - 1)
        self.draw_box(event_y, 1, event_h, width - 2, "Events")
        events = state["events"][-max(1, event_h - 3):]
        for index, event in enumerate(events):
            attr = self.color("normal")
            if "reject" in event.lower() or "bad" in event.lower():
                attr = self.color("warn")
            if "error" in event.lower():
                attr = self.color("error")
            self.addstr(event_y + 2 + index, 3, event, attr)

        self.screen.refresh()


class MyApp(ShowBase):
    def __init__(self):
        ShowBase.__init__(self)
        self.server_started_at = time.monotonic()
        self.server_event_log = []
        self.server_tui_dashboard = None
        self.server_log_last_status_time = -999.0
        self.arena_hibernating = False
        self.terrain_authority_player_id = ""
        self.terrain_authority_tank_id = ""

        self.ambient_snd = base.loader.loadSfx("sfx/tank_with_radar.ogg")
        self.mainShot_snd = base.loader.loadSfx("sfx/mainShot.ogg")
        self.enemyShot_snd = base.loader.loadSfx("sfx/enemyShot.ogg")
        self.enemyTankExplosion_snd = base.loader.loadSfx("sfx/enemyTankExplosion.ogg")
        self.playerHit_snd = base.loader.loadSfx("sfx/enemyTankExplosion.ogg")
        self.gameOver_snd = base.loader.loadSfx("sfx/gameOver.wav")
        self.investigation_snd = base.loader.loadSfx("sfx/investigation.wav")
        self.investigation_snd.setLoop(True)
        self.audio_focus_enabled = AUDIO_FOCUS_MUTE
        self.audio_has_focus = True
        self.sound_base_volumes = {
            self.ambient_snd: 1.0,
            self.mainShot_snd: 1.0,
            self.enemyShot_snd: 1.0,
            self.enemyTankExplosion_snd: 1.0,
            self.playerHit_snd: 0.42,
            self.gameOver_snd: 1.0,
            self.investigation_snd: 0.9,
        }
        self.apply_audio_focus_volume()

        if DEBUG:
            device_list = self.devices.getDevices()
            for device in device_list:
                print(device.device_class)
                # if device.device_class == DeviceClass.flight_stick:
                #    print("Have Joy stick")

        # render.setDepthTest(False)
        self.camLens.setFov(50)
        base.cam.node().setCameraMask(MAIN_CAMERA_MASK)
        render.setAntialias(AntialiasAttrib.MLine)

        base.setBackgroundColor(0, 0, 0)
        base.disableMouse()
        props = WindowProperties()
        # props.setCursorHidden(True)
        if hasattr(base.win, "requestProperties"):
            base.win.requestProperties(props)

        # Load the environment models
        self.ground = self.loader.loadModel("models/ground_bl.egg")

        self.tank = self.loader.loadModel("models/tank_bl.egg")
        self.tank.setRenderModeWireframe()

        self.ground.setRenderModeWireframe()
        self.ground.setScale(100, 100, 1)

        self.environment_index = 0
        self.active_obstacles = ENVIRONMENTS[self.environment_index]["obstacles"]

        # tank as lines
        #   set up explosion variables
        #   explosion intervals added in renderTanks() method
        for t in tanks_list:
            tanks_dict[t]["explosion"] = Parallel(name="Tank{}-Explosion".format(t))

        # group node for all enemy tanks
        self.tank_group = render.attachNewNode("Tanks")
        self.renderTanks(self.tank_group)

        # tank rounds
        with open('models/tank_round.json', "r") as f:
            data = json.load(f)
        lines = create_lineSegs_object(data, 0)
        lines.setThickness(WORLD_LINE_THICKNESS)

        gn_round = lines.create()
        np_round = NodePath(gn_round)

        self.tank_round = []
        #
        self.tank_round.append(render.attachNewNode("tank-round"))
        np_round.instanceTo(self.tank_round[0])
        self.tank_round[0].hide()
        self.tank_round[0].setColorScale(0.3, 0.3, 1.0, 1.0)
        self.tank_round[0].setPos(0, PLAYER_SHOT_START_Y, PLAYER_SHOT_START_Z - 10)
        self.tank_round[0].setHpr(self.tank_round[0], 0, 90, 0)
        self.tank_round[0].setScale(0.2, 0.2, 0.2)
        self.tank_round[0].reparentTo(camera)

        self.player_tank_visual = render.attachNewNode("Tank0-Visual")
        self.tank.instanceTo(self.player_tank_visual)
        self.player_tank_visual.setColorScale(0.05, 0.35, 1.0, 1.0)
        self.player_tank_visual.hide(MAIN_CAMERA_MASK | AUX_CAMERA_MASK)
        self.player_hit_effect_serial = 0
        self.player_damage_event_serial = 0
        self.player_hit_effect_pos = Point3(0, 0, 0)
        self.player_hit_effect_hpr = Point3(0, 0, 0)
        self.network_player_damage_event_serial = 0
        self.network_player_hit_effect_serial = 0
        self.tank_hit_event_serial = 0
        self.last_tank_hit_event = {}
        self.network_tank_hit_event_serial = 0
        self.shot_ground_burst_serial = 0
        self.last_shot_ground_burst_event = {}
        self.network_shot_ground_burst_serial = 0
        self.player_tank_visual_hidden_for_effect = False

        # render enemy tank round
        for t in tanks_list:
            tanks_dict[t]["round"] = render.attachNewNode("tank{}-round".format(t))
            np_round.instanceTo(tanks_dict[t]["round"])
            tanks_dict[t]["round"].setPos(-0.4, 0, 1.61325)
            tanks_dict[t]["round"].setHpr(tanks_dict[t]["round"], 0, 0, 90)
            tanks_dict[t]["round"].setScale(0.14, 0.14, 0.14)
            tanks_dict[t]["round"].reparentTo(tanks_dict[t]["tank"])

        self.setup_tank_runtime_states()

        #
        # new mountain method
        self.render_mountains()

        ####################
        # collisions       #
        ####################
        if DEBUG:
            print(CollisionNode.getDefaultCollideMask())

        # Initialize collision Handler
        self.collHandEvent = CollisionHandlerEvent()
        self.collHandEvent.addInPattern('into-%in')

        # collision spheres enemy tank
        for t in tanks_list:
            cs = CollisionSphere(0, 0, 0.9, tanks_dict[t]["coll_rad"])
            cnodePath = tanks_dict[t]["tank"].attachNewNode(CollisionNode('cTank' + t))
            cnodePath.node().addSolid(cs)

            if DEBUG:
                # cnodePath.show()
                pass
        self.tank_group.setCollideMask(BitMask32(0x10))


        # print(self.tank_group.getCollideMask())
        # print(tanks_dict['1']["tank"].getCollideMask())

        # collision sphere for round of main tank
        cs = CollisionSphere(0, 0, 0, PROJECTILE_COLLISION_RADIUS)
        tr_cnodePath = self.tank_round[0].attachNewNode(CollisionNode('cTankRound'))
        tr_cnodePath.node().addSolid(cs)

        # collision spheres for enemy tank rounds
        cs = CollisionSphere(0, 0, 0, PROJECTILE_COLLISION_RADIUS)
        for t in tanks_list:
            np = tanks_dict[t]["round"].attachNewNode(CollisionNode('ceTankRound' + t))
            np.node().addSolid(cs)
            np.node().setFromCollideMask(BitMask32(0x20))
            # np.show()

        # collision sphere main tank
        cs = CollisionSphere(0, 0, PLAYER_HIT_COLLISION_CENTER_Z, PLAYER_HIT_COLLISION_RADIUS)
        np = self.camera.attachNewNode(CollisionNode('cmTank'))
        np.node().addSolid(cs)
        # np.show()

        # Initialise Traverser
        traverser = CollisionTraverser('Main Traverser')
        if DEBUG:
            traverser.showCollisions(render)
        base.cTrav = traverser


        # from objects
        traverser.addCollider(tr_cnodePath, self.collHandEvent)

        np_list = render.findAllMatches("**/ceTankRound*")
        for np in np_list:
            traverser.addCollider(np, self.collHandEvent)

        self.player_barrel_tilt = 0.0
        for t in tanks_list:
            tanks_dict[t]["barrel_tilt"] = 0.0
        self.render_grid()
        self.render_obstacles()

        alight = AmbientLight('ambientLight')
        alight.setColor(Vec4(0, 0, 0, 0))  # ambient light is dim red
        # alightNP = self.render.attachNewNode(alight)

        # render sight
        self.render_sight()
        self.render_radar()
        self.render_player_hud()
        self.render_tank_hud_labels()
        self.render_auxiliary_views()
        self.render_recon_drone()
        self.render_environment_preview()
        self.display_filters = CommonFilters(base.win, base.cam)
        self.gpu_bloom_available = True

        # Tasks
        for t in tanks_list:
            tanks_dict[t]["move"] = True
        self.setup_tank_control_architecture()
        self.setup_network_controller_prototype()
        self.setup_server_operator_ui()

        self.taskMgr.add(self.spinCameraTask, "SpinCameraTask")
        self.taskMgr.add(self.updateTankControllersTask, "UpdateTankControllersTask")
        self.taskMgr.add(self.updateRadarTask, "UpdateRadarTask")
        self.taskMgr.add(self.updatePlayerFeedbackTask, "UpdatePlayerFeedbackTask")
        self.taskMgr.add(self.updateAuxiliaryViewsTask, "UpdateAuxiliaryViewsTask")
        self.taskMgr.add(self.updateReconDroneTask, "UpdateReconDroneTask")
        self.taskMgr.add(self.updateTankHudLabelsTask, "UpdateTankHudLabelsTask")
        self.taskMgr.add(self.updateAudioFocusTask, "UpdateAudioFocusTask")
        if self.network_bridge is not None:
            self.taskMgr.add(self.updateNetworkTask, "UpdateNetworkTask")
        if self.server_tui_dashboard is not None and self.server_tui_dashboard.enabled:
            self.taskMgr.add(self.updateServerTuiTask, "UpdateServerTuiTask")
        if self.server_log_enabled():
            self.taskMgr.add(self.updateServerLogTask, "UpdateServerLogTask")

        # base.messenger.toggleVerbose()

        self.bloom_enabled = True
        if self.is_network_client_low_render() or self.is_network_server_low_render():
            self.bloom_enabled = False
        self.accept('enter', self.start_game)
        self.accept('space', self.request_player_fire)
        self.accept('space-up', self.shot_clear)
        self.accept('f', self.request_player_fire)
        self.accept('f-up', self.shot_clear)
        self.accept('mouse1', self.request_player_fire)
        self.accept('mouse1-up', self.shot_clear)
        self.accept('control', self.request_player_fire)
        self.accept('control-up', self.shot_clear)
        self.accept('shot-done', self.reset_shot)
        self.accept('b', self.toggle_bloom)
        self.accept('z', self.toggle_network_interpolation)
        self.accept('s', self.toggle_enemy_shooting)
        self.accept('d', self.toggle_recon_drone)
        self.accept('i', self.toggle_investigation)
        self.accept('r', self.restart_game)
        self.accept('y', self.set_network_lobby_ready, extraArgs=[True])
        self.accept('u', self.set_network_lobby_ready, extraArgs=[False])
        self.accept('l', self.release_network_lobby_claim)
        self.accept('j', self.rejoin_network_lobby_claim)
        self.accept('tab', self.cycle_environment)
        self.accept('arrow_left', self.previous_environment)
        self.accept('arrow_right', self.next_environment)
        self.accept('0', self.set_human_control_tank, extraArgs=["0"])
        for t in sorted(tanks_list):
            self.accept(t, self.set_human_control_tank, extraArgs=[t])
        self.accept('window-event', self.handle_window_event)

        self.accept('into-' + 'cmTank', self.struck)
        for t in tanks_list:
            self.accept('into-' + 'cTank' + t, self.tank0_round_hit)
            self.accept('explosion{}-done'.format(t), self.explosion_cleanup, extraArgs=[t])
            self.accept('shot{}-done'.format(t), self.enemy_reset_shot, extraArgs=[t])
        for environment in ENVIRONMENTS:
            for obstacle in environment["obstacles"]:
                self.accept('into-cObstacle-' + obstacle["name"], self.round_obstacle_hit)

        # on-screen text
        vect = self.camera.getHpr()
        self.textObject = OnscreenText(text=str(vect[0]), pos=(-0.5, -0.9),
                                       scale=(0.03, 0.05), fg=(0.4, 1.0, 0.4, 1), mayChange=True)
        self.textObject.reparentTo(self.render2d)
        self.bloomTextObject = OnscreenText(text="", pos=(1.05, -0.9),
                                            align=TextNode.ALeft, scale=(0.03, 0.05),
                                            fg=(0.4, 1.0, 0.4, 1), mayChange=True)
        self.bloomTextObject.reparentTo(self.render2d)
        self.set_bloom_enabled(self.bloom_enabled)
        self.apply_network_client_low_render_settings()
        self.apply_network_server_low_render_settings()
        self.position_start_camera()
        self.update_start_screen_presentation()

        self.ambient_snd.setLoop(True)

        # mainShot_snd.setLoop(True)

        # sfxMgr = base.sfxManagerList[0]

    def setup_tank_control_architecture(self):
        self.tank_avatars = {
            "0": TankAvatar("0", self.camera, collision_radius=PLAYER_COLLISION_RADIUS)
        }
        self.human_tank_controller = HumanTankController()
        self.human_control_tank_id = "0"
        self.tank_controllers = {
            "0": self.human_tank_controller
        }
        self.ai_tank_controllers = {
            "0": TacticalAiTankController("0")
        }
        self.remote_tank_controllers = {}
        self.remote_tank_controllers["0"] = RemoteTankController()

        for t in tanks_list:
            self.tank_avatars[t] = TankAvatar(
                t,
                tanks_dict[t]["tank"],
                locator=tanks_dict[t]["Locator"],
                collision_radius=TANK_COLLISION_RADIUS
            )
            if ENEMY_CONTROLLER_MODE == "TACTICAL":
                self.ai_tank_controllers[t] = TacticalAiTankController(t)
            else:
                self.ai_tank_controllers[t] = SineAiTankController(t)
            self.remote_tank_controllers[t] = RemoteTankController()
            self.tank_controllers[t] = self.ai_tank_controllers[t]

    def setup_network_controller_prototype(self):
        self.network_bridge = None
        self.network_client_controller_mode = False
        self.network_client_low_render_mode = False
        self.network_snapshot_received = False
        self.network_snapshot_targets = {"tanks": {}, "shots": {}}
        self.network_snapshot_history = []
        self.network_interpolation_enabled = True
        self.network_connected_tanks = []
        self.network_claimable_tanks = sorted(CLAIMABLE_TANK_IDS, key=lambda tank_id: int(tank_id))
        self.network_claim_metadata = {}
        self.network_lobby_state = {}
        self.network_server_status = {}
        self.network_claimed_tank_id = NETWORK_TANK_ID
        self.network_player_id = ""
        self.network_claim_token = ""
        self.network_ownership_generation = 0
        self.network_terrain_authority_player_id = ""
        self.network_terrain_authority_tank_id = ""
        self.network_terrain_locked = False
        self.network_arena_hibernating = False
        self.network_join_accepted = False
        self.network_join_rejected_reason = ""
        self.network_manual_claim_released = False
        self.network_last_command_status = ""
        self.network_last_command_ok = True
        self.network_client_controller_type = self.normalized_network_client_controller_type()
        self.network_client_last_waiting = True
        self.network_client_last_game_over = False
        self.network_snapshot_shot_visible = {}
        if NETWORK_MODE not in {"host", "client"}:
            return

        if NETWORK_TANK_ID not in network_tank_ids():
            print("Ignoring network tank id {}; choose one of {}".format(NETWORK_TANK_ID, sorted(network_tank_ids())))
            return

        try:
            self.network_bridge = UdpTankInputBridge(
                self,
                NETWORK_MODE,
                NETWORK_HOST,
                NETWORK_PORT,
                NETWORK_TANK_ID
            )
        except OSError as exc:
            print("Network prototype disabled: {}".format(exc))
            self.network_bridge = None
            return

        if NETWORK_MODE == "host":
            if NETWORK_MODE_LABEL == "server":
                self.set_remote_control_tank("0")
                self.update_network_server_presentation()
            else:
                self.set_remote_control_tank(NETWORK_TANK_ID)
        elif NETWORK_MODE == "client":
            if not self.network_client_uses_autonomous_controller():
                self.set_human_control_tank(NETWORK_TANK_ID)
            self.network_client_controller_mode = True
            self.network_client_low_render_mode = NETWORK_CLIENT_LOW_RENDER
            self.update_network_client_presentation()

        if self.operator_console_enabled():
            print("{} UDP {} ACTIVE {}".format(
                self.network_bridge.status(),
                NETWORK_PORT,
                ",".join(self.tank_ids_for_state())
            ))

    def is_network_client_controller(self):
        return getattr(self, "network_client_controller_mode", False)

    def is_network_server_authority(self):
        return NETWORK_MODE == "host" and NETWORK_MODE_LABEL == "server"

    def is_network_client_low_render(self):
        return self.is_network_client_controller() and getattr(self, "network_client_low_render_mode", False)

    def is_network_server_low_render(self):
        return self.is_network_server_authority() and NETWORK_SERVER_LOW_RENDER

    def server_panda_overlay_enabled(self):
        return self.is_network_server_authority() and SERVER_UI_MODE == "panda"

    def server_log_enabled(self):
        return self.is_network_server_authority() and SERVER_UI_MODE in {"log", "logs", "json", "headless"}

    def server_window_minimized_by_default(self):
        return self.is_network_server_authority() and SERVER_UI_MODE in {
            "tui", "log", "logs", "json", "headless", "none", "off"
        }

    def operator_console_enabled(self):
        return not (self.is_network_server_authority() and SERVER_UI_MODE in {
            "tui", "log", "logs", "json", "headless", "none", "off"
        })

    def setup_server_operator_ui(self):
        if not self.is_network_server_authority():
            return
        if SERVER_UI_MODE == "tui":
            self.server_tui_dashboard = ServerTuiDashboard(self)
            if self.server_tui_dashboard.enabled:
                atexit.register(self.server_tui_dashboard.close)
                self.record_server_event("server TUI started")
            return
        if self.server_log_enabled():
            self.record_server_event("server log status started")

    def updateServerTuiTask(self, task):
        if self.server_tui_dashboard is not None:
            self.server_tui_dashboard.update(getattr(task, "time", ClockObject.getGlobalClock().getFrameTime()))
        return Task.cont

    def server_log_payload(self, kind, payload):
        data = {
            "kind": kind,
            "time": time.strftime("%Y-%m-%dT%H:%M:%S%z")
        }
        data.update(payload)
        return data

    def print_server_log_payload(self, kind, payload):
        try:
            print(json.dumps(self.server_log_payload(kind, payload), sort_keys=True), flush=True)
        except (TypeError, ValueError):
            print(json.dumps(self.server_log_payload(kind, {"message": str(payload)}), sort_keys=True), flush=True)

    def emit_server_status_log(self):
        state = self.server_dashboard_state()
        self.print_server_log_payload("status", {
            "arena": state.get("arena", {}),
            "network": state.get("network", {}),
            "autonomy": state.get("autonomy", {}),
            "lobby": state.get("lobby", {}),
            "claims": state.get("claims", []),
            "tanks": state.get("tanks", [])
        })

    def updateServerLogTask(self, task):
        if not self.server_log_enabled():
            return Task.cont
        task_time = getattr(task, "time", ClockObject.getGlobalClock().getFrameTime())
        if task_time - self.server_log_last_status_time >= SERVER_LOG_INTERVAL:
            self.server_log_last_status_time = task_time
            self.emit_server_status_log()
        return Task.cont

    def network_client_mode_label(self):
        if self.network_manual_claim_released:
            return "CLAIM RELEASED"
        if self.network_join_rejected_reason:
            return "JOIN REJECTED"
        if not self.network_join_accepted:
            return "JOINING"
        controller_label = self.network_client_controller_label()
        if self.is_network_client_low_render():
            return "{} LOW RENDER".format(controller_label)
        return "{} FULL RENDER".format(controller_label)

    def normalized_network_client_controller_type(self):
        if NETWORK_CLIENT_CONTROLLER in {"auto", "autonomous", "ai", "enemy"}:
            return "autonomous"
        return "human"

    def network_client_uses_autonomous_controller(self):
        return getattr(self, "network_client_controller_type", "human") == "autonomous"

    def network_client_controller_label(self):
        return "AUTO" if self.network_client_uses_autonomous_controller() else "HUMAN"

    def network_current_tank_id(self):
        if self.network_bridge is not None and self.is_network_client_controller():
            return str(getattr(self.network_bridge, "tank_id", self.network_claimed_tank_id))
        return str(getattr(self, "network_claimed_tank_id", NETWORK_TANK_ID))

    def apply_network_claim_identity(self, tank_id, player_id="", claim_token="", ownership_generation=0, accepted=True):
        tank_id = str(tank_id)
        if tank_id not in network_tank_ids():
            return
        previous_tank_id = getattr(self, "network_claimed_tank_id", NETWORK_TANK_ID)
        self.network_claimed_tank_id = tank_id
        self.network_join_accepted = bool(accepted)
        self.network_manual_claim_released = False
        self.network_join_rejected_reason = ""
        self.network_player_id = str(player_id or "")
        self.network_claim_token = str(claim_token or "")
        try:
            self.network_ownership_generation = int(ownership_generation or 0)
        except (TypeError, ValueError):
            self.network_ownership_generation = 0
        if self.is_network_client_controller():
            if accepted and not self.network_client_uses_autonomous_controller():
                self.set_human_control_tank(tank_id)
            if accepted and previous_tank_id != tank_id:
                self.snap_network_snapshot_render()
            self.update_network_client_presentation()

    def note_network_command_ack(self, command, accepted, reason=""):
        command_label = str(command or "").replace("_", " ").upper()
        if accepted:
            self.network_last_command_status = "OK {}".format(command_label)
            self.network_last_command_ok = True
        else:
            reason = str(reason or "rejected").upper()
            self.network_last_command_status = "ERR {} {}".format(command_label, reason)
            self.network_last_command_ok = False

    def set_network_lobby_ready(self, ready=True):
        if not self.is_network_client_controller():
            return
        if not self.waiting_to_start:
            return
        if self.network_bridge is None or not self.network_join_accepted:
            return
        self.network_bridge.send_client_ready(ready)

    def release_network_lobby_claim(self):
        if not self.is_network_client_controller():
            return
        if not self.waiting_to_start:
            return
        if self.network_bridge is None or not self.network_join_accepted:
            return
        self.network_bridge.send_client_release_claim()

    def request_network_lobby_claim_tank(self, tank_id):
        if not self.is_network_client_controller():
            return
        if not self.waiting_to_start:
            return
        tank_id = str(tank_id)
        if tank_id not in network_tank_ids():
            return
        if self.network_bridge is None:
            return
        current_tank_id = self.network_current_tank_id()
        if self.network_join_accepted:
            if tank_id == current_tank_id:
                self.network_last_command_status = "CLAIM CURRENT {}".format(tank_id)
                self.network_last_command_ok = True
                return
            self.network_bridge.send_client_claim_tank(tank_id)
            return
        if self.network_bridge.prepare_client_claim_target(tank_id):
            self.network_manual_claim_released = False
            self.network_last_command_status = "JOIN {}".format(tank_id)
            self.network_last_command_ok = True
            self.update_network_client_presentation()

    def rejoin_network_lobby_claim(self):
        if not self.is_network_client_controller():
            return
        if self.network_bridge is None:
            return
        if not getattr(self.network_bridge, "manual_claim_released", False):
            return
        self.network_bridge.manual_claim_released = False
        self.network_bridge.last_join_send_time = -999
        self.network_manual_claim_released = False
        self.network_join_rejected_reason = ""
        self.network_last_command_status = "REJOIN {}".format(self.network_current_tank_id())
        self.network_last_command_ok = True
        self.update_network_client_presentation()

    def network_autonomous_client_command(self, dt, task_time):
        if not self.network_snapshot_received:
            return TankCommand()
        tank_id = self.network_current_tank_id()
        controller = self.ai_tank_controllers.get(tank_id)
        avatar = self.tank_avatars.get(tank_id)
        if controller is None or avatar is None:
            return TankCommand()
        return controller.command(self, avatar, dt, task_time)

    def network_connected_tank_ids(self):
        if self.network_bridge is None or not hasattr(self.network_bridge, "connected_tank_ids"):
            return []
        return self.network_bridge.connected_tank_ids()

    def network_claim_metadata_snapshot(self):
        if self.network_bridge is None or not hasattr(self.network_bridge, "host_claim_snapshot"):
            return {}
        return self.network_bridge.host_claim_snapshot()

    def network_claimable_tank_ids(self):
        if self.network_bridge is None or not hasattr(self.network_bridge, "claimable_tank_ids"):
            return sorted(CLAIMABLE_TANK_IDS, key=lambda tank_id: int(tank_id))
        return self.network_bridge.claimable_tank_ids()

    def network_lobby_snapshot(self):
        if self.network_bridge is None or not hasattr(self.network_bridge, "host_lobby_snapshot"):
            return {}
        return self.network_bridge.host_lobby_snapshot()

    def network_server_status_snapshot(self):
        if self.network_bridge is None or not hasattr(self.network_bridge, "host_status_snapshot"):
            return {}
        return self.network_bridge.host_status_snapshot()

    def network_tank_client_connected(self, tank_id):
        return tank_id in set(self.network_connected_tank_ids())

    def server_required_clients_connected(self):
        if not self.is_network_server_authority():
            return True
        return self.server_lobby_expected_client_tanks().issubset(set(self.network_connected_tank_ids()))

    def server_lobby_can_start(self):
        if not self.is_network_server_authority():
            return True
        if self.network_bridge is None or not hasattr(self.network_bridge, "host_lobby_can_start"):
            return self.server_required_clients_connected()
        return self.network_bridge.host_lobby_can_start()

    def record_server_event(self, message):
        timestamp = time.strftime("%H:%M:%S")
        event = "{} {}".format(timestamp, message)
        self.server_event_log.append(event)
        self.server_event_log = self.server_event_log[-40:]
        if self.server_log_enabled():
            self.print_server_log_payload("event", {"message": event})

    def arena_is_hibernating(self):
        return bool(getattr(self, "arena_hibernating", False))

    def hibernate_empty_network_arena(self, reason="empty"):
        if not self.is_network_server_authority():
            return False
        if self.waiting_to_start or self.game_over or self.arena_is_hibernating():
            return False
        if self.network_connected_tank_ids():
            return False

        self.arena_hibernating = True
        for tank_id in network_tank_ids():
            self.submit_remote_tank_input(tank_id, throttle=0.0, turn=0.0, fire=False, barrel_tilt=0.0)
            self.reset_tank_shot(tank_id)
        detail = "" if not reason else " ({})".format(reason)
        self.record_server_event("arena hibernating{}".format(detail))
        self.update_network_server_presentation()
        return True

    def wake_network_arena_if_hibernating(self, reason=""):
        if not self.arena_is_hibernating():
            return False

        self.arena_hibernating = False
        detail = "" if not reason else " ({})".format(reason)
        if self.is_network_server_authority():
            self.record_server_event("arena woke{}".format(detail))
        self.update_network_server_presentation()
        return True

    def record_tank_fire_event(self, tank_id, source=None):
        if not self.is_network_server_authority():
            return
        suffix = "" if source is None else " {}".format(source)
        self.record_server_event("fire tank {}{}".format(tank_id, suffix))

    def terrain_selection_locked(self):
        return not getattr(self, "waiting_to_start", False)

    def terrain_authority_label(self):
        if self.terrain_selection_locked():
            return "LOCKED"
        if self.terrain_authority_player_id:
            return "{} T{}".format(self.terrain_authority_player_id, self.terrain_authority_tank_id)
        return "SERVER"

    def connected_lobby_players(self):
        if self.network_bridge is None or not hasattr(self.network_bridge, "connected_player_rows"):
            return []
        return self.network_bridge.connected_player_rows()

    def assign_lobby_terrain_authority_if_needed(self):
        if self.terrain_selection_locked() or self.terrain_authority_player_id:
            return
        players = self.connected_lobby_players()
        if not players:
            return
        first = players[0]
        self.terrain_authority_player_id = first.get("player_id", "")
        self.terrain_authority_tank_id = first.get("tank_id", "")
        if self.terrain_authority_player_id and self.is_network_server_authority():
            self.record_server_event("terrain authority {}".format(self.terrain_authority_player_id))

    def handle_lobby_player_disconnected(self, player_id):
        if self.terrain_selection_locked() or not player_id:
            return
        if player_id != self.terrain_authority_player_id:
            return
        self.terrain_authority_player_id = ""
        self.terrain_authority_tank_id = ""
        self.assign_lobby_terrain_authority_if_needed()
        if not self.terrain_authority_player_id and self.is_network_server_authority():
            self.record_server_event("terrain authority SERVER")

    def player_has_terrain_authority(self, player_id):
        return bool(player_id) and player_id == self.terrain_authority_player_id

    def request_lobby_terrain_change(self, player_id, tank_id, action, environment_index=None):
        if self.terrain_selection_locked():
            self.record_server_event("terrain rejected {} match running".format(player_id or "?"))
            return False
        self.assign_lobby_terrain_authority_if_needed()
        if not self.player_has_terrain_authority(player_id):
            self.record_server_event("terrain rejected {} not authority".format(player_id or "?"))
            return False

        if action == "next":
            target_index = self.environment_index + 1
        elif action == "previous":
            target_index = self.environment_index - 1
        elif action == "set" and environment_index is not None:
            if environment_index < 0 or environment_index >= len(ENVIRONMENTS):
                self.record_server_event("terrain rejected {} invalid environment".format(player_id or "?"))
                return False
            target_index = environment_index
        else:
            self.record_server_event("terrain rejected {} bad command".format(player_id or "?"))
            return False

        self.apply_environment_index(
            target_index,
            actor="{} T{}".format(player_id, tank_id)
        )
        return True

    def format_uptime(self):
        elapsed = max(0, int(time.monotonic() - self.server_started_at))
        hours = elapsed // 3600
        minutes = (elapsed % 3600) // 60
        seconds = elapsed % 60
        if hours:
            return "{}:{:02d}:{:02d}".format(hours, minutes, seconds)
        return "{:02d}:{:02d}".format(minutes, seconds)

    def arena_state_label(self):
        if self.investigation_mode:
            return "INVESTIGATE"
        if self.game_over:
            return "GAME OVER"
        if self.arena_is_hibernating():
            return "HIBERNATING"
        if self.waiting_to_start:
            return "WAITING"
        return "RUNNING"

    def controller_source_for_tank(self, tank_id, claims=None):
        claims = claims or self.network_claim_metadata_snapshot()
        if tank_id in claims:
            return claims[tank_id].get("controller", "CLIENT")
        if tank_id not in CLAIMABLE_TANK_IDS:
            return "RESERVED"
        if tank_id == "0":
            return "HUMAN SLOT"
        return "AI POOL"

    def claim_rows_for_dashboard(self, claims, status_time):
        rows = []
        connected = set(self.network_connected_tank_ids())
        for tank_id in self.tank_ids_for_state():
            claim = claims.get(tank_id, {})
            if tank_id in connected:
                last_seen = 0.0
                if self.network_bridge is not None:
                    last_seen = self.network_bridge.client_last_seen.get(tank_id, status_time)
                heartbeat_age = "{:.1f}s".format(max(0.0, status_time - last_seen))
                rows.append({
                    "tank": tank_id,
                    "source": claim.get("controller", "CLIENT"),
                    "player": claim.get("player_id", ""),
                    "generation": claim.get("ownership_generation", 0),
                    "sequence": claim.get("last_input_sequence", -1),
                    "heartbeat": heartbeat_age
                })
            elif tank_id in CLAIMABLE_TANK_IDS:
                rows.append({
                    "tank": tank_id,
                    "source": "POOL" if tank_id != "0" else "OPEN",
                    "player": "",
                    "generation": "-",
                    "sequence": "-",
                    "heartbeat": "-"
                })
            else:
                rows.append({
                    "tank": tank_id,
                    "source": "RESERVED",
                    "player": "",
                    "generation": "-",
                    "sequence": "-",
                    "heartbeat": "-"
                })
        return rows

    def tank_rows_for_dashboard(self, claims):
        rows = []
        for tank_id in self.tank_ids_for_state():
            if self.tank_lives(tank_id) is None:
                lives = "-"
            else:
                lives = str(int(self.tank_lives(tank_id)))
            if self.tank_is_reconstituting(tank_id):
                state = "RECONSTITUTING"
            elif not self.tank_is_alive(tank_id):
                state = "DEAD"
            else:
                state = "ALIVE"
            rows.append({
                "tank": tank_id,
                "team": "T{}".format(tank_id),
                "source": self.controller_source_for_tank(tank_id, claims),
                "lives": lives,
                "state": state,
                "shot": "SHOT" if self.tank_is_shooting(tank_id) else "IDLE"
            })
        return rows

    def server_dashboard_state(self):
        claims = self.network_claim_metadata_snapshot()
        network = self.network_server_status_snapshot()
        status_time = ClockObject.getGlobalClock().getFrameTime()
        connected_tanks = set(self.network_connected_tank_ids())
        hibernating = self.arena_is_hibernating()
        fallback_active_count = len([
            tank_id for tank_id in CLAIMABLE_TANK_IDS
            if not hibernating and tank_id != "0" and tank_id not in connected_tanks
        ])
        human_claim_count = len([
            claim for claim in claims.values()
            if str(claim.get("controller", "")).upper() == "HUMAN"
        ])
        environment = self.selected_environment()["name"] if hasattr(self, "environment_index") else ""
        lobby = self.network_lobby_snapshot()
        return {
            "arena": {
                "mode": "SERVER",
                "state": self.arena_state_label(),
                "uptime": self.format_uptime(),
                "environment": environment,
                "terrain_authority": self.terrain_authority_label(),
                "view": "HIBERNATE" if hibernating else ("PREVIEW" if self.waiting_to_start else "LIVE")
            },
            "network": {
                "host": network.get("host", NETWORK_HOST),
                "port": network.get("port", NETWORK_PORT),
                "protocol": NETWORK_PROTOCOL_VERSION,
                "transport": "UDP",
                "active_tanks": ",".join(self.tank_ids_for_state()),
                "claimable_count": network.get("claimable_count", len(CLAIMABLE_TANK_IDS)),
                "connected_count": network.get("connected_count", len(connected_tanks)),
                "rx_input_packets": network.get("rx_input_packets", 0),
                "snapshot_frames": network.get("snapshot_frames", 0),
                "snapshot_packets": network.get("snapshot_packets", 0),
                "rejected_joins": network.get("rejected_joins", 0),
                "rejected_inputs": network.get("rejected_inputs", 0),
                "rejected_sequences": network.get("rejected_sequences", 0),
            },
            "claims": self.claim_rows_for_dashboard(claims, status_time),
            "tanks": self.tank_rows_for_dashboard(claims),
            "autonomy": {
                "fallback_active_count": fallback_active_count,
                "human_claim_count": human_claim_count,
                "enemy_fire": "HIBERNATING" if hibernating else ("SUSPENDED" if self.enemy_shooting_suspended else "ENABLED"),
                "team_model": "TEAMS OF ONE"
            },
            "lobby": {
                "player_count": len(lobby.get("players", [])),
                "ready_count": lobby.get("ready_count", len([player for player in lobby.get("players", []) if player.get("ready")])),
                "start": "READY" if lobby.get("can_start", False) else "WAIT",
                "team_model": str(lobby.get("team_model", "teams_of_one")).replace("_", " ").upper()
            },
            "events": list(self.server_event_log)
        }

    def primary_player_target_available(self):
        if self.is_network_server_authority():
            return self.network_tank_client_connected("0")
        return True

    def apply_network_client_low_render_settings(self):
        if not self.is_network_client_low_render():
            return

        props = WindowProperties()
        props.setSize(*NETWORK_CLIENT_LOW_RENDER_SIZE)
        base.win.requestProperties(props)
        self.set_bloom_enabled(False)

    def apply_network_server_low_render_settings(self):
        if not self.is_network_server_low_render():
            return

        props = WindowProperties()
        props.setSize(*NETWORK_SERVER_LOW_RENDER_SIZE)
        if self.is_network_server_authority() and SERVER_UI_MODE != "panda":
            if hasattr(props, "setTitle"):
                props.setTitle("Battlezone Server")
            if (
                    self.server_window_minimized_by_default() and
                    SERVER_WINDOW_MODE in {"minimized", "minimize", "min"} and
                    hasattr(props, "setMinimized")):
                props.setMinimized(True)
        base.win.requestProperties(props)
        self.set_bloom_enabled(False)

    def update_network_client_presentation(self):
        if not self.is_network_client_controller():
            return

        self.waiting_to_start = True
        self.update_network_client_start_prompt()
        for text_object in getattr(self, "environmentNameTextObjects", []):
            text_object.hide()
        self.environmentTextObject.hide()
        if hasattr(self, "gameOverTextObject"):
            self.gameOverTextObject.hide()
        if hasattr(self, "investigateTextObject"):
            self.investigateTextObject.hide()
        if hasattr(self, "investigateTimerRoot"):
            self.investigateTimerRoot.hide()
        if hasattr(self, "hitFlashNp"):
            self.hitFlashNp.hide()
        self.update_start_screen_presentation()

    def update_network_server_presentation(self):
        if not self.is_network_server_authority():
            return

        connected = 0
        if self.network_bridge is not None:
            connected_tanks = self.network_connected_tank_ids()
            connected = len(connected_tanks)
        else:
            connected_tanks = []
        controller_types = {}
        if self.network_bridge is not None:
            controller_types = getattr(self.network_bridge, "client_controller_types", {})
        self.update_server_lobby_overlay(
            connected_tanks,
            controller_types,
            self.network_claim_metadata_snapshot(),
            self.network_server_status_snapshot()
        )
        self.position_lives_table()
        if self.waiting_to_start:
            self.startTextObject.hide()
        for text_object in getattr(self, "environmentNameTextObjects", []):
            text_object.hide()
        self.environmentTextObject.hide()
        if hasattr(self, "gameOverTextObject") and not self.game_over:
            self.gameOverTextObject.hide()
        if hasattr(self, "hitFlashNp"):
            self.hitFlashNp.hide()
        self.update_start_screen_presentation()

    def network_client_has_snapshot(self):
        return self.is_network_client_controller() and getattr(self, "network_snapshot_received", False)

    def set_human_control_tank(self, tank_id):
        if tank_id != "0" and tank_id not in tanks_list:
            return
        if self.is_network_client_controller():
            if self.waiting_to_start and (tank_id != self.network_current_tank_id() or not self.network_join_accepted):
                self.request_network_lobby_claim_tank(tank_id)
                return
            if tank_id != self.network_current_tank_id():
                return

        self.human_control_tank_id = tank_id
        self.tank_controllers["0"] = self.human_tank_controller if tank_id == "0" else TankController()
        for t in tanks_list:
            self.tank_controllers[t] = (
                self.human_tank_controller if t == tank_id else self.ai_tank_controllers[t]
            )

    def set_remote_control_tank(self, tank_id):
        if tank_id not in network_tank_ids():
            return

        if self.human_control_tank_id == tank_id:
            self.set_human_control_tank("0")
        self.tank_controllers[tank_id] = self.remote_tank_controllers[tank_id]

    def clear_remote_control_tank(self, tank_id):
        if tank_id not in network_tank_ids():
            return

        if self.human_control_tank_id == tank_id:
            return
        if tank_id == "0":
            self.tank_controllers["0"] = self.human_tank_controller
            return
        self.tank_controllers[tank_id] = self.ai_tank_controllers[tank_id]

    def submit_remote_tank_input(self, tank_id, throttle=0.0, turn=0.0, fire=False, barrel_tilt=0.0):
        if tank_id not in network_tank_ids():
            return

        self.remote_tank_controllers[tank_id].submit_input(
            throttle=throttle,
            turn=turn,
            fire=fire,
            barrel_tilt=barrel_tilt
        )

    def submit_remote_tank_command(self, tank_id, command):
        if tank_id not in network_tank_ids():
            return

        self.remote_tank_controllers[tank_id].submit_command(command)

    def updateNetworkTask(self, task):
        if self.network_bridge is not None:
            self.network_bridge.update(getattr(task, "time", ClockObject.getGlobalClock().getFrameTime()))
        if self.is_network_server_authority() and getattr(self, "waiting_to_start", False):
            self.update_network_server_presentation()
        if self.network_client_has_snapshot() and not self.investigation_mode:
            dt = min(ClockObject.getGlobalClock().getDt(), 0.05)
            self.update_network_snapshot_render(dt)
        return Task.cont

    def audio_process_should_be_audible(self):
        if self.is_network_server_authority():
            return False
        if not self.audio_focus_enabled:
            return True
        return self.audio_has_focus

    def apply_audio_focus_volume(self):
        audible = self.audio_process_should_be_audible() if hasattr(self, "audio_has_focus") else True
        for sound, base_volume in getattr(self, "sound_base_volumes", {}).items():
            sound.setVolume(base_volume if audible else 0.0)

    def update_network_client_audio_state(self, waiting, game_over):
        if not self.is_network_client_controller():
            return
        if self.investigation_mode:
            return

        was_waiting = getattr(self, "network_client_last_waiting", True)
        was_game_over = getattr(self, "network_client_last_game_over", False)
        self.network_client_last_waiting = waiting
        self.network_client_last_game_over = game_over

        if waiting:
            self.ambient_snd.stop()
            return

        if game_over:
            self.ambient_snd.stop()
            if not was_game_over:
                self.gameOver_snd.play()
            return

        if was_waiting or was_game_over or self.ambient_snd.status() != AudioSound.PLAYING:
            self.gameOver_snd.stop()
            self.ambient_snd.play()

    def trigger_player_hit_feedback(self):
        if self.is_network_server_authority():
            return
        self.hit_flash_alpha = 0.65
        now = ClockObject.getGlobalClock().getFrameTime()
        self.player_hit_shake_started_at = now
        self.player_hit_shake_until = now + PLAYER_HIT_SHAKE_SECONDS
        self.playerHit_snd.play()

    def record_player_damage_feedback(self):
        self.player_damage_event_serial += 1
        self.trigger_player_hit_feedback()

    def apply_player_hit_camera_shake(self):
        now = ClockObject.getGlobalClock().getFrameTime()
        if now >= getattr(self, "player_hit_shake_until", 0):
            return
        duration = max(0.001, PLAYER_HIT_SHAKE_SECONDS)
        elapsed = max(0, now - getattr(self, "player_hit_shake_started_at", now))
        falloff = max(0.0, 1.0 - elapsed / duration)
        jitter_yaw = math.sin(elapsed * 92.0) * PLAYER_HIT_SHAKE_YAW * falloff
        jitter_pitch = math.sin(elapsed * 137.0 + 0.7) * PLAYER_HIT_SHAKE_PITCH * falloff
        self.camera.setHpr(self.camera, jitter_yaw, jitter_pitch, 0)

    def window_has_audio_focus(self):
        try:
            properties = base.win.getProperties()
            if hasattr(properties, "getForeground"):
                return bool(properties.getForeground())
        except Exception:
            pass
        return True

    def updateAudioFocusTask(self, task):
        has_focus = self.window_has_audio_focus()
        if has_focus != self.audio_has_focus:
            self.audio_has_focus = has_focus
            self.apply_audio_focus_volume()
        return Task.cont

    def point_to_list(self, point):
        return [float(point[0]), float(point[1]), float(point[2])]

    def hpr_to_list(self, hpr):
        return [float(hpr[0]), float(hpr[1]), float(hpr[2])]

    def setup_tank_runtime_states(self):
        self.tank_runtime = {
            "0": {
                "body": self.player_tank_visual,
                "control": self.camera,
                "shot": self.tank_round[0],
                "eye_height": PLAYER_CAMERA_HEIGHT,
                "view_heading_offset": -90,
                "body_heading_offset": 90,
                "body_forward_axis": "x",
                "shot_mount": self.camera,
                "shot_start_local": Point3(0, PLAYER_SHOT_START_Y, PLAYER_SHOT_START_Z),
                "shot_stowed_local": Point3(0, PLAYER_SHOT_START_Y, PLAYER_SHOT_START_Z - 10),
                "shot_stowed_hpr": Point3(0, 90, 0),
                "aim_mount": self.camera,
                "aim_reference_local": Point3(0, PLAYER_BARREL_AIM_REFERENCE_DISTANCE, 0),
                "aim_forward_axis": "y",
                "aim_height": 0.0,
                "collision_backtrace": PLAYER_SHOT_BACKTRACE_DISTANCE,
                "shot_distance": 200,
                "shot_duration": 1.1,
                "fire_cooldown": TANK_FIRE_COOLDOWN,
                "is_player": True
            }
        }
        for t in tanks_list:
            self.tank_runtime[t] = {
                "body": tanks_dict[t]["tank"],
                "control": tanks_dict[t]["tank"],
                "shot": tanks_dict[t]["round"],
                "locator": tanks_dict[t]["Locator"],
                "eye_height": PLAYER_CAMERA_HEIGHT,
                "view_heading_offset": -90,
                "body_heading_offset": 0,
                "body_forward_axis": "x",
                "shot_mount": tanks_dict[t]["tank"],
                "shot_start_local": Point3(-0.4, 0, 1.61325),
                "shot_stowed_local": Point3(-0.4, 0, 1.61325),
                "shot_stowed_hpr": Point3(0, 0, 90),
                "aim_mount": tanks_dict[t]["tank"],
                "aim_reference_local": Point3(PLAYER_BARREL_AIM_REFERENCE_DISTANCE, 0, 0),
                "aim_forward_axis": "x",
                "aim_height": 1.61325,
                "collision_backtrace": 0,
                "shot_distance": 300,
                "shot_duration": 1.1,
                "fire_cooldown": TANK_FIRE_COOLDOWN,
                "is_player": False
            }

        self.setup_tank_lifecycle_states()

    def setup_tank_lifecycle_states(self):
        self.tank_lifecycle = {}
        for tank_id in self.tank_ids_for_state():
            self.tank_lifecycle[tank_id] = {
                "alive": True,
                "reconstituting": False,
                "lives": self.tank_max_lives(tank_id),
                "hit_cooldown_until": -PLAYER_HIT_COOLDOWN
            }
        self.incoming_player_hit_consumed_until = {}

    def tank_runtime_state(self, tank_id):
        return self.tank_runtime[tank_id]

    def tank_lifecycle_state(self, tank_id):
        return self.tank_lifecycle[tank_id]

    def tank_max_lives(self, tank_id):
        return PLAYER_MAX_LIVES if tank_id == "0" else AUTONOMOUS_TANK_MAX_LIVES

    def tank_is_alive(self, tank_id):
        return self.tank_lifecycle_state(tank_id).get("alive", True)

    def set_tank_alive(self, tank_id, alive):
        self.tank_lifecycle_state(tank_id)["alive"] = bool(alive)

    def tank_is_reconstituting(self, tank_id):
        return self.tank_lifecycle_state(tank_id).get("reconstituting", False)

    def set_tank_reconstituting(self, tank_id, reconstituting):
        self.tank_lifecycle_state(tank_id)["reconstituting"] = bool(reconstituting)

    def tank_lives(self, tank_id):
        return self.tank_lifecycle_state(tank_id).get("lives")

    def set_tank_lives(self, tank_id, lives):
        self.tank_lifecycle_state(tank_id)["lives"] = lives
        if tank_id == "0":
            self.player_lives = int(lives)

    def tank_display_name(self, tank_id):
        return "Tank {}".format(tank_id)

    def tank_lives_rows(self):
        rows = []
        for tank_id in self.tank_ids_for_state():
            lives = self.tank_lives(tank_id)
            lives_text = "-" if lives is None else str(int(lives))
            rows.append((self.tank_display_name(tank_id), lives_text))
        return rows

    def tank_lives_table_text(self):
        lines = ["TANKS       LIVES"]
        for name, lives_text in self.tank_lives_rows():
            lines.append("{:<10} {}".format(name, lives_text))
        return "\n".join(lines)

    def tank_lives_inline_text(self):
        return " ".join([
            "{} {}".format(name, lives_text)
            for name, lives_text in self.tank_lives_rows()
        ])

    def server_lobby_rows(self, connected_tanks=None, controller_types=None, claims=None):
        connected = set(connected_tanks or [])
        controller_types = controller_types or {}
        claims = claims or {}
        rows = []
        for tank_id in self.tank_ids_for_state():
            lives = self.tank_lives(tank_id)
            lives_text = "-" if lives is None else str(int(lives))
            claim_text = "OPEN"
            if tank_id not in CLAIMABLE_TANK_IDS:
                controller = "LOCKED"
                link_state = "RESERVED"
            elif tank_id in connected:
                controller = controller_types.get(tank_id, "CLIENT")
                claim = claims.get(tank_id, {})
                generation = int(claim.get("ownership_generation", 0))
                sequence = int(claim.get("last_input_sequence", -1))
                claim_text = "G{} #{}".format(generation, max(sequence, 0))
                link_state = "JOINED"
            elif tank_id == "0":
                controller = "HUMAN"
                link_state = "WAITING"
            else:
                controller = "AI"
                claim_text = "POOL"
                link_state = "SERVER"
            rows.append((tank_id, controller, lives_text, claim_text, link_state))
        return rows

    def server_lobby_expected_client_tanks(self):
        return {"0"} if "0" in CLAIMABLE_TANK_IDS else set()

    def set_tank_hit_cooldown(self, tank_id, seconds):
        self.tank_lifecycle_state(tank_id)["hit_cooldown_until"] = ClockObject.getGlobalClock().getFrameTime() + seconds

    def tank_hit_cooldown_ready(self, tank_id, now=None):
        if now is None:
            now = ClockObject.getGlobalClock().getFrameTime()
        return now >= self.tank_lifecycle_state(tank_id).get("hit_cooldown_until", 0)

    def tank_is_hittable(self, tank_id, now=None):
        if getattr(self, "waiting_to_start", False):
            return False
        if tank_id == "0" and self.game_over:
            return False
        if tank_id == "0" and self.is_network_server_authority() and not self.network_tank_client_connected("0"):
            return False
        if self.tank_lives(tank_id) is not None and self.tank_lives(tank_id) <= 0:
            return False
        if not self.tank_is_alive(tank_id) or self.tank_is_reconstituting(tank_id):
            return False
        if not self.tank_hit_cooldown_ready(tank_id, now):
            return False
        return not self.tank_body_node(tank_id).isHidden()

    def tank_can_run_controller(self, tank_id):
        if tank_id == "0":
            return True
        if tank_id not in tanks_list:
            return False
        if self.tank_lives(tank_id) is not None and self.tank_lives(tank_id) <= 0:
            return False
        if not self.tank_is_alive(tank_id) or self.tank_is_reconstituting(tank_id):
            return False
        return not self.tank_body_node(tank_id).isHidden()

    def reset_incoming_player_hit_consumption(self):
        self.incoming_player_hit_consumed_until = {}

    def consume_incoming_player_hit(self, shooter_id, now=None):
        if now is None:
            now = ClockObject.getGlobalClock().getFrameTime()
        shooter_id = str(shooter_id)
        consumed_until = self.incoming_player_hit_consumed_until.get(shooter_id, -PLAYER_HIT_COOLDOWN)
        if now < consumed_until:
            return False
        self.incoming_player_hit_consumed_until[shooter_id] = now + PLAYER_HIT_COOLDOWN
        return True

    def tank_body_node(self, tank_id):
        return self.tank_runtime_state(tank_id)["body"]

    def tank_control_node(self, tank_id):
        return self.tank_runtime_state(tank_id)["control"]

    def tank_shot_node(self, tank_id):
        return self.tank_runtime_state(tank_id)["shot"]

    def tank_shot_mount_node(self, tank_id):
        return self.tank_runtime_state(tank_id)["shot_mount"]

    def tank_aim_mount_node(self, tank_id):
        return self.tank_runtime_state(tank_id)["aim_mount"]

    def tank_body_pos(self, tank_id):
        return Point3(self.tank_body_node(tank_id).getPos(render))

    def tank_body_hpr(self, tank_id):
        return self.tank_body_node(tank_id).getHpr(render)

    def tank_control_pos(self, tank_id):
        return Point3(self.tank_control_node(tank_id).getPos(render))

    def tank_control_heading(self, tank_id):
        return self.tank_control_node(tank_id).getH(render)

    def tank_body_heading(self, tank_id):
        return self.tank_body_node(tank_id).getH(render)

    def tank_body_pose_from_control(self, tank_id):
        runtime = self.tank_runtime_state(tank_id)
        control_pos = self.tank_control_pos(tank_id)
        control_heading = self.tank_control_heading(tank_id)
        body_heading = control_heading + runtime.get("body_heading_offset", 0)
        surface_pos = self.terrain_position(control_pos)
        surface_hpr = self.terrain_surface_hpr(
            surface_pos[0],
            surface_pos[1],
            body_heading,
            runtime.get("body_forward_axis", "x")
        )
        return surface_pos, surface_hpr

    def sync_tank_body_to_control(self, tank_id):
        body_pos, body_hpr = self.tank_body_pose_from_control(tank_id)
        body_np = self.tank_body_node(tank_id)
        body_np.setPos(render, body_pos)
        body_np.setHpr(render, *body_hpr)

    def tank_eye_pos_from_body_pos(self, tank_id, body_pos):
        runtime = self.tank_runtime_state(tank_id)
        return Point3(
            body_pos[0],
            body_pos[1],
            self.terrain_z(body_pos[0], body_pos[1]) + runtime.get("eye_height", PLAYER_CAMERA_HEIGHT)
        )

    def tank_view_state_from_body_state(self, tank_id, state):
        if state is None:
            return None

        pos = self.snapshot_state_point(state, "pos")
        hpr = self.snapshot_state_hpr(state)
        runtime = self.tank_runtime_state(tank_id)
        eye_pos = self.tank_eye_pos_from_body_pos(tank_id, pos)
        return {
            "pos": self.point_to_list(eye_pos),
            "hpr": [hpr[0] + runtime.get("view_heading_offset", 0), hpr[1], hpr[2]],
            "barrel_tilt": state.get("barrel_tilt", 0.0),
            "hidden": state.get("hidden", False),
            "shooting": state.get("shooting", False)
        }

    def tank_body_target(self, tank_id):
        body_pos = self.tank_body_pos(tank_id)
        return Point3(
            body_pos[0],
            body_pos[1],
            self.terrain_z(body_pos[0], body_pos[1]) + PLAYER_CAMERA_HEIGHT + PLAYER_HIT_COLLISION_CENTER_Z
        )

    def tank_shot_start_local(self, tank_id):
        return Point3(self.tank_runtime_state(tank_id)["shot_start_local"])

    def tank_shot_stowed_local(self, tank_id):
        return Point3(self.tank_runtime_state(tank_id)["shot_stowed_local"])

    def tank_shot_stowed_hpr(self, tank_id):
        return Point3(self.tank_runtime_state(tank_id)["shot_stowed_hpr"])

    def tank_aim_point_local(self, tank_id):
        runtime = self.tank_runtime_state(tank_id)
        reference = Point3(runtime["aim_reference_local"])
        tilt_radians = math.radians(self.tank_barrel_tilt(tank_id))
        reference[2] = runtime.get("aim_height", 0.0) + math.tan(tilt_radians) * PLAYER_BARREL_AIM_REFERENCE_DISTANCE
        return reference

    def tank_shot_direction(self, tank_id, shot_start):
        aim_world = render.getRelativePoint(self.tank_aim_mount_node(tank_id), self.tank_aim_point_local(tank_id))
        return self.normalize3(aim_world - shot_start)

    def shot_direction_with_spread(self, direction, yaw_degrees, pitch_degrees):
        direction = self.normalize3(direction)
        yaw = math.tan(math.radians((random() - 0.5) * 2 * yaw_degrees))
        pitch = math.tan(math.radians((random() - 0.5) * 2 * pitch_degrees))
        world_up = Point3(0, 0, 1)
        lateral = self.cross3(world_up, direction)
        if self.dot3(lateral, lateral) < 0.0001:
            lateral = Point3(1, 0, 0)
        else:
            lateral = self.normalize3(lateral)
        vertical = self.normalize3(self.cross3(direction, lateral))
        return self.normalize3(direction + lateral * yaw + vertical * pitch)

    def tank_collision_start(self, tank_id, shot_start, shot_direction):
        backtrace = self.tank_runtime_state(tank_id).get("collision_backtrace", 0)
        if backtrace <= 0:
            return None
        return Point3(shot_start - shot_direction * backtrace)

    def tank_is_shooting(self, tank_id):
        if tank_id == "0":
            return self.player_shot_interval is not None
        return tanks_dict[tank_id]["shooting"]

    def set_tank_shooting(self, tank_id, shooting):
        if tank_id != "0":
            tanks_dict[tank_id]["shooting"] = shooting

    def tank_shot_interval(self, tank_id):
        if tank_id == "0":
            return self.player_shot_interval
        return tanks_dict[tank_id].get("shot_interval")

    def set_tank_shot_interval(self, tank_id, interval):
        if tank_id == "0":
            self.player_shot_interval = interval
        else:
            tanks_dict[tank_id]["shot_interval"] = interval

    def tank_shot_deflected(self, tank_id):
        if tank_id == "0":
            return self.player_shot_deflected
        return tanks_dict[tank_id].get("shot_deflected", False)

    def set_tank_shot_deflected(self, tank_id, shot_deflected):
        if tank_id == "0":
            self.player_shot_deflected = shot_deflected
        else:
            tanks_dict[tank_id]["shot_deflected"] = shot_deflected

    def tank_shot_done_event(self, tank_id):
        if tank_id == "0":
            return "shot-done"
        return "shot{}-done".format(tank_id)

    def tank_shot_start(self, tank_id):
        if tank_id == "0":
            return Point3(self.tank_shot_node("0").getPos(render))
        return Point3(self.tank_shot_node(tank_id).getPos(render))

    def coerce_trajectory_points(self, trajectory_points, shot_start=None, shot_end=None):
        def as_point3(point):
            try:
                return Point3(point)
            except TypeError:
                return Point3(point[0], point[1], point[2])

        points = []
        if trajectory_points:
            for point in trajectory_points:
                if point is None:
                    continue
                points.append(as_point3(point))

        if len(points) < 2:
            points = []
            if shot_start is not None:
                points.append(as_point3(shot_start))
            if shot_end is not None:
                points.append(as_point3(shot_end))
        return points

    def record_tank_shot_metadata(self, tank_id, shot_start, shot_end, trajectory_points=None):
        if tank_id == "0":
            return
        tanks_dict[tank_id]["shot_start"] = Point3(shot_start)
        tanks_dict[tank_id]["shot_end"] = Point3(shot_end)
        tanks_dict[tank_id]["shot_trajectory_points"] = self.coerce_trajectory_points(
            trajectory_points,
            shot_start,
            shot_end
        )
        tanks_dict[tank_id]["shot_shooter_pos"] = Point3(self.tank_body_node(tank_id).getPos(render))
        tanks_dict[tank_id]["shot_shooter_hpr"] = self.tank_body_node(tank_id).getHpr(render)

    def shot_trajectory_for_hit(self, shooter_id, shot_start, shot_end):
        trajectory_points = None
        if shooter_id in tanks_list:
            trajectory_points = tanks_dict[shooter_id].get("shot_trajectory_points")
        points = self.coerce_trajectory_points(trajectory_points, shot_start, shot_end)
        if len(points) > 2:
            points[-1] = Point3(shot_end)
        elif len(points) == 2:
            points = [Point3(shot_start), Point3(shot_end)]
        return points

    def investigation_trajectory_points(self, event):
        return self.coerce_trajectory_points(
            event.get("trajectory_points"),
            event.get("shot_start"),
            event.get("shot_end")
        )

    def investigation_camera_target(self, event, camera_pos):
        points = self.investigation_trajectory_points(event)
        if len(points) < 2:
            return None

        shot_from = None
        shot_to = None
        for index in range(len(points) - 1, 0, -1):
            candidate_from = Point3(points[index - 1])
            candidate_to = Point3(points[index])
            delta = candidate_to - candidate_from
            if delta[0] * delta[0] + delta[1] * delta[1] > 0.001:
                shot_from = candidate_from
                shot_to = candidate_to
                break

        if shot_from is None:
            return None

        shot_delta = shot_to - shot_from
        if self.dot3(shot_delta, shot_delta) < 0.001:
            return None

        shot_dir = self.normalize3(shot_delta)
        return Point3(camera_pos + shot_dir * 40.0)

    def tank_ids_for_state(self):
        return ["0"] + sorted(tanks_list)

    def tank_snapshot_state(self, tank_id):
        body_np = self.tank_body_node(tank_id)
        lifecycle = self.tank_lifecycle_state(tank_id)
        controller = getattr(self, "ai_tank_controllers", {}).get(tank_id)
        debug_state = getattr(controller, "debug_state", "") if controller is not None else ""
        return {
            "pos": self.point_to_list(body_np.getPos(render)),
            "hpr": self.hpr_to_list(body_np.getHpr(render)),
            "barrel_tilt": self.tank_barrel_tilt(tank_id),
            "hidden": body_np.isHidden(),
            "shooting": self.tank_is_shooting(tank_id),
            "alive": lifecycle.get("alive", True),
            "reconstituting": lifecycle.get("reconstituting", False),
            "lives": lifecycle.get("lives"),
            "debug_state": debug_state
        }

    def tank_shot_snapshot_state(self, tank_id):
        shot_np = self.tank_shot_node(tank_id)
        return {
            "pos": self.point_to_list(shot_np.getPos(render)),
            "hpr": self.hpr_to_list(shot_np.getHpr(render)),
            "hidden": shot_np.isHidden(),
            "shooting": self.tank_is_shooting(tank_id)
        }

    def update_player_tank_visual(self):
        if not hasattr(self, "player_tank_visual"):
            return

        self.sync_tank_body_to_control("0")
        if self.is_network_server_authority():
            self.player_tank_visual.hide(MAIN_CAMERA_MASK | AUX_CAMERA_MASK)
            return

        if self.current_view_tank_id() == "0":
            self.player_tank_visual.hide(MAIN_CAMERA_MASK | AUX_CAMERA_MASK)
        else:
            self.player_tank_visual.show(MAIN_CAMERA_MASK | AUX_CAMERA_MASK)

    def current_view_tank_id(self):
        if self.is_network_client_controller():
            return self.network_current_tank_id()
        if self.is_network_server_authority():
            return None
        return "0"

    def network_view_state_for_tank(self, tank_id, tank_states):
        state = tank_states.get(tank_id) or tank_states.get("0")
        return self.tank_view_state_from_body_state(tank_id, state)

    def network_player_investigation_event(self):
        event = getattr(self, "last_player_hit_event", None)
        if not event:
            return None

        now = ClockObject.getGlobalClock().getFrameTime()
        remaining = max(0.0, self.investigation_available_until - now)
        return {
            "shooter_id": str(event.get("shooter_id", "")),
            "shot_start": self.point_to_list(Point3(event.get("shot_start", Point3(0, 0, 0)))),
            "shot_end": self.point_to_list(Point3(event.get("shot_end", Point3(0, 0, 0)))),
            "trajectory_points": [
                self.point_to_list(point) for point in self.investigation_trajectory_points(event)
            ],
            "shooter_pos": self.point_to_list(Point3(event.get("shooter_pos", Point3(0, 0, 0)))),
            "shooter_hpr": self.hpr_to_list(Point3(event.get("shooter_hpr", Point3(0, 0, 0)))),
            "player_pos": self.point_to_list(Point3(event.get("player_pos", Point3(0, 0, 0)))),
            "player_hpr": self.hpr_to_list(Point3(event.get("player_hpr", Point3(0, 0, 0)))),
            "fatal": bool(event.get("fatal", False)),
            "remaining": remaining
        }

    def apply_network_player_investigation_event(self, event):
        if self.network_current_tank_id() != "0" or not event:
            return

        remaining = float(event.get("remaining", 0.0))
        fatal = bool(event.get("fatal", False))
        if remaining <= 0 and not fatal:
            return

        shot_start = Point3(*event.get("shot_start", [0, 0, 0]))
        shot_end = Point3(*event.get("shot_end", [0, 0, 0]))
        trajectory_points = [
            Point3(*point) for point in event.get("trajectory_points", [])
        ]

        self.last_player_hit_event = {
            "shooter_id": str(event.get("shooter_id", "")),
            "shot_start": shot_start,
            "shot_end": shot_end,
            "trajectory_points": self.coerce_trajectory_points(trajectory_points, shot_start, shot_end),
            "shooter_pos": Point3(*event.get("shooter_pos", [0, 0, 0])),
            "shooter_hpr": Point3(*event.get("shooter_hpr", [0, 0, 0])),
            "player_pos": Point3(*event.get("player_pos", [0, 0, 0])),
            "player_hpr": Point3(*event.get("player_hpr", [0, 0, 0])),
            "fatal": fatal
        }
        self.investigation_available_until = ClockObject.getGlobalClock().getFrameTime() + remaining
        if fatal:
            self.investigation_available_until = (
                ClockObject.getGlobalClock().getFrameTime() + max(remaining, INVESTIGATE_FATAL_WINDOW_SECONDS)
            )

    def build_network_snapshot(self, task_time):
        self.update_player_tank_visual()
        snapshot = {
            "type": "snapshot",
            "time": float(task_time),
            "environment_index": self.environment_index,
            "waiting_to_start": self.waiting_to_start,
            "game_over": self.game_over,
            "arena_hibernating": self.arena_is_hibernating(),
            "enemy_shooting_suspended": self.enemy_shooting_suspended,
            "terrain_authority_player_id": self.terrain_authority_player_id,
            "terrain_authority_tank_id": self.terrain_authority_tank_id,
            "terrain_locked": self.terrain_selection_locked(),
            "player_lives": self.player_lives,
            "player_damage_event_serial": self.player_damage_event_serial,
            "player_hit_effect_serial": self.player_hit_effect_serial,
            "player_hit_effect_pos": self.point_to_list(self.player_hit_effect_pos),
            "player_hit_effect_hpr": self.hpr_to_list(self.player_hit_effect_hpr),
            "player_investigation_event": self.network_player_investigation_event(),
            "tank_hit_event_serial": self.tank_hit_event_serial,
            "tank_hit_event": self.last_tank_hit_event,
            "shot_ground_burst_serial": self.shot_ground_burst_serial,
            "shot_ground_burst_event": self.last_shot_ground_burst_event,
            "connected_tanks": self.network_connected_tank_ids(),
            "claimable_tanks": self.network_claimable_tank_ids(),
            "claims": self.network_claim_metadata_snapshot(),
            "lobby": self.network_lobby_snapshot(),
            "server_status": self.network_server_status_snapshot(),
            "protocol": NETWORK_PROTOCOL_VERSION,
            "tanks": {},
            "shots": {}
        }

        for tank_id in self.tank_ids_for_state():
            snapshot["tanks"][tank_id] = self.tank_snapshot_state(tank_id)
            snapshot["shots"][tank_id] = self.tank_shot_snapshot_state(tank_id)

        return snapshot

    def apply_network_snapshot(self, snapshot):
        if not self.is_network_client_controller():
            return

        first_snapshot = not self.network_snapshot_received
        self.network_snapshot_received = True
        environment_index = int(snapshot.get("environment_index", self.environment_index))
        if environment_index != self.environment_index and 0 <= environment_index < len(ENVIRONMENTS):
            self.environment_index = environment_index
            self.active_obstacles = ENVIRONMENTS[self.environment_index]["obstacles"]
            self.render_grid()
            self.render_obstacles()

        self.waiting_to_start = bool(snapshot.get("waiting_to_start", False))
        self.game_over = bool(snapshot.get("game_over", False))
        self.network_arena_hibernating = bool(snapshot.get("arena_hibernating", False))
        self.enemy_shooting_suspended = bool(snapshot.get("enemy_shooting_suspended", self.enemy_shooting_suspended))
        self.update_network_client_audio_state(self.waiting_to_start, self.game_over)
        self.network_connected_tanks = snapshot.get("connected_tanks", [])
        self.network_claimable_tanks = snapshot.get("claimable_tanks", self.network_claimable_tanks)
        self.network_claim_metadata = snapshot.get("claims", {})
        self.network_lobby_state = snapshot.get("lobby", self.network_lobby_state)
        self.network_server_status = snapshot.get("server_status", {})
        self.network_terrain_authority_player_id = str(snapshot.get("terrain_authority_player_id", ""))
        self.network_terrain_authority_tank_id = str(snapshot.get("terrain_authority_tank_id", ""))
        self.network_terrain_locked = bool(snapshot.get("terrain_locked", False))
        self.player_lives = int(snapshot.get("player_lives", self.player_lives))
        for tank_id, tank_state in snapshot.get("tanks", {}).items():
            if tank_id in self.tank_lifecycle and tank_state.get("lives") is not None:
                self.set_tank_lives(tank_id, int(tank_state.get("lives")))
        self.update_lives_hud()
        tank_hit_serial = int(snapshot.get("tank_hit_event_serial", 0))
        if not first_snapshot and tank_hit_serial > self.network_tank_hit_event_serial:
            if not self.investigation_mode:
                self.play_tank_hit_event(snapshot.get("tank_hit_event", {}))
        self.network_tank_hit_event_serial = max(self.network_tank_hit_event_serial, tank_hit_serial)
        if not self.investigation_mode:
            self.update_network_snapshot_shot_audio(snapshot.get("shots", {}))

        shot_ground_burst_serial = int(snapshot.get("shot_ground_burst_serial", 0))
        if (
                not first_snapshot and
                not self.investigation_mode and
                shot_ground_burst_serial > self.network_shot_ground_burst_serial):
            self.play_shot_ground_burst_event(snapshot.get("shot_ground_burst_event", {}))
        self.network_shot_ground_burst_serial = max(self.network_shot_ground_burst_serial, shot_ground_burst_serial)

        player_damage_serial = int(snapshot.get("player_damage_event_serial", 0))
        if (
                self.network_current_tank_id() == "0" and
                not first_snapshot and
                player_damage_serial > self.network_player_damage_event_serial):
            self.apply_network_player_investigation_event(snapshot.get("player_investigation_event"))
            self.trigger_player_hit_feedback()
        self.network_player_damage_event_serial = max(self.network_player_damage_event_serial, player_damage_serial)

        player_hit_serial = int(snapshot.get("player_hit_effect_serial", 0))
        if (
                tank_hit_serial <= 0 and
                not first_snapshot and
                player_hit_serial > self.network_player_hit_effect_serial):
            effect_pos = Point3(*snapshot.get("player_hit_effect_pos", [0, 0, 0]))
            effect_hpr = Point3(*snapshot.get("player_hit_effect_hpr", [0, 0, 0]))
            if self.game_over and not self.investigation_mode:
                Sequence(
                    Wait(NETWORK_EFFECT_DELAY),
                    Func(self.play_player_tank_hit_effect, effect_pos, effect_hpr)
                ).start()
        self.network_player_hit_effect_serial = max(self.network_player_hit_effect_serial, player_hit_serial)
        self.update_network_client_start_prompt()
        self.update_network_client_game_over_prompt()

        self.network_snapshot_targets = {
            "tanks": snapshot.get("tanks", {}),
            "shots": snapshot.get("shots", {})
        }
        self.network_snapshot_history.append({
            "time": ClockObject.getGlobalClock().getFrameTime(),
            "snapshot_time": float(snapshot.get("time", 0.0)),
            "targets": self.network_snapshot_targets
        })
        self.network_snapshot_history = self.network_snapshot_history[-8:]
        self.update_network_snapshot_visibility()
        if first_snapshot:
            self.snap_network_snapshot_render()
        self.update_start_screen_presentation()

    def update_network_client_game_over_prompt(self):
        if not hasattr(self, "gameOverTextObject"):
            return
        if self.game_over:
            if self.network_current_tank_id() == "0":
                self.gameOverTextObject.text = "GAME OVER\nR TO RESTART"
            else:
                self.gameOverTextObject.text = "GAME OVER"
            self.gameOverTextObject.show()
        else:
            self.gameOverTextObject.hide()

    def network_client_terrain_authority_label(self):
        if self.network_terrain_locked:
            return "LOCKED"
        if not self.network_terrain_authority_player_id:
            return "SERVER"
        if self.network_terrain_authority_player_id == self.network_player_id:
            return "YOU"
        return self.network_terrain_authority_player_id

    def update_network_client_start_prompt(self):
        if not self.is_network_client_controller():
            return
        if not hasattr(self, "startTextObject"):
            return
        if self.waiting_to_start:
            self.startTextObject.hide()
            for text_object in getattr(self, "environmentNameTextObjects", []):
                text_object.hide()
            if hasattr(self, "environmentTextObject"):
                self.environmentTextObject.hide()
            self.update_client_lobby_panel()
            self.set_client_lobby_visible(True)
        else:
            self.startTextObject.hide()
            self.set_client_lobby_visible(False)

    def update_network_snapshot_shot_audio(self, shot_states):
        if self.waiting_to_start:
            return

        for tank_id, state in shot_states.items():
            shooting = bool(state.get("shooting", False))
            previously_shooting = getattr(self, "network_snapshot_shot_visible", {}).get(tank_id, False)
            if shooting and not previously_shooting:
                sound = self.mainShot_snd if tank_id == self.current_view_tank_id() else self.enemyShot_snd
                sound.play()
            self.network_snapshot_shot_visible[tank_id] = shooting

    def snapshot_state_point(self, state, key):
        return Point3(*state[key])

    def snapshot_state_hpr(self, state):
        return state["hpr"][0], state["hpr"][1], state["hpr"][2]

    def smooth_node_to_snapshot(self, node, state, dt):
        target_pos = self.snapshot_state_point(state, "pos")
        current_pos = node.getPos(render)
        blend = min(1.0, NETWORK_SMOOTHING_RATE * dt)
        node.setPos(render, current_pos + (target_pos - current_pos) * blend)

        current_hpr = node.getHpr(render)
        target_h, target_p, target_r = self.snapshot_state_hpr(state)
        node.setHpr(
            render,
            self.approach_angle(current_hpr[0], target_h, 720 * dt),
            self.approach_angle(current_hpr[1], target_p, 720 * dt),
            self.approach_angle(current_hpr[2], target_r, 720 * dt)
        )

    def lerp_snapshot_angle(self, start, end, alpha):
        return start + signed_angular_delta_degrees(end, start) * alpha

    def interpolate_network_snapshot_state(self, before, after, alpha):
        if before is None:
            return after
        if after is None:
            return before

        state = dict(after)
        if "pos" in before and "pos" in after:
            state["pos"] = [
                before["pos"][i] + (after["pos"][i] - before["pos"][i]) * alpha
                for i in range(3)
            ]
        if "hpr" in before and "hpr" in after:
            state["hpr"] = [
                self.lerp_snapshot_angle(before["hpr"][i], after["hpr"][i], alpha)
                for i in range(3)
            ]
        if "barrel_tilt" in before and "barrel_tilt" in after:
            state["barrel_tilt"] = before["barrel_tilt"] + (after["barrel_tilt"] - before["barrel_tilt"]) * alpha
        state["hidden"] = after.get("hidden", before.get("hidden", False)) if alpha >= 0.5 else before.get("hidden", after.get("hidden", False))
        state["shooting"] = after.get("shooting", before.get("shooting", False)) if alpha >= 0.5 else before.get("shooting", after.get("shooting", False))
        state["alive"] = after.get("alive", before.get("alive", True)) if alpha >= 0.5 else before.get("alive", after.get("alive", True))
        state["reconstituting"] = after.get("reconstituting", before.get("reconstituting", False)) if alpha >= 0.5 else before.get("reconstituting", after.get("reconstituting", False))
        state["lives"] = after.get("lives", before.get("lives"))
        return state

    def interpolate_network_snapshot_groups(self, before_targets, after_targets, alpha):
        targets = {"tanks": {}, "shots": {}}
        for group_name in ("tanks", "shots"):
            before_group = before_targets.get(group_name, {})
            after_group = after_targets.get(group_name, {})
            for key in set(before_group.keys()) | set(after_group.keys()):
                targets[group_name][key] = self.interpolate_network_snapshot_state(
                    before_group.get(key),
                    after_group.get(key),
                    alpha
                )
        return targets

    def interpolated_network_snapshot_targets(self):
        if not getattr(self, "network_interpolation_enabled", True):
            return self.network_snapshot_targets

        history = getattr(self, "network_snapshot_history", [])
        if len(history) < 2:
            return self.network_snapshot_targets

        render_time = ClockObject.getGlobalClock().getFrameTime() - NETWORK_RENDER_DELAY
        before = history[0]
        after = history[-1]
        for index in range(len(history) - 1):
            candidate_before = history[index]
            candidate_after = history[index + 1]
            if candidate_before["time"] <= render_time <= candidate_after["time"]:
                before = candidate_before
                after = candidate_after
                break
        else:
            if render_time <= history[0]["time"]:
                before = after = history[0]

        duration = after["time"] - before["time"]
        alpha = 1.0 if duration <= 0.0001 else max(0.0, min(1.0, (render_time - before["time"]) / duration))
        return self.interpolate_network_snapshot_groups(before["targets"], after["targets"], alpha)

    def set_node_to_snapshot(self, node, state):
        node.setPos(render, self.snapshot_state_point(state, "pos"))
        node.setHpr(render, *self.snapshot_state_hpr(state))

    def set_tank_body_visibility_from_snapshot(self, tank_id, state):
        body_np = self.tank_body_node(tank_id)
        if state.get("hidden", False):
            body_np.hide()
            return

        body_np.show()
        if not state.get("alive", True) or state.get("reconstituting", False):
            body_np.hide()
            return

        if tank_id == self.current_view_tank_id():
            body_np.hide(MAIN_CAMERA_MASK | AUX_CAMERA_MASK)
            return

        if tank_id == "0":
            if getattr(self, "player_tank_visual_hidden_for_effect", False):
                body_np.hide()
            else:
                body_np.show(MAIN_CAMERA_MASK | AUX_CAMERA_MASK)
            return

        body_np.show(MAIN_CAMERA_MASK | AUX_CAMERA_MASK)

    def set_tank_shot_visibility_from_snapshot(self, tank_id, state):
        shot_np = self.tank_shot_node(tank_id)
        visible = not state.get("hidden", True)

        if not visible:
            shot_np.hide()
        else:
            shot_np.show()

    def set_tank_body_from_snapshot(self, tank_id, state):
        node = self.tank_body_node(tank_id)
        self.set_node_to_snapshot(node, state)

    def set_tank_shot_from_snapshot(self, tank_id, state):
        shot_np = self.tank_shot_node(tank_id)
        shot_np.wrtReparentTo(render)
        self.set_node_to_snapshot(shot_np, state)

    def update_network_snapshot_visibility(self, targets=None):
        targets = targets or self.network_snapshot_targets
        tank_states = targets.get("tanks", {})

        for tank_id in self.tank_ids_for_state():
            state = tank_states.get(tank_id)
            if not state:
                if self.is_network_client_controller():
                    self.tank_body_node(tank_id).hide()
                continue
            self.set_tank_body_visibility_from_snapshot(tank_id, state)

        shot_states = targets.get("shots", {})
        for tank_id in self.tank_ids_for_state():
            state = shot_states.get(tank_id)
            if not state:
                if self.is_network_client_controller():
                    self.tank_shot_node(tank_id).hide()
                continue
            self.set_tank_shot_visibility_from_snapshot(tank_id, state)

    def snap_network_snapshot_render(self):
        tank_states = self.network_snapshot_targets.get("tanks", {})
        view_tank_id = self.network_current_tank_id()
        view_state = self.network_view_state_for_tank(view_tank_id, tank_states)
        if view_state:
            self.camera.setPos(render, self.snapshot_state_point(view_state, "pos"))
            self.camera.setHpr(render, *self.snapshot_state_hpr(view_state))
            self.player_barrel_tilt = float(view_state.get("barrel_tilt", 0.0))
            if view_tank_id == "0":
                self.apply_player_hit_camera_shake()

        for tank_id in self.tank_ids_for_state():
            state = tank_states.get(tank_id)
            if state:
                self.set_tank_body_from_snapshot(tank_id, state)

        shot_states = self.network_snapshot_targets.get("shots", {})
        for tank_id in self.tank_ids_for_state():
            state = shot_states.get(tank_id)
            if state:
                self.set_tank_shot_from_snapshot(tank_id, state)

    def update_network_snapshot_render(self, dt):
        targets = self.interpolated_network_snapshot_targets()
        self.update_network_snapshot_visibility(targets)

        tank_states = targets.get("tanks", {})
        view_tank_id = self.network_current_tank_id()
        view_state = self.network_view_state_for_tank(view_tank_id, tank_states)
        if view_state:
            self.set_node_to_snapshot(self.camera, view_state)
            self.player_barrel_tilt = float(view_state.get("barrel_tilt", 0.0))
            if view_tank_id == "0":
                self.apply_player_hit_camera_shake()

        for tank_id in self.tank_ids_for_state():
            state = tank_states.get(tank_id)
            if state:
                self.set_tank_body_from_snapshot(tank_id, state)

        shot_states = targets.get("shots", {})
        for tank_id in self.tank_ids_for_state():
            state = shot_states.get(tank_id)
            if state:
                self.set_tank_shot_from_snapshot(tank_id, state)

        self.update_barrel_aim_marker()

    def bloom_nodes(self):
        nodes = []
        for root in (render, render2d):
            nodes.extend(root.findAllMatches("**/*Bloom"))
            nodes.extend(root.findAllMatches("**/*Halo"))
        return nodes

    def set_bloom_enabled(self, enabled):
        self.bloom_enabled = enabled
        auxiliary_camera_mask = AUX_CAMERA_MASK | DRONE_CAMERA_MASK
        gpu_bloom_on = False

        if enabled:
            gpu_bloom_on = self.display_filters.setBloom(
                blend=GPU_BLOOM_BLEND,
                mintrigger=GPU_BLOOM_MIN_TRIGGER,
                maxtrigger=GPU_BLOOM_MAX_TRIGGER,
                desat=GPU_BLOOM_DESATURATION,
                intensity=GPU_BLOOM_INTENSITY,
                size=GPU_BLOOM_SIZE
            )
        else:
            self.display_filters.delBloom()

        self.gpu_bloom_available = enabled and gpu_bloom_on

        for node in self.bloom_nodes():
            if enabled and not self.gpu_bloom_available:
                node.show()
                node.hide(auxiliary_camera_mask)
            else:
                node.hide()

        if self.gpu_bloom_available:
            self.bloomTextObject.text = "GPU BLOOM"
        elif enabled:
            self.bloomTextObject.text = "BLOOM FALLBACK"
        else:
            self.bloomTextObject.text = "BLOOM OFF"

    def toggle_bloom(self):
        if self.is_network_client_low_render():
            self.set_bloom_enabled(False)
            return
        self.set_bloom_enabled(not self.bloom_enabled)

    def toggle_network_interpolation(self):
        if not self.is_network_client_controller():
            return
        self.network_interpolation_enabled = not getattr(self, "network_interpolation_enabled", True)
        self.network_snapshot_history = []
        if self.network_snapshot_received:
            self.snap_network_snapshot_render()
        print("Network smoothing {}".format("ON" if self.network_interpolation_enabled else "OFF"))

    def arm_investigation(
            self,
            shooter_id,
            shot_start,
            shot_end,
            shooter_pos=None,
            shooter_hpr=None,
            trajectory_points=None):
        if shooter_id in tanks_list:
            if shooter_pos is None:
                shooter_pos = tanks_dict[shooter_id]["tank"].getPos(render)
            if shooter_hpr is None:
                shooter_hpr = tanks_dict[shooter_id]["tank"].getHpr(render)

        trajectory_points = self.coerce_trajectory_points(
            trajectory_points,
            shot_start,
            shot_end
        )
        self.last_player_hit_event = {
            "shooter_id": shooter_id,
            "shot_start": Point3(shot_start),
            "shot_end": Point3(shot_end),
            "trajectory_points": trajectory_points,
            "shooter_pos": Point3(shooter_pos),
            "shooter_hpr": shooter_hpr,
            "player_pos": self.tank_body_pos("0"),
            "player_hpr": self.tank_body_hpr("0"),
            "fatal": False
        }
        self.investigation_available_until = (
            ClockObject.getGlobalClock().getFrameTime() + INVESTIGATE_WINDOW_SECONDS
        )

    def attach_investigation_cross_marker(self, name, pos, color, radius=0.9):
        marker = LineSegs(name)
        marker.setThickness(3)
        marker.setColor(*color)
        marker.moveTo(-radius, 0, 0)
        marker.drawTo(radius, 0, 0)
        marker.moveTo(0, -radius, 0)
        marker.drawTo(0, radius, 0)
        marker.moveTo(0, 0, -radius * 0.35)
        marker.drawTo(0, 0, radius * 0.9)
        marker_np = self.investigation_marker_root.attachNewNode(marker.create())
        marker_np.setPos(render, Point3(pos))
        marker_np.setTransparency(TransparencyAttrib.MAlpha, 10)
        marker_np.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.MAdd), 10)
        marker_np.setDepthWrite(False, 10)
        marker_np.setColorScale(color[0], color[1], color[2], color[3], 10)
        marker_np.showThrough()
        return marker_np

    def make_investigation_persistent_for_game_over(self):
        if self.last_player_hit_event:
            self.last_player_hit_event["fatal"] = True
            self.investigation_available_until = (
                ClockObject.getGlobalClock().getFrameTime() + INVESTIGATE_FATAL_WINDOW_SECONDS
            )

    def update_investigation_prompt(self):
        if self.investigation_mode:
            self.investigateTextObject.text = "INVESTIGATION\nI TO RESUME"
            self.investigateTextObject.show()
            self.investigateTimerRoot.hide()
            return

        if not self.last_player_hit_event:
            self.investigateTextObject.hide()
            self.investigateTimerRoot.hide()
            return

        fatal_investigation = self.last_player_hit_event.get("fatal", False)
        now = ClockObject.getGlobalClock().getFrameTime()
        remaining = self.investigation_available_until - now
        if remaining <= 0 and not fatal_investigation:
            self.last_player_hit_event = None
            self.investigateTextObject.hide()
            self.investigateTimerRoot.hide()
            return

        progress = 1 if fatal_investigation else max(0, min(1, remaining / INVESTIGATE_WINDOW_SECONDS))
        self.investigateTextObject.text = "I TO INVESTIGATE"
        self.investigateTextObject.show()
        self.investigateTimerFill.setSx(progress)
        self.investigateTimerRoot.show()

    def pause_interval_for_investigation(self, interval):
        if interval is None:
            return
        try:
            if interval.isPlaying():
                interval.pause()
                self.investigation_paused_intervals.append(interval)
        except AttributeError:
            pass

    def pause_simulation_intervals(self):
        self.investigation_paused_intervals = []
        self.pause_interval_for_investigation(self.tank_shot_interval("0"))
        for t in tanks_list:
            self.pause_interval_for_investigation(self.tank_shot_interval(t))
            self.pause_interval_for_investigation(tanks_dict[t].get("explosion"))

    def resume_simulation_intervals(self):
        for interval in self.investigation_paused_intervals:
            try:
                interval.resume()
            except AttributeError:
                pass
        self.investigation_paused_intervals = []

    def render_investigation_markers(self):
        self.clear_investigation_markers()
        event = self.last_player_hit_event
        if not event:
            return

        self.investigation_marker_root = render.attachNewNode("InvestigationMarkers")
        trajectory_points = self.investigation_trajectory_points(event)
        trajectory = LineSegs("InvestigationTrajectory")
        trajectory.setThickness(5)
        trajectory.setColor(1.0, 0.05, 0.02, 1)
        if trajectory_points:
            trajectory.moveTo(trajectory_points[0])
            for point in trajectory_points[1:]:
                trajectory.drawTo(point)
        trajectory_np = self.investigation_marker_root.attachNewNode(trajectory.create())
        trajectory_np.setTransparency(TransparencyAttrib.MAlpha, 10)
        trajectory_np.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.MAdd), 10)
        trajectory_np.setDepthWrite(False, 10)
        trajectory_np.setColorScale(1.0, 0.03, 0.02, 1, 10)
        trajectory_np.showThrough()

        for bounce_point in trajectory_points[1:-1]:
            self.attach_investigation_cross_marker(
                "InvestigationBounce",
                bounce_point,
                (1.0, 0.68, 0.02, 1.0),
                0.75
            )
        if trajectory_points:
            self.attach_investigation_cross_marker(
                "InvestigationImpact",
                trajectory_points[-1],
                (1.0, 0.03, 0.02, 1.0),
                0.55
            )

        shooter_id = event["shooter_id"]
        if shooter_id in tanks_list:
            shooter_marker = self.investigation_marker_root.attachNewNode("InvestigationShooterAtFire")
            shooter_marker.setPos(render, event["shooter_pos"])
            shooter_marker.setHpr(render, event["shooter_hpr"])
            self.tank.instanceTo(shooter_marker)
            shooter_marker.setColorScale(1.0, 0.03, 0.02, 1)
            shooter_marker.showThrough()

        hit_marker_pos = Point3(event["player_pos"])
        hit_marker_pos = self.terrain_position(hit_marker_pos)
        hit_marker = self.investigation_marker_root.attachNewNode("InvestigationPlayerAtHit")
        hit_marker.setPos(render, hit_marker_pos)
        hit_marker.setHpr(render, event["player_hpr"])
        self.tank.instanceTo(hit_marker)
        hit_marker.setColorScale(0.05, 0.35, 1.0, 1)
        hit_marker.showThrough()

    def clear_investigation_markers(self):
        if self.investigation_marker_root is not None and not self.investigation_marker_root.isEmpty():
            self.investigation_marker_root.removeNode()
            self.investigation_marker_root = None
        self.investigation_highlight_tank = None
        self.investigation_highlight_color = None

    def get_investigation_scene_center(self):
        if not self.last_player_hit_event:
            return Point3(self.camera.getPos(render))

        event = self.last_player_hit_event
        points = self.investigation_trajectory_points(event)
        points.extend([
            Point3(event["player_pos"]),
            Point3(event["shooter_pos"]),
        ])
        center = Point3(0, 0, 3.0)
        for point in points:
            center[0] += point[0]
            center[1] += point[1]
        center[0] /= len(points)
        center[1] /= len(points)
        return center

    def save_real_drone_for_investigation(self):
        if self.investigation_drone_saved_state is not None:
            return

        self.investigation_drone_saved_state = {
            "drone_hidden": self.recon_drone_np.isHidden(),
            "drone_pos": Point3(self.recon_drone_np.getPos(render)),
            "drone_hpr": self.recon_drone_np.getHpr(render),
            "camera_pos": Point3(self.drone_camera_np.getPos(render)),
            "camera_hpr": self.drone_camera_np.getHpr(render),
            "camera_heading": self.drone_camera_heading,
            "camera_pitch": self.drone_camera_pitch,
        }

    def restore_real_drone_after_investigation(self):
        if self.investigation_drone_saved_state is None:
            return

        saved = self.investigation_drone_saved_state
        self.recon_drone_np.setPos(render, saved["drone_pos"])
        self.recon_drone_np.setHpr(render, saved["drone_hpr"])
        if saved["drone_hidden"]:
            self.recon_drone_np.hide()
        else:
            self.recon_drone_np.show()
        self.recon_drone_np.hide(DRONE_CAMERA_MASK)
        self.drone_camera_np.setPos(render, saved["camera_pos"])
        self.drone_camera_np.setHpr(render, saved["camera_hpr"])
        self.drone_camera_heading = saved["camera_heading"]
        self.drone_camera_pitch = saved["camera_pitch"]
        self.investigation_drone_saved_state = None

    def toggle_investigation_drone(self):
        if self.investigation_drone_active:
            self.investigation_drone_active = False
            self.restore_real_drone_after_investigation()
            self.update_drone_status_hud()
            return

        self.save_real_drone_for_investigation()
        self.investigation_drone_active = True
        self.investigation_drone_elapsed = 0
        self.investigation_drone_focus = None
        self.recon_drone_np.show()
        self.recon_drone_np.hide(DRONE_CAMERA_MASK)
        self.update_drone_status_hud()

    def update_investigation_drone(self, dt):
        if not self.investigation_drone_active:
            return

        self.investigation_drone_elapsed += dt
        event = self.last_player_hit_event
        if not event:
            return

        player_pos = Point3(event["player_pos"])
        shooter_pos = Point3(event["shooter_pos"])
        focus_points = self.investigation_trajectory_points(event)
        focus_points.extend([player_pos, shooter_pos])
        focus_point = Point3(0, 0, 0.35)
        for point in focus_points:
            focus_point[0] += point[0]
            focus_point[1] += point[1]
        focus_point[0] /= len(focus_points)
        focus_point[1] /= len(focus_points)
        orbit_angle = math.radians(self.investigation_drone_elapsed * INVESTIGATION_DRONE_ORBIT_SPEED)
        orbit_radius = INVESTIGATION_DRONE_ORBIT_RADIUS * (0.92 + 0.08 * math.sin(self.investigation_drone_elapsed * 0.37))
        orbit_x = math.sin(orbit_angle)
        orbit_y = math.cos(orbit_angle)
        drone_pos = Point3(
            focus_point[0] + orbit_x * orbit_radius,
            focus_point[1] + orbit_y * orbit_radius,
            INVESTIGATION_DRONE_ORBIT_ALTITUDE + 3.0 * math.sin(self.investigation_drone_elapsed * 0.41)
        )
        self.investigation_drone_focus = Point3(focus_point)
        body_dx = focus_point[0] - drone_pos[0]
        body_dy = focus_point[1] - drone_pos[1]
        self.drone_heading = math.degrees(math.atan2(body_dx, body_dy))
        self.recon_drone_np.setPos(render, drone_pos)
        self.recon_drone_np.setHpr(render, self.drone_heading, -4, 0)
        self.hide_recon_drone_from_fpv()
        self.drone_camera_np.setPos(render, drone_pos)
        self.drone_camera_np.lookAt(render, focus_point)
        hpr = self.drone_camera_np.getHpr(render)
        self.drone_camera_heading = hpr[0]
        self.drone_camera_pitch = hpr[1]

    def stop_battle_sounds_for_investigation(self):
        self.ambient_snd.stop()
        self.gameOver_snd.stop()
        self.mainShot_snd.stop()
        self.enemyShot_snd.stop()
        self.enemyTankExplosion_snd.stop()
        self.playerHit_snd.stop()

    def resume_sounds_after_investigation(self):
        self.investigation_snd.stop()
        if self.game_over:
            self.gameOver_snd.play()
        else:
            self.ambient_snd.play()

    def enter_investigation(self):
        if not self.last_player_hit_event:
            return

        self.investigation_mode = True
        self.stop_battle_sounds_for_investigation()
        self.investigation_snd.play()
        self.investigation_saved_camera_pos = Point3(self.camera.getPos(render))
        self.investigation_saved_camera_hpr = self.camera.getHpr(render)
        ghost_pos = Point3(self.last_player_hit_event["player_pos"])
        ghost_pos[2] = INVESTIGATION_GHOST_HEIGHT
        self.camera.setPos(render, ghost_pos)
        shot_target = self.investigation_camera_target(self.last_player_hit_event, ghost_pos)
        if shot_target is not None:
            self.camera.lookAt(render, shot_target)
            self.camera.setR(render, 0)
        else:
            self.camera.setHpr(render, self.last_player_hit_event["player_hpr"])
        self.pause_simulation_intervals()
        self.clear_live_hit_effects_for_investigation()
        self.render_investigation_markers()
        if self.game_over:
            self.gameOverTextObject.hide()
        self.update_investigation_prompt()

    def exit_investigation(self):
        self.investigation_mode = False
        if self.investigation_saved_camera_pos is not None:
            self.camera.setPos(render, self.investigation_saved_camera_pos)
            self.camera.setHpr(render, self.investigation_saved_camera_hpr)
        self.investigation_saved_camera_pos = None
        self.investigation_saved_camera_hpr = None
        self.resume_simulation_intervals()
        self.investigation_drone_active = False
        self.investigation_drone_focus = None
        self.restore_real_drone_after_investigation()
        self.clear_investigation_markers()
        self.last_player_hit_event = None
        self.investigateTextObject.hide()
        self.investigateTimerRoot.hide()
        self.resume_sounds_after_investigation()
        if self.game_over:
            self.gameOverTextObject.show()

    def toggle_investigation(self):
        if self.investigation_mode:
            if self.is_network_client_controller() and self.network_current_tank_id() == "0" and self.network_bridge is not None:
                self.network_bridge.send_client_investigation(False)
            self.exit_investigation()
            return

        now = ClockObject.getGlobalClock().getFrameTime()
        if self.last_player_hit_event and (
                self.last_player_hit_event.get("fatal", False) or now <= self.investigation_available_until):
            if self.is_network_client_controller() and self.network_current_tank_id() == "0" and self.network_bridge is not None:
                self.network_bridge.send_client_investigation(True)
            self.enter_investigation()

    def enemy_hit_is_low_enough_for_player_tank(self, hit_point):
        hit_height = hit_point[2] - self.terrain_z(hit_point[0], hit_point[1])
        return hit_height <= PLAYER_HIT_MAX_HEIGHT_ABOVE_GROUND

    def player_tank_is_hittable(self):
        return self.tank_is_hittable("0")

    def struck(self, entry):
        if self.is_network_client_controller():
            return

        now = ClockObject.getGlobalClock().getFrameTime()
        if self.investigation_mode or not self.player_tank_is_hittable() or now - self.last_player_hit_time < PLAYER_HIT_COOLDOWN:
            return

        from_name = entry.getFromNodePath().node().name
        if not from_name.startswith("ceTankRound"):
            return

        shooter_id = from_name[-1]
        if self.tank_shot_deflected(shooter_id):
            return
        shot_start = tanks_dict[shooter_id].get("shot_start", self.tank_shot_node(shooter_id).getPos(render))
        try:
            shot_end = entry.getSurfacePoint(render)
        except Exception:
            shot_end = self.tank_shot_node(shooter_id).getPos(render)
        shot_end = Point3(shot_end)
        if not self.enemy_hit_is_low_enough_for_player_tank(shot_end):
            return
        if not self.consume_incoming_player_hit(shooter_id, now):
            return

        self.arm_investigation(
            shooter_id,
            shot_start,
            shot_end,
            tanks_dict[shooter_id].get("shot_shooter_pos"),
            tanks_dict[shooter_id].get("shot_shooter_hpr"),
            self.shot_trajectory_for_hit(shooter_id, shot_start, shot_end)
        )
        self.enemy_reset_shot(shooter_id)
        self.last_player_hit_time = now
        self.set_tank_hit_cooldown("0", PLAYER_HIT_COOLDOWN)
        self.set_tank_lives("0", max(0, self.tank_lives("0") - 1))
        self.record_player_tank_damage_event(shooter_id)
        self.record_player_damage_feedback()
        self.update_lives_hud()

        if self.tank_lives("0") <= 0:
            self.set_tank_alive("0", False)
            self.set_tank_reconstituting("0", True)
            self.record_player_tank_hit_effect(shooter_id, shot_start, shot_end, log_server=False)
            if self.is_network_server_authority():
                self.record_server_event("death tank 0")
            self.make_investigation_persistent_for_game_over()
            self.end_game()

    def register_incoming_player_tank_hit(self, shooter_id, shot_start, shot_end, trajectory_points=None):
        now = ClockObject.getGlobalClock().getFrameTime()
        if self.investigation_mode or not self.player_tank_is_hittable() or now - self.last_player_hit_time < PLAYER_HIT_COOLDOWN:
            return
        if shooter_id not in tanks_list:
            return
        if self.tank_shot_deflected(shooter_id):
            return

        shot_end = Point3(shot_end)
        if not self.enemy_hit_is_low_enough_for_player_tank(shot_end):
            return
        if not self.consume_incoming_player_hit(shooter_id, now):
            return

        self.arm_investigation(
            shooter_id,
            Point3(shot_start),
            shot_end,
            tanks_dict[shooter_id].get("shot_shooter_pos"),
            tanks_dict[shooter_id].get("shot_shooter_hpr"),
            trajectory_points
        )

        self.last_player_hit_time = now
        self.set_tank_hit_cooldown("0", PLAYER_HIT_COOLDOWN)
        self.set_tank_lives("0", max(0, self.tank_lives("0") - 1))
        self.record_player_tank_damage_event(shooter_id)
        self.record_player_damage_feedback()
        self.update_lives_hud()

        if self.tank_lives("0") <= 0:
            self.set_tank_alive("0", False)
            self.set_tank_reconstituting("0", True)
            self.record_player_tank_hit_effect(shooter_id, shot_start, shot_end, log_server=False)
            if self.is_network_server_authority():
                self.record_server_event("death tank 0")
            self.make_investigation_persistent_for_game_over()
            self.end_game()

    def tank_hit_effect_pose(self, tank_id):
        if tank_id == "0":
            self.update_player_tank_visual()
        return self.tank_body_pos(tank_id), self.tank_body_hpr(tank_id)

    def tank_hit_effect_color(self, tank_id):
        if tank_id == "0":
            return Point4(0.05, 0.35, 1.0, 1.0)
        return tanks_dict[tank_id].get("color_scale", Point4(0.0, 0.8, 0.0, 1.0))

    def record_tank_hit_event(
            self,
            victim_id,
            shooter_id=None,
            shot_start=None,
            shot_end=None,
            play_local=False,
            log_server=True):
        pos, hpr = self.tank_hit_effect_pose(victim_id)
        self.tank_hit_event_serial += 1
        self.last_tank_hit_event = {
            "serial": self.tank_hit_event_serial,
            "victim_id": str(victim_id),
            "shooter_id": str(shooter_id) if shooter_id is not None else "",
            "pos": self.point_to_list(pos),
            "hpr": self.hpr_to_list(hpr),
            "shot_start": self.point_to_list(Point3(shot_start)) if shot_start is not None else None,
            "shot_end": self.point_to_list(Point3(shot_end)) if shot_end is not None else None
        }

        if victim_id == "0":
            self.player_hit_effect_serial = self.tank_hit_event_serial
            self.player_hit_effect_pos = Point3(pos)
            self.player_hit_effect_hpr = hpr

        if log_server and self.is_network_server_authority():
            self.record_server_event("hit tank {} by {}".format(victim_id, shooter_id if shooter_id is not None else "?"))

        if play_local:
            self.play_tank_hit_effect(victim_id, pos, hpr)

    def play_tank_hit_event(self, event):
        if not event:
            return

        victim_id = str(event.get("victim_id", ""))
        if victim_id not in self.tank_ids_for_state():
            return

        pos = Point3(*event.get("pos", [0, 0, 0]))
        hpr = Point3(*event.get("hpr", [0, 0, 0]))
        Sequence(
            Wait(NETWORK_EFFECT_DELAY),
            Func(self.play_tank_hit_effect, victim_id, pos, hpr)
        ).start()

    def play_tank_hit_effect(self, tank_id, pos, hpr):
        if self.investigation_mode:
            return
        if not hasattr(self, "tank_fragment_data"):
            return

        if tank_id != "0":
            self.enemyTankExplosion_snd.play()

        if tank_id == "0":
            self.hide_player_tank_for_hit_effect()
        root = render.attachNewNode("Tank{}-HitEffect".format(tank_id))
        root.setPos(render, Point3(pos))
        root.setHpr(render, hpr)
        root.setColorScale(self.tank_hit_effect_color(tank_id))
        fragments = Parallel(name="Tank{}-HitFragments".format(tank_id))
        for frag in self.tank_fragment_data:
            lines = create_lineSegs_object(frag["model"], 0, frag["name"])
            lines.setThickness(WORLD_LINE_THICKNESS)
            np = root.attachNewNode(lines.create())
            fragments.append(
                ProjectileInterval(
                    np,
                    startPos=np.getPos(),
                    endZ=-0.8,
                    startVel=Point3(6 * (random() - 0.5), 6 * (random() - 0.5), 13 + 8 * random()),
                    name="tank0-hit-fragment"
                )
            )
            fragments.append(
                LerpHprInterval(
                    np,
                    PLAYER_HIT_EFFECT_SECONDS,
                    hpr=(180 * (random() - 0.5), 120 * (random() - 0.5), 90 * (random() - 0.5))
                )
            )

        Sequence(
            fragments,
            Func(self.restore_player_tank_after_hit_effect if tank_id == "0" else lambda: None),
            Func(root.removeNode)
        ).start()

    def record_player_tank_damage_event(self, shooter_id=None):
        if self.is_network_server_authority():
            self.record_server_event("hit tank 0 by {}".format(shooter_id if shooter_id is not None else "?"))

    def record_player_tank_hit_effect(self, shooter_id=None, shot_start=None, shot_end=None, log_server=True):
        self.record_tank_hit_event("0", shooter_id, shot_start, shot_end, play_local=True, log_server=log_server)

    def play_player_tank_hit_effect(self, pos, hpr):
        self.play_tank_hit_effect("0", pos, hpr)

    def hide_player_tank_for_hit_effect(self):
        if not hasattr(self, "player_tank_visual"):
            return
        self.player_tank_visual.hide()
        self.player_tank_visual_hidden_for_effect = True

    def restore_player_tank_after_hit_effect(self):
        if not getattr(self, "player_tank_visual_hidden_for_effect", False):
            return
        self.player_tank_visual_hidden_for_effect = False
        if not self.game_over and self.tank_lives("0") > 0:
            self.set_tank_alive("0", True)
            self.set_tank_reconstituting("0", False)
        self.player_tank_visual.show()
        self.update_player_tank_visual()

    def clear_live_hit_effects_for_investigation(self):
        for node in render.findAllMatches("**/Tank*-HitEffect"):
            node.removeNode()

    def end_game(self):
        self.game_over = True
        self.waiting_to_start = False
        self.arena_hibernating = False
        self.set_tank_alive("0", False)
        self.set_tank_reconstituting("0", False)
        if self.last_player_hit_event:
            self.gameOverTextObject.text = "GAME OVER\nI TO INVESTIGATE\nR TO RESTART"
        else:
            self.gameOverTextObject.text = "GAME OVER\nR TO RESTART"
        self.gameOverTextObject.show()
        self.sight_engaged_np.hide()
        self.sight_clear_np.show()
        self.ambient_snd.stop()
        self.gameOver_snd.play()
        for t in tanks_list:
            tanks_dict[t]["move"] = False
            tanks_dict[t]["shooting"] = False

    def start_game(self):
        if self.is_network_client_controller():
            if self.network_bridge is not None:
                self.network_bridge.send_client_start()
            return

        if not self.waiting_to_start:
            return

        if self.is_network_server_authority() and not self.server_lobby_can_start():
            self.update_network_server_presentation()
            return

        self.waiting_to_start = False
        self.arena_hibernating = False
        if self.is_network_server_authority():
            self.record_server_event("arena started")
        self.camera.setPos(render, self.terrain_position(Point3(0, 0, 0), PLAYER_CAMERA_HEIGHT))
        self.camera.setHpr(0, 0, 0)
        self.set_player_camera_on_terrain()
        self.reset_incoming_player_hit_consumption()
        self.set_tank_alive("0", True)
        self.set_tank_reconstituting("0", False)
        self.set_tank_lives("0", self.tank_max_lives("0"))
        self.set_tank_hit_cooldown("0", PLAYER_RESTART_GRACE_SECONDS)
        self.player_barrel_tilt = 0.0
        self.reset_tank_shot("0")
        for t in tanks_list:
            tanks_dict[t]["barrel_tilt"] = 0.0
            self.set_tank_alive(t, True)
            self.set_tank_reconstituting(t, False)
            self.set_tank_lives(t, self.tank_max_lives(t))
            self.set_tank_hit_cooldown(t, 0)
            self.enemy_reset_shot(t)
            self.reset_ai_tank_controller_for_match(t)
        self.startTextObject.hide()
        for text_object in getattr(self, "environmentNameTextObjects", []):
            text_object.hide()
        self.environmentTextObject.hide()
        self.update_start_screen_presentation()
        self.ambient_snd.play()

    def update_start_screen_presentation(self):
        waiting = getattr(self, "waiting_to_start", False)
        client_controller = self.is_network_client_controller()
        client_low_render = self.is_network_client_low_render()
        client_snapshot = self.network_client_has_snapshot()
        server_authority = self.is_network_server_authority()

        if hasattr(self, "obstacle_group"):
            if (waiting or client_controller) and not client_snapshot:
                self.obstacle_group.hide()
            else:
                self.obstacle_group.show()

        if hasattr(self, "radar_np"):
            radar_visible = (
                not server_authority and
                not waiting and
                (not client_controller or client_snapshot) and
                not client_low_render
            )
            if radar_visible:
                self.radar_np.show()
            else:
                self.radar_np.hide()

        if hasattr(self, "sight_clear_np"):
            sight_visible = not server_authority and not waiting and (not client_controller or client_snapshot)
            if not sight_visible:
                self.sight_clear_np.hide()
                self.sight_engaged_np.hide()
                self.barrelAimMarkerNp.hide()
                self.levelShotMarkerNp.hide()
            else:
                self.sight_clear_np.show()
                self.update_barrel_aim_marker()

        self.set_auxiliary_views_visible(not server_authority and ((not waiting and not client_controller) or client_snapshot) and not client_low_render)
        self.set_drone_view_visible(
            not server_authority and
            not waiting and
            ((not client_controller) or client_snapshot) and
            not client_low_render
        )
        self.set_recon_drone_world_visible(not server_authority and not client_low_render)
        self.set_environment_preview_visible(waiting and not server_authority)
        self.set_client_lobby_visible(waiting and client_controller)
        self.set_server_lobby_visible(waiting and self.server_panda_overlay_enabled())

    def set_auxiliary_views_visible(self, visible):
        if hasattr(self, "panorama_overlay_region"):
            self.panorama_overlay_region.setActive(visible)

        for view in getattr(self, "auxiliary_cameras", []):
            view["region"].setActive(visible)

        for node in getattr(self, "auxiliary_hud_nodes", []):
            if visible:
                node.show()
            else:
                node.hide()

    def set_drone_view_visible(self, visible):
        if hasattr(self, "drone_display_region"):
            self.drone_display_region.setActive(visible)

        for node_name in ("drone_frame_np", "droneTextObject", "droneTitleObject"):
            if not hasattr(self, node_name):
                continue
            node = getattr(self, node_name)
            if visible:
                node.show()
            else:
                node.hide()

    def set_recon_drone_world_visible(self, visible):
        for node_name in ("recon_drone_np", "drone_home_marker_np"):
            if not hasattr(self, node_name):
                continue
            node = getattr(self, node_name)
            if visible:
                node.show()
                if node_name == "recon_drone_np":
                    node.hide(DRONE_CAMERA_MASK)
                else:
                    node.hide(MAIN_CAMERA_MASK | AUX_CAMERA_MASK)
                    node.show(DRONE_CAMERA_MASK)
            else:
                node.hide()

    def set_environment_preview_visible(self, visible):
        if hasattr(self, "environment_preview_region"):
            self.environment_preview_region.setActive(visible)

        for node_name in ("environment_preview_frame_np", "environmentPreviewTitleObject"):
            if not hasattr(self, node_name):
                continue
            node = getattr(self, node_name)
            if visible:
                node.show()
            else:
                node.hide()

    def set_client_lobby_visible(self, visible):
        if not hasattr(self, "clientLobbyRoot"):
            return
        if visible:
            self.clientLobbyRoot.show()
        else:
            self.clientLobbyRoot.hide()

    def update_client_lobby_panel(self):
        if not hasattr(self, "clientLobbyTitleObject"):
            return

        lobby = getattr(self, "network_lobby_state", {}) or {}
        players = lobby.get("players", [])
        tanks = lobby.get("tanks", [])
        terrain = lobby.get("terrain", {})
        authority = self.network_client_terrain_authority_label()
        link_state = self.network_client_mode_label()
        if self.network_join_accepted:
            link_state = "CONNECTED"
        elif self.network_join_rejected_reason:
            link_state = "REJECTED"

        current_tank_id = self.network_current_tank_id()
        own_player = next((row for row in players if row.get("player_id") == self.network_player_id), {})
        own_team = own_player.get("team_id", "T{}".format(current_tank_id))
        own_role = own_player.get("role", "driver").upper()
        own_ready = bool(own_player.get("ready", self.network_join_accepted and not self.network_manual_claim_released))
        claimed_tanks = len([row for row in tanks if row.get("claimed")])
        open_tanks = [
            str(row.get("tank_id"))
            for row in tanks
            if row.get("claimable") and not row.get("claimed")
        ]
        player_count = len(players)
        ready_count = lobby.get("ready_count", len([player for player in players if player.get("ready")]))
        required_tanks = lobby.get("required_tanks", [])
        terrain_control = "ENABLED" if authority == "YOU" else "VIEW ONLY"
        if self.network_manual_claim_released:
            ready_state = "RELEASED"
            start_state = "REJOIN"
        elif not self.network_join_accepted:
            ready_state = "NO CLAIM"
            start_state = "JOINING"
        elif lobby.get("can_start", False):
            ready_state = "YES" if own_ready else "NO"
            start_state = "READY"
        else:
            ready_state = "YES" if own_ready else "NO"
            start_state = "WAITING {}".format(",".join(required_tanks) if required_tanks else "SERVER")
        policy = "{} {}".format(
            str(lobby.get("team_model", "teams_of_one")).replace("_", " ").upper(),
            "LATE JOIN" if lobby.get("late_join", True) else "SYNC START"
        )
        server = "{}:{}".format(NETWORK_HOST, NETWORK_PORT)
        open_label = ",".join(open_tanks) if open_tanks else "NONE"
        command_status = self.network_last_command_status or "IDLE"

        self.clientLobbyTitleObject.text = "BATTLEZONE ARENA"
        self.clientLobbyStatusObject.text = str(lobby.get("state", "LOBBY")).upper()
        self.clientLobbyRows["tank"].text = "TANK        {}".format(current_tank_id)
        self.clientLobbyRows["link"].text = "LINK        {}".format(link_state)
        self.clientLobbyRows["server"].text = "SERVER      {}".format(server)
        self.clientLobbyRows["players"].text = "PLAYERS     {}  READY {}  CLAIMS {}".format(player_count, ready_count, claimed_tanks)
        self.clientLobbyRows["ready"].text = "READY       {}".format(ready_state)
        self.clientLobbyRows["team"].text = "TEAM        {}  {}".format(own_team, own_role)
        self.clientLobbyRows["policy"].text = "POLICY      {}".format(policy)
        self.clientLobbyRows["terrain"].text = "TERRAIN     {}".format(terrain.get("environment_name", self.selected_environment()["name"]))
        self.clientLobbyRows["authority"].text = "AUTHORITY   {}".format(authority)
        self.clientLobbyRows["control"].text = "TERRAIN     {}".format(terrain_control)
        self.clientLobbyRows["claim"].text = "CLAIM       CURRENT {}  OPEN {}".format(current_tank_id, open_label)
        self.clientLobbyRows["start"].text = "START       {}".format(start_state)
        self.clientLobbyRows["command"].text = "COMMAND     {}".format(command_status[:42])

        authority_color = (0.48, 1.0, 0.48, 1) if authority == "YOU" else (0.18, 0.72, 0.28, 1)
        self.clientLobbyRows["authority"].setFg(authority_color)
        self.clientLobbyRows["control"].setFg(authority_color)
        ready_color = (0.48, 1.0, 0.48, 1) if own_ready and self.network_join_accepted else (0.18, 0.72, 0.28, 1)
        self.clientLobbyRows["ready"].setFg(ready_color)
        start_color = (0.48, 1.0, 0.48, 1) if lobby.get("can_start", False) else (0.18, 0.72, 0.28, 1)
        self.clientLobbyRows["start"].setFg(start_color)
        command_color = (0.48, 1.0, 0.48, 1) if self.network_last_command_ok else (1.0, 0.34, 0.28, 1)
        self.clientLobbyRows["command"].setFg(command_color)

    def render_client_lobby_panel(self):
        self.clientLobbyLayerRoot = NodePath("ClientLobbyLayer")
        lobby_camera_node = Camera("ClientLobbyCamera")
        lobby_camera_node.setLens(base.cam2d.node().getLens())
        lobby_camera_node.setScene(self.clientLobbyLayerRoot)
        self.clientLobbyCamera = NodePath(lobby_camera_node)
        self.clientLobbyRegion = base.win.makeDisplayRegion(0, 1, 0, 1)
        self.clientLobbyRegion.setSort(60)
        self.clientLobbyRegion.setClearColorActive(False)
        self.clientLobbyRegion.setClearDepthActive(False)
        self.clientLobbyRegion.setCamera(self.clientLobbyCamera)

        self.clientLobbyAspectRoot = self.clientLobbyLayerRoot.attachNewNode("ClientLobbyAspect")
        self.clientLobbyAspectRoot.setTransform(aspect2d.getTransform(render2d))
        self.clientLobbyRoot = self.clientLobbyAspectRoot.attachNewNode("ClientLobbyPanel")
        self.clientLobbyRoot.setPos(-1.24, 0, 0.58)

        panel = CardMaker("client-lobby-panel")
        panel.setFrame(0, 1.16, -0.84, 0.12)
        panel_np = self.clientLobbyRoot.attachNewNode(panel.generate())
        panel_np.setTransparency(TransparencyAttrib.MAlpha)
        panel_np.setColorScale(0.0, 0.045, 0.015, 0.82)
        panel_np.setBin("fixed", 2)

        frame = LineSegs("client-lobby-frame")
        frame.setThickness(2)
        frame.moveTo(0, 0, -0.84)
        frame.drawTo(1.16, 0, -0.84)
        frame.drawTo(1.16, 0, 0.12)
        frame.drawTo(0, 0, 0.12)
        frame.drawTo(0, 0, -0.84)
        frame_np = self.clientLobbyRoot.attachNewNode(frame.create())
        frame_np.setColorScale(0.08, 0.82, 0.18, 1)

        self.clientLobbyTitleObject = OnscreenText(
            text="BATTLEZONE ARENA",
            pos=(0.05, 0.045),
            align=TextNode.ALeft,
            scale=(0.038, 0.055),
            fg=(0.55, 1.0, 0.55, 1),
            mayChange=True
        )
        self.clientLobbyTitleObject.reparentTo(self.clientLobbyRoot)

        self.clientLobbyStatusObject = OnscreenText(
            text="LOBBY",
            pos=(0.86, 0.045),
            align=TextNode.ARight,
            scale=(0.031, 0.046),
            fg=(0.28, 0.9, 0.34, 1),
            mayChange=True
        )
        self.clientLobbyStatusObject.reparentTo(self.clientLobbyRoot)

        self.clientLobbyRows = {}
        rows = (
            "tank", "link", "server", "players", "ready", "team", "policy",
            "terrain", "authority", "control", "claim", "start", "command"
        )
        for index, row_name in enumerate(rows):
            text_obj = OnscreenText(
                text="",
                pos=(0.05, -0.052 - index * 0.058),
                align=TextNode.ALeft,
                scale=(0.024, 0.036),
                fg=(0.34, 0.96, 0.38, 1),
                mayChange=True
            )
            text_obj.reparentTo(self.clientLobbyRoot)
            self.clientLobbyRows[row_name] = text_obj

        self.clientLobbyRoot.hide()

    def selected_environment(self):
        return ENVIRONMENTS[self.environment_index]

    def selected_terrain(self):
        return self.selected_environment().get("terrain")

    def terrain_z(self, x, y):
        return terrain_height(x, y, self.selected_terrain())

    def terrain_position(self, pos, height_offset=0):
        return Point3(pos[0], pos[1], self.terrain_z(pos[0], pos[1]) + height_offset)

    def terrain_surface_hpr(self, x, y, heading=0, forward_axis="y"):
        sample = TERRAIN_SLOPE_SAMPLE_DISTANCE
        heading_radians = math.radians(heading)
        if forward_axis == "x":
            forward_x = math.cos(heading_radians)
            forward_y = math.sin(heading_radians)
            right_x = -math.sin(heading_radians)
            right_y = math.cos(heading_radians)
        else:
            forward_x = math.sin(heading_radians)
            forward_y = math.cos(heading_radians)
            right_x = math.cos(heading_radians)
            right_y = -math.sin(heading_radians)

        forward_rise = (
            self.terrain_z(x + forward_x * sample, y + forward_y * sample) -
            self.terrain_z(x - forward_x * sample, y - forward_y * sample)
        )
        right_rise = (
            self.terrain_z(x + right_x * sample, y + right_y * sample) -
            self.terrain_z(x - right_x * sample, y - right_y * sample)
        )
        pitch = -math.degrees(math.atan2(forward_rise, sample * 2)) * TERRAIN_SLOPE_RESPONSE
        roll = math.degrees(math.atan2(right_rise, sample * 2)) * TERRAIN_SLOPE_RESPONSE
        return heading, pitch, roll

    def set_player_camera_on_terrain(self):
        pos = self.camera.getPos(render)
        heading = self.camera.getH(render)
        self.camera.setPos(render, self.terrain_position(pos, PLAYER_CAMERA_HEIGHT))
        hpr = self.terrain_surface_hpr(pos[0], pos[1], heading, "y")
        self.camera.setHpr(render, hpr[0], hpr[1], hpr[2])
        self.sync_tank_body_to_control("0")

    def obstacle_surface_pos(self, obstacle):
        return self.terrain_position(obstacle["pos"])

    def obstacle_surface_hpr(self, obstacle):
        pos = obstacle["pos"]
        return self.terrain_surface_hpr(pos[0], pos[1], obstacle.get("heading", 0), "y")

    def obstacle_world_point(self, obstacle, local_point):
        if not hasattr(self, "obstacle_transform_np"):
            self.obstacle_transform_np = render.attachNewNode("ObstacleTransform")
            self.obstacle_transform_np.hide()

        self.obstacle_transform_np.setPos(render, self.obstacle_surface_pos(obstacle))
        self.obstacle_transform_np.setHpr(render, self.obstacle_surface_hpr(obstacle))
        return render.getRelativePoint(self.obstacle_transform_np, local_point)

    def position_start_camera(self):
        terrain_z = terrain_height(0, 0, self.selected_terrain())
        self.camera.setPos(0, 0, max(PLAYER_CAMERA_HEIGHT, terrain_z + START_CAMERA_TERRAIN_CLEARANCE))
        self.camera.setHpr(0, 0, 0)

    def update_environment_hud(self):
        if not hasattr(self, "environmentTextObject"):
            return

        environment = self.selected_environment()
        for text_object in getattr(self, "environmentNameTextObjects", []):
            text_object.text = environment["name"]
        self.environmentTextObject.text = "{}\nTAB OR ARROWS TO CHANGE".format(
            environment["description"]
        )

    def apply_environment_index(self, index, actor=None):
        self.environment_index = index % len(ENVIRONMENTS)
        self.active_obstacles = self.selected_environment()["obstacles"]
        self.render_grid()
        self.render_obstacles()
        self.build_environment_preview_scene()
        self.update_environment_hud()
        self.position_start_camera()
        self.update_start_screen_presentation()
        if actor is not None and self.is_network_server_authority():
            self.record_server_event("terrain set {} by {}".format(self.selected_environment()["name"], actor))

    def set_environment_index(self, index):
        if not self.waiting_to_start:
            return

        if self.is_network_client_controller():
            if self.network_bridge is not None:
                self.network_bridge.send_client_terrain("set", index)
            return

        actor = "SERVER" if self.is_network_server_authority() else None
        self.apply_environment_index(index, actor=actor)

    def next_environment(self):
        if self.is_network_client_controller():
            if self.waiting_to_start and self.network_bridge is not None:
                self.network_bridge.send_client_terrain("next")
            return
        self.set_environment_index(self.environment_index + 1)

    def previous_environment(self):
        if self.is_network_client_controller():
            if self.waiting_to_start and self.network_bridge is not None:
                self.network_bridge.send_client_terrain("previous")
            return
        self.set_environment_index(self.environment_index - 1)

    def cycle_environment(self):
        self.next_environment()

    def return_to_lobby_after_game_over(self, reason=""):
        if self.is_network_client_controller() or not self.game_over:
            return

        if self.investigation_mode:
            self.exit_investigation()
        else:
            self.clear_investigation_markers()
            self.last_player_hit_event = None
            self.investigateTextObject.hide()
            self.investigateTimerRoot.hide()

        self.game_over = False
        self.waiting_to_start = True
        self.arena_hibernating = False
        self.terrain_authority_player_id = ""
        self.terrain_authority_tank_id = ""
        if self.is_network_server_authority():
            detail = "" if not reason else " ({})".format(reason)
            self.record_server_event("arena returned to lobby{}".format(detail))

        self.last_player_hit_time = -PLAYER_HIT_COOLDOWN
        self.reset_incoming_player_hit_consumption()
        self.set_tank_alive("0", True)
        self.set_tank_reconstituting("0", False)
        self.set_tank_lives("0", self.tank_max_lives("0"))
        self.set_tank_hit_cooldown("0", 0)
        self.hit_flash_alpha = 0
        self.player_hit_shake_until = 0
        self.player_hit_shake_started_at = 0
        self.player_tank_visual_hidden_for_effect = False
        self.hitFlashNp.hide()
        self.gameOverTextObject.hide()
        self.investigation_snd.stop()
        self.gameOver_snd.stop()
        self.ambient_snd.stop()
        self.position_start_camera()
        self.player_tank_visual.show()
        self.update_player_tank_visual()
        self.player_barrel_tilt = 0.0
        self.reset_shot()

        for t in tanks_list:
            tanks_dict[t]["barrel_tilt"] = 0.0
            tanks_dict[t]["move"] = True
            tanks_dict[t]["shooting"] = False
            tanks_dict[t]["tank"].show()
            tanks_dict[t]["frags"].hide()
            tanks_dict[t].pop("last_pos", None)
            tanks_dict[t]["attack_ready_time"] = 0
            self.set_tank_alive(t, True)
            self.set_tank_reconstituting(t, False)
            self.set_tank_lives(t, self.tank_max_lives(t))
            self.set_tank_hit_cooldown(t, 0)
            self.enemy_reset_shot(t)

        self.update_lives_hud()
        self.update_environment_hud()
        self.assign_lobby_terrain_authority_if_needed()
        self.update_start_screen_presentation()

    def restart_game(self):
        if self.is_network_client_controller():
            if self.game_over and self.network_bridge is not None:
                self.network_bridge.send_client_restart()
            return

        if not self.game_over:
            return

        if self.investigation_mode:
            self.exit_investigation()
        else:
            self.clear_investigation_markers()
            self.last_player_hit_event = None
            self.investigateTextObject.hide()
            self.investigateTimerRoot.hide()

        self.game_over = False
        self.arena_hibernating = False
        if self.is_network_server_authority():
            self.record_server_event("arena restarted")
        self.last_player_hit_time = -PLAYER_HIT_COOLDOWN
        self.reset_incoming_player_hit_consumption()
        self.set_tank_alive("0", True)
        self.set_tank_reconstituting("0", False)
        self.set_tank_lives("0", self.tank_max_lives("0"))
        self.set_tank_hit_cooldown("0", PLAYER_RESTART_GRACE_SECONDS)
        self.hit_flash_alpha = 0
        self.player_hit_shake_until = 0
        self.player_hit_shake_started_at = 0
        self.player_tank_visual_hidden_for_effect = False
        self.gameOverTextObject.hide()
        self.startTextObject.hide()
        for text_object in getattr(self, "environmentNameTextObjects", []):
            text_object.hide()
        self.environmentTextObject.hide()
        self.hitFlashNp.hide()
        self.investigation_snd.stop()
        self.gameOver_snd.stop()
        self.ambient_snd.play()
        self.camera.setPos(render, self.terrain_position(Point3(0, 0, 0), PLAYER_CAMERA_HEIGHT))
        self.camera.setHpr(0, 0, 0)
        self.set_player_camera_on_terrain()
        self.player_tank_visual.show()
        self.update_player_tank_visual()
        self.player_barrel_tilt = 0.0
        for t in tanks_list:
            tanks_dict[t]["barrel_tilt"] = 0.0
            self.set_tank_lives(t, self.tank_max_lives(t))
        self.update_barrel_aim_marker()
        self.reset_shot()
        for t in tanks_list:
            tanks_dict[t]["move"] = True
            tanks_dict[t]["shooting"] = False
            tanks_dict[t]["tank"].show()
            tanks_dict[t]["frags"].hide()
            tanks_dict[t].pop("last_pos", None)
            self.set_tank_alive(t, True)
            self.set_tank_reconstituting(t, False)
            self.set_tank_lives(t, self.tank_max_lives(t))
            self.set_tank_hit_cooldown(t, 0)
            self.enemy_reset_shot(t)
            self.reset_ai_tank_controller_for_match(t)
        self.update_lives_hud()

    def updatePlayerFeedbackTask(self, task):
        if not self.is_network_client_controller() or self.network_current_tank_id() == "0":
            self.update_investigation_prompt()

        if self.investigation_mode:
            return Task.cont

        if self.hit_flash_alpha > 0:
            fade = ClockObject.getGlobalClock().getDt() / PLAYER_FLASH_SECONDS
            self.hit_flash_alpha = max(0, self.hit_flash_alpha - fade)
            self.hitFlashNp.setColorScale(1, 0, 0, self.hit_flash_alpha)
            self.hitFlashNp.show()
        else:
            self.hitFlashNp.hide()

        return Task.cont

    def render_mountains(self):
        if hasattr(self, "mountain_group"):
            self.mountain_group.removeNode()
        self.mountain_group = self.render.attachNewNode("Mountains")

        with open('models/digitization01_cleaned_02.json', "r") as f:
            data = json.load(f)

        #   map mountain_line to a cylinder
        n = 2  # number of repeats in circumference
        data['points'] = map_mountains(data['points'], n)

        mountain_core = create_line_nodepath(data, 1, "mountain-core-lines", WORLD_LINE_THICKNESS)
        mountain_bloom = create_line_nodepath(data, 1, "mountain-bloom-lines", MOUNTAIN_BLOOM_THICKNESS)
        mountain_halo = create_line_nodepath(data, 1, "mountain-halo-lines", MOUNTAIN_HALO_THICKNESS)
        scale = 7000
        for i in range(n):
            angleRadians = 2 * pi / n * i
            placeholder = self.mountain_group.attachNewNode("MountainLine-Placeholder")
            placeholder.setH(placeholder, 360 / n * i)
            # placeholder.setPos(sin(angleRadians), cos(angleRadians), 0)
            placeholder.setScale(scale, scale, scale / n / 2.5)
            placeholder.setColorScale(0, 0.7, 0, 1.0)

            halo_np = placeholder.attachNewNode("mountain-lines-Halo")
            mountain_halo.instanceTo(halo_np)
            configure_bloom_layer(halo_np, MOUNTAIN_HALO_ALPHA)

            bloom_np = placeholder.attachNewNode("mountain-lines-Bloom")
            mountain_bloom.instanceTo(bloom_np)
            configure_bloom_layer(bloom_np, MOUNTAIN_BLOOM_ALPHA)

            mountain_core.instanceTo(placeholder.attachNewNode("mountain-lines-Core"))

    def render_grid(self):
        if hasattr(self, "grid"):
            self.grid.removeNode()

        grid_lines = procedural_grid(-1000, 500, -1000, 500, 50, self.selected_terrain())
        grid_lines.setThickness(1)
        grid_np = NodePath(grid_lines.create())
        self.grid = render.attachNewNode("Grid")
        grid_np.instanceTo(self.grid)
        self.grid.setColorScale(0.15, 0.2, 0.15, 1.0)
        self.grid.setPos(0, 0, -0.2)

    def render_obstacles(self):
        if hasattr(self, "obstacle_group"):
            self.obstacle_group.removeNode()

        self.obstacle_group = render.attachNewNode("Obstacles")
        factories = {
            "block": procedural_block,
            "pyramid": procedural_pyramid,
            "cone": procedural_cone,
        }

        for obstacle in self.active_obstacles:
            lines = factories[obstacle["kind"]]()
            lines.setThickness(WORLD_LINE_THICKNESS)
            node_path = NodePath(lines.create())
            face_path = create_structure_faces(obstacle["kind"])
            placeholder = self.obstacle_group.attachNewNode(obstacle["name"])
            faces_np = placeholder.attachNewNode(obstacle["name"] + "-Faces")
            face_path.instanceTo(faces_np)
            faces_np.setTransparency(TransparencyAttrib.MAlpha, 20)
            faces_np.setColorScale(0, 0.8, 0.22, 0.18, 20)
            faces_np.setBin("transparent", 0)
            faces_np.setDepthWrite(False, 20)
            node_path.instanceTo(placeholder.attachNewNode(obstacle["name"] + "-Lines"))
            placeholder.setPos(render, self.obstacle_surface_pos(obstacle))
            placeholder.setHpr(render, self.obstacle_surface_hpr(obstacle))
            placeholder.setScale(obstacle["scale"])
            placeholder.find("**/*-Lines").setColorScale(0, 0.55, 0.15, 1.0)

            collision_np = self.obstacle_group.attachNewNode(CollisionNode("cObstacle-" + obstacle["name"]))
            collision_np.setPos(render, self.obstacle_surface_pos(obstacle))
            collision_np.setHpr(render, self.obstacle_surface_hpr(obstacle))
            add_obstacle_shot_solids(collision_np.node(), obstacle)
            if DEBUG:
                collision_np.show()

        if getattr(self, "waiting_to_start", False):
            self.obstacle_group.hide()

    def render_environment_preview(self):
        self.environment_preview_root = NodePath("EnvironmentPreviewScene")
        self.environment_preview_camera_np = NodePath(Camera("EnvironmentPreviewCamera"))
        self.environment_preview_camera_np.node().setScene(self.environment_preview_root)

        slot_left, slot_right, slot_bottom, slot_top = ENVIRONMENT_PREVIEW_SLOT
        self.environment_preview_region = base.win.makeDisplayRegion(slot_left, slot_right, slot_bottom, slot_top)
        self.environment_preview_region.setSort(13)
        self.environment_preview_region.setClearColorActive(True)
        self.environment_preview_region.setClearColor(Vec4(0, 0, 0, 1))
        self.environment_preview_region.setCamera(self.environment_preview_camera_np)

        lens = PerspectiveLens()
        lens.setFov(38)
        lens.setAspectRatio((slot_right - slot_left) * base.getAspectRatio() / (slot_top - slot_bottom))
        self.environment_preview_camera_np.node().setLens(lens)

        self.environment_preview_frame_np = render2d.attachNewNode("EnvironmentPreviewFrame")
        self.environmentPreviewTitleObject = OnscreenText(text="ENVIRON",
                                                          pos=(0, 0),
                                                          align=TextNode.ACenter,
                                                          scale=(0.024, 0.036),
                                                          fg=(0.35, 1.0, 0.35, 1),
                                                          mayChange=True)
        self.environmentPreviewTitleObject.reparentTo(render2d)
        self.update_environment_preview_overlay()
        self.build_environment_preview_scene()

    def environment_preview_bounds(self):
        slot_left, slot_right, slot_bottom, slot_top = ENVIRONMENT_PREVIEW_SLOT
        return slot_left * 2 - 1, slot_right * 2 - 1, slot_bottom * 2 - 1, slot_top * 2 - 1

    def update_environment_preview_overlay(self):
        if not hasattr(self, "environment_preview_frame_np"):
            return

        x0, x1, z0, z1 = self.environment_preview_bounds()
        self.environment_preview_frame_np.node().removeAllChildren()
        frame = LineSegs("EnvironmentPreviewFrame")
        frame.setThickness(2)
        frame.moveTo(x0, 0, z0)
        frame.drawTo(x1, 0, z0)
        frame.drawTo(x1, 0, z1)
        frame.drawTo(x0, 0, z1)
        frame.drawTo(x0, 0, z0)
        self.environment_preview_frame_np.attachNewNode(frame.create())
        self.environment_preview_frame_np.setColorScale(0, 0.65, 0.18, 1)
        self.environmentPreviewTitleObject.setPos((x0 + x1) * 0.5, z1 + 0.04)

        if hasattr(self, "environment_preview_camera_np"):
            slot_left, slot_right, slot_bottom, slot_top = ENVIRONMENT_PREVIEW_SLOT
            self.environment_preview_camera_np.node().getLens().setAspectRatio(
                (slot_right - slot_left) * base.getAspectRatio() / (slot_top - slot_bottom)
            )

    def build_environment_preview_scene(self):
        if not hasattr(self, "environment_preview_root"):
            return

        self.environment_preview_root.getChildren().detach()
        factories = {
            "block": procedural_block,
            "pyramid": procedural_pyramid,
            "cone": procedural_cone,
        }

        min_x = min(obstacle["pos"][0] - obstacle["scale"][0] * 0.5 for obstacle in self.active_obstacles)
        max_x = max(obstacle["pos"][0] + obstacle["scale"][0] * 0.5 for obstacle in self.active_obstacles)
        min_y = min(obstacle["pos"][1] - obstacle["scale"][1] * 0.5 for obstacle in self.active_obstacles)
        max_y = max(obstacle["pos"][1] + obstacle["scale"][1] * 0.5 for obstacle in self.active_obstacles)
        max_z = max(obstacle["scale"][2] for obstacle in self.active_obstacles)
        center = Point3((min_x + max_x) * 0.5, (min_y + max_y) * 0.5, max_z * 0.35)
        span = max(max_x - min_x, max_y - min_y, 24)

        for obstacle in self.active_obstacles:
            placeholder = self.environment_preview_root.attachNewNode(obstacle["name"] + "-Preview")
            lines = factories[obstacle["kind"]]()
            lines.setThickness(WORLD_LINE_THICKNESS)
            line_np = placeholder.attachNewNode(lines.create())
            line_np.setColorScale(0, 0.8, 0.22, 1)
            face_np = placeholder.attachNewNode(create_structure_faces(obstacle["kind"]).node())
            face_np.setTransparency(TransparencyAttrib.MAlpha, 20)
            face_np.setColorScale(0, 0.8, 0.22, 0.18, 20)
            face_np.setBin("transparent", 0)
            face_np.setDepthWrite(False, 20)
            placeholder.setPos(self.obstacle_surface_pos(obstacle))
            placeholder.setHpr(self.obstacle_surface_hpr(obstacle))
            placeholder.setScale(obstacle["scale"])

        ground_lines = procedural_grid(min_x - 8, max_x + 8, min_y - 8, max_y + 8, 8, self.selected_terrain(), 4)
        ground_lines.setThickness(1)
        ground_np = self.environment_preview_root.attachNewNode(ground_lines.create())
        ground_np.setColorScale(0.05, 0.28, 0.08, 1)
        ground_np.setZ(-0.05)

        camera_pos = Point3(center[0] + span * 0.85, center[1] - span * 1.05, max_z + span * 0.75)
        self.environment_preview_camera_np.setPos(camera_pos)
        self.environment_preview_camera_np.lookAt(center)

    def render_sight(self):
        ls = procedural_sight(LineSegs(), True, False)
        ls = procedural_sight(ls, False, False)
        ls.setThickness(3)
        self.sight_clear_node = ls.create()

        ls = procedural_sight(LineSegs(), True, True)
        ls = procedural_sight(ls, False, True)
        ls.setThickness(3)
        self.sight_engaged_node = ls.create()

        self.sight_clear_np = NodePath(self.sight_clear_node)
        self.sight_clear_np.setColorScale(0, 0.5, 0, 1.0)

        self.sight_engaged_np = NodePath(self.sight_engaged_node)
        self.sight_engaged_np.setColorScale(GG)

        self.sightRootNp = render2d.attachNewNode("player-sight-root")
        self.sight_clear_np.reparentTo(self.sightRootNp)
        self.sight_engaged_np.reparentTo(self.sightRootNp)
        self.sight_engaged_np.hide()

        aim_marker = LineSegs("barrel-tilt-aim-marker")
        aim_marker.setThickness(3)
        aim_marker.moveTo(-0.12, 0, 0)
        aim_marker.drawTo(0.12, 0, 0)
        aim_marker.moveTo(0, 0, -0.035)
        aim_marker.drawTo(0, 0, 0.035)
        self.barrelAimMarkerNp = NodePath(aim_marker.create())
        self.barrelAimMarkerNp.setColorScale(0.0, 0.85, 0.18, 1.0)
        self.barrelAimMarkerNp.reparentTo(render2d)

        level_marker = LineSegs("level-shot-reference-marker")
        level_marker.setThickness(2)
        level_marker.moveTo(-0.16, 0, 0)
        level_marker.drawTo(-0.045, 0, 0)
        level_marker.moveTo(0.045, 0, 0)
        level_marker.drawTo(0.16, 0, 0)
        level_marker.moveTo(0, 0, -0.025)
        level_marker.drawTo(0, 0, 0.025)
        self.levelShotMarkerNp = NodePath(level_marker.create())
        self.levelShotMarkerNp.setColorScale(0.0, 0.38, 0.08, 1.0)
        self.levelShotMarkerNp.reparentTo(render2d)
        self.update_barrel_aim_marker()

    def update_barrel_aim_marker(self):
        if not hasattr(self, "barrelAimMarkerNp"):
            return

        if getattr(self, "waiting_to_start", False):
            self.sightRootNp.setZ(0)
            self.barrelAimMarkerNp.hide()
            self.levelShotMarkerNp.hide()
            return

        aim_point = self.tank_aim_point_local("0")
        projected = Point2()
        if aim_point[1] <= 0 or not self.camLens.project(aim_point, projected):
            self.sightRootNp.hide()
            self.barrelAimMarkerNp.hide()
            self.levelShotMarkerNp.hide()
            return

        self.sightRootNp.show()
        if PLAYER_SIGHT_MOVES_WITH_BARREL:
            self.sightRootNp.setPos(projected[0], 0, projected[1])
            self.barrelAimMarkerNp.hide()
            self.levelShotMarkerNp.setPos(0, 0, 0)
            self.levelShotMarkerNp.show()
        else:
            self.sightRootNp.setPos(0, 0, 0)
            self.barrelAimMarkerNp.setPos(projected[0], 0, projected[1])
            self.barrelAimMarkerNp.show()
            self.levelShotMarkerNp.hide()

    def render_radar(self):
        self.radar_np = aspect2d.attachNewNode("Radar")
        self.radar_np.setPos(-base.getAspectRatio() + RADAR_RADIUS + RADAR_MARGIN,
                             0,
                             -1 + RADAR_RADIUS + RADAR_MARGIN)

        frame_lines = procedural_radar_frame(RADAR_RADIUS)
        frame_lines.setThickness(2)
        frame_np = self.radar_np.attachNewNode(frame_lines.create())
        frame_np.setColorScale(0, 0.45, 0, 1.0)

        center_lines = procedural_radar_blip(0.012)
        center_lines.setThickness(2)
        center_np = self.radar_np.attachNewNode(center_lines.create())
        center_np.setColorScale(GG)

        self.radar_sweep_slice = create_radar_sweep_slice(
            RADAR_RADIUS * 0.9,
            RADAR_SWEEP_SLICE_DEGREES,
            RADAR_SWEEP_SLICE_ALPHA
        )
        self.radar_sweep_slice.reparentTo(self.radar_np)
        self.radar_sweep_slice.setTransparency(TransparencyAttrib.MAlpha, 10)
        self.radar_sweep_slice.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.MAdd), 10)
        self.radar_sweep_slice.setDepthWrite(False, 10)
        self.radar_sweep_slice.setBin("transparent", 0)

        sweep_lines = procedural_radar_sweep(RADAR_RADIUS)
        self.radar_sweep_nodes = []
        for idx, (angle_offset, alpha, thickness) in enumerate(RADAR_SWEEP_TRAILS):
            sweep_lines.setThickness(thickness)
            sweep_np = self.radar_np.attachNewNode(sweep_lines.create())
            sweep_np.setName("Radar-Sweep-{}".format(idx))
            sweep_np.setTransparency(TransparencyAttrib.MAlpha, 10)
            sweep_np.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.MAdd), 10)
            sweep_np.setDepthWrite(False, 10)
            sweep_np.setColorScale(0, alpha, 0, alpha, 10)
            self.radar_sweep_nodes.append((sweep_np, angle_offset))

        blip_lines = procedural_radar_blip(0.015)
        blip_lines.setThickness(3)
        blip_node = NodePath(blip_lines.create())
        self.radar_blips = {}
        self.radar_blip_luminance = {}
        self.radar_last_update_time = None
        for t in tanks_list:
            blip_np = self.radar_np.attachNewNode("Radar-Blip-{}".format(t))
            blip_node.instanceTo(blip_np)
            blip_np.setTransparency(TransparencyAttrib.MAlpha, 10)
            blip_np.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.MAdd), 10)
            blip_np.setDepthWrite(False, 10)
            blip_np.hide()
            self.radar_blips[t] = blip_np
            self.radar_blip_luminance[t] = 0

    def render_player_hud(self):
        self.waiting_to_start = True
        self.game_over = False
        self.arena_hibernating = False
        self.last_player_hit_time = -PLAYER_HIT_COOLDOWN
        self.reset_incoming_player_hit_consumption()
        self.set_tank_alive("0", True)
        self.set_tank_reconstituting("0", False)
        self.set_tank_lives("0", self.tank_max_lives("0"))
        self.set_tank_hit_cooldown("0", 0)
        for t in tanks_list:
            self.set_tank_alive(t, True)
            self.set_tank_reconstituting(t, False)
            self.set_tank_lives(t, self.tank_max_lives(t))
            self.set_tank_hit_cooldown(t, 0)
        self.hit_flash_alpha = 0
        self.player_hit_shake_until = 0
        self.player_hit_shake_started_at = 0
        self.player_damage_event_serial = 0
        self.network_player_damage_event_serial = 0
        self.investigation_mode = False
        self.investigation_available_until = 0
        self.last_player_hit_event = None
        self.player_tank_visual_hidden_for_effect = False
        self.investigation_saved_camera_pos = None
        self.investigation_saved_camera_hpr = None
        self.investigation_marker_root = None
        self.investigation_highlight_tank = None
        self.investigation_highlight_color = None
        self.investigation_paused_intervals = []
        self.investigation_drone_active = False
        self.investigation_drone_elapsed = 0
        self.investigation_drone_focus = None
        self.investigation_drone_saved_state = None
        self.player_shot_interval = None
        self.player_shot_deflected = False
        self.enemy_shooting_suspended = False
        self.player_barrel_tilt = 0.0
        for t in tanks_list:
            tanks_dict[t]["barrel_tilt"] = 0.0

        self.livesTableRoot = aspect2d.attachNewNode("LivesTable")
        self.livesTableRoot.setPos(-1.18, 0, -0.62)
        self.livesNameTextObjects = []
        self.livesValueTextObjects = []
        header_scale = (0.038, 0.055)
        row_scale = (0.033, 0.048)
        self.livesHeaderNameTextObject = OnscreenText(
            text="TANKS", pos=(0, 0), align=TextNode.ALeft,
            scale=header_scale, fg=(0.4, 1.0, 0.4, 1), mayChange=False
        )
        self.livesHeaderLivesTextObject = OnscreenText(
            text="LIVES", pos=(0.38, 0), align=TextNode.ARight,
            scale=header_scale, fg=(0.4, 1.0, 0.4, 1), mayChange=False
        )
        self.livesHeaderNameTextObject.reparentTo(self.livesTableRoot)
        self.livesHeaderLivesTextObject.reparentTo(self.livesTableRoot)
        for index, tank_id in enumerate(self.tank_ids_for_state()):
            z = -0.07 * (index + 1)
            name_text = OnscreenText(
                text="", pos=(0, z), align=TextNode.ALeft,
                scale=row_scale, fg=(0.4, 1.0, 0.4, 1), mayChange=True
            )
            lives_text = OnscreenText(
                text="", pos=(0.38, z), align=TextNode.ARight,
                scale=row_scale, fg=(0.4, 1.0, 0.4, 1), mayChange=True
            )
            name_text.reparentTo(self.livesTableRoot)
            lives_text.reparentTo(self.livesTableRoot)
            self.livesNameTextObjects.append(name_text)
            self.livesValueTextObjects.append(lives_text)

        self.gameOverTextObject = OnscreenText(text="GAME OVER\nR TO RESTART", pos=(0, 0.08),
                                               align=TextNode.ACenter, scale=(0.08, 0.1),
                                               fg=(0.4, 1.0, 0.4, 1), mayChange=True)
        self.gameOverTextObject.reparentTo(aspect2d)
        self.gameOverTextObject.hide()

        self.startTextObject = OnscreenText(text="BATTLEZONE\nPRESS ENTER OR SPACE",
                                            pos=(0, 0.12),
                                            align=TextNode.ACenter, scale=(0.075, 0.1),
                                            fg=(0.4, 1.0, 0.4, 1), mayChange=True)
        self.startTextObject.reparentTo(aspect2d)
        self.render_client_lobby_panel()
        self.render_server_lobby_overlay()

        self.environmentNameTextObjects = []
        for offset_x, offset_z in ((0, 0), (0.003, 0), (-0.003, 0), (0, 0.003)):
            environment_name = OnscreenText(text="",
                                            pos=(offset_x, -0.16 + offset_z),
                                            align=TextNode.ACenter, scale=(0.055, 0.078),
                                            fg=(0.38, 1.0, 0.42, 1), mayChange=True)
            environment_name.reparentTo(aspect2d)
            self.environmentNameTextObjects.append(environment_name)

        self.environmentTextObject = OnscreenText(text="",
                                                  pos=(0, -0.29),
                                                  align=TextNode.ACenter, scale=(0.04, 0.058),
                                                  fg=(0.25, 0.85, 0.35, 1), mayChange=True)
        self.environmentTextObject.reparentTo(aspect2d)
        self.update_environment_hud()

        card = CardMaker("player-hit-flash")
        card.setFrameFullscreenQuad()
        self.hitFlashNp = render2d.attachNewNode(card.generate())
        self.hitFlashNp.setTransparency(TransparencyAttrib.MAlpha)
        self.hitFlashNp.setBin("fixed", 10)
        self.hitFlashNp.setDepthWrite(False)
        self.hitFlashNp.setColorScale(1, 0, 0, 0)
        self.hitFlashNp.hide()

        self.investigateTextObject = OnscreenText(text="", pos=(0, -0.69),
                                                  align=TextNode.ACenter, scale=(0.045, 0.065),
                                                  fg=(0.35, 1.0, 0.35, 1), mayChange=True)
        self.investigateTextObject.reparentTo(aspect2d)
        self.investigateTextObject.hide()

        self.investigateTimerRoot = aspect2d.attachNewNode("InvestigateTimer")
        self.investigateTimerRoot.setPos(-0.24, 0, -0.76)
        timer_bg = CardMaker("investigate-timer-bg")
        timer_bg.setFrame(0, 0.48, 0, 0.026)
        self.investigateTimerBg = self.investigateTimerRoot.attachNewNode(timer_bg.generate())
        self.investigateTimerBg.setTransparency(TransparencyAttrib.MAlpha)
        self.investigateTimerBg.setColorScale(0.0, 0.18, 0.0, 0.7)
        timer_fill = CardMaker("investigate-timer-fill")
        timer_fill.setFrame(0, 0.48, 0, 0.026)
        self.investigateTimerFill = self.investigateTimerRoot.attachNewNode(timer_fill.generate())
        self.investigateTimerFill.setTransparency(TransparencyAttrib.MAlpha)
        self.investigateTimerFill.setColorScale(0.25, 1.0, 0.25, 0.85)
        self.investigateTimerRoot.hide()

        self.update_lives_hud()

    def update_lives_hud(self):
        rows = self.tank_lives_rows()
        for index, (name, lives_text) in enumerate(rows):
            self.livesNameTextObjects[index].text = name
            self.livesValueTextObjects[index].text = lives_text
        self.position_lives_table()

    def position_lives_table(self):
        if not hasattr(self, "livesTableRoot"):
            return
        if self.is_network_server_authority() and getattr(self, "waiting_to_start", False):
            self.livesTableRoot.hide()
        else:
            self.livesTableRoot.show()
            self.livesTableRoot.setPos(-1.18, 0, -0.62)

    def render_server_lobby_overlay(self):
        self.serverLobbyDimNp = render2d.attachNewNode("ServerLobbyDim")
        dim_card = CardMaker("server-lobby-dim-card")
        dim_card.setFrameFullscreenQuad()
        dim_np = self.serverLobbyDimNp.attachNewNode(dim_card.generate())
        dim_np.setTransparency(TransparencyAttrib.MAlpha)
        dim_np.setColorScale(0, 0, 0, 0.58)
        self.serverLobbyDimNp.setBin("fixed", 5)
        self.serverLobbyDimNp.setDepthWrite(False)

        self.serverLobbyRoot = aspect2d.attachNewNode("ServerLobby")
        self.serverLobbyRoot.setBin("fixed", 20)
        panel = CardMaker("server-lobby-panel")
        panel.setFrame(-0.94, 0.94, -0.48, 0.48)
        panel_np = self.serverLobbyRoot.attachNewNode(panel.generate())
        panel_np.setTransparency(TransparencyAttrib.MAlpha)
        panel_np.setColorScale(0.0, 0.035, 0.015, 0.88)

        frame = LineSegs("server-lobby-frame")
        frame.setThickness(2)
        frame.moveTo(-0.94, 0, -0.48)
        frame.drawTo(0.94, 0, -0.48)
        frame.drawTo(0.94, 0, 0.48)
        frame.drawTo(-0.94, 0, 0.48)
        frame.drawTo(-0.94, 0, -0.48)
        frame.moveTo(-0.82, 0, 0.13)
        frame.drawTo(0.82, 0, 0.13)
        frame.moveTo(-0.82, 0, -0.11)
        frame.drawTo(0.82, 0, -0.11)
        frame_np = self.serverLobbyRoot.attachNewNode(frame.create())
        frame_np.setColorScale(0.0, 0.62, 0.22, 1)

        self.serverLobbyTitleObject = OnscreenText(
            text="BATTLEZONE SERVER", pos=(0, 0.32), align=TextNode.ACenter,
            scale=(0.052, 0.075), fg=(0.5, 1.0, 0.55, 1), mayChange=False
        )
        self.serverLobbySubtitleObject = OnscreenText(
            text="NETWORK LOBBY", pos=(0, 0.23), align=TextNode.ACenter,
            scale=(0.026, 0.04), fg=(0.12, 0.75, 0.28, 1), mayChange=False
        )
        self.serverLobbyStatusObject = OnscreenText(
            text="", pos=(-0.68, 0.08), align=TextNode.ALeft,
            scale=(0.029, 0.043), fg=(0.34, 1.0, 0.42, 1), mayChange=True
        )
        self.serverLobbyPromptObject = OnscreenText(
            text="", pos=(0, -0.38), align=TextNode.ACenter,
            scale=(0.034, 0.05), fg=(0.55, 1.0, 0.55, 1), mayChange=True
        )
        self.serverLobbyMetricsObject = OnscreenText(
            text="", pos=(-0.68, -0.055), align=TextNode.ALeft,
            scale=(0.021, 0.032), fg=(0.16, 0.78, 0.3, 1), mayChange=True
        )
        for obj in (
            self.serverLobbyTitleObject,
            self.serverLobbySubtitleObject,
            self.serverLobbyStatusObject,
            self.serverLobbyPromptObject,
            self.serverLobbyMetricsObject,
        ):
            obj.reparentTo(self.serverLobbyRoot)

        self.serverLobbyHeaderObjects = []
        headers = (("TANK", -0.72, TextNode.ALeft), ("CTRL", -0.34, TextNode.ALeft),
                   ("LIVES", -0.03, TextNode.ARight), ("CLAIM", 0.28, TextNode.ARight),
                   ("LINK", 0.72, TextNode.ARight))
        for text, x, align in headers:
            header = OnscreenText(
                text=text, pos=(x, 0.02), align=align,
                scale=(0.024, 0.036), fg=(0.16, 0.78, 0.3, 1), mayChange=False
            )
            header.reparentTo(self.serverLobbyRoot)
            self.serverLobbyHeaderObjects.append(header)

        self.serverLobbyRowObjects = []
        for row_index, tank_id in enumerate(self.tank_ids_for_state()):
            z = -0.16 - row_index * 0.065
            row = []
            row_specs = ((-0.72, TextNode.ALeft), (-0.34, TextNode.ALeft),
                         (-0.03, TextNode.ARight), (0.28, TextNode.ARight),
                         (0.72, TextNode.ARight))
            for x, align in row_specs:
                text_obj = OnscreenText(
                    text="", pos=(x, z), align=align,
                    scale=(0.031, 0.047), fg=(0.42, 1.0, 0.42, 1), mayChange=True
                )
                text_obj.reparentTo(self.serverLobbyRoot)
                row.append(text_obj)
            self.serverLobbyRowObjects.append(row)

        self.set_server_lobby_visible(False)

    def set_server_lobby_visible(self, visible):
        if not hasattr(self, "serverLobbyRoot"):
            return
        if visible:
            self.serverLobbyRoot.show()
            self.serverLobbyDimNp.show()
        else:
            self.serverLobbyRoot.hide()
            self.serverLobbyDimNp.hide()

    def update_server_lobby_overlay(self, connected_tanks=None, controller_types=None, claims=None, status=None):
        if not hasattr(self, "serverLobbyRoot"):
            return
        claims = claims or {}
        status = status or {}
        rows = self.server_lobby_rows(connected_tanks, controller_types, claims)
        lobby = self.network_lobby_snapshot()
        players = lobby.get("players", [])
        ready_count = lobby.get("ready_count", len([player for player in players if player.get("ready")]))
        expected_tanks = self.server_lobby_expected_client_tanks()
        connected = len(expected_tanks.intersection(set(connected_tanks or [])))
        expected_clients = len(expected_tanks)
        client_word = "CLIENT" if expected_clients == 1 else "CLIENTS"
        self.serverLobbyStatusObject.text = "{} / {} {} CONNECTED | CLAIMS {} / {}".format(
            connected,
            expected_clients,
            client_word,
            status.get("connected_count", len(connected_tanks or [])),
            status.get("claimable_count", len(CLAIMABLE_TANK_IDS))
        )
        self.serverLobbyMetricsObject.text = (
            "HOST {host}:{port}  PLAYERS {players}  READY {ready}  TEAM {team}  RX {rx}  SNAP {snap}/{frames}"
        ).format(
            host=status.get("host", NETWORK_HOST),
            port=status.get("port", NETWORK_PORT),
            players=len(players),
            ready=ready_count,
            team=str(lobby.get("team_model", "teams_of_one")).replace("_", " ").upper(),
            rx=status.get("rx_input_packets", 0),
            snap=status.get("snapshot_packets", 0),
            frames=status.get("snapshot_frames", 0)
        )
        if lobby.get("can_start", connected >= expected_clients):
            self.serverLobbyPromptObject.text = "CLIENT READY TO START"
            self.serverLobbyPromptObject.setFg((0.55, 1.0, 0.55, 1))
        else:
            self.serverLobbyPromptObject.text = "WAITING FOR TANK 0"
            self.serverLobbyPromptObject.setFg((0.16, 0.72, 0.28, 1))
        for row_index, row_values in enumerate(rows):
            row_objects = self.serverLobbyRowObjects[row_index]
            tank_id, controller, lives_text, claim_text, link_state = row_values
            display_values = ("TANK {}".format(tank_id), controller, lives_text, claim_text, link_state)
            if link_state == "RESERVED":
                row_color = (0.08, 0.32, 0.16, 1)
            elif link_state == "WAITING":
                row_color = (0.12, 0.55, 0.22, 1)
            elif link_state == "SERVER":
                row_color = (0.2, 0.76, 0.3, 1)
            else:
                row_color = (0.42, 1.0, 0.42, 1)
            for text_obj, value in zip(row_objects, display_values):
                text_obj.text = value
                text_obj.setFg(row_color)

    def render_tank_hud_labels(self):
        self.tank_hud_label_lines = {}
        self.tank_hud_label_text = {}
        self.tank_hud_label_cards = {}
        for t in sorted(tanks_list):
            card_np = render2d.attachNewNode("Tank{}HudLabelCard".format(t))
            line_np = render2d.attachNewNode("Tank{}HudLabelLine".format(t))
            self.tank_hud_label_cards[t] = card_np
            self.tank_hud_label_lines[t] = line_np
            color = tanks_dict[t]["color_scale"]
            label = OnscreenText(text=t, pos=(0, 0), align=TextNode.ACenter,
                                 scale=(0.038, 0.057),
                                 fg=(color[0], color[1], color[2], 1), mayChange=True)
            label.reparentTo(render2d)
            label.hide()
            card_np.hide()
            line_np.hide()
            self.tank_hud_label_text[t] = label

    def hide_tank_hud_label(self, t):
        self.tank_hud_label_text[t].hide()
        self.tank_hud_label_cards[t].hide()
        self.tank_hud_label_lines[t].hide()

    def tank_hud_label_text_value(self, t):
        if not TACTICAL_AI_DEBUG_LABELS:
            return t
        if self.is_network_client_controller():
            tank_state = self.network_snapshot_targets.get("tanks", {}).get(t, {})
            debug_state = tank_state.get("debug_state", "")
            return "{}:{}".format(t, debug_state) if debug_state else t
        controller = getattr(self, "ai_tank_controllers", {}).get(t)
        if controller is None:
            return t
        return "{}:{}".format(t, getattr(controller, "debug_state", ""))

    def updateTankHudLabelsTask(self, task):
        if self.waiting_to_start or self.is_network_client_low_render() or self.is_network_server_authority():
            for t in tanks_list:
                self.hide_tank_hud_label(t)
            return Task.cont

        for t in tanks_list:
            tank_np = tanks_dict[t]["tank"]
            if tank_np.isHidden():
                self.hide_tank_hud_label(t)
                continue

            target_world = tank_np.getPos(render) + Point3(0, 0, 2.2)
            camera_space = self.camera.getRelativePoint(render, target_world)
            projected = Point2()
            if camera_space[1] <= 0 or not self.camLens.project(camera_space, projected):
                self.hide_tank_hud_label(t)
                continue

            target_x = projected[0]
            target_z = projected[1]
            if abs(target_x) > 1.08 or abs(target_z) > 1.08:
                self.hide_tank_hud_label(t)
                continue

            side = -1 if target_x > 0.72 else 1
            label_x = max(-0.94, min(0.94, target_x + side * 0.08))
            label_z = max(-0.82, min(0.62, target_z + 0.09))
            debug_enabled = TACTICAL_AI_DEBUG_LABELS
            frame_w = 0.13 if debug_enabled else 0.082
            frame_h = 0.082
            anchor_x = label_x - side * frame_w * 0.5
            anchor_z = label_z - frame_h * 0.22

            label = self.tank_hud_label_text[t]
            label.text = self.tank_hud_label_text_value(t)
            if debug_enabled:
                label.setScale(0.026, 0.044)
            else:
                label.setScale(0.038, 0.057)
            label.setPos(label_x, label_z - 0.004)
            label.show()

            color = tanks_dict[t]["color_scale"]
            x0 = label_x - frame_w * 0.5
            x1 = label_x + frame_w * 0.5
            z0 = label_z - frame_h * 0.5
            z1 = label_z + frame_h * 0.5

            card_root = self.tank_hud_label_cards[t]
            card_root.node().removeAllChildren()
            card = CardMaker("Tank{}HudLabelBackdrop".format(t))
            card.setFrame(x0, x1, z0, z1)
            card_np = card_root.attachNewNode(card.generate())
            card_np.setTransparency(TransparencyAttrib.MAlpha)
            card_np.setColorScale(0, 0, 0, 0.38)
            card_root.show()

            line_root = self.tank_hud_label_lines[t]
            line_root.node().removeAllChildren()
            lines = LineSegs("Tank{}HudLabelBubble".format(t))
            lines.setThickness(1.6)
            lines.setColor(color[0], color[1], color[2], 1)
            lines.moveTo(x0, 0, z0)
            lines.drawTo(x1, 0, z0)
            lines.drawTo(x1, 0, z1)
            lines.drawTo(x0, 0, z1)
            lines.drawTo(x0, 0, z0)
            lines.moveTo(target_x, 0, target_z)
            lines.drawTo(anchor_x, 0, anchor_z)
            line_root.attachNewNode(lines.create())
            line_root.show()

        return Task.cont

    def render_auxiliary_views(self):
        self.auxiliary_cameras = []
        self.auxiliary_hud_nodes = []
        self.panorama_overlay_root = NodePath("PanoramaOverlay")
        overlay_camera_node = Camera("PanoramaOverlayCamera")
        overlay_camera_node.setLens(base.cam2d.node().getLens())
        overlay_camera_node.setScene(self.panorama_overlay_root)
        overlay_camera = NodePath(overlay_camera_node)
        overlay_region = base.win.makeDisplayRegion(0, 1, 0, 1)
        overlay_region.setSort(30)
        overlay_region.setClearColorActive(False)
        overlay_region.setClearDepthActive(False)
        overlay_region.setCamera(overlay_camera)
        self.panorama_overlay_camera = overlay_camera
        self.panorama_overlay_region = overlay_region
        aspect = base.getAspectRatio()

        for view in HUD_VIEWPORTS:
            slot_left, slot_right, slot_bottom, slot_top = view["slot"]
            slot_width = slot_right - slot_left
            slot_height = slot_top - slot_bottom
            view_aspect = view["aspect"]
            desired_width = slot_height * view_aspect / aspect
            desired_height = slot_width * aspect / view_aspect

            if desired_width <= slot_width:
                width = desired_width
                height = slot_height
            else:
                width = slot_width
                height = desired_height

            left = slot_left + (slot_width - width) * 0.5 + HUD_VIEW_PADDING
            right = slot_left + (slot_width + width) * 0.5 - HUD_VIEW_PADDING
            bottom = slot_bottom + (slot_height - height) * 0.5 + HUD_VIEW_PADDING
            top = slot_bottom + (slot_height + height) * 0.5 - HUD_VIEW_PADDING

            slices = view.get("slices", 1)
            slice_fov = view["fov"] / slices
            for slice_index in range(slices):
                slice_left = left + (right - left) * slice_index / slices
                slice_right = left + (right - left) * (slice_index + 1) / slices

                display_region = base.win.makeDisplayRegion(slice_left, slice_right, bottom, top)
                display_region.setSort(10)
                display_region.setClearColorActive(True)
                display_region.setClearColor(Vec4(0, 0, 0, 1))

                lens = PerspectiveLens()
                lens.setFov(slice_fov)
                lens.setAspectRatio((slice_right - slice_left) * aspect / (top - bottom))
                camera_node = Camera("Hud{}Camera{}".format(view["name"].title(), slice_index))
                camera_node.setLens(lens)
                camera_np = render.attachNewNode(camera_node)
                display_region.setCamera(camera_np)

                ordered_slice_index = slices - slice_index - 1
                heading_offset = -view["fov"] * 0.5 + slice_fov * (ordered_slice_index + 0.5)
                self.auxiliary_cameras.append({
                    "camera": camera_np,
                    "heading": view["heading"] + heading_offset,
                    "region": display_region,
                })

            x0 = (left * 2 - 1) * aspect
            x1 = (right * 2 - 1) * aspect
            z0 = bottom * 2 - 1
            z1 = top * 2 - 1
            frame = LineSegs("Hud{}ViewFrame".format(view["name"].title()))
            frame.setThickness(2)
            frame.moveTo(x0, 0, z0)
            frame.drawTo(x1, 0, z0)
            frame.drawTo(x1, 0, z1)
            frame.drawTo(x0, 0, z1)
            frame.drawTo(x0, 0, z0)
            frame_np = aspect2d.attachNewNode(frame.create())
            frame_np.setColorScale(0, 0.55, 0, 1)
            self.auxiliary_hud_nodes.append(frame_np)

            if view["name"] == "PANORAMA":
                self.render_panorama_main_view_edges(view, x0, x1, z0, z1)

            label = OnscreenText(text=view["name"], pos=((x0 + x1) * 0.5, z0 - 0.035),
                                 align=TextNode.ACenter, scale=(0.025, 0.038),
                                 fg=(0.35, 1.0, 0.35, 1), mayChange=False)
            label.reparentTo(aspect2d)
            self.auxiliary_hud_nodes.append(label)

        self.hide_bloom_from_auxiliary_views()

    def render_panorama_main_view_edges(self, view, x0, x1, z0, z1):
        edge_angle = self.camLens.getFov()[0] * 0.5
        dash_count = 12
        dash_gap = (z1 - z0) / (dash_count * 2 - 1)
        markers = LineSegs("PanoramaMainViewportEdges")
        markers.setThickness(2)

        for angle in (edge_angle, -edge_angle):
            relative_angle = angle - view["heading"]
            fraction = (view["fov"] * 0.5 - relative_angle) / view["fov"]
            x = x0 + (x1 - x0) * fraction
            for dash_index in range(dash_count):
                dash_start = z0 + dash_gap * dash_index * 2
                dash_end = min(dash_start + dash_gap, z1)
                markers.moveTo(x, 0, dash_start)
                markers.drawTo(x, 0, dash_end)

        marker_np = self.panorama_overlay_root.attachNewNode(markers.create())
        marker_np.setScale(1 / base.getAspectRatio(), 1, 1)
        marker_np.setColorScale(0.0, 0.45, 0.65, 1)
        self.auxiliary_hud_nodes.append(marker_np)

    def render_recon_drone(self):
        self.drone_state = "DOCKED"
        self.drone_battery = DRONE_BATTERY_MAX
        self.drone_elapsed = 0
        self.drone_heading = 0
        self.drone_camera_heading = 0
        self.drone_camera_pitch = -10
        self.drone_waypoint = None
        self.drone_target_id = None
        self.drone_sweep_index = 0

        drone_lines = procedural_recon_drone()
        drone_lines.setThickness(WORLD_LINE_THICKNESS)
        self.recon_drone_np = render.attachNewNode(drone_lines.create())
        self.recon_drone_np.setColorScale(DRONE_CYAN)
        self.recon_drone_np.setScale(1.2)
        self.recon_drone_np.hide(DRONE_CAMERA_MASK)
        self.recon_drone_np.setPos(render, self.get_recon_drone_dock_pos())
        self.recon_drone_np.show()
        self.recon_drone_np.hide(DRONE_CAMERA_MASK)

        home_lines = procedural_home_tank_marker()
        home_lines.setThickness(WORLD_LINE_THICKNESS)
        self.drone_home_marker_np = render.attachNewNode(home_lines.create())
        self.drone_home_marker_np.setColorScale(DRONE_BLUE)
        self.drone_home_marker_np.setScale(1.4)
        self.drone_home_marker_np.hide(MAIN_CAMERA_MASK | AUX_CAMERA_MASK)
        self.drone_home_marker_np.show(DRONE_CAMERA_MASK)

        slot_left, slot_right, slot_bottom, slot_top = DRONE_VIEW_SLOT
        self.drone_display_region = base.win.makeDisplayRegion(slot_left, slot_right, slot_bottom, slot_top)
        self.drone_display_region.setSort(12)
        self.drone_display_region.setClearColorActive(True)
        self.drone_display_region.setClearColor(DRONE_DIM_BLUE)

        lens = PerspectiveLens()
        lens.setFov(DRONE_CAMERA_FOV)
        lens.setAspectRatio((slot_right - slot_left) * base.getAspectRatio() / (slot_top - slot_bottom))
        drone_camera_node = Camera("ReconDroneCamera")
        drone_camera_node.setLens(lens)
        drone_camera_node.setCameraMask(DRONE_CAMERA_MASK)
        self.drone_camera_np = render.attachNewNode(drone_camera_node)
        self.drone_display_region.setCamera(self.drone_camera_np)

        self.drone_frame_np = render2d.attachNewNode("ReconDroneViewFrame")
        self.update_drone_view_overlay()

        self.droneTextObject = OnscreenText(text="", pos=(0, 0),
                                            align=TextNode.ALeft, scale=(0.027, 0.042),
                                            fg=(0.25, 0.65, 1.0, 1), mayChange=True)
        self.droneTextObject.reparentTo(render2d)
        self.droneTitleObject = OnscreenText(text="DRONE FEED", pos=(0, 0),
                                             align=TextNode.ACenter, scale=(0.034, 0.052),
                                             fg=(0.35, 0.95, 1.0, 1), mayChange=True)
        self.droneTitleObject.reparentTo(render2d)
        self.update_drone_view_overlay()
        self.update_drone_status_hud()
        self.update_drone_home_marker()

    def get_drone_view_bounds(self):
        slot_left, slot_right, slot_bottom, slot_top = DRONE_VIEW_SLOT
        x0 = slot_left * 2 - 1
        x1 = slot_right * 2 - 1
        z0 = slot_bottom * 2 - 1
        z1 = slot_top * 2 - 1
        return x0, x1, z0, z1

    def update_drone_view_overlay(self):
        if not hasattr(self, "drone_frame_np"):
            return

        x0, x1, z0, z1 = self.get_drone_view_bounds()
        self.drone_frame_np.node().removeAllChildren()
        frame = LineSegs("ReconDroneViewFrame")
        frame.setThickness(2)
        frame.moveTo(x0, 0, z0)
        frame.drawTo(x1, 0, z0)
        frame.drawTo(x1, 0, z1)
        frame.drawTo(x0, 0, z1)
        frame.drawTo(x0, 0, z0)
        self.drone_frame_np.attachNewNode(frame.create())
        self.drone_frame_np.setColorScale(DRONE_BLUE)

        if hasattr(self, "droneTextObject"):
            self.droneTextObject.setPos(x0 + 0.11, z1 - 0.085)

        if hasattr(self, "droneTitleObject"):
            self.droneTitleObject.setPos((x0 + x1) * 0.5, z1 + 0.065)

        if hasattr(self, "drone_camera_np"):
            slot_left, slot_right, slot_bottom, slot_top = DRONE_VIEW_SLOT
            lens = self.drone_camera_np.node().getLens()
            lens.setAspectRatio((slot_right - slot_left) * base.getAspectRatio() / (slot_top - slot_bottom))

    def handle_window_event(self, window):
        if window != base.win:
            return

        if hasattr(window, "isClosed") and window.isClosed():
            self.userExit()
            return

        self.audio_has_focus = self.window_has_audio_focus()
        self.apply_audio_focus_volume()
        self.update_drone_view_overlay()
        self.update_environment_preview_overlay()

    def stop_all_game_sounds(self):
        for sound in (
            self.ambient_snd,
            self.mainShot_snd,
            self.enemyShot_snd,
            self.enemyTankExplosion_snd,
            self.playerHit_snd,
            self.gameOver_snd,
            self.investigation_snd,
        ):
            sound.stop()

    def userExit(self):
        self.stop_all_game_sounds()
        if self.network_bridge is not None:
            self.network_bridge.close()
            self.network_bridge = None
        ShowBase.userExit(self)

    def hide_bloom_from_auxiliary_views(self):
        camera_mask = AUX_CAMERA_MASK | DRONE_CAMERA_MASK
        for view in self.auxiliary_cameras:
            view["camera"].node().setCameraMask(AUX_CAMERA_MASK)

        for node in self.bloom_nodes():
            node.hide(camera_mask)

    def updateAuxiliaryViewsTask(self, task):
        if self.is_network_server_authority():
            return Task.cont

        if self.is_network_client_low_render():
            return Task.cont

        pos = self.camera.getPos(render)
        hpr = self.camera.getHpr(render)
        for view in self.auxiliary_cameras:
            view["camera"].setPos(render, pos)
            view["camera"].setHpr(render, hpr[0] + view["heading"], 0, 0)

        return Task.cont

    def update_drone_status_hud(self):
        if hasattr(self, "droneTextObject"):
            if self.investigation_mode and self.investigation_drone_active:
                self.droneTextObject.text = "DRONE GHOST\nBAT ---%\nKILL SCENE"
                return

            target_text = "TGT {}".format(self.drone_target_id) if self.drone_target_id else "HOME TANK"
            self.droneTextObject.text = "DRONE {}\nBAT {:03.0f}%\n{}".format(
                self.drone_state,
                self.drone_battery,
                target_text
            )

    def update_drone_home_marker(self):
        if not hasattr(self, "drone_home_marker_np"):
            return

        self.drone_home_marker_np.setPos(render, self.camera.getPos(render))
        self.drone_home_marker_np.setHpr(render, self.camera.getHpr(render))

    def get_recon_drone_dock_pos(self):
        dock_offset = render.getRelativeVector(
            self.camera,
            (-DRONE_DOCK_LEFT_OFFSET, -DRONE_DOCK_REAR_OFFSET, 0)
        )
        dock_pos = Point3(self.camera.getPos(render) + dock_offset)
        dock_pos[2] = DRONE_DOCK_ALTITUDE
        return dock_pos

    def hide_recon_drone_from_fpv(self):
        if hasattr(self, "recon_drone_np"):
            self.recon_drone_np.hide(DRONE_CAMERA_MASK)

    def approach_angle(self, current, target, max_step):
        error = (target - current + 180) % 360 - 180
        return current + max(-max_step, min(max_step, error))

    def approach_value(self, current, target, max_step):
        return current + max(-max_step, min(max_step, target - current))

    def choose_recon_drone_survey_waypoint(self):
        home_pos = self.camera.getPos(render)
        heading = math.radians(self.camera.getH(render) + 28 * math.sin(self.drone_elapsed * 0.32))
        distance = 75 + 18 * math.sin(self.drone_elapsed * 0.41)
        self.drone_waypoint = Point3(
            home_pos[0] + math.sin(heading) * distance,
            home_pos[1] + math.cos(heading) * distance,
            DRONE_SURVEY_ALTITUDE
        )

    def get_recon_drone_target_pos(self):
        if self.drone_target_id and not tanks_dict[self.drone_target_id]["tank"].isHidden():
            target_pos = Point3(tanks_dict[self.drone_target_id]["tank"].getPos(render))
            target_pos[2] = 1.5
            return target_pos
        return None

    def get_battle_scene_center(self):
        points = [Point3(self.camera.getPos(render))]
        for t in tanks_list:
            if not tanks_dict[t]["tank"].isHidden():
                points.append(Point3(tanks_dict[t]["tank"].getPos(render)))
        for obstacle in self.active_obstacles:
            points.append(Point3(obstacle["pos"]))

        center = Point3(0, 0, DRONE_CAMERA_SCENE_HEIGHT)
        for point in points:
            center[0] += point[0]
            center[1] += point[1]
        center[0] /= len(points)
        center[1] /= len(points)
        return center

    def get_recon_drone_camera_target(self, drone_pos):
        scene_center = self.get_battle_scene_center()
        target_pos = self.get_recon_drone_target_pos()
        if self.drone_state != "OUTBOUND" or target_pos is None:
            return scene_center

        dx = target_pos[0] - drone_pos[0]
        dy = target_pos[1] - drone_pos[1]
        distance = math.sqrt(dx ** 2 + dy ** 2)
        range_focus = max(0, min(1, (DRONE_CAMERA_TARGET_FOCUS_RANGE - distance) / DRONE_CAMERA_TARGET_FOCUS_RANGE))
        sweep_focus = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(self.drone_elapsed * 0.9))
        focus = min(DRONE_CAMERA_MAX_TARGET_FOCUS, range_focus * sweep_focus)
        return Point3(
            scene_center[0] * (1 - focus) + target_pos[0] * focus,
            scene_center[1] * (1 - focus) + target_pos[1] * focus,
            scene_center[2] * (1 - focus) + target_pos[2] * focus
        )

    def choose_recon_drone_target(self, drone_pos):
        live_targets = [
            t for t in sorted(tanks_list)
            if not tanks_dict[t]["tank"].isHidden()
        ]
        if not live_targets:
            self.drone_target_id = None
            return None

        self.drone_target_id = min(
            live_targets,
            key=lambda t: (tanks_dict[t]["tank"].getPos(render) - drone_pos).length()
        )
        return self.get_recon_drone_target_pos()

    def choose_recon_drone_waypoint(self):
        drone_pos = self.recon_drone_np.getPos(render) if hasattr(self, "recon_drone_np") else self.camera.getPos(render)
        target_pos = self.get_recon_drone_target_pos() or self.choose_recon_drone_target(drone_pos)

        if target_pos:
            sweep_angle = math.radians(self.drone_sweep_index * 58 + int(self.drone_target_id) * 80)
            sweep_radius = DRONE_TARGET_SWEEP_RADIUS + DRONE_TARGET_SWEEP_VARIATION * math.sin(self.drone_sweep_index * 1.7)
            altitude = DRONE_LOW_ALTITUDE + (
                DRONE_HIGH_ALTITUDE - DRONE_LOW_ALTITUDE
            ) * (0.5 + 0.5 * math.sin(self.drone_sweep_index * 1.1))
            self.drone_waypoint = Point3(
                target_pos[0] + math.sin(sweep_angle) * sweep_radius,
                target_pos[1] + math.cos(sweep_angle) * sweep_radius,
                altitude
            )
            self.drone_sweep_index += 1
            return

        home_pos = self.camera.getPos(render)
        angle = math.radians(self.camera.getH(render) + 55 * math.sin(self.drone_elapsed * 0.7))
        distance = DRONE_WAYPOINT_MIN_RANGE + (
            DRONE_WAYPOINT_MAX_RANGE - DRONE_WAYPOINT_MIN_RANGE
        ) * (0.5 + 0.5 * math.sin(self.drone_elapsed * 0.43 + 1.2))
        self.drone_waypoint = Point3(
            home_pos[0] + math.sin(angle) * distance,
            home_pos[1] + math.cos(angle) * distance,
            DRONE_ALTITUDE
        )

    def toggle_recon_drone(self):
        if self.waiting_to_start:
            return

        if self.investigation_mode:
            self.toggle_investigation_drone()
            return

        if self.drone_state in {"OUTBOUND", "RETURNING"}:
            self.drone_state = "RETURNING"
            self.update_drone_status_hud()
            return

        if self.drone_battery < DRONE_DEPLOY_MIN_BATTERY:
            self.drone_state = "CHARGING"
            self.update_drone_status_hud()
            return

        self.drone_state = "SURVEY"
        self.drone_elapsed = 0
        self.drone_heading = self.camera.getH(render)
        self.drone_camera_heading = self.drone_heading
        self.drone_camera_pitch = -35
        self.drone_target_id = None
        self.drone_sweep_index = 0
        launch_pos = self.get_recon_drone_dock_pos()
        launch_pos[2] = DRONE_ALTITUDE
        self.recon_drone_np.setPos(render, launch_pos)
        self.recon_drone_np.setHpr(render, self.drone_heading, -5, 0)
        self.choose_recon_drone_survey_waypoint()
        self.recon_drone_np.show()
        self.recon_drone_np.hide(DRONE_CAMERA_MASK)
        self.update_drone_status_hud()

    def updateReconDroneTask(self, task):
        if self.is_network_server_authority():
            self.set_recon_drone_world_visible(False)
            return Task.cont

        if self.is_network_client_low_render():
            self.set_recon_drone_world_visible(False)
            return Task.cont

        dt = min(ClockObject.getGlobalClock().getDt(), 0.05)
        if self.waiting_to_start:
            return Task.cont

        if self.investigation_mode:
            self.update_investigation_drone(dt)
            self.update_drone_status_hud()
            return Task.cont

        self.update_drone_home_marker()

        home_pos = Point3(self.camera.getPos(render))
        home_pos[2] = DRONE_ALTITUDE

        if self.drone_state in {"DOCKED", "CHARGING"}:
            scan_time = ClockObject.getGlobalClock().getFrameTime()
            dock_pos = self.get_recon_drone_dock_pos()
            idle_heading = self.camera.getH(render) + math.sin(scan_time * DRONE_IDLE_SCAN_SPEED) * DRONE_IDLE_SCAN_DEGREES
            self.drone_battery = min(DRONE_BATTERY_MAX, self.drone_battery + DRONE_RECHARGE_PER_SECOND * dt)
            if self.drone_battery >= DRONE_BATTERY_MAX:
                self.drone_state = "DOCKED"
            else:
                self.drone_state = "CHARGING"
            self.recon_drone_np.setPos(render, dock_pos)
            self.recon_drone_np.setHpr(render, idle_heading, -3, 0)
            self.recon_drone_np.show()
            self.drone_camera_np.setPos(render, dock_pos)
            self.drone_camera_heading = idle_heading
            self.drone_camera_pitch = -6
            self.drone_camera_np.setHpr(render, self.drone_camera_heading, self.drone_camera_pitch, 0)
            self.drone_target_id = None
            self.hide_recon_drone_from_fpv()
            self.update_drone_status_hud()
            return Task.cont

        self.drone_battery = max(0, self.drone_battery - DRONE_DRAIN_PER_SECOND * dt)
        drone_pos = Point3(self.recon_drone_np.getPos(render))
        home_distance = math.sqrt((home_pos[0] - drone_pos[0]) ** 2 + (home_pos[1] - drone_pos[1]) ** 2)

        if self.drone_state in {"SURVEY", "OUTBOUND"}:
            self.drone_elapsed += dt
            distance_from_home = math.sqrt((drone_pos[0] - home_pos[0]) ** 2 + (drone_pos[1] - home_pos[1]) ** 2)
            if self.drone_battery <= DRONE_RETURN_BATTERY or distance_from_home >= DRONE_MAX_RANGE:
                self.drone_state = "RETURNING"
            else:
                if self.drone_state == "SURVEY":
                    if self.drone_elapsed >= DRONE_SURVEY_SECONDS:
                        self.drone_state = "OUTBOUND"
                        self.drone_waypoint = None
                        self.choose_recon_drone_waypoint()
                    elif self.drone_waypoint is None:
                        self.choose_recon_drone_survey_waypoint()
                elif self.drone_waypoint is None:
                    self.choose_recon_drone_waypoint()

                waypoint_dx = self.drone_waypoint[0] - drone_pos[0]
                waypoint_dy = self.drone_waypoint[1] - drone_pos[1]
                waypoint_dz = self.drone_waypoint[2] - drone_pos[2]
                waypoint_distance = math.sqrt(waypoint_dx ** 2 + waypoint_dy ** 2)
                if waypoint_distance <= DRONE_WAYPOINT_REACHED:
                    if self.drone_state == "SURVEY":
                        self.choose_recon_drone_survey_waypoint()
                    else:
                        self.choose_recon_drone_waypoint()
                    waypoint_dx = self.drone_waypoint[0] - drone_pos[0]
                    waypoint_dy = self.drone_waypoint[1] - drone_pos[1]
                    waypoint_dz = self.drone_waypoint[2] - drone_pos[2]

                target_heading = math.degrees(math.atan2(waypoint_dx, waypoint_dy))
                heading_error = (target_heading - self.drone_heading + 180) % 360 - 180
                self.drone_heading += max(-DRONE_TURN_RATE * dt, min(DRONE_TURN_RATE * dt, heading_error))
                heading_radians = math.radians(self.drone_heading)
                drone_pos[0] += math.sin(heading_radians) * DRONE_SPEED * dt
                drone_pos[1] += math.cos(heading_radians) * DRONE_SPEED * dt
                drone_pos[2] += max(-4.5 * dt, min(4.5 * dt, waypoint_dz))

        if self.drone_state == "RETURNING":
            self.drone_waypoint = None
            self.drone_target_id = None
            dx = home_pos[0] - drone_pos[0]
            dy = home_pos[1] - drone_pos[1]
            distance = max(0.001, math.sqrt(dx ** 2 + dy ** 2))
            self.drone_heading = self.approach_angle(
                self.drone_heading,
                math.degrees(math.atan2(dx, dy)),
                DRONE_TURN_RATE * dt
            )
            travel = min(distance, DRONE_RETURN_SPEED * dt)
            drone_pos[0] += dx / distance * travel
            drone_pos[1] += dy / distance * travel
            drone_pos[2] = self.approach_value(drone_pos[2], DRONE_ALTITUDE, 5 * dt)
            if distance <= 4:
                self.drone_state = "CHARGING"

        self.recon_drone_np.setPos(render, drone_pos)
        self.recon_drone_np.setHpr(render, self.drone_heading, -5, 0)
        self.hide_recon_drone_from_fpv()
        camera_target = self.get_recon_drone_camera_target(drone_pos)
        camera_dx = camera_target[0] - drone_pos[0]
        camera_dy = camera_target[1] - drone_pos[1]
        camera_dz = camera_target[2] - drone_pos[2]
        camera_distance = max(0.001, math.sqrt(camera_dx ** 2 + camera_dy ** 2))
        desired_camera_heading = math.degrees(math.atan2(camera_dx, camera_dy)) + math.sin(self.drone_elapsed * 0.8) * 3
        desired_camera_pitch = math.degrees(math.atan2(camera_dz, camera_distance))
        self.drone_camera_heading = self.approach_angle(
            self.drone_camera_heading,
            desired_camera_heading,
            DRONE_CAMERA_TURN_RATE * dt
        )
        self.drone_camera_pitch = self.approach_value(
            self.drone_camera_pitch,
            desired_camera_pitch,
            DRONE_CAMERA_PITCH_RATE * dt
        )
        camera_heading_radians = math.radians(self.drone_camera_heading)
        camera_pos = Point3(
            drone_pos[0] + math.sin(camera_heading_radians) * DRONE_CAMERA_FORWARD_OFFSET,
            drone_pos[1] + math.cos(camera_heading_radians) * DRONE_CAMERA_FORWARD_OFFSET,
            drone_pos[2] + DRONE_CAMERA_VERTICAL_OFFSET
        )
        self.drone_camera_np.setPos(render, camera_pos)
        self.drone_camera_np.setHpr(render, self.drone_camera_heading, self.drone_camera_pitch, 0)
        self.update_drone_status_hud()
        return Task.cont

    def explosion_cleanup(self, t):
        if t in tanks_list:
            tanks_dict[t]["frags"].hide()
            if self.tank_lives(t) is not None and self.tank_lives(t) <= 0:
                tanks_dict[t]["move"] = False
                tanks_dict[t]["tank"].hide()
                self.set_tank_alive(t, False)
                self.set_tank_reconstituting(t, False)
                self.update_lives_hud()
                return

            pos = tanks_dict[t]["Locator"].getPos()
            self.set_tank_on_terrain(t, Point3(-pos[1], -pos[0], 0), tanks_dict[t]["tank"].getH(render))
            tanks_dict[t]["move"] = True
            tanks_dict[t].pop("last_pos", None)
            tanks_dict[t]["tank"].show()
            self.set_tank_alive(t, True)
            self.set_tank_reconstituting(t, False)
            self.set_tank_hit_cooldown(t, PLAYER_HIT_COOLDOWN)
            controller = getattr(self, "ai_tank_controllers", {}).get(t)
            respawn_delay = getattr(controller, "respawn_attack_delay", TANK_RESPAWN_ATTACK_COOLDOWN)
            self.set_tank_attack_cooldown(t, respawn_delay)

    def set_tank_attack_cooldown(self, t, seconds):
        ready_time = ClockObject.getGlobalClock().getFrameTime() + seconds
        tanks_dict[t]["attack_ready_time"] = ready_time
        controller = getattr(self, "ai_tank_controllers", {}).get(t)
        if controller is not None:
            if hasattr(controller, "next_fire_time"):
                controller.next_fire_time = max(controller.next_fire_time, ready_time)
            if hasattr(controller, "aim_acquired_since"):
                controller.aim_acquired_since = None

    def tank_attack_ready(self, t, task_time):
        return task_time >= tanks_dict[t].get("attack_ready_time", 0)

    def reset_ai_tank_controller_for_match(self, t):
        controller = getattr(self, "ai_tank_controllers", {}).get(t)
        if controller is not None and hasattr(controller, "reset_for_match"):
            controller.reset_for_match(ClockObject.getGlobalClock().getFrameTime())
            tanks_dict[t]["attack_ready_time"] = getattr(controller, "next_fire_time", 0)

    def set_tank_on_terrain(self, t, world_pos, heading=None):
        if heading is None:
            heading = tanks_dict[t].get("init_heading", 0)
        surface_world = self.terrain_position(world_pos)
        tanks_dict[t]["Locator"].setPos(render, surface_world)
        tanks_dict[t]["tank"].setPos(0, 0, 0)
        tanks_dict[t]["tank"].setHpr(render, *self.terrain_surface_hpr(surface_world[0], surface_world[1], heading, "x"))
        tanks_dict[t]["last_pos"] = Point3(surface_world)

    def renderTanks(self, tanks_group):
        # tank as lines
        with open('models/tankDesignB.json', "r") as f:
            data = json.load(f)
        lines = create_lineSegs_object(data, 0)
        lines.setThickness(WORLD_LINE_THICKNESS)
        node = lines.create()
        self.tank = NodePath(node)

        # tank fragments
        with open('models/tank_frag_all.json', "r") as f:
            data = json.load(f)
        self.tank_fragment_data = data

        for t in tanks_list:
            tanks_dict[t]["Locator"] = tanks_group.attachNewNode("Tank{}-Locator".format(t))
            tanks_dict[t]["tank"] = tanks_dict[t]["Locator"].attachNewNode("Tank{}-Placeholder".format(t))
            tanks_dict[t]["attack_ready_time"] = 0
            self.set_tank_on_terrain(t, tanks_dict[t]["init_pos"])
            tanks_dict[t]["tank"].setColorScale(tanks_dict[t]["color_scale"])
            self.tank.instanceTo(tanks_dict[t]["tank"])
            # frags
            tanks_dict[t]["frags"] = tanks_dict[t]["tank"].attachNewNode("Tank{}-Frags".format(t))
            for frag in data:
                # print(frag["name"])
                lines = create_lineSegs_object(frag["model"], 0, frag["name"])
                lines.setThickness(WORLD_LINE_THICKNESS)
                node = lines.create()
                np = tanks_dict[t]["frags"].attachNewNode(node)
                i = ProjectileInterval(np, startPos=np.getPos(), endZ=0,
                                       startVel=Point3(5 * (1 - random()), 5 * (1 - random()), 30),
                                       name="explosion{}".format(t))
                tanks_dict[t]["explosion"].append(i)
                i = LerpHprInterval(np, 2, hpr=(180*(1 - random()), 0, 0))
                tanks_dict[t]["explosion"].append(i)

            tanks_dict[t]["frags"].hide()
            tanks_dict[t]["explosion"].setDoneEvent('explosion{}-done'.format(t))

        # print(tanks_group.find("**/Tank1-Frags"))

    def resolve_obstacle_position(self, pos, body_radius):
        resolved = Point3(pos)
        for obstacle in self.active_obstacles:
            obstacle_pos = obstacle["pos"]
            min_dist = obstacle["radius"] + body_radius
            dx = resolved[0] - obstacle_pos[0]
            dy = resolved[1] - obstacle_pos[1]
            dist = math.sqrt(dx ** 2 + dy ** 2)

            if dist >= min_dist:
                continue

            if dist < 0.001:
                dx = 1
                dy = 0
                dist = 1

            resolved[0] = obstacle_pos[0] + dx / dist * min_dist
            resolved[1] = obstacle_pos[1] + dy / dist * min_dist

        return resolved

    def is_obstacle_blocked(self, pos, body_radius):
        resolved = self.resolve_obstacle_position(pos, body_radius)
        return math.sqrt((resolved[0] - pos[0]) ** 2 + (resolved[1] - pos[1]) ** 2) > 0.001

    def dot3(self, a, b):
        return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]

    def cross3(self, a, b):
        return Point3(
            a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0]
        )

    def normalize3(self, vector):
        length = math.sqrt(self.dot3(vector, vector))
        if length < 0.001:
            return Point3(0, 1, 0)
        return Point3(vector[0] / length, vector[1] / length, vector[2] / length)

    def obstacle_shot_triangles(self, obstacle):
        pos = obstacle["pos"]
        scale = obstacle["scale"]
        half_x = scale[0] * 0.5
        half_y = scale[1] * 0.5
        height = scale[2]

        def world(point):
            return self.obstacle_world_point(obstacle, Point3(point[0], point[1], point[2]))

        triangles = []
        if obstacle["kind"] == "block":
            points = [
                (-half_x, -half_y, 0), (half_x, -half_y, 0), (half_x, half_y, 0), (-half_x, half_y, 0),
                (-half_x, -half_y, height), (half_x, -half_y, height), (half_x, half_y, height), (-half_x, half_y, height),
            ]
            faces = ((0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1),
                     (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0))
            for a, b, c, d in faces:
                triangles.append((world(points[a]), world(points[b]), world(points[c])))
                triangles.append((world(points[a]), world(points[c]), world(points[d])))
        elif obstacle["kind"] == "pyramid":
            base = [(-half_x, -half_y, 0), (half_x, -half_y, 0), (half_x, half_y, 0), (-half_x, half_y, 0)]
            apex = (0, 0, height)
            triangles.append((world(base[0]), world(base[1]), world(base[2])))
            triangles.append((world(base[0]), world(base[2]), world(base[3])))
            for idx, point in enumerate(base):
                triangles.append((world(point), world(base[(idx + 1) % len(base)]), world(apex)))
        elif obstacle["kind"] == "cone":
            segments = 24
            center = (0, 0, 0)
            apex = (0, 0, height)
            points = []
            for i in range(segments):
                theta = 2 * pi * i / segments
                points.append((half_x * cos(theta), half_y * sin(theta), 0))
            for idx, point in enumerate(points):
                next_point = points[(idx + 1) % segments]
                triangles.append((world(center), world(next_point), world(point)))
                triangles.append((world(point), world(next_point), world(apex)))

        return triangles

    def segment_triangle_hit(self, start, end, triangle):
        epsilon = 0.00001
        direction = end - start
        edge1 = triangle[1] - triangle[0]
        edge2 = triangle[2] - triangle[0]
        h = self.cross3(direction, edge2)
        determinant = self.dot3(edge1, h)
        if abs(determinant) < epsilon:
            return None

        inverse_det = 1.0 / determinant
        s = start - triangle[0]
        u = inverse_det * self.dot3(s, h)
        if u < 0 or u > 1:
            return None

        q = self.cross3(s, edge1)
        v = inverse_det * self.dot3(direction, q)
        if v < 0 or u + v > 1:
            return None

        t = inverse_det * self.dot3(edge2, q)
        if t <= epsilon or t >= 1:
            return None

        normal = self.normalize3(self.cross3(edge1, edge2))
        incoming = self.normalize3(direction)
        if self.dot3(incoming, normal) > 0:
            normal = Point3(-normal[0], -normal[1], -normal[2])
        return t, Point3(start + direction * t), normal

    def find_shot_obstacle_hit(self, start, end):
        closest_hit = None
        for obstacle in self.active_obstacles:
            for triangle in self.obstacle_shot_triangles(obstacle):
                hit = self.segment_triangle_hit(start, end, triangle)
                if not hit:
                    continue
                if closest_hit is None or hit[0] < closest_hit["t"]:
                    closest_hit = {
                        "t": hit[0],
                        "point": hit[1],
                        "normal": hit[2],
                        "obstacle": obstacle["name"]
                    }
        return closest_hit

    def segment_sphere_hit(self, start, end, center, radius):
        direction = end - start
        segment_len_sq = self.dot3(direction, direction)
        if segment_len_sq < 0.0001:
            return None

        to_center = center - start
        t = max(0, min(1, self.dot3(to_center, direction) / segment_len_sq))
        closest = start + direction * t
        miss = closest - center
        if self.dot3(miss, miss) > radius * radius:
            return None
        return t, Point3(closest)

    def find_player_shot_tank_hit(self, start, end, minimum_t=0.0):
        closest_hit = None
        for t in tanks_list:
            tank_np = tanks_dict[t]["tank"]
            if not self.tank_is_hittable(t):
                continue

            center = render.getRelativePoint(tank_np, Point3(0, 0, 0.9))
            radius = tanks_dict[t]["coll_rad"] + 1.0
            hit = self.segment_sphere_hit(start, end, center, radius)
            if not hit:
                continue

            hit_t, hit_point = hit
            if hit_t < minimum_t:
                continue
            if closest_hit is None or hit_t < closest_hit["t"]:
                closest_hit = {
                    "t": hit_t,
                    "point": hit_point,
                    "tank_id": t
                }
        return closest_hit

    def find_incoming_player_tank_hit(self, start, end, minimum_t=0.0):
        if not self.player_tank_is_hittable():
            return None

        center = self.player_tank_body_target()
        hit = self.segment_sphere_hit(start, end, center, PLAYER_NETWORK_HIT_RADIUS)
        if not hit:
            return None

        hit_t, hit_point = hit
        if hit_t < minimum_t:
            return None

        return {
            "t": hit_t,
            "point": hit_point,
            "tank_id": "0"
        }

    def find_shot_ground_hit(self, start, end):
        start = Point3(start)
        end = Point3(end)
        direction = end - start
        previous_t = 0.0
        previous_height = start[2] - self.terrain_z(start[0], start[1])
        if previous_height <= 0:
            return {
                "t": 0.0,
                "point": Point3(start[0], start[1], self.terrain_z(start[0], start[1])),
                "kind": "ground"
            }

        samples = 80
        for sample in range(1, samples + 1):
            t = sample / samples
            point = start + direction * t
            height = point[2] - self.terrain_z(point[0], point[1])
            if height <= 0:
                low_t = previous_t
                high_t = t
                for _ in range(10):
                    mid_t = (low_t + high_t) * 0.5
                    mid_point = start + direction * mid_t
                    mid_height = mid_point[2] - self.terrain_z(mid_point[0], mid_point[1])
                    if mid_height <= 0:
                        high_t = mid_t
                    else:
                        low_t = mid_t
                impact_t = high_t
                impact = start + direction * impact_t
                return {
                    "t": impact_t,
                    "point": Point3(impact[0], impact[1], self.terrain_z(impact[0], impact[1])),
                    "kind": "ground"
                }
            previous_t = t
            previous_height = height

        return None

    def play_shot_ground_burst(self, impact):
        if self.investigation_mode:
            return

        burst_lines = LineSegs("shot-ground-burst")
        burst_lines.setThickness(2)
        burst_radius = SHOT_GROUND_BURST_RADIUS
        rays = (
            (1, 0, 0.22), (-1, 0, 0.22), (0, 1, 0.22), (0, -1, 0.22),
            (0.7, 0.7, 0.28), (-0.7, 0.7, 0.28), (0.7, -0.7, 0.28), (-0.7, -0.7, 0.28),
            (0.35, 0, 0.8), (-0.35, 0, 0.8), (0, 0.35, 0.8), (0, -0.35, 0.8)
        )
        for ray in rays:
            end = self.normalize3(Point3(ray[0], ray[1], ray[2])) * burst_radius
            burst_lines.moveTo(0, 0, 0.08)
            burst_lines.drawTo(end[0], end[1], end[2])

        burst_np = render.attachNewNode(burst_lines.create())
        burst_np.setPos(render, Point3(impact))
        burst_np.setTransparency(TransparencyAttrib.MAlpha, 10)
        burst_np.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.MAdd), 10)
        burst_np.setDepthWrite(False, 10)
        burst_np.setColorScale(0.1, 1.0, 0.18, 0.95)
        burst_np.setScale(0.25)
        Sequence(
            Parallel(
                LerpScaleInterval(burst_np, SHOT_GROUND_BURST_SECONDS, 1.0),
                LerpColorScaleInterval(burst_np, SHOT_GROUND_BURST_SECONDS, (0.0, 0.9, 0.1, 0.0))
            ),
            Func(burst_np.removeNode)
        ).start()

    def record_shot_ground_burst(self, impact):
        impact = Point3(impact)
        self.shot_ground_burst_serial += 1
        self.last_shot_ground_burst_event = {
            "serial": self.shot_ground_burst_serial,
            "pos": self.point_to_list(impact)
        }
        self.play_shot_ground_burst(impact)

    def play_shot_ground_burst_event(self, event):
        if not event:
            return
        pos = Point3(*event.get("pos", [0, 0, 0]))
        Sequence(
            Wait(NETWORK_EFFECT_DELAY),
            Func(self.play_shot_ground_burst, pos)
        ).start()

    def register_player_tank_hit(self, tank_id, shooter_id="0", shot_start=None, shot_end=None):
        if tank_id not in tanks_list:
            return
        if not self.tank_is_hittable(tank_id):
            return

        self.record_tank_hit_event(tank_id, shooter_id, shot_start, shot_end, play_local=False)
        self.set_tank_alive(tank_id, False)
        self.set_tank_reconstituting(tank_id, True)
        self.set_tank_hit_cooldown(tank_id, PLAYER_HIT_COOLDOWN)
        self.set_tank_lives(tank_id, max(0, self.tank_lives(tank_id) - 1))
        self.update_lives_hud()
        if self.tank_lives(tank_id) <= 0 and self.is_network_server_authority():
            self.record_server_event("death tank {}".format(tank_id))
        tanks_dict[tank_id]["move"] = False
        tanks_dict[tank_id]["tank"].hide()
        tanks_dict[tank_id]["frags"].showThrough()
        tanks_dict[tank_id]["explosion"].start()
        self.enemyTankExplosion_snd.play()

    def has_tank_line_of_sight(self, tank_pos, target_pos):
        start = Point3(tank_pos[0], tank_pos[1], tank_pos[2] + 1.5)
        end = Point3(target_pos[0], target_pos[1], target_pos[2])
        return self.find_shot_obstacle_hit(start, end) is None

    def tank_line_of_sight_clear_fraction(self, tank_pos, target_pos):
        start = Point3(tank_pos[0], tank_pos[1], tank_pos[2] + 1.5)
        end = Point3(target_pos[0], target_pos[1], target_pos[2])
        hit = self.find_shot_obstacle_hit(start, end)
        if not hit:
            return 1.0
        return hit["t"]

    def tank_barrel_tilt_to_target(self, tank_id, target):
        local_target = self.tank_aim_mount_node(tank_id).getRelativePoint(render, target)
        runtime = self.tank_runtime_state(tank_id)
        forward_distance = local_target[1] if runtime.get("aim_forward_axis", "x") == "y" else local_target[0]
        forward_distance = max(0.001, forward_distance)
        height_delta = local_target[2] - runtime.get("aim_height", 0.0)
        return max(
            PLAYER_BARREL_TILT_MIN,
            min(PLAYER_BARREL_TILT_MAX, math.degrees(math.atan2(height_delta, forward_distance)))
        )

    def tank_barrel_tilt_error(self, tank_id, target):
        return self.tank_barrel_tilt_to_target(tank_id, target) - self.tank_barrel_tilt(tank_id)

    def build_tank_observation(self, tank_id):
        tank_np = self.tank_body_node(tank_id)
        tank_pos = Point3(tank_np.getPos(render))
        target_tank_id = "0"
        if tank_id == "0":
            target_tank_id = sorted(tanks_list, key=lambda value: int(value))[0] if tanks_list else "0"
        player_pos = self.tank_body_pos(target_tank_id)
        player_body_pos = self.tank_body_target(target_tank_id)
        player_dx = player_pos[0] - tank_pos[0]
        player_dy = player_pos[1] - tank_pos[1]
        distance = math.sqrt(player_dx ** 2 + player_dy ** 2)
        heading_to_player = math.degrees(math.atan2(player_dy, player_dx))
        tank_heading = tank_np.getH(render)
        aim_error = signed_angular_delta_degrees(heading_to_player, tank_heading)
        barrel_tilt_target = self.tank_barrel_tilt_to_target(tank_id, player_body_pos)
        barrel_tilt_error = barrel_tilt_target - self.tank_barrel_tilt(tank_id)
        line_of_sight_clear_fraction = self.tank_line_of_sight_clear_fraction(tank_pos, player_body_pos)
        line_of_sight = line_of_sight_clear_fraction >= 1.0

        return {
            "tank_id": tank_id,
            "tank_pos": tank_pos,
            "tank_heading": tank_heading,
            "player_pos": player_pos,
            "player_body_pos": player_body_pos,
            "player_dx": player_dx,
            "player_dy": player_dy,
            "distance_to_player": distance,
            "heading_to_player": heading_to_player,
            "aim_error": aim_error,
            "barrel_tilt_target": barrel_tilt_target,
            "barrel_tilt_error": barrel_tilt_error,
            "line_of_sight": line_of_sight,
            "line_of_sight_clear_fraction": line_of_sight_clear_fraction,
            "risky_line_of_sight": line_of_sight_clear_fraction >= TACTICAL_AI_RISKY_SHOT_CLEAR_FRACTION,
            "is_shooting": self.tank_is_shooting(tank_id),
        }

    def create_shot_interval(self, round_np, start, direction, distance, duration, done_event, collision_start=None, shooter_id=None):
        shot_dir = self.normalize3(direction)
        if collision_start is None:
            collision_start = start
        if shooter_id is None:
            shooter_id = "0" if done_event == 'shot-done' else done_event[4:5]
        collision_start = Point3(collision_start)
        visible_offset = max(0, self.dot3(start - collision_start, shot_dir))
        collision_distance = visible_offset + distance
        collision_end = Point3(collision_start + shot_dir * collision_distance)
        raw_end = Point3(start + shot_dir * distance)
        hit = self.find_shot_obstacle_hit(collision_start, collision_end)
        ground_hit = self.find_shot_ground_hit(collision_start, collision_end)
        minimum_hit_t = max(0, visible_offset / max(collision_distance, 0.001))
        tank_hit = self.find_player_shot_tank_hit(
            collision_start,
            collision_end,
            minimum_hit_t
        ) if shooter_id == "0" else None
        incoming_player_hit = None
        if shooter_id in tanks_list:
            incoming_player_hit = self.find_incoming_player_tank_hit(
                collision_start,
                collision_end,
                minimum_hit_t
            )

        if tank_hit and (not hit or tank_hit["t"] < hit["t"]) and (not ground_hit or tank_hit["t"] < ground_hit["t"]):
            hit_distance = collision_distance * tank_hit["t"]
            visible_distance_to_impact = max(0, hit_distance - visible_offset)
            impact = tank_hit["point"]
            trajectory_points = [Point3(start), Point3(impact)]
            first_duration = max(0.03, duration * min(1, visible_distance_to_impact / distance))
            interval = Sequence(
                LerpPosInterval(round_np, first_duration, pos=impact),
                Func(self.register_player_tank_hit, tank_hit["tank_id"], shooter_id, start, impact)
            )
            interval.setDoneEvent(done_event)
            return interval, impact, False, trajectory_points

        if (
                incoming_player_hit and
                (not hit or incoming_player_hit["t"] < hit["t"]) and
                (not ground_hit or incoming_player_hit["t"] < ground_hit["t"])):
            hit_distance = collision_distance * incoming_player_hit["t"]
            visible_distance_to_impact = max(0, hit_distance - visible_offset)
            impact = incoming_player_hit["point"]
            trajectory_points = [Point3(start), Point3(impact)]
            first_duration = max(0.03, duration * min(1, visible_distance_to_impact / distance))
            interval = Sequence(
                LerpPosInterval(round_np, first_duration, pos=impact),
                Func(self.register_incoming_player_tank_hit, shooter_id, start, impact, trajectory_points)
            )
            interval.setDoneEvent(done_event)
            return interval, impact, False, trajectory_points

        if ground_hit and (not hit or ground_hit["t"] < hit["t"]):
            hit_distance = collision_distance * ground_hit["t"]
            visible_distance_to_impact = max(0, hit_distance - visible_offset)
            impact = ground_hit["point"]
            trajectory_points = [Point3(start), Point3(impact)]
            first_duration = max(0.03, duration * min(1, visible_distance_to_impact / distance))
            interval = Sequence(
                LerpPosInterval(round_np, first_duration, pos=impact),
                Func(self.record_shot_ground_burst, impact),
                Func(round_np.hide),
                Wait(SHOT_GROUND_BURST_SECONDS)
            )
            interval.setDoneEvent(done_event)
            return interval, impact, False, trajectory_points

        if not hit:
            interval = LerpPosInterval(round_np, duration, pos=raw_end)
            interval.setDoneEvent(done_event)
            return interval, raw_end, False, [Point3(start), Point3(raw_end)]

        impact = hit["point"]
        hit_distance = collision_distance * hit["t"]
        visible_distance_to_impact = hit_distance - visible_offset
        normal = hit["normal"]
        reflected_dir = Point3(
            shot_dir[0] - 2 * self.dot3(shot_dir, normal) * normal[0],
            shot_dir[1] - 2 * self.dot3(shot_dir, normal) * normal[1],
            shot_dir[2] - 2 * self.dot3(shot_dir, normal) * normal[2]
        )
        reflected_dir = self.normalize3(reflected_dir)
        remaining_distance = max(0, collision_distance - hit_distance)
        reflected_start = Point3(impact + reflected_dir * SHOT_DEFLECTION_CLEARANCE)
        reflected_end = Point3(reflected_start + reflected_dir * remaining_distance)
        trajectory_points = [Point3(start), Point3(impact), Point3(reflected_end)]

        if visible_distance_to_impact <= SHOT_DEFLECTION_CLEARANCE:
            round_np.setPos(render, impact)
            interval = LerpPosInterval(round_np, duration, pos=reflected_end)
        else:
            first_duration = max(0.03, duration * min(1, visible_distance_to_impact / distance))
            second_duration = max(0.03, duration - first_duration)
            interval = Sequence(
                LerpPosInterval(round_np, first_duration, pos=impact),
                LerpPosInterval(round_np, second_duration, pos=reflected_end)
            )
        interval.setDoneEvent(done_event)
        return interval, reflected_end, True, trajectory_points

    def normalized_xy(self, vector):
        length = math.sqrt(vector[0] ** 2 + vector[1] ** 2)
        if length < 0.001:
            return Point3(0, 1, 0)
        return Point3(vector[0] / length, vector[1] / length, 0)

    def round_obstacle_hit(self, entry):
        if self.is_network_client_controller():
            return

        from_name = entry.getFromNodePath().node().name
        if from_name == "cTankRound":
            if self.tank_shot_deflected("0"):
                return
            self.reset_shot()
        elif from_name.startswith("ceTankRound"):
            t = from_name[-1]
            if t in tanks_list:
                if self.tank_shot_deflected(t):
                    return
                self.enemy_reset_shot(t)

    def move_investigation_camera(self, dt):
        is_down = base.mouseWatcherNode.is_button_down
        turn_step = camera_dict["turn_ang_vel"] * dt
        move_step = INVESTIGATION_GHOST_SPEED * dt

        if is_down(arrow_right):
            self.camera.setHpr(self.camera, -turn_step, 0, 0)
        if is_down(arrow_left):
            self.camera.setHpr(self.camera, turn_step, 0, 0)
        if is_down(arrow_back):
            step = render.getRelativeVector(self.camera, (0, -move_step, 0))
            self.camera.setPos(render, self.camera.getPos(render) + step)
        if is_down(arrow_forward):
            step = render.getRelativeVector(self.camera, (0, move_step, 0))
            self.camera.setPos(render, self.camera.getPos(render) + step)

    def updateTankControllersTask(self, task):
        dt = min(ClockObject.getGlobalClock().getDt(), 0.05)
        if self.waiting_to_start:
            return Task.cont

        if self.arena_is_hibernating():
            return Task.cont

        if self.investigation_mode:
            self.move_investigation_camera(dt)
            return Task.cont

        if self.is_network_client_controller():
            return Task.cont

        if self.game_over:
            return Task.cont

        self.apply_controller_command("0", dt, task.time)
        for t in tanks_list:
            if self.tank_can_run_controller(t):
                self.apply_controller_command(t, dt, task.time)

        return Task.cont

    def apply_controller_command(self, tank_id, dt, task_time):
        if not self.tank_can_run_controller(tank_id):
            return

        command = self.tank_controllers[tank_id].command(
            self, self.tank_avatars[tank_id], dt, task_time
        )

        if tank_id == "0":
            if command.desired_world_pos is not None:
                self.apply_autonomous_player_tank_command(command, dt)
                if command.fire:
                    self.shoot()
                return
            self.apply_player_tank_command(command, dt)
            return

        if command.desired_world_pos is not None:
            self.apply_autonomous_tank_command(tank_id, command, dt)
        else:
            self.apply_direct_tank_command(tank_id, command, dt)

        remote_controlled = isinstance(self.tank_controllers[tank_id], RemoteTankController)
        if (
                command.fire and
                self.tank_attack_ready(tank_id, task_time) and
                not self.tank_is_shooting(tank_id)):
            if remote_controlled:
                self.fire_remote_tank(tank_id)
            elif not self.enemy_shooting_suspended:
                self.fire_enemy_tank(tank_id)

    def apply_player_tank_command(self, command, dt):
        self.apply_barrel_tilt_command("0", command, dt)

        if command.turn:
            turn_step = camera_dict["turn_ang_vel"] * dt * command.turn
            self.camera.setHpr(self.camera, turn_step, 0, 0)

        if command.throttle:
            move_step = camera_dict["translate_vel"] * dt * command.throttle
            step = render.getRelativeVector(self.camera, (0, move_step, 0))
            next_pos = self.resolve_obstacle_position(
                self.camera.getPos(render) + step,
                self.tank_avatars["0"].collision_radius
            )
            self.camera.setPos(render, self.terrain_position(next_pos, PLAYER_CAMERA_HEIGHT))

        if command.fire:
            self.shoot()

    def tank_barrel_tilt(self, tank_id):
        if tank_id == "0":
            return getattr(self, "player_barrel_tilt", 0.0)
        return tanks_dict[tank_id].get("barrel_tilt", 0.0)

    def set_tank_barrel_tilt(self, tank_id, value):
        value = max(PLAYER_BARREL_TILT_MIN, min(PLAYER_BARREL_TILT_MAX, value))
        if tank_id == "0":
            self.player_barrel_tilt = value
            self.update_barrel_aim_marker()
        else:
            tanks_dict[tank_id]["barrel_tilt"] = value

    def apply_barrel_tilt_command(self, tank_id, command, dt):
        if command.desired_barrel_tilt is not None:
            next_tilt = self.approach_value(
                self.tank_barrel_tilt(tank_id),
                command.desired_barrel_tilt,
                PLAYER_BARREL_TILT_RATE * dt
            )
            self.set_tank_barrel_tilt(tank_id, next_tilt)
            return

        if not command.barrel_tilt:
            return

        tilt_step = PLAYER_BARREL_TILT_RATE * dt * command.barrel_tilt
        self.set_tank_barrel_tilt(tank_id, self.tank_barrel_tilt(tank_id) + tilt_step)

    def player_tank_body_target(self):
        return self.tank_body_target("0")

    def apply_autonomous_player_tank_command(self, command, dt):
        if command.desired_world_pos is None:
            return

        self.apply_barrel_tilt_command("0", command, dt)

        target_world = self.resolve_obstacle_position(
            command.desired_world_pos,
            self.tank_avatars["0"].collision_radius
        )
        current_world = Point3(self.camera.getPos(render))
        to_target = target_world - current_world
        distance = math.sqrt(to_target[0] ** 2 + to_target[1] ** 2)
        max_step = AUTONOMOUS_TANK_MAX_SPEED * dt
        current_heading = self.camera.getH(render)
        runtime = self.tank_runtime_state("0")
        target_heading = command.desired_heading
        if target_heading is not None:
            target_heading = 90 - target_heading
        else:
            target_heading = current_heading

        if distance > 0.001:
            target_heading = math.degrees(math.atan2(to_target[0], to_target[1]))

        heading = self.approach_angle(
            current_heading,
            target_heading,
            ENEMY_TURN_ANG_VEL * dt
        )
        heading_error = abs(signed_angular_delta_degrees(target_heading, heading))
        alignment = max(
            AUTONOMOUS_TANK_TURNING_SPEED_FACTOR,
            math.cos(math.radians(heading_error))
        )
        move_step = min(max_step * alignment, distance) if distance > 0.001 else 0
        heading_radians = math.radians(heading)
        candidate_world = Point3(
            current_world[0] + math.sin(heading_radians) * move_step,
            current_world[1] + math.cos(heading_radians) * move_step,
            current_world[2]
        )
        avoided_world = self.resolve_obstacle_position(
            candidate_world,
            self.tank_avatars["0"].collision_radius
        )
        self.camera.setPos(render, self.terrain_position(avoided_world, PLAYER_CAMERA_HEIGHT))
        self.camera.setHpr(render, *self.terrain_surface_hpr(
            self.camera.getX(render),
            self.camera.getY(render),
            heading,
            "y"
        ))

    def apply_direct_tank_command(self, t, command, dt):
        if not tanks_dict[t]["move"] or self.tank_avatars[t].is_hidden():
            return

        tank_np = tanks_dict[t]["tank"]
        self.apply_barrel_tilt_command(t, command, dt)

        if command.turn:
            turn_step = camera_dict["turn_ang_vel"] * dt * command.turn
            tank_np.setH(tank_np, turn_step)

        if command.throttle:
            move_step = camera_dict["translate_vel"] * dt * command.throttle
            step = render.getRelativeVector(tank_np, (move_step, 0, 0))
            avoided_world = self.resolve_obstacle_position(
                tank_np.getPos(render) + step,
                self.tank_avatars[t].collision_radius
            )
            surface_world = self.terrain_position(avoided_world)
            local_pos = tanks_dict[t]["Locator"].getRelativePoint(render, surface_world)
            tanks_dict[t]["last_pos"] = Point3(surface_world)
            tank_np.setPos(local_pos)
            heading = tank_np.getH(render)
            tank_np.setHpr(render, *self.terrain_surface_hpr(surface_world[0], surface_world[1], heading, "x"))

    def apply_autonomous_tank_command(self, t, command, dt):
        if command.desired_world_pos is None:
            return

        self.apply_barrel_tilt_command(t, command, dt)

        locator = tanks_dict[t]["Locator"]
        tank_np = tanks_dict[t]["tank"]
        target_world = self.resolve_obstacle_position(
            command.desired_world_pos,
            self.tank_avatars[t].collision_radius
        )
        current_world = Point3(tank_np.getPos(render))
        to_target = target_world - current_world
        distance = math.sqrt(to_target[0] ** 2 + to_target[1] ** 2)
        max_step = AUTONOMOUS_TANK_MAX_SPEED * dt
        current_heading = tank_np.getH(render)
        target_heading = command.desired_heading
        if target_heading is None:
            target_heading = current_heading

        if distance > 0.001:
            target_heading = math.degrees(math.atan2(to_target[1], to_target[0]))

        heading = self.approach_angle(
            current_heading,
            target_heading,
            ENEMY_TURN_ANG_VEL * dt
        )
        heading_error = abs(signed_angular_delta_degrees(target_heading, heading))
        alignment = max(
            AUTONOMOUS_TANK_TURNING_SPEED_FACTOR,
            math.cos(math.radians(heading_error))
        )
        move_step = min(max_step * alignment, distance) if distance > 0.001 else 0
        heading_radians = math.radians(heading)
        candidate_world = Point3(
            current_world[0] + math.cos(heading_radians) * move_step,
            current_world[1] + math.sin(heading_radians) * move_step,
            current_world[2]
        )

        avoided_world = self.resolve_obstacle_position(
            candidate_world,
            self.tank_avatars[t].collision_radius
        )
        surface_world = self.terrain_position(avoided_world)
        local_pos = locator.getRelativePoint(render, surface_world)
        tanks_dict[t]["last_pos"] = Point3(surface_world)
        tanks_dict[t]["tank"].setPos(local_pos)
        tanks_dict[t]["tank"].setHpr(render, *self.terrain_surface_hpr(surface_world[0], surface_world[1], heading, "x"))

    def prepare_tank_shot(self, tank_id):
        shot_np = self.tank_shot_node(tank_id)
        shot_np.reparentTo(self.tank_shot_mount_node(tank_id))
        shot_np.setPos(self.tank_shot_start_local(tank_id))
        shot_np.setHpr(self.tank_shot_stowed_hpr(tank_id))
        if tank_id == "0":
            self.sight_engaged_np.show()
            self.sight_clear_np.hide()
        else:
            self.set_tank_shooting(tank_id, True)

        shot_np.wrtReparentTo(render)
        shot_np.show()
        return Point3(shot_np.getPos(render))

    def complete_tank_shot_start(self, tank_id, shot_start, interval, shot_end, shot_deflected, trajectory_points=None):
        self.set_tank_shot_interval(tank_id, interval)
        self.set_tank_shot_deflected(tank_id, shot_deflected)
        self.record_tank_shot_metadata(tank_id, shot_start, shot_end, trajectory_points)
        interval.start()

    def fire_tank_shot(self, tank_id, direction, distance, duration, sound, collision_start=None, shot_start=None):
        if shot_start is None:
            shot_start = self.prepare_tank_shot(tank_id)
        interval, shot_end, shot_deflected, trajectory_points = self.create_shot_interval(
            self.tank_shot_node(tank_id),
            shot_start,
            direction,
            distance,
            duration,
            self.tank_shot_done_event(tank_id),
            collision_start,
            shooter_id=tank_id
        )
        self.complete_tank_shot_start(tank_id, shot_start, interval, shot_end, shot_deflected, trajectory_points)
        sound.play()
        return shot_end

    def fire_tank(self, tank_id, sound=None, direction=None, shot_start=None, apply_spread=False):
        if not self.tank_can_run_controller(tank_id):
            return None

        runtime = self.tank_runtime_state(tank_id)
        if shot_start is None:
            shot_start = self.prepare_tank_shot(tank_id)
        shot_direction = direction if direction is not None else self.tank_shot_direction(tank_id, shot_start)
        if apply_spread:
            shot_direction = self.shot_direction_with_spread(
                shot_direction,
                AI_SHOT_SPREAD_YAW_DEGREES,
                AI_SHOT_SPREAD_PITCH_DEGREES
            )
        collision_start = self.tank_collision_start(tank_id, shot_start, shot_direction)
        if sound is None:
            sound = self.mainShot_snd if runtime.get("is_player", False) else self.enemyShot_snd
        shot_end = self.fire_tank_shot(
            tank_id,
            shot_direction,
            runtime.get("shot_distance", 300),
            runtime.get("shot_duration", 1.0),
            sound,
            collision_start,
            shot_start
        )
        if tank_id != "0":
            self.set_tank_attack_cooldown(tank_id, runtime.get("fire_cooldown", TANK_FIRE_COOLDOWN))
        self.record_tank_fire_event(tank_id)
        return shot_end

    def fire_enemy_tank(self, t):
        self.fire_tank(t, self.enemyShot_snd, apply_spread=True)

    def fire_remote_tank(self, t):
        self.fire_tank(t, self.mainShot_snd)

    def reset_tank_shot(self, tank_id):
        shot_interval = self.tank_shot_interval(tank_id)
        if shot_interval:
            if shot_interval.isPlaying():
                shot_interval.pause()
            self.set_tank_shot_interval(tank_id, None)

        self.set_tank_shot_deflected(tank_id, False)
        if tank_id in tanks_list:
            tanks_dict[tank_id]["shot_trajectory_points"] = []
        shot_np = self.tank_shot_node(tank_id)
        shot_np.reparentTo(self.tank_shot_mount_node(tank_id))
        shot_np.setPos(self.tank_shot_stowed_local(tank_id))
        shot_np.setHpr(self.tank_shot_stowed_hpr(tank_id))
        if tank_id == "0":
            shot_np.hide()
        else:
            shot_np.show()
            self.set_tank_shooting(tank_id, False)

    def reset_shot(self):
        self.reset_tank_shot("0")

    def enemy_reset_shot(self, t):
        self.reset_tank_shot(t)

    def request_player_fire(self):
        if self.is_network_client_controller():
            return

        if self.waiting_to_start:
            self.start_game()
            return

        if self.game_over or self.investigation_mode or not self.player_tank_is_hittable():
            return

        if self.tank_shot_interval("0") is not None:
            return

        self.human_tank_controller.request_fire()

    def toggle_enemy_shooting(self):
        if self.is_network_client_controller():
            if self.network_current_tank_id() != "0":
                return
            self.set_enemy_shooting_suspended(not self.enemy_shooting_suspended)
            if self.network_bridge is not None:
                self.network_bridge.send_client_enemy_fire(self.enemy_shooting_suspended)
            return

        if self.waiting_to_start:
            return

        self.set_enemy_shooting_suspended(not self.enemy_shooting_suspended)

    def set_enemy_shooting_suspended(self, suspended):
        self.enemy_shooting_suspended = bool(suspended)

    def shoot(self):
        if self.is_network_client_controller():
            return

        if self.waiting_to_start:
            self.start_game()
            return

        if self.game_over or self.investigation_mode or not self.player_tank_is_hittable():
            return

        if self.tank_shot_interval("0") is not None:
            return

        self.fire_tank("0", self.mainShot_snd)
        return

    def tank0_round_hit(self, entry):
        if self.is_network_client_controller():
            return

        if entry.getIntoNodePath().node().name[:5] == 'cTank':
            if self.tank_shot_deflected("0"):
                return
            t = entry.getIntoNodePath().node().name[5:6]
            self.register_player_tank_hit(t)
        elif DEBUG:
            print("hit something, but not a tank")

    def shot_clear(self):
        self.sight_engaged_np.hide()
        self.sight_clear_np.show()
        return

    def updateRadarTask(self, task):
        if self.is_network_server_authority():
            return Task.cont

        if self.waiting_to_start:
            return Task.cont

        if self.is_network_client_low_render():
            return Task.cont

        if self.is_network_client_controller() and not self.network_client_has_snapshot():
            return Task.cont

        if self.investigation_mode:
            return Task.cont

        sweep_time = getattr(task, "time", ClockObject.getGlobalClock().getFrameTime())
        if self.radar_last_update_time is None:
            dt = 0
        else:
            dt = max(0, sweep_time - self.radar_last_update_time)
        self.radar_last_update_time = sweep_time

        sweep_angle = (sweep_time * RADAR_SWEEP_SPEED) % 360
        self.radar_sweep_slice.setR(sweep_angle)
        for sweep_np, angle_offset in self.radar_sweep_nodes:
            sweep_np.setR(sweep_angle - angle_offset)

        for t in tanks_list:
            blip_np = self.radar_blips[t]
            tank_np = tanks_dict[t]["tank"]

            if tank_np.isHidden():
                blip_np.hide()
                self.radar_blip_luminance[t] = 0
                continue

            rel_pos = self.camera.getRelativePoint(render, tank_np.getPos(render))
            radar_x = rel_pos[0]
            radar_y = rel_pos[1]
            distance = math.sqrt(radar_x ** 2 + radar_y ** 2)

            if distance > 0:
                scale = min(distance, RADAR_RANGE) / RADAR_RANGE * RADAR_RADIUS
                radar_x = radar_x / distance * scale
                radar_y = radar_y / distance * scale

            blip_np.setPos(radar_x, 0, radar_y)

            blip_angle = math.degrees(math.atan2(radar_x, radar_y)) % 360
            if angular_distance_degrees(sweep_angle, blip_angle) <= RADAR_SCAN_WIDTH_DEGREES:
                self.radar_blip_luminance[t] = 1.0
            else:
                fade = dt / RADAR_BLIP_FADE_SECONDS
                self.radar_blip_luminance[t] = max(0, self.radar_blip_luminance[t] - fade)

            luminance = self.radar_blip_luminance[t]
            if luminance <= 0:
                blip_np.hide()
                continue

            base_color = tanks_dict[t]["color_scale"]
            alpha = RADAR_BLIP_IDLE_ALPHA + (1 - RADAR_BLIP_IDLE_ALPHA) * luminance
            blip_np.setColorScale(base_color[0] * alpha,
                                  base_color[1] * alpha,
                                  base_color[2] * alpha,
                                  alpha)
            blip_np.show()

        return Task.cont

    # Define a procedure to move the camera.
    def spinCameraTask(self, task):
        if self.waiting_to_start:
            return Task.cont

        if self.investigation_mode:
            return Task.cont

        # angleDegrees = task.time * 10.0
        # angleRadians = angleDegrees * (pi / 180.0)
        # rad = 100
        # self.camera.setPos(rad * sin(angleRadians), rad * cos(angleRadians), 4)
        # self.camera.headsUp(tanks_dict['1']["tank"], Vec3(0, 0, 1))
        if not self.network_client_has_snapshot():
            self.set_player_camera_on_terrain()
            self.update_player_tank_visual()

        vectH = self.camera.getHpr()
        vectP = self.camera.getPos()
        rad = math.sqrt(vectP[0] ** 2 + vectP[1] ** 2)
        theta = math.atan2(vectP[1], vectP[0]) * 180. / math.pi
        enemy_fire_text = " OFF" if self.enemy_shooting_suspended else " ON"
        status_text = str(int(vectH[0] + 180)) + ", " + str(int(rad)) + ", " + str(int(theta)) + ", " \
                    + str(int(vectH[0] - theta)) + "\nCTRL TANK " + self.human_control_tank_id + \
                    "\nENEMY FIRE" + enemy_fire_text + \
                    "\nBARREL " + str(int(self.player_barrel_tilt)) + \
                    "\n" + self.tank_lives_inline_text()
        if self.network_bridge is not None:
            status_text += "\n" + self.network_bridge.status()
        elif self.is_network_client_controller():
            connected = ",".join(getattr(self, "network_connected_tanks", [])) or "?"
            status_text += "\nNET CLIENT {}\nSERVER TANKS {}".format(self.network_current_tank_id(), connected)
        if self.is_network_client_low_render():
            status_text += "\nCLIENT LOW RENDER"
        if self.is_network_client_controller():
            status_text += "\nZ SMOOTH " + ("ON" if self.network_interpolation_enabled else "OFF")
        self.textObject.text = status_text

        # mat = Mat4(self.camera.getMat())
        # mat.invertInPlace()
        # base.mouseInterfaceNode.setMat(mat)
        # print(self.camera.getPos())
        # self.camera.setPos(100, 100, 0)
        # self.camera.setHpr(180-angleDegrees+10*sin(task.time), 0, 0)
        return Task.cont


if __name__ == "__main__":
    app = MyApp()
    app.run()
