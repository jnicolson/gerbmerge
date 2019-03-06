import builtins
import re

from . import amacro, aptable, config, geometry, util

# Patterns for Gerber RS274X file interpretation
apdef_pat = re.compile(r'^%AD(D\d+)([^*$]+)\*%$')  # Aperture definition
apmdef_pat = re.compile(r'^%AM([^*$]+)\*$')  # Aperture macro definition
comment_pat = re.compile(r'G0?4[^*]*\*')  # Comment (GerbTool comment omits the 0)
tool_pat = re.compile(r'(D\d+)\*')  # Aperture selection
gcode_pat = re.compile(r'G(\d{1,2})\*?')  # G-codes
drawXY_pat = re.compile(r'X([+-]?\d+)Y([+-]?\d+)D0?([123])\*')  # Drawing command
drawX_pat = re.compile(r'X([+-]?\d+)D0?([123])\*')  # Drawing command, Y is implied
drawY_pat = re.compile(r'Y([+-]?\d+)D0?([123])\*')  # Drawing command, X is implied
format_pat = re.compile(r'%FS(L|T)?(A|I)(N\d+)?(X\d\d)(Y\d\d)\*%')  # Format statement
layerpol_pat = re.compile(r'^%LP[CD]\*%')  # Layer polarity (D=dark, C=clear)

# Gerber X2
attr_pat = re.compile(r'^\%TF\.(.*?),(.*)\*\%$')

# Circular interpolation drawing commands (from Protel)
cdrawXY_pat = re.compile(r'X([+-]?\d+)Y([+-]?\d+)I([+-]?\d+)J([+-]?\d+)D0?([123])\*')
cdrawX_pat = re.compile(r'X([+-]?\d+)I([+-]?\d+)J([+-]?\d+)D0?([123])\*')  # Y is implied
cdrawY_pat = re.compile(r'Y([+-]?\d+)I([+-]?\d+)J([+-]?\d+)D0?([123])\*')  # X is implied

IgnoreList = ( \
    # These are for Eagle, and RS274X files in general
    re.compile(r'^%OFA0B0\*%$'),
    re.compile(r'^%IPPOS\*%'),
    # Eagle's octagon defined by macro with a $1 parameter
    re.compile(r'^%AMOC8\*$'),
    # Eagle's octagon, 22.5 degree rotation
    re.compile(r'^5,1,8,0,0,1\.08239X\$1,22\.5\*$'),
    # Eagle's octagon, 0.0 degree rotation
    re.compile(r'^5,1,8,0,0,1\.08239X\$1,0\.0\*$'),
    re.compile(r'^\*?%$'),
    re.compile(r'^M0?2\*$'),

    # These additional ones are for Orcad Layout, PCB, Protel, etc.
    re.compile(r'\*'),            # Empty statement
    re.compile(r'^%IN.*\*%'),
    re.compile(r'^%ICAS\*%'),      # Not in RS274X spec.
    re.compile(r'^%MOIN\*%'),
    re.compile(r'^%ASAXBY\*%'),
    re.compile(r'^%AD\*%'),        # GerbTool empty aperture definition
    re.compile(r'^%LN.*\*%')       # Layer name
)


class GerberParser(object):
    def __init__(self):
        # Aperture translation table relative to GAT. Each value
        # is a dictionary where each key is an aperture in the file.
        # The value is the key in the GAT. Example:
        #       apxlat['D10'] = 'D12'
        #       apxlat['D11'] = 'D15'
        #       apxlat['D10'] = 'D15'
        self.apxlat = {}

        # Aperture macro translation table relative to GAMT. This dictionary
        # has as each key an aperture macro name in the file.
        # The value is the key in the GAMT. Example:
        #       apxlat['THD10X'] = 'M1'
        #       apxlat['AND10'] = 'M5'
        self.apmxlat = {}

        # Commands are one of:
        #     A. strings for:
        #           - aperture changes like "D12"
        #           - G-code commands like "G36"
        #           - RS-274X commands like "%LPD*%" that begin with '%'
        #     B. (X,Y,D) triples comprising X,Y integers in the range 0 through 999999
        #        and draw commands that are either D01, D02, or D03. The character
        #        D in the triple above is the integer 1, 2, or 3.
        #     C. (X,Y,I,J,D,s) 6-tuples comprising X,Y,I,J integers in the range 0 through 999999
        #        and D as with (X,Y,D) triples. The 's' integer is non-zero to indicate that
        #        the (I,J) tuple is a SIGNED offset (for multi-quadrant circular interpolation)
        #        else the tuple is unsigned.
        #
        # This variable is, as for apxlat, a dictionary keyed by layer name.
        self.commands = {}

        # This list stores all GLOBAL apertures actually needed by this
        # layer, i.e., apertures specified prior to draw commands.  Each entry
        # is a list of aperture code strings, like 'D12'. This helps us to figure out the
        # minimum number of apertures that need to be written out in the Gerber
        # header of the merged file. Once again, the list of apertures refers to
        # GLOBAL aperture codes in the GAT, not ones local to this layer.
        self.apertures = []

        self.filename = ""
        self.update_extents = 0
        self.minx = self.miny = 9999999
        self.maxx = self.maxy = -9999999

    @property
    def extents(self):
        return self.minx, self.miny, self.maxx, self.maxy

    def inBorders(self, x, y):
        return (x >= self.minx) and (x <= self.maxx) and (
            y >= self.miny) and (y <= self.maxy)

    def updateExtents(self, extents):
        self.minx, self.miny, self.maxx, self.maxy = extents

    def parse(self, filename, updateExtents=0):
        """Do the dirty work. Read the Gerber file given the
           global aperture table GAT and global aperture macro table GAMT"""

        self.filename = filename
        self.update_extents = updateExtents

        GAT = config.GAT
        GAMT = config.GAMT
        # First construct reverse GAT/GAMT, mapping definition to code
        RevGAT = config.buildRevDict(GAT)     # RevGAT[hash] = aperturename
        # RevGAMT[hash] = aperturemacroname
        RevGAMT = config.buildRevDict(GAMT)

        # print('Reading data from %s ...' % filename)

        fid = open(self.filename, 'rt')
        currtool = None

        self.apxlat = {}
        self.apmxlat = {}
        self.commands = []
        self.apertures = []

        # These divisors are used to scale (X,Y) co-ordinates. We store
        # everything as integers in hundred-thousandths of an inch (i.e., M.5
        # format). If we get something in M.4 format, we must multiply by
        # 10. If we get something in M.6 format we must divide by 10, etc.
        x_div = 1.0
        y_div = 1.0

        # Drawing commands can be repeated with X or Y omitted if they are
        # the same as before. These variables store the last X/Y value as
        # integers in hundred-thousandths of an inch.
        last_x = last_y = 0

        # Last modal G-code. Some G-codes introduce "modes", such as circular interpolation
        # mode, and we want to remember what mode we're in. We're interested in:
        #    G01 -- linear interpolation, cancels all circular interpolation modes
        #    G36 -- Turn on polygon area fill
        #    G37 -- Turn off polygon area fill
        last_gmode = 1  # G01 by default, linear interpolation

        # We want to know whether to do signed (G75) or unsigned (G74) I/J offsets. These
        # modes are independent of G01/G02/G03, e.g., Protel will issue multiple G03/G01
        # codes all in G75 mode.
        #    G74 -- Single-quadrant circular interpolation (disables multi-quadrant interpolation)
        #           G02/G03 codes set clockwise/counterclockwise arcs in a single quadrant only
        #           using X/Y/I/J commands with UNSIGNED (I,J).
        #    G75 -- Multi-quadrant circular interpolation --> X/Y/I/J with signed (I,J)
        #           G02/G03 codes set clockwise/counterclockwise arcs in all 4 quadrants
        #           using X/Y/I/J commands with SIGNED (I,J).
        circ_signed = True   # Assume G75...make sure this matches canned header we write out

        # If the very first flash/draw is a shorthand command (i.e., without an Xxxxx or Yxxxx)
        # component then we don't really "see" the first point X00000Y00000. To account for this
        # we use the following Boolean flag as well as the isLastShorthand flag during parsing
        # to manually insert the point X000000Y00000 into the command stream.
        firstFlash = True

        for line in fid:
            # Get rid of CR characters (0x0D) and leading/trailing blanks
            line = line.replace('\x0D', '').strip()

            # Old location of format_pat search. Now moved down into the
            # sub-line parse loop below.

            # RS-274X statement? If so, echo it. Currently, only the "LP" statement is expected
            # (from Protel, of course). These will be distinguished from D-code and G-code
            # commands by the fact that the first character of the string is
            # '%'.
            match = layerpol_pat.match(line)
            if match:
                self.commands.append(line)
                continue

            # See if this is an aperture definition, and if so, map it.
            match = apdef_pat.match(line)
            if match:
                if currtool:
                    raise RuntimeError(
                        "File %s has an aperture definition that comes after drawing commands." % self.filename)

                A = aptable.parseAperture(line, self.apmxlat)
                if not A:
                    raise RuntimeError(
                        "Unknown aperture definition in file %s" % self.filename)

                hash = A.hash()
                if hash not in RevGAT:
                    # print(line)
                    # print(self.apmxlat)
                    # print(RevGAT)
                    raise RuntimeError(
                        'File %s has aperture definition "%s" not in global aperture table.' % (self.filename, hash))

                # This says that all draw commands with this aperture code will
                # be replaced by aperture self.apxlat[code].
                self.apxlat[A.code] = RevGAT[hash]
                continue

            # Ignore %AMOC8* from Eagle for now as it uses a macro parameter, which
            # is not yet supported in GerbMerge.
            if line[:7] == '%AMOC8*':
                continue

            # DipTrace specific fixes, but could be emitted by any CAD program. They are Standard Gerber RS-274X
            # a hack to fix lack of recognition for metric direction from
            # DipTrace - %MOMM*%
            if (line[:7] == '%MOMM*%'):
                if (config.Config['measurementunits'] == 'inch'):
                    raise RuntimeError(
                        "File %s units do match config file" % self.filename)
                else:
                    # print("ignoring metric directive: " + line)
                    continue  # ignore it so func doesn't choke on it

            if line[:3] == '%SF':  # scale factor - we will ignore it
                print('Scale factor parameter ignored: ' + line)
                continue

            # end basic diptrace fixes

            # See if this is an aperture macro definition, and if so, map it.
            M = amacro.parseApertureMacro(line, fid)
            if M:
                if currtool:
                    raise RuntimeError(
                        "File %s has an aperture macro definition that comes after drawing commands." % self.filename)

                hash = M.hash()
                if hash not in RevGAMT:
                    raise RuntimeError(
                        'File %s has aperture macro definition not in global aperture macro table:\n%s' % (self.filename, hash))

                # This says that all aperture definition commands that reference this macro name
                # will be replaced by aperture macro name
                # self.apmxlat[macroname].
                self.apmxlat[M.name] = RevGAMT[hash]
                continue

            # From this point on we may have more than one match on this line, e.g.:
            #   G54D11*X22400Y22300D02*X22500Y22200D01*
            sub_line = line
            while sub_line:
                # Handle "comment" G-codes first
                match = comment_pat.match(sub_line)
                if match:
                    sub_line = sub_line[match.end():]
                    continue

                # See if this is a format statement, and if so, map it. In version 1.3 this was moved down
                # from the line-only parse checks above (see comment) to handle OrCAD lines like
                # G74*%FSLAN2X34Y34*%
                # Used to be format_pat.search
                match = format_pat.match(sub_line)
                if match:
                    sub_line = sub_line[match.end():]
                    for item in match.groups():
                        if item is None:
                            continue   # Optional group didn't match

                        if item[0] in "LA":   # omit leading zeroes and absolute co-ordinates
                            continue

                        if item[0] == 'T':      # omit trailing zeroes
                            raise RuntimeError(
                                "Trailing zeroes not supported in RS274X files")
                        if item[0] == 'I':      # incremental co-ordinates
                            raise RuntimeError(
                                "Incremental co-ordinates not supported in RS274X files")

                        if item[0] == 'N':      # Maximum digits for N* commands...ignore it
                            continue

                        # allow for metric - scale to 1/1000 mm
                        if config.Config['measurementunits'] == 'inch':
                            # M.N specification for X-axis.
                            if item[0] == 'X':
                                fracpart = int(item[2])
                                x_div = 10.0**(5 - fracpart)
                            # M.N specification for Y-axis.
                            if item[0] == 'Y':
                                fracpart = int(item[2])
                                y_div = 10.0**(5 - fracpart)
                        else:
                            # M.N specification for X-axis.
                            if item[0] == 'X':
                                fracpart = int(item[2])
                                x_div = 10.0**(3 - fracpart)
                                # print("x_div= %5.3f." % x_div)
                            # M.N specification for Y-axis.
                            if item[0] == 'Y':
                                fracpart = int(item[2])
                                y_div = 10.0**(3 - fracpart)
                                # print("y_div= %5.3f." % y_div)

                    continue

                # Parse and interpret G-codes
                match = gcode_pat.match(sub_line)
                if match:
                    sub_line = sub_line[match.end():]
                    gcode = int(match.group(1))

                    # Determine if this is a G-Code that should be ignored because it has no effect
                    # (e.g., G70 specifies "inches" which is already in effect).
                    # added 71 - specify mm (metric)
                    if gcode in [54, 70, 90, 71]:
                        continue

                    # Determine if this is a G-Code that we have to emit
                    # because it matters.
                    if gcode in [1, 2, 3, 36, 37, 74, 75]:
                        self.commands.append("G%02d" % gcode)

                        # Determine if this is a G-code that sets a new mode
                        if gcode in [1, 36, 37]:
                            last_gmode = gcode

                        # Remember last G74/G75 code so we know whether to do signed or unsigned I/J
                        # offsets.
                        if gcode == 74:
                            circ_signed = False
                        elif gcode == 75:
                            circ_signed = True

                        continue

                    raise RuntimeError(
                        "G-Code 'G%02d' is not supported" % gcode)

                # See if this is a tool change (aperture change) command
                match = tool_pat.match(sub_line)

                if match:
                    currtool = match.group(1)

                    # Diptrace hack
                    # There is a D2* command in board outlines. I believe this should be D02.
                    # Let's change it then when it occurs:
                    if (currtool == 'D1'):
                        currtool = 'D01'
                    if (currtool == 'D2'):
                        currtool = 'D02'
                    if (currtool == 'D3'):
                        currtool = 'D03'

                    # Protel likes to issue random D01, D02, and D03 commands instead of aperture
                    # codes. We can ignore D01 because it simply means to move to the current location
                    # while drawing. Well, that's drawing a point. We can ignore D02 because it means
                    # to move to the current location without drawing. Truly pointless. We do NOT want
                    # to ignore D03 because it implies a flash. Protel very inefficiently issues a D02
                    # move to a location without drawing, then a single-line D03 to flash. However, a D02
                    # terminates a polygon in G36 mode, so keep D02's in this
                    # case.
                    if currtool == 'D01' or (
                            currtool == 'D02' and (last_gmode != 36)):
                        sub_line = sub_line[match.end():]
                        continue

                    if (currtool == 'D03') or (
                            currtool == 'D02' and (last_gmode == 36)):
                        self.commands.append(currtool)
                        sub_line = sub_line[match.end():]
                        continue

                    # Map it using our translation table
                    if currtool not in self.apxlat:
                        raise RuntimeError(
                            'File %s has tool change command "%s" with no corresponding translation' % (self.filename, currtool))

                    currtool = self.apxlat[currtool]

                    # Add it to the list of things to write out
                    self.commands.append(currtool)

                    # Add it to the list of all apertures needed by this layer
                    self.apertures.append(currtool)

                    # Move on to next match, if any
                    sub_line = sub_line[match.end():]
                    continue

                # Is it a simple draw command?
                I = J = None  # For circular interpolation drawing commands
                match = drawXY_pat.match(sub_line)
                isLastShorthand = False    # By default assume we don't make use of last_x and last_y
                if match:
                    x, y, d = map(builtins.int, match.groups())
                else:
                    match = drawX_pat.match(sub_line)
                    if match:
                        x, d = map(builtins.int, match.groups())
                        y = last_y
                        isLastShorthand = True  # Indicate we're making use of last_x/last_y
                    else:
                        match = drawY_pat.match(sub_line)
                        if match:
                            y, d = map(builtins.int, match.groups())
                            x = last_x
                            isLastShorthand = True  # Indicate we're making use of last_x/last_y

                # Maybe it's a circular interpolation draw command with IJ
                # components
                if match is None:
                    match = cdrawXY_pat.match(sub_line)
                    if match:
                        x, y, I, J, d = map(builtins.int, match.groups())
                    else:
                        match = cdrawX_pat.match(sub_line)
                        if match:
                            x, I, J, d = map(builtins.int, match.groups())
                            y = last_y
                            isLastShorthand = True  # Indicate we're making use of last_x/last_y
                        else:
                            match = cdrawY_pat.match(sub_line)
                            if match:
                                y, I, J, d = map(builtins.int, match.groups())
                                x = last_x
                                isLastShorthand = True  # Indicate we're making use of last_x/last_y
                if match:
                    if currtool is None:
                        # It's OK if this is an exposure-off movement command (specified with D02).
                        # It's also OK if we're in the middle of a G36 polygon fill as we're only defining
                        # the polygon extents.
                        if (d != 2) and (last_gmode != 36):
                            raise RuntimeError(
                                'File %s has draw command %s with no aperture chosen' % (self.filename, sub_line))

                    # Save last_x/y BEFORE scaling to 2.5 format else subsequent single-ordinate
                    # flashes (e.g., Y with no X) will be scaled twice!
                    last_x = x
                    last_y = y

                    # Corner case: if this is the first flash/draw and we are using shorthand (i.e., missing Xxxx
                    # or Yxxxxx) then prepend the point X0000Y0000 into the commands as it is actually the starting
                    # point of our layer. We prepend the command X0000Y0000D02,
                    # i.e., a move to (0,0) without drawing.
                    if (isLastShorthand and firstFlash):
                        self.commands.append((0, 0, 2))
                        if self.update_extents:
                            self.minx = min(self.minx, 0)
                            self.maxx = max(self.maxx, 0)
                            self.miny = min(self.miny, 0)
                            self.maxy = max(self.maxy, 0)

                    x = int(round(x * x_div))
                    y = int(round(y * y_div))
                    if I is not None:
                        I = int(round(I * x_div))
                        J = int(round(J * y_div))
                        self.commands.append(
                            (x, y, I, J, d, circ_signed))
                    else:
                        self.commands.append((x, y, d))
                    firstFlash = False

                    # Update dimensions...this is complicated for circular interpolation commands
                    # that span more than one quadrant. For now, we ignore this problem since users
                    # should be using a border layer to indicate extents.
                    if self.update_extents:
                        if x < self.minx:
                            self.minx = x
                        if x > self.maxx:
                            self.maxx = x
                        if y < self.miny:
                            self.miny = y
                        if y > self.maxy:
                            self.maxy = y

                    # Move on to next match, if any
                    sub_line = sub_line[match.end():]
                    continue

                # If it's none of the above, it had better be on our ignore
                # list.
                for pat in IgnoreList:
                    match = pat.match(sub_line)
                    if match:
                        break
                else:
                    raise RuntimeError(
                        'File %s has uninterpretable line:\n  %s' % (self.filename, line))

                sub_line = sub_line[match.end():]
            # end while still things to match on this line
        # end of for each line in file

        fid.close()
        if 0:
            print(self.commands)

    def trim(self):
        "Modify drawing commands that are outside job dimensions"

        newcmds = []
        lastInBorders = True
        # (minx,miny,exposure off)
        lastx, lasty = self.minx, self.miny
        bordersRect = (self.minx, self.miny, self.maxx, self.maxy)
        lastAperture = None

        for cmd in self.commands:
            if isinstance(cmd, tuple):
                # It is a data command: tuple (X, Y, D), all integers, or (X,
                # Y, I, J, D), all integers.
                if len(cmd) == 3:
                    x, y, d = cmd
                    # I=J=None   # In case we support circular interpolation in
                    # the future
                else:
                    # We don't do anything with circular interpolation for now, so just issue
                    # the command and be done with it.
                    # x, y, I, J, d, s = cmd
                    newcmds.append(cmd)
                    continue

                newInBorders = self.inBorders(x, y)

                # Flash commands are easy (for now). If they're outside borders,
                # ignore them. There's no need to consider the previous command.
                # What should we do if the flash is partially inside and partially
                # outside the border? Ideally, define a macro that constructs the
                # part of the flash that is inside the border. Practically, you've
                # got to be kidding.
                #
                # Actually, it's not that tough for rectangle apertures. We identify
                # the intersection rectangle of the aperture and the bounding box,
                # determine the new rectangular aperture required along with the
                # new flash point, add the aperture to the GAT if necessary, and
                # make the change. Spiffy.
                #
                # For circular interpolation commands, it's definitely harder since
                # we have to construct arcs that are a subset of the original arc.
                #
                # For polygon fills, we similarly have to break up the polygon into
                # sub-polygons that are contained within the allowable extents.
                #
                # Both circular interpolation and polygon fills are a) uncommon,
                # and b) hard to handle. The current version of GerbMerge does not
                # handle these cases.
                if d == 3:
                    if lastAperture.isRectangle():
                        apertureRect = lastAperture.rectangleAsRect(x, y)
                        if geometry.isRect1InRect2(apertureRect, bordersRect):
                            newcmds.append(cmd)
                        else:
                            newRect = geometry.intersectExtents(
                                apertureRect, bordersRect)

                            if newRect:
                                newRectWidth = geometry.rectWidth(newRect)
                                newRectHeight = geometry.rectHeight(newRect)
                                newX, newY = geometry.rectCenter(newRect)

                                # We arbitrarily remove all flashes that lead to rectangles
                                # with a width or length less than 1 mil (10 Gerber units). - sdd s.b. 0.1mil???
                                # Should we make this configurable?
                                # add metric support (1/1000 mm vs. 1/100,000 inch)
                                #                if config.Config['measurementunits'] == 'inch':
                                #                  minFlash = 10;
                                #                else
                                #                  minFlash =
                                # sdd - change for metric case at some point
                                if min(newRectWidth, newRectHeight) >= 10:
                                    # Construct an Aperture that is a Rectangle
                                    # of dimensions
                                    # (newRectWidth,newRectHeight)
                                    newAP = aptable.Aperture('Rectangle', 'D??',
                                                             util.gerb2in(newRectWidth), util.gerb2in(newRectHeight))
                                    global_code = aptable.findOrAddAperture(
                                        newAP)

                                    # We need an unused local aperture code to
                                    # correspond to this newly-created global
                                    # one.
                                    self.makeLocalApertureCode(newAP)

                                    # Make sure to indicate that the new
                                    # aperture is one that is used by this
                                    # layer
                                    if global_code not in self.apertures:
                                        self.apertures.append(
                                            global_code)

                                    # Switch to new aperture code, flash new
                                    # aperture, switch back to previous
                                    # aperture code
                                    newcmds.append(global_code)
                                    newcmds.append((newX, newY, 3))
                                    newcmds.append(lastAperture.code)
                                else:
                                    pass    # Ignore this flash...area in common is too thin
                            else:
                                pass      # Ignore this flash...no area in common
                    elif self.inBorders(x, y):
                        # Aperture is not a rectangle and its center is somewhere within our
                        # borders. Flash it and ignore part outside borders
                        # (for now).
                        newcmds.append(cmd)
                    else:
                        pass    # Ignore this flash

                # If this is a exposure off command, then it doesn't matter what the
                # previous command is. This command just updates the (X,Y) position
                # and sets the start point for a line draw to a new location.
                elif d == 2:
                    if self.inBorders(x, y):
                        newcmds.append(cmd)

                else:
                    # This is an exposure on (draw line) command. Now things get interesting.
                    # Regardless of what the last command was (draw, exposure off, flash), we
                    # are planning on drawing a visible line using the current aperture from
                    # the (lastx,lasty) position to the new (x,y) position. The cases are:
                    #   A: (lastx,lasty) is outside borders, (x,y) is outside borders.
                    #      (lastx,lasty) have already been eliminated. Just update (lastx,lasty)
                    #      with new (x,y) and remove the new command too. There is one case which
                    #      may be of concern, and that is when the line defined by (lastx,lasty)-(x,y)
                    #      actually crosses through the job. In this case, we have to draw the
                    #      partial line (x1,y1)-(x2,y2) where (x1,y1) and (x2,y2) lie on the
                    #      borders. We will add 3 commands:
                    #           X(x1)Y(y1)D02   # exposure off
                    #           X(x2)Y(y2)D01   # exposure on
                    #           X(x)Y(y)D02     # exposure off
                    #
                    #   B: (lastx,lasty) is outside borders, (x,y) is inside borders.
                    #      We have to find the intersection of the line (lastx,lasty)-(x,y)
                    #      with the borders and draw only the line segment (x1,y1)-(x,y):
                    #           X(x1)Y(y1)D02   # exposure off
                    #           X(x)Y(y)D01     # exposure on
                    #
                    #   C: (lastx,lasty) is inside borders, (x,y) is outside borders.
                    #      We have to find the intersection of the line (lastx,lasty)-(x,y)
                    #      with the borders and draw only the line segment (lastx,lasty)-(x1,y1):
                    #      then update to the new position:
                    #           X(x1)Y(y1)D01   # exposure on
                    #           X(x)Y(y)D02     # exposure off
                    #
                    #   D: (lastx,lasty) is inside borders, (x,y) is inside borders. This is
                    #      the most common and simplest case...just copy the command over:
                    #           X(x)Y(y)D01     # exposure on
                    #
                    # All of the above are for linear interpolation. Circular interpolation
                    # is ignored for now.
                    if lastInBorders and newInBorders:    # Case D
                        newcmds.append(cmd)

                    else:
                        # segmentXbox() returns a list of 0, 1, or 2 points describing the intersection
                        # points of the segment (lastx,lasty)-(x,y) with the box defined
                        # by lower-left corner (minx,miny) and upper-right
                        # corner (maxx,maxy).
                        pointsL = geometry.segmentXbox(
                            (lastx, lasty), (x, y), (self.minx, self.miny), (self.maxx, self.maxy))

                        if len(pointsL) == 0:   # Case A, no intersection
                            # Both points are outside the box and there is no overlap with box.
                            # Command is effectively removed since newcmds
                            # wasn't extended.
                            d = 2
                            # Ensure "last command" is exposure off to reflect
                            # this.

                        elif len(pointsL) == 1:     # Cases B and C
                            pt1 = pointsL[0]
                            if newInBorders:      # Case B
                                # Go to intersection point, exposure off
                                newcmds.append((pt1[0], pt1[1], 2))
                                # Go to destination point, exposure on
                                newcmds.append(cmd)
                            else:                 # Case C
                                # Go to intersection point, exposure on
                                newcmds.append((pt1[0], pt1[1], 1))
                                # Go to destination point, exposure off
                                newcmds.append((x, y, 2))

                        else:                 # Case A, two points of intersection
                            pt1 = pointsL[0]
                            pt2 = pointsL[1]

                            # Go to first intersection point, exposure off
                            newcmds.append((pt1[0], pt1[1], 2))
                            # Draw to second intersection point, exposure on
                            newcmds.append((pt2[0], pt2[1], 1))
                            # Go to destination point, exposure off
                            newcmds.append((x, y, 2))

                lastx, lasty = x, y
                lastInBorders = newInBorders
            else:
                # It's a string indicating an aperture change, G-code, or RS-274X
                # command (e.g., "D13", "G75", "%LPD*%")
                newcmds.append(cmd)
                # Don't interpret D01, D02, D03
                if cmd[0] == 'D' and int(cmd[1:]) >= 10:
                    lastAperture = config.GAT[cmd]

        self.commands = newcmds

    def makeLocalApertureCode(self, AP):
        "Find or create a layer-specific aperture code to represent the global aperture given"
        if AP.code not in self.apxlat.values():
            lastCode = aptable.findHighestApertureCode(
                self.apxlat.keys())
            localCode = 'D%d' % (lastCode + 1)
            self.apxlat[localCode] = AP.code

    def write(self, fid, Xoff, Yoff):
        "Write out the data such that the lower-left corner of this job is at the given (X,Y) position, in inches"

        # add metric support (1/1000 mm vs. 1/100,000 inch)
        # TODO: config
        if config.Config['measurementunits'] == 'inch':
            # First convert given inches to 2.5 co-ordinates
            X = int(round(Xoff / 0.00001))
            Y = int(round(Yoff / 0.00001))
        else:
            # First convert given mm to 5.3 co-ordinates
            X = int(round(Xoff / 0.001))
            Y = int(round(Yoff / 0.001))

        # Now calculate displacement for each position so that we end up at
        # specified origin
        DX = X - self.minx
        DY = Y - self.miny

        # Rock and roll. First, write out a dummy flash using code D02
        # (exposure off). This prevents an unintentional draw from the end
        # of one job to the beginning of the next when a layer is repeated
        # due to panelizing.
        fid.write('X%07dY%07dD02*\n' % (X, Y))
        for cmd in self.commands:
            if isinstance(cmd, tuple):
                if len(cmd) == 3:
                    x, y, d = cmd
                    fid.write('X%07dY%07dD%02d*\n' % (x + DX, y + DY, d))
                else:
                    x, y, I, J, d, s = cmd
                    fid.write('X%07dY%07dI%07dJ%07dD%02d*\n' %
                              (x + DX, y + DY, I, J, d))  # I,J are relative
            else:
                # It's an aperture change, G-code, or RS274-X command that begins with '%'. If
                # it's an aperture code, the aperture has already been translated
                # to the global aperture table during the parse phase.
                if cmd[0] == '%':
                    # The command already has a * in it (e.g., "%LPD*%")
                    fid.write('%s\n' % cmd)
                else:
                    fid.write('%s*\n' % cmd)