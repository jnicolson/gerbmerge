import re

from . import config, makestroke

# Patterns for Excellon interpretation
xtool_pat = re.compile(r'^(T\d+)$')           # Tool selection
# xydraw_pat = re.compile(r'^X([+-]?\d+)Y([+-]?\d+)$')    # Plunge command
xydraw_pat = re.compile(r'^X(?P<x>[+-]?\d+\.\d+)Y(?P<y>[+-]?\d+\.\d+)$')
# Plunge command, repeat last Y value
xdraw_pat = re.compile(r'^X([+-]?\d+)$')
# Plunge command, repeat last X value
ydraw_pat = re.compile(r'^Y([+-]?\d+)$')

# Tool+diameter definition with optional
# feed/speed (for Protel)
xtdef_pat = re.compile(r'^(T\d+)(?:F\d+)?(?:S\d+)?C([0-9.]+)$')

# Tool+diameter definition with optional
# feed/speed at the end (for OrCAD)
xtdef2_pat = re.compile(r'^(T\d+)C([0-9.]+)(?:F\d+)?(?:S\d+)?$')

# Leading/trailing zeros INCLUDED
xzsup_pat = re.compile(r'^INCH,([LT])Z$')

# Format header
format_pat = re.compile(r'^FMAT,(\d)$')

# Mode header
position_mode_pat = re.compile(r'^G9[01]$')

tool_mode_pat = re.compile(r'G0[0-5]')

XIgnoreList = (
    re.compile(r'^%$'),
    re.compile(r'^M30$'),   # End of job
    re.compile(r'^M48$'),   # Program header to first %
    re.compile(r'^M72$')    # Inches
)


class ExcellonParser(object):
    def __init__(self, filename, decimals):
        self.filename = filename
        self.decimals = decimals
        self.xdiam = {}
        self.ToolList = {}
        self.xcommands = {}
        self.minx = self.miny = 9999999
        self.maxx = self.maxy = -9999999
        # TODO: Replace with enum
        self.mode = 'Absolute'

    def __str__(self):
        return ("xdiam: {}, ToolList: {}".format(self.xdiam, self.ToolList))

    def xln2tenthou(self, L, divisor, zeropadto, suppress_leading):
        """Helper function to convert X/Y strings into integers in units of
        ten-thousandth of an inch."""
        V = []
        for s in L:
            if not suppress_leading:
                s = s + '0' * (zeropadto - len(s))
            V.append(int(round(int(s) * divisor)))
        return tuple(V)

    def parse(self):
        # print('Reading data from %s ...' % self.filename)

        fid = open(self.filename, 'rt')
        currtool = None
        suppress_leading = True     # Suppress leading zeros by default, equivalent to 'INCH,TZ'

        # We store Excellon X/Y data in ten-thousandths of an inch. If the Config
        # option ExcellonDecimals is not 4, we must adjust the values read from the
        # file by a divisor to convert to ten-thousandths.  This is only used in
        # leading-zero suppression mode. In trailing-zero suppression mode, we must
        # trailing-zero-pad all input integers to M+N digits (e.g., 6 digits for 2.4 mode)
        # specified by the 'zeropadto' variable.
        if self.decimals > 0:
            divisor = 10.0**(4 - self.decimals)
            zeropadto = 2 + self.decimals
        else:
            divisor = 10.0**(4 - config.Config['excellondecimals'])
            zeropadto = 2 + config.Config['excellondecimals']

        # Protel takes advantage of optional X/Y components when the previous one is the same,
        # so we have to remember them.
        last_x = last_y = 0

        for line in fid:
            # Get rid of CR characters
            line = line.replace('\x0D', '')

            match = format_pat.match(line)
            if match:
                if match.group(1) == 1:
                    raise RuntimeError("Drill file uses format 1 commands.  These are not supported at this time")
                continue
            
            match = position_mode_pat.match(line)
            if match:
                if line == 'G90':
                    self.mode = 'Absolute'
                elif line == 'G91':
                    self.mode = 'Incremental'
                continue

            match = tool_mode_pat.match(line)
            if match:
                # TODO: do something with the tool mode
                continue

            # add support for DipTrace
            if line[:6] == 'METRIC':
                if (config.Config['measurementunits'] == 'inch'):
                    raise RuntimeError(
                        "File %s units do match config file" % self.filename)
                else:
                    # rint("ignoring METRIC directive: " + line)
                    continue  # ignore it so func doesn't choke on it

            if line[:3] == 'T00':  # a tidying up that we can ignore
                continue
            # end metric/diptrace support

            # Protel likes to embed comment lines beginning with ';'
            if line[0] == ';':
                continue

            # Check for leading/trailing zeros included ("INCH,LZ" or
            # "INCH,TZ")
            match = xzsup_pat.match(line)
            if match:
                if match.group(1) == 'L':
                    # LZ --> Leading zeros INCLUDED
                    suppress_leading = False
                else:
                    # TZ --> Trailing zeros INCLUDED
                    suppress_leading = True
                continue

            # See if a tool is being defined. First try to match with tool name+size
            # xtdef_pat and xtdef2_pat expect tool name and diameter
            match = xtdef_pat.match(line)
            if match is None:                # but xtdef_pat expects optional feed/speed between T and C
                # and xtdef_2pat expects feed/speed at the end
                match = xtdef2_pat.match(line)
            if match:
                currtool, diam = match.groups()
                try:
                    diam = float(diam)
                except Exception:
                    raise RuntimeError(
                        "File %s has illegal tool diameter '%s'" % (self.filename, diam))

                # Canonicalize tool number because Protel (of course) sometimes specifies it
                # as T01 and sometimes as T1. We canonicalize to T01.
                currtool = 'T%02d' % int(currtool[1:])

                if currtool in self.xdiam:
                    raise RuntimeError(
                        "File %s defines tool %s more than once" % (self.filename, currtool))
                self.xdiam[currtool] = diam
                continue

            # Didn't match TxxxCyyy. It could be a tool change command 'Tdd'.
            match = xtool_pat.match(line)
            if match:
                currtool = match.group(1)

                # Canonicalize tool number because Protel (of course) sometimes specifies it
                # as T01 and sometimes as T1. We canonicalize to T01.
                currtool = 'T%02d' % int(currtool[1:])

                # Diameter will be obtained from embedded tool definition,
                # local tool list or if not found, the global tool list
                try:
                    diam = self.xdiam[currtool]
                except Exception:
                    if self.ToolList:
                        try:
                            diam = self.ToolList[currtool]
                        except Exception:
                            raise RuntimeError(
                                "File %s uses tool code %s that is not defined in the job's tool list" % (self.filename, currtool))
                    else:
                        try:
                            diam = config.DefaultToolList[currtool]
                        except Exception:
                            # print(config.DefaultToolList)
                            raise RuntimeError(
                                "File %s uses tool code %s that is not defined in default tool list" % (self.filename, currtool))

                self.xdiam[currtool] = diam
                continue

            # Plunge command?
            match = xydraw_pat.match(line)
            if match:
                x, y = self.xln2tenthou(match.groups(), divisor, zeropadto, suppress_leading)
            else:
                match = xdraw_pat.match(line)
                if match:
                    x = self.xln2tenthou(match.groups(), divisor, zeropadto, suppress_leading)[0]
                    y = last_y
                else:
                    match = ydraw_pat.match(line)
                    if match:
                        y = self.xln2tenthou(match.groups(), divisor, zeropadto, suppress_leading)[0]
                        x = last_x

            if match:
                if currtool is None:
                    raise RuntimeError(
                        'File %s has plunge command without previous tool selection' % self.filename)

                try:
                    self.xcommands[currtool].append((x, y))
                except KeyError:
                    self.xcommands[currtool] = [(x, y)]

                last_x = x
                last_y = y
                continue

            # It had better be an ignorable
            for pat in XIgnoreList:
                if pat.match(line):
                    break
            else:
                raise RuntimeError(
                    'File %s has uninterpretable line:\n  %s' % (self.filename, line))

    def inBorders(self, x, y):
        return (x >= self.minx) and (x <= self.maxx) and (
            y >= self.miny) and (y <= self.maxy)

    def updateExtents(self, extents):
        self.minx, self.miny, self.maxx, self.maxy = extents

    def trim(self):
        """Remove plunge commands that are outside job dimensions."""
        keys = list(self.xcommands.keys())

        for toolname in keys:
            # Remember Excellon is 2.4 format while Gerber data is 2.5 format
            # add metric support (1/1000 mm vs. 1/100,000 inch)
            # the normal metric scale factor isn't working right, so we'll
            # leave it alone!!!!?
            if config.Config['measurementunits'] == 'inch':
                validList = [(x, y) for x, y in self.xcommands[toolname] if self.inBorders(10 * x, 10 * y)]
            else:
                validList = [(x, y) for x, y in self.xcommands[toolname] if self.inBorders(0.1 * x, 0.1 * y)]

            if validList:
                self.xcommands[toolname] = validList
            else:
                del self.xcommands[toolname]
                del self.xdiam[toolname]

    def findTools(self, diameter):
        "Find the tools, if any, with the given diameter in inches. There may be more than one!"
        return [tool for tool, diam in self.xdiam.items() if diam == diameter]

    def writeDrillHits(self, fid, diameter, toolNum, Xoff, Yoff):
        """Write a drill hit pattern. diameter is tool diameter in inches, while toolNum is
        an integer index into strokes.DrillStrokeList"""

        # add metric support (1/1000 mm vs. 1/100,000 inch)
        if config.Config['measurementunits'] == 'inch':
            # First convert given inches to 2.5 co-ordinates
            X = int(round(Xoff / 0.00001))
            Y = int(round(Yoff / 0.00001))
        else:
            # First convert given inches to 5.3 co-ordinates
            X = int(round(Xoff / 0.001))
            Y = int(round(Yoff / 0.001))

        # Now calculate displacement for each position so that we end up at
        # specified origin
        DX = X - self.minx
        DY = Y - self.miny

        # Do NOT round down to 2.4 format. These drill hits are in Gerber 2.5 format, not
        # Excellon plunge commands.

        ltools = self.findTools(diameter)

        for ltool in ltools:
            if ltool in self.xcommands:
                for cmd in self.xcommands[ltool]:
                    x, y = cmd
                    # add metric support (1/1000 mm vs. 1/100,000 inch)
                    # TODO - verify metric scaling is correct???
                    makestroke.drawDrillHit(fid, 10 * x + DX, 10 * y + DY, toolNum)
        
    def write(self, fid, diameter, Xoff, Yoff):
        "Write out the data such that the lower-left corner of this job is at the given (X,Y) position, in inches"

        # First convert given inches to 2.4 co-ordinates. Note that Gerber is 2.5 (as of GerbMerge 1.2)
        # and our internal Excellon representation is 2.4 as of GerbMerge
        # version 0.91. We use X,Y to calculate DX,DY in 2.4 units (i.e., with a
        # resolution of 0.0001".
        # add metric support (1/1000 mm vs. 1/100,000 inch)
        if config.Config['measurementunits'] == 'inch':
            # First work in 2.5 format to match Gerber
            X = int(round(Xoff / 0.00001))
            Y = int(round(Yoff / 0.00001))
        else:
            # First work in 5.3 format to match Gerber
            X = int(round(Xoff / 0.001))
            Y = int(round(Yoff / 0.001))

        # Now calculate displacement for each position so that we end up at
        # specified origin
        DX = X - self.minx
        DY = Y - self.miny

        # Now round down to 2.4 format
        # this scaling seems to work for either unit system
        DX = int(round(DX / 10.0))
        DY = int(round(DY / 10.0))

        ltools = self.findTools(diameter)

        if config.Config['excellonleadingzeros']:
            fmtstr = 'X%06dY%06d\n'
        else:
            fmtstr = 'X%dY%d\n'

        # Boogie
        for ltool in ltools:
            if ltool in self.xcommands:
                for cmd in self.xcommands[ltool]:
                    x, y = cmd
                    fid.write(fmtstr % (x + DX, y + DY))

    def drillhits(self, diameter):
        tools = self.findTools(diameter)
        total = 0
        for tool in tools:
            try:
                total += len(self.xcommands[tool])
            except Exception:
                pass

        return total
