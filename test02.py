from panda3d.core import loadPrcFile

loadPrcFile("config/conf.prc")

import json
import math
from math import pi, sin, cos
from random import random

from direct.showbase.ShowBase import ShowBase
from direct.task import Task

from panda3d.core import AmbientLight
from panda3d.core import Vec4
from panda3d.core import LineSegs, NodePath
from panda3d.core import Vec3

from pandac.PandaModules import WindowProperties


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


class MyApp(ShowBase):
    def __init__(self):
        ShowBase.__init__(self)

        render.setDepthTest(False)
        base.setBackgroundColor(0, 0, 0)
        # base.disableMouse()
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
        self.ground.setScale(50, 50, 1)
        self.mountain.setScale(30, 1, 30)

        # old tanks method
        # self.tank.setPos(0, 0, 0)
        # self.tank1 = render.attachNewNode("Tank-Placeholder")
        # self.tank2 = render.attachNewNode("Tank-Placeholder")
        # self.tank1.setPos(100, 100, 0)
        # self.tank2.setPos(150, 70, 0)
        # self.tank.instanceTo(self.tank1)
        # self.tank.instanceTo(self.tank2)

        # self.cube01.setPos(20, 20, 0)

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
        self.np.setColorScale(0, 0.7, 0, 0.5)

        # tank as lines
        with open('models/tankDesignB.json', "r") as f:
            data = json.load(f)
        lines = draw_lines_object(data, 0)
        lines.setThickness(3)
        node = lines.create()
        self.tank = NodePath(node)

        #self.tank.setPos(0, 0, 0)
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

        # render scope
        scope_width = 0.3
        scope_tick  = 0.1
        scope_lower = -0.30
        scope_upper = 0.30
        scope_lines = LineSegs()
        x0 = -scope_width/2
        z0 = scope_tick
        scope_lines.moveTo(x0, 0, z0 + scope_lower)
        scope_lines.draw_to(x0, 0, 0 + scope_lower)
        scope_lines.draw_to(x0 + scope_width, 0, 0 + scope_lower)
        scope_lines.draw_to(x0 + scope_width, 0, z0 + scope_lower)
        scope_lines.moveTo(0, 0, 0 + scope_lower)
        scope_lines.draw_to(0, 0,0 + scope_lower - 0.2 )
        #
        scope_lines.moveTo(x0, 0, -z0 + scope_upper)
        scope_lines.draw_to(x0, 0,  0 + scope_upper)
        scope_lines.draw_to(x0 + scope_width, 0, 0 + scope_upper)
        scope_lines.draw_to(x0 + scope_width, 0, -z0 + scope_upper)
        scope_lines.moveTo(0, 0, 0 + scope_upper)
        scope_lines.draw_to(0, 0, 0 + scope_upper + 0.2)

        scope_lines.setThickness(3)
        node = scope_lines.create()

        self.scope = NodePath(node)
        self.scope.setColorScale(0, 1, 0, .9)

        self.scope.reparentTo(render2d)

        # Add the spinCameraTask procedure to the task manager.
        self.taskMgr.add(self.spinCameraTask, "SpinCameraTask")
        self.taskMgr.add(self.moveTanksTask, "MoveTanksTask")

    def moveTanksTask(self, task):
        Ax1 = 25;
        Ay1 = 18
        Bx1 = -0.1;
        By1 = 0.2
        x = Ax1 * sin(Bx1 * task.time) + 10
        y = Ay1 * sin(By1 * task.time)
        dx = Ax1 * Bx1 * cos(Bx1 * task.time)
        dy = Ay1 * By1 * cos(By1 * task.time)
        heading = math.degrees(math.atan2(dy, dx))
        self.tank1.setPos(x, y, 0)
        self.tank1.setH(heading)

        Ax1 = 16;
        Ay1 = 18
        Bx1 = 0.25;
        By1 = 0.3
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
        self.camera.setPos(pos[0], pos[1], 5)
        ort = self.camera.getHpr()
        self.camera.setHpr(ort[0], 0, 0)
        # self.camera.setPos(100, 100, 0)
        # self.camera.setHpr(180-angleDegrees+10*sin(task.time), 0, 0)
        return Task.cont


app = MyApp()
app.run()
