#!/usr/bin/env python

"""
Merge several RS274X (Gerber) files generated by Eagle into a single
job.

This program expects that each separate job has at least three files:
  - a board outline (RS274X)
  - data layers (copper, silkscreen, etc. in RS274X format)
  - an Excellon drill file

Furthermore, it is expected that each job was generated by Eagle
using the GERBER_RS274X plotter, except for the drill file which
was generated by the EXCELLON plotter.

This program places all jobs into a single job.

--------------------------------------------------------------------

This program is licensed under the GNU General Public License (GPL)
Version 3.  See http://www.fsf.org for details of the license.

Rugged Circuits LLC
http://ruggedcircuits.com/gerbmerge
"""

import sys

from . import (aptable, config, drillcluster, fabdrawing, jobs, parselayout,
               placement, schwartz, scoring, strokes, tilesearch1, tilesearch2,
               util)


VERSION_MAJOR = 1
VERSION_MINOR = '9b'

RANDOM_SEARCH = 1
EXHAUSTIVE_SEARCH = 2
FROM_FILE = 3
config.AutoSearchType = RANDOM_SEARCH
config.RandomSearchExhaustiveJobs = 2
config.PlacementFile = None

# This is a handle to a GUI front end, if any, else None for command-line usage
GUI = None


# changed these two writeGerberHeader files to take metric units (mm) into
# account:


def writeGerberHeader22degrees(fid):
    if config.Config['measurementunits'] == 'inch':
        fid.write(
            """%FSLAX25Y25*%
%LPD*%
%AMOC8*
5,1,8,0,0,1.08239X$1,22.5*
%
""")
    else:    # assume mm - also remove eagleware hack for %AMOC8
        fid.write(
            """%FSLAX53Y53*%
%MOMM*%
%LPD*%
""")


def writeGerberHeader0degrees(fid):
    if config.Config['measurementunits'] == 'inch':
        fid.write(
            """%FSLAX25Y25*%
%LPD*%
%AMOC8*
5,1,8,0,0,1.08239X$1,0.0*
%
""")
    else:    # assume mm - also remove eagleware hack for %AMOC8
        fid.write(
            """%FSLAX53Y53*%
%MOMM*%
%LPD*%
""")


writeGerberHeader = writeGerberHeader22degrees


def writeApertureMacros(fid, usedDict):
    keys = sorted(config.GAMT.keys())
    for key in keys:
        if key in usedDict:
            config.GAMT[key].writeDef(fid)


def writeApertures(fid, usedDict):
    keys = sorted(config.GAT.keys())
    for key in keys:
        if key in usedDict:
            config.GAT[key].writeDef(fid)


def writeGerberFooter(fid):
    fid.write('M02*\n')


def writeExcellonHeader(fid):
    if config.Config['measurementunits'] != 'inch':  # metric - mm
        fid.write("""M48
METRIC,0000.00
""")
    else:
        fid.write("""M48
INCH
""")


def writeExcellonEndHeader(fid):
    fid.write('%\n')


def writeExcellonFooter(fid):
    fid.write('M30\n')


def writeExcellonToolHeader(fid, tool, size):
    fid.write('%sC%f\n' % (tool, size))


def writeExcellonTool(fid, tool):
    fid.write('%s\n' % tool)


def writeFiducials(fid, drawcode, OriginX, OriginY, MaxXExtent, MaxYExtent):
    """Place fiducials at arbitrary points. The FiducialPoints list in the config specifies
    sets of X,Y co-ordinates. Positive values of X/Y represent offsets from the lower left
    of the panel. Negative values of X/Y represent offsets from the top right. So:
           FiducialPoints = 0.125,0.125,-0.125,-0.125
    means to put a fiducial 0.125,0.125 from the lower left and 0.125,0.125 from the top right"""
    fid.write('%s*\n' % drawcode)    # Choose drawing aperture

    fList = config.Config['fiducialpoints'].split(',')
    for i in range(0, len(fList), 2):
        x, y = float(fList[i]), float(fList[i + 1])
        if x >= 0:
            x += OriginX
        else:
            x = MaxXExtent + x
        if y >= 0:
            y += OriginX
        else:
            y = MaxYExtent + y
        fid.write('X%07dY%07dD03*\n' % (util.in2gerb(x), util.in2gerb(y)))


def writeCropMarks(fid, drawing_code, OriginX,
                   OriginY, MaxXExtent, MaxYExtent):
    """Add corner crop marks on the given layer"""

    # Draw 125mil lines at each corner, with line edge right up against
    # panel border. This means the center of the line is D/2 offset
    # from the panel border, where D is the drawing line diameter.

    # use 3mm lines for metric

    fid.write('%s*\n' % drawing_code)    # Choose drawing aperture

    offset = config.GAT[drawing_code].dimx / 2.0

    # should we be using 'cropmarkwidth' from config.py?
    if config.Config['measurementunits'] == 'inch':
        cropW = 0.125  # inch
    else:
        cropW = 3  # mm

    # Lower-left
    x = OriginX + offset
    y = OriginY + offset
    fid.write('X%07dY%07dD02*\n' %
              (util.in2gerb(x + cropW), util.in2gerb(y + 0.000)))
    fid.write('X%07dY%07dD01*\n' %
              (util.in2gerb(x + 0.000), util.in2gerb(y + 0.000)))
    fid.write('X%07dY%07dD01*\n' %
              (util.in2gerb(x + 0.000), util.in2gerb(y + cropW)))

    # Lower-right
    x = MaxXExtent - offset
    y = OriginY + offset
    fid.write('X%07dY%07dD02*\n' %
              (util.in2gerb(x + 0.000), util.in2gerb(y + cropW)))
    fid.write('X%07dY%07dD01*\n' %
              (util.in2gerb(x + 0.000), util.in2gerb(y + 0.000)))
    fid.write('X%07dY%07dD01*\n' %
              (util.in2gerb(x - cropW), util.in2gerb(y + 0.000)))

    # Upper-right
    x = MaxXExtent - offset
    y = MaxYExtent - offset
    fid.write('X%07dY%07dD02*\n' %
              (util.in2gerb(x - cropW), util.in2gerb(y + 0.000)))
    fid.write('X%07dY%07dD01*\n' %
              (util.in2gerb(x + 0.000), util.in2gerb(y + 0.000)))
    fid.write('X%07dY%07dD01*\n' %
              (util.in2gerb(x + 0.000), util.in2gerb(y - cropW)))

    # Upper-left
    x = OriginX + offset
    y = MaxYExtent - offset
    fid.write('X%07dY%07dD02*\n' %
              (util.in2gerb(x + 0.000), util.in2gerb(y - cropW)))
    fid.write('X%07dY%07dD01*\n' %
              (util.in2gerb(x + 0.000), util.in2gerb(y + 0.000)))
    fid.write('X%07dY%07dD01*\n' %
              (util.in2gerb(x + cropW), util.in2gerb(y + 0.000)))


def disclaimer():
    if (config.Config['skipdisclaimer'] > 0):  # remove annoying disclaimer
        return

    print("""
****************************************************
*           R E A D    C A R E F U L L Y           *
*                                                  *
* This program comes with no warranty. You use     *
* this program at your own risk. Do not submit     *
* board files for manufacture until you have       *
* thoroughly inspected the output of this program  *
* using a previewing program such as:              *
*                                                  *
* Windows:                                         *
*          - GC-Prevue <http://www.graphicode.com> *
*          - ViewMate  <http://www.pentalogix.com> *
*                                                  *
* Linux:                                           *
*          - gerbv <http://gerbv.sourceforge.net>  *
*                                                  *
* By using this program you agree to take full     *
* responsibility for the correctness of the data   *
* that is generated by this program.               *
****************************************************

To agree to the above terms, press 'y' then Enter.
Any other key will exit the program.

""")

    s = input()
    if s == 'y':
        print("")
        return

    print("\nExiting...")
    sys.exit(0)


def tile_jobs(Jobs):
    """Take a list of raw Job objects and find best tiling by calling tile_search"""

    # We must take the raw jobs and construct a list of 4-tuples (Xdim,Ydim,job,rjob).
    # This means we must construct a rotated job for each entry. We first sort all
    # jobs from largest to smallest. This should give us the best tilings first so
    # we can interrupt the tiling process and get a decent layout.
    L = []
    # sortJobs = schwartz.schwartz(Jobs, jobs.Job.jobarea)
    sortJobs = schwartz.schwartz(Jobs, jobs.Job.maxdimension)
    sortJobs.reverse()

    for job in sortJobs:
        Xdim = job.width
        Ydim = job.height
        # NOTE: This will only try 90 degree rotations though 180 & 270 are
        # available

        rjob = jobs.rotateJob(job, 90)

        for count in range(job.Repeat):
            L.append((Xdim, Ydim, job, rjob))

    PX, PY = config.Config['panelwidth'], config.Config['panelheight']
    if config.AutoSearchType == RANDOM_SEARCH:
        tile = tilesearch2.tile_search2(L, PX, PY)
    else:
        tile = tilesearch1.tile_search1(L, PX, PY)

    if not tile:
        # add metric support (1/1000 mm vs. 1/100,000 inch)
        if config.Config['measurementunits'] == 'inch':
            raise RuntimeError(
                'Panel size %.2f"x%.2f" is too small to hold jobs' % (PX, PY))
        else:
            raise RuntimeError(
                'Panel size %.2fmmx%.2fmm is too small to hold jobs' % (PX, PY))

    return tile


def merge(args, gui=None):
    writeGerberHeader = writeGerberHeader22degrees

    global GUI
    GUI = gui

    skipDisclaimer = 0

    if args.octagons == 'rotate':
        writeGerberHeader = writeGerberHeader0degrees
    elif args.octagons == 'normal':
        writeGerberHeader = writeGerberHeader22degrees

    if args.random_search:
        config.AutoSearchType = RANDOM_SEARCH
    elif args.full_search:
        config.AutoSearchType = EXHAUSTIVE_SEARCH

    config.RandomSearchExhaustiveJobs = args.rs_fsjobs
    config.SearchTimeout = args.search_timeout

    if args.place_file:
        config.AutoSearchType = FROM_FILE
        config.PlacementFile = args.place_file

    if args.no_trim_gerber:
        config.TrimGerber = 0

    if args.no_trim_excellon:
        config.TrimExcellon = 0

    if args.skipdisclaimer:
        skipDisclaimer = 1

    if (skipDisclaimer == 0):
        disclaimer()

    # Load up the Jobs global dictionary, also filling out GAT, the
    # global aperture table and GAMT, the global aperture macro table.
    updateGUI("Reading job files...")
    config.parseConfigFile(args.configfile)

    # Force all X and Y coordinates positive by adding absolute value of
    # minimum X and Y
    for name, job in config.Jobs.items():
        min_x, min_y = job.mincoordinates()
        shift_x = shift_y = 0
        if min_x < 0:
            shift_x = abs(min_x)
        if min_y < 0:
            shift_y = abs(min_y)
        if (shift_x > 0) or (shift_y > 0):
            job.fixcoordinates(shift_x, shift_y)

    # Display job properties
    for job in config.Jobs.values():
        print('Job %s:' % job.name, "\n")
        if job.Repeat > 1:
            print('(%d instances)' % job.Repeat)
        else:
            print("\n")
        print('  Extents: (%d,%d)-(%d,%d)' %
              (job.minx, job.miny, job.maxx, job.maxy))
        # add metric support (1/1000 mm vs. 1/100,000 inch)
        if config.Config['measurementunits'] == 'inch':
            print('  Size: %f" x %f"' % (job.width, job.height))
        else:
            print('  Size: %5.3fmm x %5.3fmm' %
                  (job.width, job.height))
        print("\n")

    # Trim drill locations and flash data to board extents
    if config.TrimExcellon:
        updateGUI("Trimming Excellon data...")
        print('Trimming Excellon data to board outlines ...')
        for job in config.Jobs.values():
            job.trimExcellon()

    if config.TrimGerber:
        updateGUI("Trimming Gerber data...")
        print('Trimming Gerber data to board outlines ...')
        for job in config.Jobs.values():
            job.trimGerber()

    # We start origin at (0.1", 0.1") just so we don't get numbers close to 0
    # which could trip up Excellon leading-0 elimination.
    # I don't want to change the origin. If this a code bug, then it should be
    # fixed (SDD)
    OriginX = OriginY = 0  # 0.1

    # Read the layout file and construct the nested list of jobs. If there
    # is no layout file, do auto-layout.
    updateGUI("Performing layout...")
    print('Performing layout ...')

    Place = placement.Placement()

    if args.layoutfile:
        Layout = parselayout.parseLayoutFile(args.layoutfile)

        # Do the layout, updating offsets for each component job.
        X = OriginX + config.Config['leftmargin']
        Y = OriginY + config.Config['bottommargin']

        for row in Layout:
            row.setPosition(X, Y)
            Y += row.height + config.Config['yspacing']

        # Construct a canonical placement from the layout
        Place.addFromLayout(Layout)

        del Layout

    elif config.AutoSearchType == FROM_FILE:
        Place.addFromFile(config.PlacementFile, config.Jobs)
    else:
        # Do an automatic layout based on our tiling algorithm.
        tile = tile_jobs(config.Jobs.values())

        Place.addFromTiling(
            tile, OriginX + config.Config['leftmargin'], OriginY + config.Config['bottommargin'])

    (MaxXExtent, MaxYExtent) = Place.extents()
    MaxXExtent += config.Config['rightmargin']
    MaxYExtent += config.Config['topmargin']

    # Start printing out the Gerbers. In preparation for drawing cut marks
    # and crop marks, make sure we have an aperture to draw with. Use a 10mil line.
    # If we're doing a fabrication drawing, we'll need a 1mil line.
    OutputFiles = []

    try:
        fullname = config.MergeOutputFiles['placement']
    except KeyError:
        fullname = 'merged.placement.txt'
    Place.write(fullname)
    OutputFiles.append(fullname)

    # For cut lines
    AP = aptable.Aperture('Circle', 'D??', config.Config['cutlinewidth'])
    drawing_code_cut = aptable.findInApertureTable(AP)
    if drawing_code_cut is None:
        drawing_code_cut = aptable.addToApertureTable(AP)

    # For crop marks
    AP = aptable.Aperture('Circle', 'D??',
                          config.Config['cropmarkwidth'])
    drawing_code_crop = aptable.findInApertureTable(AP)
    if drawing_code_crop is None:
        drawing_code_crop = aptable.addToApertureTable(AP)

    # For fiducials
    drawing_code_fiducial_copper = drawing_code_fiducial_soldermask = None
    if config.Config['fiducialpoints']:
        AP = aptable.Aperture('Circle', 'D??',
                              config.Config['fiducialcopperdiameter'])
        drawing_code_fiducial_copper = aptable.findInApertureTable(AP)
        if drawing_code_fiducial_copper is None:
            drawing_code_fiducial_copper = aptable.addToApertureTable(AP)
        AP = aptable.Aperture('Circle', 'D??',
                              config.Config['fiducialmaskdiameter'])
        drawing_code_fiducial_soldermask = aptable.findInApertureTable(AP)
        if drawing_code_fiducial_soldermask is None:
            drawing_code_fiducial_soldermask = aptable.addToApertureTable(AP)

    # For fabrication drawing.
    AP = aptable.Aperture('Circle', 'D??', 0.001)
    drawing_code1 = aptable.findInApertureTable(AP)
    if drawing_code1 is None:
        drawing_code1 = aptable.addToApertureTable(AP)

    updateGUI("Writing merged files...")
    print('Writing merged output files ...')

    for layername in config.LayerList.keys():
        lname = layername
        if lname[0] == '*':
            lname = lname[1:]

        try:
            fullname = config.MergeOutputFiles[layername]
        except KeyError:
            fullname = 'merged.%s.ger' % lname
        OutputFiles.append(fullname)
        # print('Writing %s ...' % fullname)
        fid = open(fullname, 'wt')
        writeGerberHeader(fid)

        # Determine which apertures and macros are truly needed
        apUsedDict = {}
        apmUsedDict = {}

        for job in Place.jobs:
            apd, apmd = job.aperturesAndMacros(layername)
            apUsedDict.update(apd)
            apmUsedDict.update(apmd)

        # Increase aperature sizes to match minimum feature dimension
        if layername in config.MinimumFeatureDimension:

            print('  Thickening', lname, 'feature dimensions ...')

            # Fix each aperture used in this layer
            for ap in list(apUsedDict.keys()):
                new = config.GAT[ap].getAdjusted(
                    config.MinimumFeatureDimension[layername])
                if not new:  # current aperture size met minimum requirement
                    continue
                else:  # new aperture was created
                    # get name of existing aperture or create new one if needed
                    new_code = aptable.findOrAddAperture(new)
                    # the old aperture is no longer used in this layer
                    del apUsedDict[ap]
                    # the new aperture will be used in this layer
                    apUsedDict[new_code] = None

                    # Replace all references to the old aperture with the new
                    # one
                    for joblayout in Place.jobs:
                        job = joblayout.job  # access job inside job layout
                        temp = []
                        if job.hasLayer(layername):
                            for x in job.gerbers[layername].commands:
                                if x == ap:
                                    # replace old aperture with new one
                                    temp.append(new_code)
                                else:
                                    temp.append(x)  # keep old command
                            job.gerbers[layername].commands = temp

        if config.Config['cutlinelayers'] and (
                layername in config.Config['cutlinelayers']):
            apUsedDict[drawing_code_cut] = None

        if config.Config['cropmarklayers'] and (
                layername in config.Config['cropmarklayers']):
            apUsedDict[drawing_code_crop] = None

        if config.Config['fiducialpoints']:
            if ((layername == '*toplayer') or (layername == '*bottomlayer')):
                apUsedDict[drawing_code_fiducial_copper] = None
            elif ((layername == '*topsoldermask') or (layername == '*bottomsoldermask')):
                apUsedDict[drawing_code_fiducial_soldermask] = None

        # Write only necessary macro and aperture definitions to Gerber file
        writeApertureMacros(fid, apmUsedDict)
        writeApertures(fid, apUsedDict)

        # for row in Layout:
        #  row.writeGerber(fid, layername)

        #  # Do cut lines
        #  if config.Config['cutlinelayers'] and (layername in config.Config['cutlinelayers']):
        #    fid.write('%s*\n' % drawing_code_cut)    # Choose drawing aperture
        #    row.writeCutLines(fid, drawing_code_cut, OriginX, OriginY, MaxXExtent, MaxYExtent)

        # Finally, write actual flash data
        for job in Place.jobs:

            updateGUI("Writing merged output files...")
            job.writeGerber(fid, layername)

            if config.Config['cutlinelayers'] and (
                    layername in config.Config['cutlinelayers']):
                # Choose drawing aperture
                fid.write('%s*\n' % drawing_code_cut)
                # print("writing drawcode_cut: %s" % drawing_code_cut)
                job.writeCutLines(fid, drawing_code_cut, OriginX,
                                  OriginY, MaxXExtent, MaxYExtent)

        if config.Config['cropmarklayers']:
            if layername in config.Config['cropmarklayers']:
                writeCropMarks(fid, drawing_code_crop, OriginX,
                               OriginY, MaxXExtent, MaxYExtent)

        if config.Config['fiducialpoints']:
            if ((layername == '*toplayer') or (layername == '*bottomlayer')):
                writeFiducials(fid, drawing_code_fiducial_copper,
                               OriginX, OriginY, MaxXExtent, MaxYExtent)
            elif ((layername == '*topsoldermask') or (layername == '*bottomsoldermask')):
                writeFiducials(fid, drawing_code_fiducial_soldermask,
                               OriginX, OriginY, MaxXExtent, MaxYExtent)

        writeGerberFooter(fid)
        fid.close()

    # Write board outline layer if selected
    fullname = config.Config['outlinelayerfile']
    if fullname and fullname.lower() != "none":
        OutputFiles.append(fullname)
        # print('Writing %s ...' % fullname)
        fid = open(fullname, 'wt')
        writeGerberHeader(fid)

        # Write width-1 aperture to file
        # add metric support
        if config.Config['measurementunits'] == 'inch':
            AP = aptable.Aperture('Circle', 'D10', 0.001)
        else:
            # we'll use 0.25 mm - same as Diptrace
            AP = aptable.Aperture('Circle', 'D10', 0.25)
        AP.writeDef(fid)

        # Choose drawing aperture D10
        fid.write('D10*\n')

        # Draw the rectangle
        fid.write('X%07dY%07dD02*\n' % (util.in2gerb(OriginX),
                                        util.in2gerb(OriginY)))        # Bottom-left
        fid.write('X%07dY%07dD01*\n' % (util.in2gerb(OriginX),
                                        util.in2gerb(MaxYExtent)))     # Top-left
        fid.write('X%07dY%07dD01*\n' % (util.in2gerb(MaxXExtent),
                                        util.in2gerb(MaxYExtent)))  # Top-right
        fid.write('X%07dY%07dD01*\n' % (util.in2gerb(MaxXExtent),
                                        util.in2gerb(OriginY)))     # Bottom-right
        fid.write('X%07dY%07dD01*\n' % (util.in2gerb(OriginX),
                                        util.in2gerb(OriginY)))        # Bottom-left

        writeGerberFooter(fid)
        fid.close()

    # Write scoring layer if selected
    fullname = config.Config['scoringfile']
    if fullname and fullname.lower() != "none":
        OutputFiles.append(fullname)
        # print('Writing %s ...' % fullname)
        fid = open(fullname, 'wt')
        writeGerberHeader(fid)

        # Write width-1 aperture to file
        AP = aptable.Aperture('Circle', 'D10', 0.001)
        AP.writeDef(fid)

        # Choose drawing aperture D10
        fid.write('D10*\n')

        # Draw the scoring lines
        scoring.writeScoring(fid, Place, OriginX, OriginY,
                             MaxXExtent, MaxYExtent)

        writeGerberFooter(fid)
        fid.close()

    # Get a list of all tools used by merging keys from each job's dictionary
    # of tools.
    if 0:
        Tools = {}

        for job in config.Jobs.values():
            for key in job.drills.xcommands.keys():
                Tools[key] = 1

        Tools = sorted(Tools.keys())
    else:
        toolNum = 0

        # First construct global mapping of diameters to tool numbers
        for job in config.Jobs.values():

            for tool, diam in job.drills.xdiam.items():
                if diam in config.GlobalToolRMap:
                    continue

                toolNum += 1
                config.GlobalToolRMap[diam] = "T%02d" % toolNum

        # Cluster similar tool sizes to reduce number of drills
        if config.Config['drillclustertolerance'] > 0:
            config.GlobalToolRMap = drillcluster.cluster(
                config.GlobalToolRMap, config.Config['drillclustertolerance'])
            drillcluster.remap(Place.jobs, config.GlobalToolRMap.items())

        # Now construct mapping of tool numbers to diameters
        for diam, tool in config.GlobalToolRMap.items():
            config.GlobalToolMap[tool] = diam

        # Tools is just a list of tool names
        Tools = sorted(config.GlobalToolMap.keys())

    fullname = config.Config['fabricationdrawingfile']
    if fullname and fullname.lower() != 'none':
        if len(Tools) > strokes.MaxNumDrillTools:
            raise RuntimeError(
                "Only %d different tool sizes supported for fabrication drawing." % strokes.MaxNumDrillTools)

        OutputFiles.append(fullname)
        # print('Writing %s ...' % fullname)
        fid = open(fullname, 'wt')
        writeGerberHeader(fid)
        writeApertures(fid, {drawing_code1: None})
        fid.write('%s*\n' % drawing_code1)    # Choose drawing aperture

        fabdrawing.writeFabDrawing(
            fid, Place, Tools, OriginX, OriginY, MaxXExtent, MaxYExtent)

        writeGerberFooter(fid)
        fid.close()

    # Finally, print out the Excellon
    try:
        fullname = config.MergeOutputFiles['drills']
    except KeyError:
        fullname = 'merged.drills.xln'
    OutputFiles.append(fullname)
    # print('Writing %s ...' % fullname)
    fid = open(fullname, 'wt')

    writeExcellonHeader(fid)
    for tool in Tools:
        try:
            size = config.GlobalToolMap[tool]
        except Exception:
            raise RuntimeError(
                "INTERNAL ERROR: Tool code %s not found in global tool map" % tool)

        writeExcellonToolHeader(fid, tool, size)
    writeExcellonEndHeader(fid)

    # Ensure each one of our tools is represented in the tool list specified
    # by the user.
    for tool in Tools:
        try:
            size = config.GlobalToolMap[tool]
        except Exception:
            raise RuntimeError(
                "INTERNAL ERROR: Tool code %s not found in global tool map" % tool)

        writeExcellonTool(fid, tool)

        # for row in Layout:
        #  row.writeExcellon(fid, size)
        for job in Place.jobs:
            job.writeExcellon(fid, size)

    writeExcellonFooter(fid)
    fid.close()

    updateGUI("Closing files...")

    # Compute stats
    jobarea = 0.0
    # for row in Layout:
    #  jobarea += row.jobarea()
    for job in Place.jobs:
        jobarea += job.jobarea()

    totalarea = ((MaxXExtent - OriginX) * (MaxYExtent - OriginY))

    ToolStats = {}
    drillhits = 0
    for tool in Tools:
        ToolStats[tool] = 0
        # for row in Layout:
        #  hits = row.drillhits(config.GlobalToolMap[tool])
        #  ToolStats[tool] += hits
        #  drillhits += hits
        for job in Place.jobs:
            hits = job.drillhits(config.GlobalToolMap[tool])
            ToolStats[tool] += hits
            drillhits += hits

    try:
        fullname = config.MergeOutputFiles['toollist']
    except KeyError:
        fullname = 'merged.toollist.drl'
    OutputFiles.append(fullname)
    # print('Writing %s ...' % fullname)
    fid = open(fullname, 'wt')

    print('-' * 50)
    # add metric support (1/1000 mm vs. 1/100,000 inch)
    if config.Config['measurementunits'] == 'inch':
        print('     Job Size : %f" x %f"' % (MaxXExtent - OriginX, MaxYExtent - OriginY))
        print('     Job Area : %.2f sq. in.' % totalarea)
    else:
        print('     Job Size : %.2fmm x %.2fmm' % (MaxXExtent - OriginX, MaxYExtent - OriginY))
        print('     Job Area : %.0f mm2' % totalarea)

    print('   Area Usage : %.1f%%' % (jobarea / totalarea * 100))
    print('   Drill hits : %d' % drillhits)
    if config.Config['measurementunits'] == 'inch':
        print('Drill density : %.1f hits/sq.in.' % (drillhits / totalarea))
    else:
        print('Drill density : %.2f hits/cm2' % (100 * drillhits / totalarea))

    print('\nTool List:')
    smallestDrill = 999.9
    for tool in Tools:
        if ToolStats[tool]:
            if config.Config['measurementunits'] == 'inch':
                fid.write('%s %.4fin\n' % (tool, config.GlobalToolMap[tool]))
                print('  %s %.4f" %5d hits' %
                      (tool, config.GlobalToolMap[tool], ToolStats[tool]))
            else:
                fid.write('%s %.4fmm\n' % (tool, config.GlobalToolMap[tool]))
                print('  %s %.4fmm %5d hits' %
                      (tool, config.GlobalToolMap[tool], ToolStats[tool]))
            smallestDrill = min(smallestDrill, config.GlobalToolMap[tool])

    fid.close()
    if config.Config['measurementunits'] == 'inch':
        print("Smallest Tool: %.4fin" % smallestDrill)
    else:
        print("Smallest Tool: %.4fmm" % smallestDrill)

    print("\n")
    print('Output Files :')
    for f in OutputFiles:
        print('  ', f)

    if (MaxXExtent - OriginX) > config.Config['panelwidth'] or (
            MaxYExtent - OriginY) > config.Config['panelheight']:
        print('*' * 75)
        print('*')
        # add metric support (1/1000 mm vs. 1/100,000 inch)
        if config.Config['measurementunits'] == 'inch':
            print('* ERROR: Merged job exceeds panel dimensions of %.1f"x%.1f"' %
                  (config.Config['panelwidth'], config.Config['panelheight']))
        else:
            print('* ERROR: Merged job exceeds panel dimensions of %.1fmmx%.1fmm' %
                  (config.Config['panelwidth'], config.Config['panelheight']))
        print('*')
        print('*' * 75)
        sys.exit(1)

    # Done!
    return 0


def updateGUI(text=None):
    global GUI
    if GUI is not None:
        GUI.updateProgress(text)


def main():
    from . import cli
    args = cli.get_args()
    sys.exit(merge(args))  # run germberge
