from panda3d.core import loadPrcFile, AntialiasAttrib, KeyboardButton, CollisionSphere, CollisionNode, CollisionBox, CollisionPolygon
from panda3d.core import CollisionTraverser, CollisionHandlerEvent

from direct.interval.IntervalGlobal import *

loadPrcFile("config/conf.prc")

import json
import math
import os
from math import pi, sin, cos
from random import random

from direct.showbase.ShowBase import ShowBase
from direct.task import Task

from panda3d.core import AmbientLight
from panda3d.core import Vec4, Mat4, Point3, Point4, BitMask32
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
GG = LVecBase4(0, 1, 0, 1)  # game green constant
camera_dict = {"turn_ang_vel": 0.36, "translate_vel": 0.5}
NUMET = 2  # number of enemy tanks
tanks_dict = {"0": {},
              "1": {"init_pos": Point3(30, 50, 0),
                    "color_scale": Point4(0, 0.7, 0, 1.0),
                    "move_params": {"Ax": 25, "Ay": 18, "Bx": -0.15, "By": 0.25, "phix": 10, "phiy": 0},
                    "coll_rad": 1.4,
                    "shooting": False
                    },
              "2": {"init_pos": Point3(0, 50, 0),
                    "color_scale": Point4(1, 0.6, 0.1, 1.0),
                    "move_params": {"Ax": 16, "Ay": 18, "Bx": 0.3, "By": 0.35, "phix": 20, "phiy": 3},
                    "coll_rad": 1.4,
                    "shooting": False
                    },
              "3": {"init_pos": Point3(-30, 40, 0),
                    "color_scale": Point4(0.1, 0.6, 0.5, 1.0),
                    "move_params": {"Ax": 16, "Ay": 18, "Bx": 0.3, "By": 0.35, "phix": -10, "phiy": 7},
                    "coll_rad": 1.4,
                    "shooting": False
                    }
              }

tanks_list = {'1', '2', '3'}
DEBUG = os.environ.get("BATTLEZONE_DEBUG", "").lower() in {"1", "true", "yes", "on"}
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
PLAYER_HIT_COOLDOWN = 1.2
PLAYER_FLASH_SECONDS = 0.45
PLAYER_COLLISION_RADIUS = 1.5
TANK_COLLISION_RADIUS = 1.6
INVESTIGATE_WINDOW_SECONDS = 4.0
INVESTIGATE_FATAL_WINDOW_SECONDS = 999999.0
INVESTIGATION_GHOST_SPEED = 0.85
INVESTIGATION_GHOST_HEIGHT = 5.0
SHOT_DEFLECTION_CLEARANCE = 0.25
MAIN_CAMERA_MASK = BitMask32.bit(0)
AUX_CAMERA_MASK = BitMask32.bit(1)
DRONE_CAMERA_MASK = BitMask32.bit(2)
DRONE_VIEW_SLOT = (0.72, 0.98, 0.02, 0.25)
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
OBSTACLES = (
    {"name": "Block-1", "kind": "block", "pos": Point3(18, 38, 0), "scale": Point3(7, 7, 5),
     "radius": 6.0},
    {"name": "Pyramid-1", "kind": "pyramid", "pos": Point3(-16, 32, 0), "scale": Point3(9, 9, 7),
     "radius": 6.5},
    {"name": "Cone-1", "kind": "cone", "pos": Point3(4, 68, 0), "scale": Point3(8, 8, 8),
     "radius": 5.8},
)
RADAR_SWEEP_TRAILS = (
    (0, 0.55, 2),
    (28, 0.10, 1),
    (56, 0.04, 1),
)


def procedural_grid(x_min, x_max, y_min, y_max, n):
    del_x = (x_max - x_min) / n
    del_y = (y_max - y_min) / n

    lines = LineSegs()
    # constant y lines
    x0 = x_min
    x1 = x_max
    y0 = y_min
    for i in range(0, n + 1):
        lines.moveTo(x0, y0, 0.1)
        lines.draw_to(x1, y0, 0.1)
        y0 += del_y

    # constant x lines
    y0 = y_min
    y1 = y_max
    x0 = x_min
    for i in range(0, n + 1):
        lines.moveTo(x0, y0, 0.1)
        lines.draw_to(x0, y1, 0.1)
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


class MyApp(ShowBase):
    def __init__(self):
        ShowBase.__init__(self)

        self.ambient_snd = base.loader.loadSfx("sfx/tank_with_radar.ogg")
        self.mainShot_snd = base.loader.loadSfx("sfx/mainShot.ogg")
        self.enemyShot_snd = base.loader.loadSfx("sfx/enemyShot.ogg")
        self.enemyTankExplosion_snd = base.loader.loadSfx("sfx/enemyTankExplosion.ogg")
        self.gameOver_snd = base.loader.loadSfx("sfx/gameOver.wav")
        self.investigation_snd = base.loader.loadSfx("sfx/investigation.wav")
        self.investigation_snd.setLoop(True)
        self.investigation_snd.setVolume(0.9)

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
        # self.tank_round[0].hide()
        self.tank_round[0].setColorScale(0.3, 0.3, 1.0, 1.0)
        self.tank_round[0].setPos(0, 20, -0.2 - 10)
        self.tank_round[0].setHpr(self.tank_round[0], 0, 90, 0)
        self.tank_round[0].setScale(0.2, 0.2, 0.2)
        self.tank_round[0].reparentTo(camera)

        # render enemy tank round
        for t in tanks_list:
            tanks_dict[t]["round"] = render.attachNewNode("tank{}-round".format(t))
            np_round.instanceTo(tanks_dict[t]["round"])
            tanks_dict[t]["round"].setPos(-0.4, 0, 1.61325)
            tanks_dict[t]["round"].setHpr(tanks_dict[t]["round"], 0, 0, 90)
            tanks_dict[t]["round"].setScale(0.14, 0.14, 0.14)
            tanks_dict[t]["round"].reparentTo(tanks_dict[t]["tank"])

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
        cs = CollisionSphere(0, 0, 0, 1)
        tr_cnodePath = self.tank_round[0].attachNewNode(CollisionNode('cTankRound'))
        tr_cnodePath.node().addSolid(cs)

        # collision spheres for enemy tank rounds
        cs = CollisionSphere(0, 0, 0, 1)
        for t in tanks_list:
            np = tanks_dict[t]["round"].attachNewNode(CollisionNode('ceTankRound' + t))
            np.node().addSolid(cs)
            np.node().setFromCollideMask(BitMask32(0x20))
            # np.show()

        # collision sphere main tank
        cs = CollisionSphere(0, 0, 0, 1)
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


        # grid
        grid_lines = procedural_grid(-1000, 500, -1000, 500, 50)
        grid_lines.setThickness(1)
        node = grid_lines.create()
        grid_np = NodePath(node)
        self.grid = render.attachNewNode("Grid")
        grid_np.instanceTo(self.grid)
        self.grid.setColorScale(0.15, 0.2, 0.15, 1.0)
        self.grid.setPos(0, 0, -0.2)
        self.render_obstacles()

        alight = AmbientLight('ambientLight')
        alight.setColor(Vec4(0, 0, 0, 0))  # ambient light is dim red
        # alightNP = self.render.attachNewNode(alight)

        # render sight
        self.render_sight()
        self.render_radar()
        self.render_player_hud()
        self.render_auxiliary_views()
        self.render_recon_drone()
        self.display_filters = CommonFilters(base.win, base.cam)
        self.gpu_bloom_available = True

        # Tasks
        for t in tanks_list:
            tanks_dict[t]["move"] = True

        self.taskMgr.add(self.spinCameraTask, "SpinCameraTask")
        self.taskMgr.add(self.moveTanksTask, "MoveTanksTask")
        self.taskMgr.add(self.moveTask, "MoveTask")
        self.taskMgr.add(self.enemy_shoot_task, "EnemyShoot")
        self.taskMgr.add(self.updateRadarTask, "UpdateRadarTask")
        self.taskMgr.add(self.updatePlayerFeedbackTask, "UpdatePlayerFeedbackTask")
        self.taskMgr.add(self.updateAuxiliaryViewsTask, "UpdateAuxiliaryViewsTask")
        self.taskMgr.add(self.updateReconDroneTask, "UpdateReconDroneTask")

        # base.messenger.toggleVerbose()

        self.bloom_enabled = True
        self.accept('space', self.shoot)
        self.accept('space-up', self.shot_clear)
        self.accept('f', self.shoot)
        self.accept('f-up', self.shot_clear)
        self.accept('mouse1', self.shoot)
        self.accept('mouse1-up', self.shot_clear)
        self.accept('control', self.shoot)
        self.accept('control-up', self.shot_clear)
        self.accept('shot-done', self.reset_shot)
        self.accept('b', self.toggle_bloom)
        self.accept('d', self.toggle_recon_drone)
        self.accept('i', self.toggle_investigation)
        self.accept('r', self.restart_game)

        self.accept('into-' + 'cmTank', self.struck)
        for t in tanks_list:
            self.accept('into-' + 'cTank' + t, self.tank0_round_hit)
            self.accept('explosion{}-done'.format(t), self.explosion_cleanup, extraArgs=[t])
            self.accept('shot{}-done'.format(t), self.enemy_reset_shot, extraArgs=[t])
        for obstacle in OBSTACLES:
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

        self.ambient_snd.setLoop(True)
        self.ambient_snd.play()

        # mainShot_snd.setLoop(True)

        # sfxMgr = base.sfxManagerList[0]

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
        self.set_bloom_enabled(not self.bloom_enabled)

    def arm_investigation(self, shooter_id, shot_start, shot_end, shooter_pos=None, shooter_hpr=None):
        if shooter_id in tanks_list:
            if shooter_pos is None:
                shooter_pos = tanks_dict[shooter_id]["tank"].getPos(render)
            if shooter_hpr is None:
                shooter_hpr = tanks_dict[shooter_id]["tank"].getHpr(render)

        self.last_player_hit_event = {
            "shooter_id": shooter_id,
            "shot_start": Point3(shot_start),
            "shot_end": Point3(shot_end),
            "shooter_pos": Point3(shooter_pos),
            "shooter_hpr": shooter_hpr,
            "player_pos": Point3(self.camera.getPos(render)),
            "player_hpr": self.camera.getHpr(render),
            "fatal": False
        }
        self.investigation_available_until = (
            ClockObject.getGlobalClock().getFrameTime() + INVESTIGATE_WINDOW_SECONDS
        )

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
        self.pause_interval_for_investigation(self.player_shot_interval)
        for t in tanks_list:
            self.pause_interval_for_investigation(tanks_dict[t].get("shot_interval"))
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
        self.investigation_marker_root.hide(AUX_CAMERA_MASK | DRONE_CAMERA_MASK)
        trajectory = LineSegs("InvestigationTrajectory")
        trajectory.setThickness(5)
        trajectory.setColor(1.0, 0.05, 0.02, 1)
        trajectory.moveTo(event["shot_start"])
        trajectory.drawTo(event["shot_end"])
        trajectory_np = self.investigation_marker_root.attachNewNode(trajectory.create())
        trajectory_np.setTransparency(TransparencyAttrib.MAlpha, 10)
        trajectory_np.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.MAdd), 10)
        trajectory_np.setDepthWrite(False, 10)

        shooter_id = event["shooter_id"]
        if shooter_id in tanks_list:
            shooter_marker = self.investigation_marker_root.attachNewNode("InvestigationShooterAtFire")
            shooter_marker.setPos(render, event["shooter_pos"])
            shooter_marker.setHpr(render, event["shooter_hpr"])
            self.tank.instanceTo(shooter_marker)
            shooter_marker.setColorScale(1.0, 0.03, 0.02, 1)

        hit_marker_pos = Point3(event["player_pos"])
        hit_marker_pos[2] = 0
        hit_marker = self.investigation_marker_root.attachNewNode("InvestigationPlayerAtHit")
        hit_marker.setPos(render, hit_marker_pos)
        hit_marker.setHpr(render, event["player_hpr"][0] + 90, 0, 0)
        self.tank.instanceTo(hit_marker)
        hit_marker.setColorScale(0.05, 0.35, 1.0, 1)

    def clear_investigation_markers(self):
        if self.investigation_marker_root is not None and not self.investigation_marker_root.isEmpty():
            self.investigation_marker_root.removeNode()
            self.investigation_marker_root = None

        self.investigation_highlight_tank = None
        self.investigation_highlight_color = None

    def stop_battle_sounds_for_investigation(self):
        self.ambient_snd.stop()
        self.gameOver_snd.stop()
        self.mainShot_snd.stop()
        self.enemyShot_snd.stop()
        self.enemyTankExplosion_snd.stop()

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
        self.camera.setHpr(render, self.last_player_hit_event["player_hpr"])
        self.pause_simulation_intervals()
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
        self.clear_investigation_markers()
        self.last_player_hit_event = None
        self.investigateTextObject.hide()
        self.investigateTimerRoot.hide()
        self.resume_sounds_after_investigation()
        if self.game_over:
            self.gameOverTextObject.show()

    def toggle_investigation(self):
        if self.investigation_mode:
            self.exit_investigation()
            return

        now = ClockObject.getGlobalClock().getFrameTime()
        if self.last_player_hit_event and (
                self.last_player_hit_event.get("fatal", False) or now <= self.investigation_available_until):
            self.enter_investigation()

    def struck(self, entry):
        now = ClockObject.getGlobalClock().getFrameTime()
        if self.investigation_mode or self.game_over or now - self.last_player_hit_time < PLAYER_HIT_COOLDOWN:
            return

        from_name = entry.getFromNodePath().node().name
        if from_name.startswith("ceTankRound"):
            shooter_id = from_name[-1]
            shot_start = tanks_dict[shooter_id].get("shot_start", tanks_dict[shooter_id]["round"].getPos(render))
            try:
                shot_end = entry.getSurfacePoint(render)
            except Exception:
                shot_end = tanks_dict[shooter_id]["round"].getPos(render)
            self.arm_investigation(
                shooter_id,
                shot_start,
                shot_end,
                tanks_dict[shooter_id].get("shot_shooter_pos"),
                tanks_dict[shooter_id].get("shot_shooter_hpr")
            )
            self.enemy_reset_shot(shooter_id)

        self.last_player_hit_time = now
        self.player_lives = max(0, self.player_lives - 1)
        self.hit_flash_alpha = 0.5
        self.update_lives_hud()

        if self.player_lives <= 0:
            self.make_investigation_persistent_for_game_over()
            self.end_game()

    def end_game(self):
        self.game_over = True
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

    def restart_game(self):
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
        self.player_lives = PLAYER_MAX_LIVES
        self.last_player_hit_time = -PLAYER_HIT_COOLDOWN
        self.hit_flash_alpha = 0
        self.gameOverTextObject.hide()
        self.hitFlashNp.hide()
        self.investigation_snd.stop()
        self.gameOver_snd.stop()
        self.ambient_snd.play()
        self.camera.setPos(0, 0, 2)
        self.camera.setHpr(0, 0, 0)
        self.reset_shot()
        for t in tanks_list:
            tanks_dict[t]["move"] = True
            tanks_dict[t]["shooting"] = False
            tanks_dict[t]["tank"].show()
            tanks_dict[t]["frags"].hide()
            tanks_dict[t].pop("last_pos", None)
            self.enemy_reset_shot(t)
        self.update_lives_hud()

    def updatePlayerFeedbackTask(self, task):
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

    def enemy_shoot_task(self, task):
        if self.game_over or self.investigation_mode:
            return Task.cont

        for t in tanks_list:
            ShootAt = tanks_dict[t]["tank"].getRelativePoint(self.camera, (0 + random(), 0 + random(), 0 + random()))
            ShootAt = LVecBase2d(ShootAt[0], ShootAt[1]).normalized()
            if ShootAt[0] > 0.99999 and not tanks_dict[t]["shooting"]:
                print('Tank {} shooting'.format(t))
                tanks_dict[t]["shooting"] = True
                tanks_dict[t]["round"].wrtReparentTo(render)
                ShootAt = render.getRelativeVector(tanks_dict[t]["tank"], (1, 0, 0))
                shot_start = Point3(tanks_dict[t]["round"].getPos(render))
                shot_end = shot_start + ShootAt * 300
                tanks_dict[t]["shot_start"] = shot_start
                tanks_dict[t]["shot_shooter_pos"] = Point3(tanks_dict[t]["tank"].getPos(render))
                tanks_dict[t]["shot_shooter_hpr"] = tanks_dict[t]["tank"].getHpr(render)
                i, shot_end, shot_deflected = self.create_shot_interval(
                    tanks_dict[t]["round"],
                    shot_start,
                    ShootAt,
                    300,
                    1,
                    'shot{}-done'.format(t)
                )
                tanks_dict[t]["shot_end"] = Point3(shot_end)
                tanks_dict[t]["shot_deflected"] = shot_deflected
                tanks_dict[t]["shot_interval"] = i
                i.start()
                self.enemyShot_snd.play()
        return Task.cont

    def render_mountains(self):
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
            placeholder = self.render.attachNewNode("MountainLine-Placeholder")
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

    def render_obstacles(self):
        self.obstacle_group = render.attachNewNode("Obstacles")
        factories = {
            "block": procedural_block,
            "pyramid": procedural_pyramid,
            "cone": procedural_cone,
        }

        for obstacle in OBSTACLES:
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
            placeholder.setPos(obstacle["pos"])
            placeholder.setScale(obstacle["scale"])
            placeholder.find("**/*-Lines").setColorScale(0, 0.55, 0.15, 1.0)

            collision_np = self.obstacle_group.attachNewNode(CollisionNode("cObstacle-" + obstacle["name"]))
            collision_np.setPos(obstacle["pos"])
            add_obstacle_shot_solids(collision_np.node(), obstacle)
            if DEBUG:
                collision_np.show()

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

        self.sight_clear_np.reparentTo(render2d)
        self.sight_engaged_np.reparentTo(render2d)
        self.sight_engaged_np.hide()

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
        self.player_lives = PLAYER_MAX_LIVES
        self.game_over = False
        self.last_player_hit_time = -PLAYER_HIT_COOLDOWN
        self.hit_flash_alpha = 0
        self.investigation_mode = False
        self.investigation_available_until = 0
        self.last_player_hit_event = None
        self.investigation_saved_camera_pos = None
        self.investigation_saved_camera_hpr = None
        self.investigation_marker_root = None
        self.investigation_highlight_tank = None
        self.investigation_highlight_color = None
        self.investigation_paused_intervals = []
        self.player_shot_interval = None
        self.player_shot_deflected = False

        self.livesTextObject = OnscreenText(text="", pos=(-1.28, 0.9),
                                            align=TextNode.ALeft, scale=(0.04, 0.06),
                                            fg=(0.4, 1.0, 0.4, 1), mayChange=True)
        self.livesTextObject.reparentTo(aspect2d)

        self.gameOverTextObject = OnscreenText(text="GAME OVER\nR TO RESTART", pos=(0, 0.08),
                                               align=TextNode.ACenter, scale=(0.08, 0.1),
                                               fg=(0.4, 1.0, 0.4, 1), mayChange=True)
        self.gameOverTextObject.reparentTo(aspect2d)
        self.gameOverTextObject.hide()

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
        self.livesTextObject.text = "LIVES " + " ".join(["|"] * self.player_lives)

    def render_auxiliary_views(self):
        self.auxiliary_cameras = []
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

            if view["name"] == "PANORAMA":
                self.render_panorama_main_view_edges(view, x0, x1, z0, z1)

            label = OnscreenText(text=view["name"], pos=((x0 + x1) * 0.5, z0 - 0.035),
                                 align=TextNode.ACenter, scale=(0.025, 0.038),
                                 fg=(0.35, 1.0, 0.35, 1), mayChange=False)
            label.reparentTo(aspect2d)

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

        aspect = base.getAspectRatio()
        x0 = (slot_left * 2 - 1) * aspect
        x1 = (slot_right * 2 - 1) * aspect
        z0 = slot_bottom * 2 - 1
        z1 = slot_top * 2 - 1
        frame = LineSegs("ReconDroneViewFrame")
        frame.setThickness(2)
        frame.moveTo(x0, 0, z0)
        frame.drawTo(x1, 0, z0)
        frame.drawTo(x1, 0, z1)
        frame.drawTo(x0, 0, z1)
        frame.drawTo(x0, 0, z0)
        frame_np = aspect2d.attachNewNode(frame.create())
        frame_np.setColorScale(DRONE_BLUE)

        self.droneTextObject = OnscreenText(text="", pos=(x0 + 0.02, z1 - 0.045),
                                            align=TextNode.ALeft, scale=(0.027, 0.042),
                                            fg=(0.25, 0.65, 1.0, 1), mayChange=True)
        self.droneTextObject.reparentTo(aspect2d)
        self.update_drone_status_hud()
        self.update_drone_home_marker()

    def hide_bloom_from_auxiliary_views(self):
        camera_mask = AUX_CAMERA_MASK | DRONE_CAMERA_MASK
        for view in self.auxiliary_cameras:
            view["camera"].node().setCameraMask(AUX_CAMERA_MASK)

        for node in self.bloom_nodes():
            node.hide(camera_mask)

    def updateAuxiliaryViewsTask(self, task):
        pos = self.camera.getPos(render)
        hpr = self.camera.getHpr(render)
        for view in self.auxiliary_cameras:
            view["camera"].setPos(render, pos)
            view["camera"].setHpr(render, hpr[0] + view["heading"], 0, 0)

        return Task.cont

    def update_drone_status_hud(self):
        if hasattr(self, "droneTextObject"):
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
        for obstacle in OBSTACLES:
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
        if self.investigation_mode:
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
        if self.investigation_mode:
            return Task.cont

        dt = min(ClockObject.getGlobalClock().getDt(), 0.05)
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
            pos = tanks_dict[t]["Locator"].getPos()
            tanks_dict[t]["Locator"].setPos(-pos[1], -pos[0], 0)
            tanks_dict[t]["move"] = True
            tanks_dict[t].pop("last_pos", None)
            tanks_dict[t]["tank"].show()

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

        for t in tanks_list:
            tanks_dict[t]["Locator"] = tanks_group.attachNewNode("Tank{}-Locator".format(t))
            tanks_dict[t]["tank"] = tanks_dict[t]["Locator"].attachNewNode("Tank{}-Placeholder".format(t))
            tanks_dict[t]["Locator"].setPos(tanks_dict[t]["init_pos"])
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
        for obstacle in OBSTACLES:
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
            return Point3(pos[0] + point[0], pos[1] + point[1], pos[2] + point[2])

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
        for obstacle in OBSTACLES:
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

    def create_shot_interval(self, round_np, start, direction, distance, duration, done_event):
        shot_dir = self.normalize3(direction)
        raw_end = Point3(start + shot_dir * distance)
        hit = self.find_shot_obstacle_hit(start, raw_end)
        if not hit:
            interval = LerpPosInterval(round_np, duration, pos=raw_end)
            interval.setDoneEvent(done_event)
            return interval, raw_end, False

        impact = hit["point"]
        normal = hit["normal"]
        reflected_dir = Point3(
            shot_dir[0] - 2 * self.dot3(shot_dir, normal) * normal[0],
            shot_dir[1] - 2 * self.dot3(shot_dir, normal) * normal[1],
            shot_dir[2] - 2 * self.dot3(shot_dir, normal) * normal[2]
        )
        reflected_dir = self.normalize3(reflected_dir)
        remaining_distance = distance * (1 - hit["t"])
        reflected_start = Point3(impact + reflected_dir * SHOT_DEFLECTION_CLEARANCE)
        reflected_end = Point3(reflected_start + reflected_dir * remaining_distance)
        first_duration = max(0.03, duration * hit["t"])
        second_duration = max(0.03, duration - first_duration)
        interval = Sequence(
            LerpPosInterval(round_np, first_duration, pos=impact),
            LerpPosInterval(round_np, second_duration, pos=reflected_end)
        )
        interval.setDoneEvent(done_event)
        return interval, reflected_end, True

    def normalized_xy(self, vector):
        length = math.sqrt(vector[0] ** 2 + vector[1] ** 2)
        if length < 0.001:
            return Point3(0, 1, 0)
        return Point3(vector[0] / length, vector[1] / length, 0)

    def round_obstacle_hit(self, entry):
        from_name = entry.getFromNodePath().node().name
        if from_name == "cTankRound":
            if self.player_shot_deflected:
                return
            self.reset_shot()
        elif from_name.startswith("ceTankRound"):
            t = from_name[-1]
            if t in tanks_list:
                if tanks_dict[t].get("shot_deflected", False):
                    return
                self.enemy_reset_shot(t)

    def move_investigation_camera(self):
        is_down = base.mouseWatcherNode.is_button_down

        if is_down(arrow_right):
            self.camera.setHpr(self.camera, -camera_dict["turn_ang_vel"], 0, 0)
        if is_down(arrow_left):
            self.camera.setHpr(self.camera, camera_dict["turn_ang_vel"], 0, 0)
        if is_down(arrow_back):
            step = render.getRelativeVector(self.camera, (0, -INVESTIGATION_GHOST_SPEED, 0))
            self.camera.setPos(render, self.camera.getPos(render) + step)
        if is_down(arrow_forward):
            step = render.getRelativeVector(self.camera, (0, INVESTIGATION_GHOST_SPEED, 0))
            self.camera.setPos(render, self.camera.getPos(render) + step)

    def moveTask(self, task):
        if self.investigation_mode:
            self.move_investigation_camera()
            return Task.cont

        if self.game_over:
            return Task.cont

        is_down = base.mouseWatcherNode.is_button_down

        if is_down(arrow_right):
            self.camera.setHpr(self.camera, -camera_dict["turn_ang_vel"], 0, 0)
        if is_down(arrow_left):
            self.camera.setHpr(self.camera, camera_dict["turn_ang_vel"], 0, 0)
        if is_down(arrow_back):
            step = render.getRelativeVector(self.camera, (0, -camera_dict["translate_vel"], 0))
            next_pos = self.resolve_obstacle_position(self.camera.getPos(render) + step, PLAYER_COLLISION_RADIUS)
            self.camera.setPos(render, next_pos)
        if is_down(arrow_forward):
            step = render.getRelativeVector(self.camera, (0, camera_dict["translate_vel"], 0))
            next_pos = self.resolve_obstacle_position(self.camera.getPos(render) + step, PLAYER_COLLISION_RADIUS)
            self.camera.setPos(render, next_pos)
        return Task.cont

    def reset_shot(self):
        # print('reset_shot')
        if self.player_shot_interval:
            if self.player_shot_interval.isPlaying():
                self.player_shot_interval.pause()
            self.player_shot_interval = None
        self.player_shot_deflected = False
        self.tank_round[0].hide()
        self.tank_round[0].reparentTo(self.camera)
        self.tank_round[0].setPos(0, 20, -0.2 - 10)
        self.tank_round[0].setHpr(0, 90, 0)

    def enemy_reset_shot(self, t):
        # print("reset shot {}".format(t))
        shot_interval = tanks_dict[t].get("shot_interval")
        if shot_interval:
            if shot_interval.isPlaying():
                shot_interval.pause()
            tanks_dict[t]["shot_interval"] = None
        tanks_dict[t]["shot_deflected"] = False
        tanks_dict[t]["round"].reparentTo(tanks_dict[t]["tank"])
        tanks_dict[t]["round"].setPos(-0.4, 0, 1.61325)
        tanks_dict[t]["round"].setHpr(0, 0, 90)
        tanks_dict[t]["shooting"] = False

    def shoot(self):
        if self.game_over or self.investigation_mode:
            return

        self.tank_round[0].setPos(0, 20, -0.2)
        self.sight_engaged_np.show()
        self.sight_clear_np.hide()

        self.tank_round[0].wrtReparentTo(render)
        # print(self.tank_round[0].getPos(), self.tank_round[0].getHpr())
        ShootAt = render.getRelativeVector(base.camera, (0, 1, 0))
        # self.tank_round[0].setPos(self.tank_round[0].getPos() + ShootAt)

        self.tank_round[0].show()
        self.mainShot_snd.play()
        shot_start = Point3(self.tank_round[0].getPos(render))
        i, shot_end, shot_deflected = self.create_shot_interval(
            self.tank_round[0],
            shot_start,
            ShootAt,
            200,
            1.1,
            'shot-done'
        )
        self.player_shot_interval = i
        self.player_shot_deflected = shot_deflected
        i.start()
        # print(ShootAt)
        return

    def tank0_round_hit(self, entry):
        if entry.getIntoNodePath().node().name[:5] == 'cTank':
            t = entry.getIntoNodePath().node().name[5:6]
            print('hit tank ' + t)
            tanks_dict[t]["move"] = False
            tanks_dict[t]["tank"].hide()
            tanks_dict[t]["frags"].showThrough()
            tanks_dict[t]["explosion"].start()
            self.enemyTankExplosion_snd.play()
        else:
            print("hit something, but not a tank")

    def shot_clear(self):
        self.sight_engaged_np.hide()
        self.sight_clear_np.show()
        return

    def updateRadarTask(self, task):
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

    def moveTanksTask(self, task):
        if self.investigation_mode:
            return Task.cont

        for t in tanks_list:
            if tanks_dict[t]["move"]:
                Ax = tanks_dict[t]["move_params"]["Ax"]
                Ay = tanks_dict[t]["move_params"]["Ay"]
                Bx = tanks_dict[t]["move_params"]["Bx"]
                By = tanks_dict[t]["move_params"]["By"]
                phix = tanks_dict[t]["move_params"]["phix"]
                phiy = tanks_dict[t]["move_params"]["phiy"]
                #
                x = Ax * sin(Bx * task.time) + phix
                y = Ay * sin(By * task.time) + phiy
                dx = Ax * Bx * cos(Bx * task.time)
                dy = Ay * By * cos(By * task.time)
                heading = math.degrees(math.atan2(dy, dx))
                locator = tanks_dict[t]["Locator"]
                desired_world = render.getRelativePoint(locator, Point3(x, y, 0))
                avoided_world = self.resolve_obstacle_position(desired_world, TANK_COLLISION_RADIUS)
                local_pos = locator.getRelativePoint(render, avoided_world)

                previous_world = tanks_dict[t].get("last_pos", desired_world)
                move_dx = avoided_world[0] - previous_world[0]
                move_dy = avoided_world[1] - previous_world[1]
                if abs(move_dx) + abs(move_dy) > 0.001:
                    heading = math.degrees(math.atan2(move_dy, move_dx))

                tanks_dict[t]["last_pos"] = Point3(avoided_world)
                tanks_dict[t]["tank"].setPos(local_pos[0], local_pos[1], 0)
                tanks_dict[t]["tank"].setH(heading)

        return Task.cont

    # Define a procedure to move the camera.
    def spinCameraTask(self, task):
        if self.investigation_mode:
            return Task.cont

        # angleDegrees = task.time * 10.0
        # angleRadians = angleDegrees * (pi / 180.0)
        # rad = 100
        # self.camera.setPos(rad * sin(angleRadians), rad * cos(angleRadians), 4)
        # self.camera.headsUp(tanks_dict['1']["tank"], Vec3(0, 0, 1))
        pos = self.camera.getPos()
        self.camera.setPos(pos[0], pos[1], 2)
        ort = self.camera.getHpr()
        self.camera.setHpr(ort[0], 0, 0)

        vectH = self.camera.getHpr()
        vectP = self.camera.getPos()
        rad = math.sqrt(vectP[0] ** 2 + vectP[1] ** 2)
        theta = math.atan2(vectP[1], vectP[0]) * 180. / math.pi
        self.textObject.text = str(int(vectH[0] + 180)) + ", " + str(int(rad)) + ", " + str(int(theta)) + ", " \
                             + str(int(vectH[0] - theta))

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
