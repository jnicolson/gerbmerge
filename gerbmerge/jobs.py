#!/usr/bin/env python
"""
This module reads all Gerber and Excellon files and stores the
data for each job.

--------------------------------------------------------------------

This program is licensed under the GNU General Public License (GPL)
Version 3.  See http://www.fsf.org for details of the license.

Rugged Circuits LLC
http://ruggedcircuits.com/gerbmerge
"""

import builtins
import copy

from . import (aptable, config, util)
from .gerber import GerberParser

# Parsing Gerber/Excellon files is currently very brittle. A more robust
# RS274X/Excellon parser would be a good idea and allow this program to work
# robustly with more than just Eagle CAM files.

# Reminder to self:
#
#   D01 -- move and draw line with exposure on
#   D02 -- move with exposure off
#   D03 -- flash aperture

# TODO:
#
# Need to add error checking for metric/imperial units matching those of the files input
# Check fabdrawing.py to see if writeDrillHits is scaling properly (the
# only place it is used)

# A Job is a single input board. It is expected to have:
#    - a board outline file in RS274X format
#    - several (at least one) Gerber files in RS274X format
#    - a drill file in Excellon format
#
# The board outline and Excellon filenames must be given separately.
# The board outline file determines the extents of the job.


class Job(object):
    def __init__(self, name):
        self.name = name

        # Minimum and maximum (X,Y) absolute co-ordinates encountered
        # in GERBER data only (not Excellon). Note that coordinates
        # are stored in hundred-thousandsths of an inch so 9999999 is 99.99999
        # inches.
        # in the case all coordinates are < 0, this will prevent maxx and maxy
        # from defaulting to 0
        self.maxx = self.maxy = -9999999
        self.minx = self.miny = 9999999

        # Excellon commands are grouped by tool number in a dictionary.
        # This is to help sorting all jobs and writing out all plunge
        # commands for a single tool.
        #
        # The key to this dictionary is the full tool name, e.g., T03
        # as a string. Each command is an (X,Y) integer tuple.
        self.xcommands = {}

        # This is a dictionary mapping LOCAL tool names (e.g., T03) to diameters
        # in inches for THIS JOB. This dictionary will be initially empty
        # for old-style Excellon files with no embedded tool sizes. The
        # main program will construct this dictionary from the global tool
        # table in this case, once all jobs have been read in.
        self.xdiam = {}

        # This is a mapping from tool name to diameter for THIS JOB
        self.ToolList = None

        # How many times to replicate this job if using auto-placement
        self.Repeat = 1

        # How many decimal digits of precision there are in the Excellon file.
        # A value greater than 0 overrides the global ExcellonDecimals setting
        # for this file, allowing jobs with different Excellon decimal settings
        # to be combined.
        self.ExcellonDecimals = 0     # 0 means global value prevails

        self.drills = None
        self.gerbers = {}

    @property
    def width(self):
        # add metric support (1/1000 mm vs. 1/100,000 inch)
        # TODO: config
        if config.Config['measurementunits'] == 'inch':
            "Return width in INCHES"
            return float(self.maxx - self.minx) * 0.00001
        else:
            return float(self.maxx - self.minx) * 0.001

    @property
    def height(self):
        # add metric support (1/1000 mm vs. 1/100,000 inch)
        # TODO: config
        if config.Config['measurementunits'] == 'inch':
            "Return height in INCHES"
            return float(self.maxy - self.miny) * 0.00001
        else:
            return float(self.maxy - self.miny) * 0.001

    def jobarea(self):
        return self.width * self.height

    def maxdimension(self):
        return max(self.width, self.height)

    def mincoordinates(self):
        "Return minimum X and Y coordinate"

        return self.minx, self.miny

    def parseExcellon(self, fullname, decimals):
        from .excellon import ExcellonParser
        self.drills = ExcellonParser(fullname, decimals)
        self.drills.parse()

    def hasLayer(self, layername):
        return layername in self.gerbers

    def findTools(self, diameter):
        "Find the tools, if any, with the given diameter in inches. There may be more than one!"
        L = []
        for tool, diam in self.drills.xdiam.items():
            if diam == diameter:
                L.append(tool)
        return L

    def fixcoordinates(self, x_shift, y_shift):
        "Add x_shift and y_shift to all coordinates in the job"

        # Shift maximum and minimum coordinates
        self.minx += x_shift
        self.maxx += x_shift
        self.miny += y_shift
        self.maxy += y_shift

        # Shift all commands
        for layer, command in self.commands.items():

            # Loop through each command in each layer
            for index in range(len(command)):
                c = command[index]

                # Shift X and Y coordinate of command
                if isinstance(
                        c, tuple):  # ensure that command is of type tuple
                    command_list = list(c)  # convert tuple to list
                    if isinstance(command_list[0], int) \
                            and isinstance(command_list[1], int):  # ensure that first two elemenst are integers
                        command_list[0] += x_shift
                        command_list[1] += y_shift
                    # convert list back to tuple
                    command[index] = tuple(command_list)

            self.commands[layer] = command  # set modified command

        # Shift all excellon commands
        for tool, command in self.drills.xcommands.items():

            # Loop through each command in each layer
            for index in range(len(command)):
                c = command[index]

                # Shift X and Y coordinate of command
                command_list = list(c)  # convert tuple to list
                if isinstance(command_list[0], int) \
                        and isinstance(command_list[1], int):  # ensure that first two elemenst are integers
                    command_list[0] += x_shift / 10
                    command_list[1] += y_shift / 10
                # convert list back to tuple
                command[index] = tuple(command_list)

            self.drills.xcommands[tool] = command  # set modified command

    def aperturesAndMacros(self, layername):
        """Return dictionaries whose keys are all necessary aperture names and macro names for this layer."""

        GAT = config.GAT

        if layername not in self.gerbers:
            return {}, {}

        else:
            apertures = self.gerbers[layername].apertures

            apdict = {}.fromkeys(apertures)
            apmlist = [GAT[ap].dimx for ap in apertures if GAT[ap].apname == 'Macro']
            apmdict = {}.fromkeys(apmlist)

            return apdict, apmdict

    def parseGerber(self, filename, layername, updateExtents=0):
        self.gerbers[layername] = GerberParser()
        self.gerbers[layername].parse(filename, updateExtents)
        if updateExtents:
            self.updateExtents(self.gerbers[layername].extents)

    def updateExtents(self, extents):
        self.minx, self.miny, self.maxx, self.maxy = extents
        self.drills.updateExtents(extents)
        for job in self.gerbers:
            self.gerbers[job].updateExtents(extents)

    def trimExcellon(self):
        self.drills.trim()

    def trimGerber(self):
        for layername in self.gerbers.keys():
            self.gerbers[layername].trim()

# This class encapsulates a Job object, providing absolute
# positioning information.


class JobLayout(object):
    def __init__(self, job):
        self.job = job
        self.x = None
        self.y = None

    def canonicalize(self):       # Must return a JobLayout object as a list
        return [self]

    def writeGerber(self, fid, layername):
        assert self.x is not None
        self.job.gerbers[layername].write(fid, self.x, self.y)

    def aperturesAndMacros(self, layername):
        return self.job.aperturesAndMacros(layername)

    def writeExcellon(self, fid, diameter):
        assert self.x is not None
        self.job.drills.write(fid, diameter, self.x, self.y)

    def writeDrillHits(self, fid, diameter, toolNum):
        assert self.x is not None
        self.job.drills.writeDrillHits(fid, diameter, toolNum, self.x, self.y)

    def writeCutLines(self, fid, drawing_code, X1, Y1, X2, Y2):
        """Draw a board outline using the given aperture code"""
        def notEdge(x, X):
            return round(abs(1000 * (x - X)))

        # assert self.x and self.y

# if job has a boardoutline layer, write it, else calculate one
        outline_layer = 'boardoutline'
        if self.job.hasLayer(outline_layer):
            # somewhat of a hack here; making use of code in gerbmerge, around line 516,
            # we are going to replace the used of the existing draw code in the boardoutline
            # file with the one passed in (which was created from layout.cfg ('CutLineWidth')
            # It is a hack in that we are assuming there is only one draw code in the
            # boardoutline file. We are just going to ignore that definition and change
            # all usages of that code to our new one. As a side effect, it will make
            # the merged boardoutline file invalid, but we aren't using it with
            # this method.
            temp = []
            for x in self.job.gerbers[outline_layer].commands:
                if x[0] == 'D':
                    # replace old aperture with new one
                    temp.append(drawing_code)
                else:
                    temp.append(x)  # keep old command
            self.job.gerbers[outline_layer].commands = temp

            # self.job.writeGerber(fid, outline_layer, X1, Y1)
            self.writeGerber(fid, outline_layer)

        else:
            radius = config.GAT[drawing_code].dimx / 2.0

            # Start at lower-left, proceed clockwise
            x = self.x - radius
            y = self.y - radius

            left = notEdge(self.x, X1)
            right = notEdge(self.x + self.width, X2)
            bot = notEdge(self.y, Y1)
            top = notEdge(self.y + self.height, Y2)

            BL = ((x), (y))
            TL = ((x), (y + self.height + 2 * radius))
            TR = ((x + self.width + 2 * radius),
                  (y + self.height + 2 * radius))
            BR = ((x + self.width + 2 * radius), (y))

            if not left:
                BL = (BL[0] + 2 * radius, BL[1])
                TL = (TL[0] + 2 * radius, TL[1])

            if not top:
                TL = (TL[0], TL[1] - 2 * radius)
                TR = (TR[0], TR[1] - 2 * radius)

            if not right:
                TR = (TR[0] - 2 * radius, TR[1])
                BR = (BR[0] - 2 * radius, BR[1])

            if not bot:
                BL = (BL[0], BL[1] + 2 * radius)
                BR = (BR[0], BR[1] + 2 * radius)

            BL = (util.in2gerb(BL[0]), util.in2gerb(BL[1]))
            TL = (util.in2gerb(TL[0]), util.in2gerb(TL[1]))
            TR = (util.in2gerb(TR[0]), util.in2gerb(TR[1]))
            BR = (util.in2gerb(BR[0]), util.in2gerb(BR[1]))

            # The "if 1 or ..." construct draws all four sides of the job. By
            # removing the 1 from the expression, only the sides that do not
            # correspond to panel edges are drawn. The former is probably better
            # since panels tend to have a little slop from the cutting operation
            # and it's easier to just cut it smaller when there's a cut line.
            # The way it is now with "if 1 or....", much of this function is
            # unnecessary. Heck, we could even just use the boardoutline layer
            # directly.
            if 1 or left:
                fid.write('X%07dY%07dD02*\n' % BL)
                fid.write('X%07dY%07dD01*\n' % TL)

            if 1 or top:
                if not left:
                    fid.write('X%07dY%07dD02*\n' % TL)
                fid.write('X%07dY%07dD01*\n' % TR)

            if 1 or right:
                if not top:
                    fid.write('X%07dY%07dD02*\n' % TR)
                fid.write('X%07dY%07dD01*\n' % BR)

            if 1 or bot:
                if not right:
                    fid.write('X%07dY%07dD02*\n' % BR)
                fid.write('X%07dY%07dD01*\n' % BL)

    def setPosition(self, x, y):
        self.x = x
        self.y = y

    @property
    def width(self):
        return self.job.width

    @property
    def height(self):
        return self.job.height

    def jobarea(self):
        return self.job.jobarea()

    def drillhits(self, diameter):
        return self.job.drills.drillhits(diameter)


def rotateJob(job, degrees=90, firstpass=True):
    """Create a new job from an existing one, rotating by specified degrees in 90 degree passes"""
    GAT = config.GAT
    GAMT = config.GAMT
    # print("rotating job:", job.name, degrees, firstpass)
    if firstpass:
        if degrees == 270:
            J = Job(job.name + '*rotated270')
        elif degrees == 180:
            J = Job(job.name + '*rotated180')
        else:
            J = Job(job.name + '*rotated90')
    else:
        J = Job(job.name)

    # Keep the origin (lower-left) in the same place
    J.maxx = job.minx + job.maxy - job.miny
    J.maxy = job.miny + job.maxx - job.minx
    J.minx = job.minx
    J.miny = job.miny

    RevGAT = config.buildRevDict(GAT)   # RevGAT[hash] = aperturename
    RevGAMT = config.buildRevDict(GAMT)  # RevGAMT[hash] = aperturemacroname

    # Keep list of tool diameters and default tool list
    J.drills = copy.deepcopy(job.drills)
    # J.xdiam = job.xdiam
    # J.ToolList = job.ToolList
    J.Repeat = job.Repeat

    # D-code translation table is the same, except we have to rotate
    # those apertures which have an orientation: rectangles, ovals, and macros.

    ToolChangeReplace = {}
    for layername in job.gerbers.keys():
        J.gerbers[layername] = GerberParser()
        J.gerbers[layername].apxlat = {}

        for ap in job.gerbers[layername].apxlat.keys():
            code = job.gerbers[layername].apxlat[ap]
            A = GAT[code]

            if A.apname in ('Circle', 'Octagon'):
                # This aperture is fine. Copy it over.
                J.gerbers[layername].apxlat[ap] = code
                continue

            # Must rotate the aperture
            APR = A.rotated(RevGAMT)

            # Does it already exist in the GAT?
            hash = APR.hash()
            try:
                # Yup...add it to apxlat
                newcode = RevGAT[hash]
            except KeyError:
                # Must add new aperture to GAT
                newcode = aptable.addToApertureTable(APR)

                # Rebuild RevGAT
                # RevGAT = config.buildRevDict(GAT)
                RevGAT[hash] = newcode

            J.gerbers[layername].apxlat[ap] = newcode

            # Must also replace all tool change commands from
            # old code to new command.
            ToolChangeReplace[code] = newcode

    # Now we copy commands, rotating X,Y positions.
    # Rotations will occur counterclockwise about the
    # point (minx,miny). Then, we shift to the right
    # by the height so that the lower-left point of
    # the rotated job continues to be (minx,miny).
    #
    # We also have to take aperture change commands and
    # replace them with the new aperture code if we have
    # a rotation.
    offset = job.maxy - job.miny
    for layername in job.gerbers.keys():
        J.gerbers[layername].commands = []
        J.gerbers[layername].apertures = []

        for cmd in job.gerbers[layername].commands:
            # Is it a drawing command?
            if isinstance(cmd, tuple):
                if len(cmd) == 3:
                    x, y, d = map(builtins.int, cmd)
                    II = JJ = None
                else:
                    # J is already used as Job object
                    x, y, II, JJ, d, signed = map(builtins.int, cmd)
            else:
                # No, must be a string indicating aperture change, G-code, or
                # RS274-X command.
                if cmd[0] in ('G', '%'):
                    # G-codes and RS274-X commands are just copied verbatim and
                    # not affected by rotation
                    J.gerbers[layername].commands.append(cmd)
                    continue

                # It's a D-code. See if we need to replace aperture changes with a rotated aperture.
                # But only for D-codes >= 10.
                if int(cmd[1:]) < 10:
                    J.gerbers[layername].commands.append(cmd)
                    continue

                try:
                    newcmd = ToolChangeReplace[cmd]
                    J.gerbers[layername].commands.append(newcmd)
                    J.gerbers[layername].apertures.append(newcmd)
                except KeyError:
                    J.gerbers[layername].commands.append(cmd)
                    J.gerbers[layername].apertures.append(cmd)
                continue

            # (X,Y) --> (-Y,X) effects a 90-degree counterclockwise shift
            # Adding 'offset' to -Y maintains the lower-left origin of
            # (minx,miny).
            newx = -(y - job.miny) + job.minx + offset
            newy = (x - job.minx) + job.miny

            # For circular interpolation commands, (I,J) components are always relative
            # so we do not worry about offsets, just reverse their sense, i.e., I becomes J
            # and J becomes I. For 360-degree circular interpolation, I/J are signed and we
            # must map (I,J) --> (-J,I).
            if II is not None:
                if signed:
                    J.gerbers[layername].commands.append(
                        (newx, newy, -JJ, II, d, signed))
                else:
                    J.gerbers[layername].commands.append(
                        (newx, newy, JJ, II, d, signed))
            else:
                J.gerbers[layername].commands.append((newx, newy, d))

        if 0:
            print(job.minx, job.miny, offset)
            print(layername)
            print(J.gerbers[layername].commands)

    # Finally, rotate drills. Offset is in hundred-thousandths (2.5) while Excellon
    # data is in 2.4 format.
    for tool in job.drills.xcommands.keys():
        J.drills.xcommands[tool] = []

        for x, y in job.drills.xcommands[tool]:
            # add metric support (1/1000 mm vs. 1/100,000 inch)
            # NOTE: There don't appear to be any need for a change. The usual
            # x10 factor seems to apply

            newx = -(10 * y - job.miny) + job.minx + offset
            newy = (10 * x - job.minx) + job.miny

            newx = int(round(newx / 10.0))
            newy = int(round(newy / 10.0))

            J.drills.xcommands[tool].append((newx, newy))

    # Rotate some more if required
    degrees -= 90
    if degrees > 0:
        return rotateJob(J, degrees, False)
    else:
        # print("rotated:", J.name)
        return J
