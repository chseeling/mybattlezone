from panda3d.core import loadPrcFile, AntialiasAttrib, KeyboardButton

loadPrcFile("config/conf.prc")

import json
import math
from math import pi, sin, cos
from random import random

from direct.showbase.ShowBase import ShowBase
from direct.task import Task

from panda3d.core import AmbientLight
from panda3d.core import Vec4, Mat4
from panda3d.core import LineSegs, NodePath
from panda3d.core import Vec3

from pandac.PandaModules import WindowProperties

from direct.gui.OnscreenText import OnscreenText
from direct.interval.LerpInterval import LerpPosInterval

arrow_right   = KeyboardButton.right()
arrow_left    = KeyboardButton.left()
arrow_back    = KeyboardButton.down()
arrow_forward = KeyboardButton.up()

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


def draw_lines_object(data, idx_start=1):
    points = data['points']
    lines_def = data['lines']

    lines = LineSegs()
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

        # render.setDepthTest(False)
        self.camLens.setFov(50)
        render.setAntialias(AntialiasAttrib.MLine)

        base.setBackgroundColor(0, 0, 0)
        base.disableMouse()
        props = WindowProperties()
        # props.setCursorHidden(True)
        # props.setMouseMode(WindowProperties.M_relative)
        base.win.requestProperties(props)
        # Load the environment model.
        # self.scene = self.loader.loadModel("models/environment")
        self.ground = self.loader.loadModel("models/ground_bl.egg")
        self.tank = self.loader.loadModel("models/tank_bl.egg")
        self.mountain = self.loader.loadModel("models/mountain_bl.egg")
        self.mountain_line = self.loader.loadModel("models/mountain_line.egg")
        # self.pyramid = self.loader.loadModel("models/pyramid01.bam")
        # self.cube01 = self.loader.loadModel("models/cube01.bam")
        self.tank.setRenderModeWireframe()
        self.ground.setRenderModeWireframe()
        self.mountain.setRenderModeWireframe()
        # self.cube01.setRenderModeWireframe()
        # self.pyramid.setRenderModeWireframe()

        # Reparent the model to render.
        # self.tank.reparentTo(self.render)
        # self.ground.reparentTo(self.render)
        # self.mountain_line.reparentTo(self.render)
        # self.mountain.reparentTo(self.render)
        # self.cube01.reparentTo(self.render)
        # self.pyramid.reparentTo(self.render)
        # Apply scale and position transforms on the model.
        # scale = 5
        # self.tank.setScale(1, 1, 1)
        # self.cube01.setScale(scale, scale, scale)
        # self.pyramid.setScale(scale, scale, scale)
        self.ground.setScale(100, 100, 1)
        self.mountain.setScale(30, 1, 30)

        # render mountains
        self.mountain_line.setPos(10, 0, 10)

        # old mountain method
        far_rad = 4000
        for i in range(36):
            angleRadians = (i * 10) * (pi / 180.0)
            placeholder = render.attachNewNode("Mountain-Placeholder")
            placeholder.setPos(far_rad * sin(angleRadians), far_rad * cos(angleRadians), 0)
            placeholder.setH(placeholder, -i * 10)
            placeholder.setScale(0.4 + 0.6 * random(), 1, 0.1 + 3 * random())
            # self.mountain.instanceTo(placeholder)

        # tank round
        with open('models/tank_round.json', "r") as f:
            data = json.load(f)
        lines = draw_lines_object(data, 0)
        lines.setThickness(2)
        node = lines.create()
        self.tank_round = NodePath(node)
        self.tank_round.hide()
        self.tank_round.setColorScale(0.4, 0.4, 1.0, 1.0)
        self.tank_round.setPos(0, 20, -0.2)
        self.tank_round.setHpr(self.tank_round, 0, 90, 0)
        self.tank_round.setScale(0.2, 0.2, 0.2)
        self.tank_round.reparentTo(camera)

        # new mountain method
        with open('models/digitization01_cleaned_02.json', "r") as f:
            data = json.load(f)

        #   map mountain_line to a cylinder
        n = 2  # number of repeats in circumference
        data['points'] = map_mountains(data['points'], n)

        lines = draw_lines_object(data, 1)
        lines.setThickness(3)
        node = lines.create()
        self.np = NodePath(node)
        scale = 7000
        for i in range(n):
            angleRadians = 2 * pi / n * i
            placeholder = render.attachNewNode("MountainLine-Placeholder")
            placeholder.setH(placeholder, 360 / n * i)
            # placeholder.setPos(sin(angleRadians), cos(angleRadians), 0)
            placeholder.setScale(scale, scale, scale / n / 2.5)
            self.np.instanceTo(placeholder)
        self.np.setColorScale(0, 0.7, 0, 1.0)

        # tank as lines
        with open('models/tankDesignB.json', "r") as f:
            data = json.load(f)
        lines = draw_lines_object(data, 0)
        lines.setThickness(3)
        node = lines.create()
        self.tank = NodePath(node)

        self.tank1 = render.attachNewNode("Tank-Placeholder")
        self.tank2 = render.attachNewNode("Tank-Placeholder")
        self.tank1.setPos(100, 100, 0)
        self.tank2.setPos(150, 70, 0)
        self.tank.instanceTo(self.tank1)
        self.tank.instanceTo(self.tank2)
        self.tank1.setColorScale(0, 0.7, 0, 0.5)
        self.tank2.setColorScale(1, 0.6, 0.1, 0.5)

        # grid
        grid_lines = procedural_grid(-1000, 500, -1000, 500, 50)
        grid_lines.setThickness(1)
        node = grid_lines.create()
        self.grid = NodePath(node)
        self.grid.setColorScale(0.15, 0.2, 0.15, .9)
        # self.grid.reparentTo(self.camera)
        # self.grid.setPos(self.camera, 0, 0, -3)
        self.grid.setPos(0, 0, -0.2)
        self.grid.reparentTo(render)

        # np.set_color(0, 0, 1, 0)
        # self.np.setColorScale(0, 1, 0, 1.0)
        # self.np.setScale(10, 10, 10)
        # self.np.setPos(70,0,0)
        # self.np.setH(self.np, 0)

        # self.np.reparentTo(render)
        # b = self.np.getTightBounds()
        # print(b)

        alight = AmbientLight('ambientLight')
        alight.setColor(Vec4(0, 0, 0, 0))  # ambient light is dim red
        # alightNP = self.render.attachNewNode(alight)

        # render sight
        sight_lower = -0.30
        sight_upper = 0.30

        ls = procedural_sight(LineSegs(), True, False)
        ls = procedural_sight(ls, False, False)
        ls.setThickness(3)
        self.sight_clear_node = ls.create()

        ls = procedural_sight(LineSegs(), True, True)
        ls = procedural_sight(ls, False, True)
        ls.setThickness(3)
        self.sight_engaged_node = ls.create()

        self.sight_clear_np = NodePath(self.sight_clear_node)
        self.sight_clear_np.setColorScale(0, 0.5, 0, .9)

        self.sight_engaged_np = NodePath(self.sight_engaged_node)
        self.sight_engaged_np.setColorScale(0, 1, 0, .9)

        self.sight_clear_np.reparentTo(render2d)
        self.sight_engaged_np.reparentTo(render2d)
        self.sight_engaged_np.hide()

        # Add the spinCameraTask procedure to the task manager.
        self.taskMgr.add(self.spinCameraTask, "SpinCameraTask")
        self.taskMgr.add(self.moveTanksTask, "MoveTanksTask")
        self.taskMgr.add(self.moveTask, "MoveTask")

        # base.messenger.toggleVerbose()

        self.accept('space', self.shoot)
        self.accept('space-up', self.shoot_clear)
        self.accept('shot-done', self.reset_shot)

        vect = self.camera.getHpr()
        self.textObject = OnscreenText(text=str(vect[0]), pos=(-0.5, -0.9),
                                       scale=(0.03, 0.05), fg=(0.4, 1.0, 0.4, 1), mayChange=True)
        self.textObject.reparentTo(self.render2d)

    def moveTask(self, task):
        is_down = base.mouseWatcherNode.is_button_down

        if is_down(arrow_right):
            self.camera.setHpr(self.camera, -0.25, 0, 0)
        if is_down(arrow_left):
            self.camera.setHpr(self.camera,  0.25, 0, 0)
        if is_down(arrow_back):
            self.camera.setPos(self.camera, 0, -0.5, 0)
        if is_down(arrow_forward):
            self.camera.setPos(self.camera, 0,  0.5, 0)
        return Task.cont

    def reset_shot(self):
        print('reset_shot')
        self.tank_round.hide()
        self.tank_round.reparentTo(self.camera)
        self.tank_round.setPos(0, 20, -0.2)
        self.tank_round.setHpr(0, 90, 0)

    def shoot(self):
        self.sight_engaged_np.show()
        self.sight_clear_np.hide()
        # print('round', self.tank_round.getPos())
        # print('camera',  self.camera.getPos(), self.camera.getHpr())
        self.tank_round.wrtReparentTo(render)
        # print(self.tank_round.getPos(), self.tank_round.getHpr())
        ShootAt = render.getRelativeVector(base.camera, (0, 1, 0))
        # self.tank_round.setPos(self.tank_round.getPos() + ShootAt)

        self.tank_round.show()
        i = LerpPosInterval(self.tank_round, 1, pos=(self.tank_round.getPos() + ShootAt * 200))
        i.setDoneEvent('shot-done')
        i.start()
        print(ShootAt)
        return

    def shoot_clear(self):
        self.sight_engaged_np.hide()
        self.sight_clear_np.show()
        return

    def moveTanksTask(self, task):
        Ax1 = 25;
        Ay1 = 18
        Bx1 = -0.15;
        By1 = 0.25
        x = Ax1 * sin(Bx1 * task.time) + 10
        y = Ay1 * sin(By1 * task.time)
        dx = Ax1 * Bx1 * cos(Bx1 * task.time)
        dy = Ay1 * By1 * cos(By1 * task.time)
        heading = math.degrees(math.atan2(dy, dx))
        self.tank1.setPos(x, y, 0)
        self.tank1.setH(heading)

        Ax1 = 16;
        Ay1 = 18
        Bx1 = 0.3;
        By1 = 0.35
        x = Ax1 * sin(Bx1 * task.time) + 20
        y = Ay1 * sin(By1 * task.time) + 3
        dx = Ax1 * Bx1 * cos(Bx1 * task.time)
        dy = Ay1 * By1 * cos(By1 * task.time)
        heading = math.degrees(math.atan2(dy, dx))
        self.tank2.setPos(x, y, 0)
        self.tank2.setH(heading)
        return Task.cont

    # Define a procedure to move the camera.
    def spinCameraTask(self, task):
        angleDegrees = task.time * 10.0
        angleRadians = angleDegrees * (pi / 180.0)
        rad = 200
        # self.camera.setPos(rad * sin(angleRadians), rad * cos(angleRadians), 4)
        # self.camera.headsUp(self.tank1, Vec3(0, 0, 1))
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

        mat = Mat4(self.camera.getMat())
        mat.invertInPlace()
        base.mouseInterfaceNode.setMat(mat)
        # print(self.camera.getPos())
        # self.camera.setPos(100, 100, 0)
        # self.camera.setHpr(180-angleDegrees+10*sin(task.time), 0, 0)
        return Task.cont


app = MyApp()
app.run()
