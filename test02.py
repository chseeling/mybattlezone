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

from pandac.PandaModules import WindowProperties

class MyApp(ShowBase):
    def __init__(self):
        ShowBase.__init__(self)
        base.setBackgroundColor(0, 0, 0)
        # base.disableMouse()
        props = WindowProperties()
        props.setCursorHidden(True)
        props.setMouseMode(WindowProperties.M_relative)
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
        self.ground.reparentTo(self.render)
        # self.mountain_line.reparentTo(self.render)
        # self.mountain.reparentTo(self.render)
        # self.cube01.reparentTo(self.render)
        # self.pyramid.reparentTo(self.render)
        # Apply scale and position transforms on the model.
        scale = 5
        # self.tank.setScale(1, 1, 1)
        # self.cube01.setScale(scale, scale, scale)
        # self.pyramid.setScale(scale, scale, scale)
        self.ground.setScale(50, 50, 1)
        self.mountain.setScale(30, 1, 30)

        # render tanks
        self.tank.setPos(0, 0, 0)
        tank1 = render.attachNewNode("Tank-Placeholder")
        tank2 = render.attachNewNode("Tank-Placeholder")
        tank1.setPos(100, 100, 0)
        tank2.setPos(150, 70, 0)
        self.tank.instanceTo(tank1)
        self.tank.instanceTo(tank2)

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
            #self.mountain.instanceTo(placeholder)

        with open('models/digitization01_cleaned_02.json', "r") as f:
            data = json.load(f)
        points = data['points']
        lines_def = data['lines']

#   scale mountain_line
        n = 2   # number of repeats in circumference
        # find range of x
        xmin = points[0][0]
        xmax = xmin
        for point in points[1:]:
            if xmin > point[0]:
                xmin = point[0]
            if xmax < point[0]:
                xmax = point[0]
        radius = (xmax-xmin)*n/2.0/math.pi
        print(radius)
        # map to circle of radius rad
        points_mapped = []
        for point in points:
            z = point[2]
            theta = (point[0] - xmin)/radius
            x = math.cos(-theta)
            y = math.sin(-theta)
            z = point[2]
            points_mapped.append([x, y, z])
        points = points_mapped

        lines = LineSegs()
        for line_def in lines_def:
            # print(line_def)
            idx0 = line_def[0] - 1
            lines.moveTo(points[idx0][0], points[idx0][1], points[idx0][2])
            for idx1 in line_def[1:]:
                # print(idx1)
                idx1 = idx1 - 1
                lines.drawTo(points[idx1][0], points[idx1][1], points[idx1][2])

        lines.setThickness(4)
        node = lines.create()
        self.np = NodePath(node)
        scale = 4000
        for i in range(n):
            angleRadians = 2*pi/n*i
            placeholder = render.attachNewNode("MountainLine-Placeholder")
            placeholder.setH(placeholder, 360/n*i)
            # placeholder.setPos(sin(angleRadians), cos(angleRadians), 0)
            placeholder.setScale(scale, scale, scale/n/2)
            self.np.instanceTo(placeholder)


        # np.set_color(0, 0, 1, 0)
        self.np.setColorScale(0, 1, 0, 1.0)
        # self.np.setScale(10, 10, 10)
        # self.np.setPos(70,0,0)
        # self.np.setH(self.np, 0)

        # self.np.reparentTo(render)
        # b = self.np.getTightBounds()
        # print(b)

        alight = AmbientLight('ambientLight')
        alight.setColor(Vec4(0, 0, 0, 0))  # ambient light is dim red
        #alightNP = self.render.attachNewNode(alight)

        # Add the spinCameraTask procedure to the task manager.
        #self.taskMgr.add(self.spinCameraTask, "SpinCameraTask")

    # Define a procedure to move the camera.
    def spinCameraTask(self, task):
        angleDegrees = task.time * 10.0
        angleRadians = angleDegrees * (pi / 180.0)
        rad = 20
        self.camera.setPos(rad * sin(angleRadians), rad * cos(angleRadians), 2)
        self.camera.lookAt(self.tank, 0, 0, 0)
        # self.camera.setPos(100, 100, 0)
        # self.camera.setHpr(180-angleDegrees+10*sin(task.time), 0, 0)
        return Task.cont


app = MyApp()
app.run()
