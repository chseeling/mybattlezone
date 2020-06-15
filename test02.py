from panda3d.core import loadPrcFile, AntialiasAttrib, KeyboardButton, CollisionSphere, CollisionNode
from panda3d.core import CollisionTraverser, CollisionHandlerEvent

from direct.interval.IntervalGlobal import *

loadPrcFile("config/conf.prc")

import json
import math
from math import pi, sin, cos
from random import random

from direct.showbase.ShowBase import ShowBase
from direct.task import Task

from panda3d.core import AmbientLight
from panda3d.core import Vec4, Mat4, Point3, Point4, BitMask32
from panda3d.core import LineSegs, NodePath
from panda3d.core import LVecBase4, LVecBase2d, InputDevice

from pandac.PandaModules import WindowProperties

from direct.gui.OnscreenText import OnscreenText
from direct.interval.LerpInterval import LerpPosInterval



arrow_right = KeyboardButton.right()
arrow_left = KeyboardButton.left()
arrow_back = KeyboardButton.down()
arrow_forward = KeyboardButton.up()
GG = LVecBase4(0, 1, 0, 1)  # game green constant
camera_dict = {"turn_ang_vel": 0.25, "translate_vel": 0.5}
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
DEBUG = True


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


class MyApp(ShowBase):
    def __init__(self):
        ShowBase.__init__(self)

        mySound = base.loader.loadSfx("sfx/tank_with_radar.ogg")
        self.mainShot_snd = base.loader.loadSfx("sfx/mainShot.ogg")
        self.enemyShot_snd = base.loader.loadSfx("sfx/enemyShot.ogg")
        self.enemyTankExplosion_snd = base.loader.loadSfx("sfx/enemyTankExplosion.ogg")

        device_list = self.devices.getDevices()
        for device in device_list:
            print(device.device_class)
            if device.device_class == DeviceClass.flight_stick:
                print("Have Joy stick")

        # render.setDepthTest(False)
        self.camLens.setFov(50)
        render.setAntialias(AntialiasAttrib.MLine)

        base.setBackgroundColor(0, 0, 0)
        base.disableMouse()
        props = WindowProperties()
        # props.setCursorHidden(True)
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
        lines.setThickness(3)

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
        self.grid = NodePath(node)
        self.grid.setColorScale(0.15, 0.2, 0.15, 1.0)
        self.grid.setPos(0, 0, -0.2)

        alight = AmbientLight('ambientLight')
        alight.setColor(Vec4(0, 0, 0, 0))  # ambient light is dim red
        # alightNP = self.render.attachNewNode(alight)

        # render sight
        self.render_sight()

        # Tasks
        for t in tanks_list:
            tanks_dict[t]["move"] = True

        self.taskMgr.add(self.spinCameraTask, "SpinCameraTask")
        self.taskMgr.add(self.moveTanksTask, "MoveTanksTask")
        self.taskMgr.add(self.moveTask, "MoveTask")
        self.taskMgr.add(self.enemy_shoot_task, "EnemyShoot")

        # base.messenger.toggleVerbose()

        self.accept('space', self.shoot)
        self.accept('space-up', self.shot_clear)
        self.accept('shot-done', self.reset_shot)

        self.accept('into-' + 'cmTank', self.struck)
        for t in tanks_list:
            self.accept('into-' + 'cTank' + t, self.tank0_round_hit)
            self.accept('explosion{}-done'.format(t), self.explosion_cleanup, extraArgs=[t])
            self.accept('shot{}-done'.format(t), self.enemy_reset_shot, extraArgs=[t])

        # on-screen text
        vect = self.camera.getHpr()
        self.textObject = OnscreenText(text=str(vect[0]), pos=(-0.5, -0.9),
                                       scale=(0.03, 0.05), fg=(0.4, 1.0, 0.4, 1), mayChange=True)
        self.textObject.reparentTo(self.render2d)

        mySound.setLoop(True)
        mySound.play()

        # mainShot_snd.setLoop(True)

        # sfxMgr = base.sfxManagerList[0]

    def struck(self, entry):
        print("struck")

    def enemy_shoot_task(self, task):
        for t in tanks_list:
            ShootAt = tanks_dict[t]["tank"].getRelativePoint(self.camera, (0 + random(), 0 + random(), 0 + random()))
            ShootAt = LVecBase2d(ShootAt[0], ShootAt[1]).normalized()
            if ShootAt[0] > 0.99999 and not tanks_dict[t]["shooting"]:
                print('Tank {} shooting'.format(t))
                tanks_dict[t]["shooting"] = True
                tanks_dict[t]["round"].wrtReparentTo(render)
                ShootAt = render.getRelativeVector(tanks_dict[t]["tank"], (1, 0, 0))
                i = LerpPosInterval(tanks_dict[t]["round"], 1, pos=(tanks_dict[t]["round"].getPos() + ShootAt * 300))
                i.setDoneEvent('shot{}-done'.format(t))
                i.start()
                self.enemyShot_snd.play()
        return Task.cont

    def render_mountains(self):
        with open('models/digitization01_cleaned_02.json', "r") as f:
            data = json.load(f)

        #   map mountain_line to a cylinder
        n = 2  # number of repeats in circumference
        data['points'] = map_mountains(data['points'], n)

        lines = create_lineSegs_object(data, 1)
        lines.setThickness(3)
        node = lines.create()
        np = NodePath(node)
        scale = 7000
        for i in range(n):
            angleRadians = 2 * pi / n * i
            placeholder = self.render.attachNewNode("MountainLine-Placeholder")
            placeholder.setH(placeholder, 360 / n * i)
            # placeholder.setPos(sin(angleRadians), cos(angleRadians), 0)
            placeholder.setScale(scale, scale, scale / n / 2.5)
            np.instanceTo(placeholder)
        np.setColorScale(0, 0.7, 0, 1.0)

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

    def explosion_cleanup(self, t):
        if t in tanks_list:
            tanks_dict[t]["frags"].hide()
            pos = tanks_dict[t]["Locator"].getPos()
            tanks_dict[t]["Locator"].setPos(-pos[1], -pos[0], 0)
            tanks_dict[t]["move"] = True
            tanks_dict[t]["tank"].show()

    def renderTanks(self, tanks_group):
        # tank as lines
        with open('models/tankDesignB.json', "r") as f:
            data = json.load(f)
        lines = create_lineSegs_object(data, 0)
        lines.setThickness(3)
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
                lines.setThickness(3)
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

    def moveTask(self, task):
        is_down = base.mouseWatcherNode.is_button_down

        if is_down(arrow_right):
            self.camera.setHpr(self.camera, -camera_dict["turn_ang_vel"], 0, 0)
        if is_down(arrow_left):
            self.camera.setHpr(self.camera, camera_dict["turn_ang_vel"], 0, 0)
        if is_down(arrow_back):
            self.camera.setPos(self.camera, 0, -camera_dict["translate_vel"], 0)
        if is_down(arrow_forward):
            self.camera.setPos(self.camera, 0, camera_dict["translate_vel"], 0)
        return Task.cont

    def reset_shot(self):
        # print('reset_shot')
        self.tank_round[0].hide()
        self.tank_round[0].reparentTo(self.camera)
        self.tank_round[0].setPos(0, 20, -0.2 - 10)
        self.tank_round[0].setHpr(0, 90, 0)

    def enemy_reset_shot(self, t):
        # print("reset shot {}".format(t))
        tanks_dict[t]["round"].reparentTo(tanks_dict[t]["tank"])
        tanks_dict[t]["round"].setPos(-0.4, 0, 1.61325)
        tanks_dict[t]["round"].setHpr(0, 0, 90)
        tanks_dict[t]["shooting"] = False

    def shoot(self):

        self.tank_round[0].setPos(0, 20, -0.2)
        self.sight_engaged_np.show()
        self.sight_clear_np.hide()

        self.tank_round[0].wrtReparentTo(render)
        # print(self.tank_round[0].getPos(), self.tank_round[0].getHpr())
        ShootAt = render.getRelativeVector(base.camera, (0, 1, 0))
        # self.tank_round[0].setPos(self.tank_round[0].getPos() + ShootAt)

        self.tank_round[0].show()
        self.mainShot_snd.play()
        i = LerpPosInterval(self.tank_round[0], 1.1, pos=(self.tank_round[0].getPos() + ShootAt * 200))
        i.setDoneEvent('shot-done')
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

    def moveTanksTask(self, task):

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
                tanks_dict[t]["tank"].setPos(x, y, 0)
                tanks_dict[t]["tank"].setH(heading)

        return Task.cont

    # Define a procedure to move the camera.
    def spinCameraTask(self, task):
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


app = MyApp()
app.run()
