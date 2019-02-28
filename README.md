# GerbMerge -- A Gerber-file merging program

## What's New

In release 1.9
* Added metric support
* Added default timeout for random tile placement
* Added DipTrace support
* Use boardoutline files (when present) to build cutlines in silkscreen layers instead of the default calculated algorithm. This change permits non-rectangular board outlines.

In release 1.8:
* Released under more recent GPL v3 license
* Summary statistics prints out smallest drill tool diameter
* Added `FiducialPoints`, `FiducialCopperDiameter`, and `FiducialMaskDiameter` configuration options
* Added option to write fiducials to final panel
* Scoring lines now go all the way across a panel

In release 1.7:
* Added a new command-line option `--search-timeout` to time-limit the automatic placement process.
* Added preliminary support for a GUI controller interface.

## Introduction
GerbMerge is a program for combining (panelizing) the CAM data from multiple printed circuit board designs into a single set of CAM files. The purpose of doing so is to submit a single job to a board manufacturer, thereby saving on manufacturing costs.

GerbMerge currently works with:
  * CAM data generated by the <A HREF="http://www.cadsoft.de">Eagle</A> circuit board
      design program, with &quot;best effort&quot; support for Orcad, Protel, and <A HREF="http://www.sourceforge.net/projects/pcb">PCB</A></LI>
  * Artwork in Gerber RS274-X format</LI>
  * Drill files in Excellon format</LI>

Here is [one sample](doc\sample.jpg) and [another sample](doc\sample2.jpg) of the program's output. These samples demonstrate panelizing multiple, different jobs, and also demonstrate board rotation.

## Requirements
GerbMerge is written in pure Python. It depends upon the following packages for operation:

  * Python version 2.4 or later
  * SimpleParse</A> version 2.1.0 or later

All of the above packages come with easy installation programs for both Windows, Mac OS X,and Linux.

## Installation
First, install all of the packages listed above in the Requirements section.

### Windows
Run the `gerbmerge1.8.exe` installation program. I will assume
you choose all of the default installation options. The installer
will create and populate the following directories:

```
c:\Python24\lib\site-packages\gerbmerge
c:\Python24\gerbmerge
```

The above assumes you have Python installed in `C:\Python24`. The
first directory is where the actual program resides. The second directory
contains the documentation, example files, etc. In the `C:\Python24`
directory is a sample batch file `GERBMERGE.BAT` which shows you how to
run the GerbMerge program.

### Unix / Mac OS X
Extract the `gerbmerge1.8.tar.gz` file then install as follows:

`python setup.py install`&nbsp;&nbsp;&nbsp;(You may need to be root to install to system directories)

The installer will create and populate the following directories/files:

```
/usr/local/lib/python2.4/site-packages/gerbmerge
/usr/local/lib/python2.4/gerbmerge
/usr/local/bin/gerbmerge
```

The above assumes your Python library directory is as indicated (it may be
elsewhere but the installer should be able to find it, so don't worry about
it). The first directory is where the actual program resides. The second
directory contains the documentation, example files, etc. A sample program for
invoking GerbMerge is installed as `/usr/local/bin/gerbmerge`...feel free to move
it somewhere else.

Not all Linux distributions are the same, however. If you have trouble, there is a useful set of instructions from <A HREF="http://blog.bhargavaz.us/2009/05/installing-gerbmerge-on-ubuntu-linux.html">Chetan Bhargava</A> for installing GerbMerge on Ubuntu distributions.

## Running GerbMerge
### Windows
Open a DOS box and invoke the Python interpreter on the `gerbmerge.py` file.
Have a look at GERBMERGE.BAT (and put this on your Path somewhere) for an example.
```c:\python24\python c:\python24\lib\site-packages\gerbmerge\gerbmerge.py```

### Unix / Mac OS X
You run GerbMerge by invoking the Python interpreter on the `gerbmerge.py`
file of the `gerbmerge` package. For example:

```python /usr/local/lib/python2.4/site-packages/gerbmerge/gerbmerge.py```

The `gerbmerge` shell script that comes with this software contains an
example for running GerbMerge, modelled on the above. By default, this shell
script is installed in `/usr/local/bin` so you should just be able
to type `gerbmerge` from a shell prompt.

### Operation
There are three ways to run GerbMerge:
  1. By manually specifying the relative placement of jobs
  2. By manually specifying the absolute placement of jobs
  3. By letting GerbMerge automatically search for a placement that minimizes total panel area

#### Manual Relative Placement
For the manual relative placement approach, GerbMerge needs two input text files:

  * The _configuration file_ specifies global options and defines the jobs to be panelized
  * The _layout file_ specifies how the jobs are to be laid out.

The names of these files are the two required parameters to GerbMerge:
`gerbmerge file.cfg file.def`

The following links describe the contents of the [configuration file](doc\cfgfile.md) and [layout file](doc\layoutfile.md).

#### Manual Absolute Placement
For the manual absolute placement approach, GerbMerge also needs the configuration file as well as another text file that specifies where each job is located on the panel and whether or not it is rotated:

`gerbmerge --place-file=place.txt file.cfg`

The `place.txt` file looks something like:
```job1 0.100 0.100
cpu 0.756 0.100
cpu*rotated 1.35 1.50
```

This method of placement is not meant for normal use. It can be used to recreate a previous invocation of GerbMerge, since GerbMerge saves its results in a text file (whose name is set in the [MergeOutputFiles](doc\cfgfile.md#MergeOutputFiles) section of the configuration file) after every run. Thus, you can experiment with different parameters, save a placement you like, do some more experimentation, then return to the saved placement if necessary.

Alternatively, this method of placement can be used with third-party back ends that implement intelligent auto-placement algorithms, using GerbMerge only for doing the actual panelization.

#### Automatic Placement
For the [automatic placement](doc\autosearch.html) approach, GerbMerge only needs the configuration file:
`gerbmerge file.cfg`
Command-line options can be used to modify the search algorithm. See the [Automatic Placement](doc\autosearch.html) page for more information.

### Input File Requirements
GerbMerge requires the following input CAM files:

  * Each job must have a Gerber file describing the board outline, which is assumed rectangular. In Eagle, a board outline is usually generated from the Dimension layer. This board outline is a width-0 line describing the physical extents of the board. If you're not using Eagle, you don't have to generate a width-0 rectangle, but GerbMerge does need to use some Gerber layer to determine the extents of the board. GerbMerge will take the maximum extents of all drawn objects in this layer as the extents of the board.
  * Each job must have an Excellon drill file.
  * Each job can have any number of optional Gerber files describing copper layers, silkscreen, solder masks, etc.
  * All files must have the same offset and must be shown looking from the top of the board, i.e., not mirrored.
  * Each job may have an optional tool list file indicating the tool names used in the Excellon file and the diameter of each tool. This file is not necessary if tool sizes are embedded in the Excellon file. A typical tool list file looks like:

```
T01 0.025in
T02 0.032in
T03 0.045in
```

## Verifying the Output

Before sending your job to be manufactured, it is imperative that you verify the correctness of the output. Remember that GerbMerge comes with NO WARRANTY. Manufacturing circuit boards costs real money and a single mistake can render an entire lot of boards unusable.

I recommend the following programs for viewing the final output data. Take the time to become very familiar with at least one of these tools and to use it before every job you send out for manufacture.

<dl>
  <dt><b>gerbv</b></dt>
  <dd>For Linux, the best option (currently) for viewing Gerber and Excellon files is the <A HREF="http://gerbv.sourceforge.net">`gerbv`</A> program. Simply type in the names of all files generated by GerbMerge as parameters to `gerbv`: <CENTER><PRE>gerbv merged.*.ger merged.*.xln</PRE></CENTER></dd>

  <dt><B>GC-Prevue</B></dt>
  <dd>For Windows, [GC-Prevue](http://www.graphicode.com) is a good program that I have used often. It is a free program. GraphiCode makes lots of other, more powerful Gerber manipulation and viewing programs but they are quite pricey ($495 and up).</dd>

  <dt><B>ViewMate</B></dt>
  <dd>Another free Windows program, [ViewMate](http://www.pentalogix.com) is similar to GC-Prevue. I have not used ViewMate much, but that is mostly due to familiarity with GC-Prevue. The two programs are comparable, although I'm sure that someone who is much more familiar with both could point out some differences.</dd>
</dl>

## Limitations

  * This program has mainly been tested with output from the Eagle CAD program. Limited testing has been performed with Orcad, Protel, and PCB. Other CAD programs will NOT WORK with a very high probability, as the input parser is quite primitive.

  If you have the need/motivation to adapt GerbMerge to other CAD programs, have a look at the `gerber2pdf` program. It is written in Python and implements a much more complete RS274-X input file parser. Combining GerbMerge with `gerber2pdf` should be a fairly simple exercise. Also, feel free to send us samples of Gerber/Excellon output of your CAD tool and we'll see if we can add support for it.

  * This program handles apertures that are rectangles, ovals, circles, macros without parameters or operators, and Eagle octagons (which are defined using a macro with a single parameter, hence currently handled as a special case).

  * The panelizing capabilities of this program do not allow for arbitrary placement of jobs, although there is a fair amount of flexibility.

  * All jobs are assumed to be rectangular in shape. Non-rectangular jobs can be handled but will lead to wasted space in the final panel.

  * A maximum of 26 different drill sizes is supported for generating a fabrication drawing.

## Program Options

<dl>
  <dt>--octagons=normal</dt>
  <dt>--octagons=rotate</dt>
  <dd>The `--octagons` option affects how the octagon aperture is defined in the output files. The parameter to this option must either be `rotate` or `normal`. Normally, octagons begin at an angle of 22.5 degrees, but some Gerber viewers have a problem with that (notably CircuitMaker from LPKF). These programs expect octagons to begin at 0.0 degrees.</dd>
  <dd>The `--octagons=normal` option is the default (22.5 degrees) and need not be specified. A rotation of 0.0 degrees can be achieved by specifying `--octagons=rotate`.</DD>

  <dt>--random-search</dt>
  <dd>This option is the default when only a configuration file is specified (see the documentation on [Automatic Placement](doc\autosearch.md) for more information). It indicates that a randomized search of possible job tilings is to be performed. This option does not make sense when a layout file is specified.</dd>


  <dt>--full-search</dt>
  <dd>This option may be specified to indicate that all possible job tilings are to be searched (see the documentation on [Automatic Placement](doc\autosearch.md) for more information). This option does not make sense when a layout file is specified.</dd>

  <dt>--rs-fsjobs=N</dt>
  <dd>This option is used with randomized search to indicate how many jobs are to undergo full search for each tiling. See the documentation on [Automatic Placement](doc\autosearch.md) for more information.</dd>

  <dt>--place-file=filename</dt>
  <dd>This option performs a panel layout based upon absolute job positions in the given text file, rather than by random/full search or by a layout file. The placement file created by GerbMerge can be used as an input file to this option in order to recreate a previous layout.</dd>

  <dt>--no-trim-gerber</dt>
  <dd>This option prevents GerbMerge from trying to trim all Gerber data to lie within the extents of a given job's board outline. Normally, GerbMerge will try to do so to prevent one job's Gerber data (most notably, silkscreen lines for connectors that protrude from the board) from interfering with a neighboring job on the final panel. Specify this command-line option if you do not want this trimming to occur.</DD>

  <dt>--no-trim-excellon</dt>
  <dd>This option prevents GerbMerge from trying to trim all Excellon data to lie within the extents of a given job's board outline. Normally, GerbMerge will try to do so to prevent one job's drill holes from landing in the middle of a neighboring job on the final panel. Specify this command-line option if you do not want this trimming to occur.</DD>

  <dt>--search-timeout=seconds</dt>
  <dd>When random placements are used, this option can be used to automatically terminate the search process after the specified number of seconds. If the number of seconds is 0 or this option is not specified, then random placements are tried forever, until Ctrl-C is pressed to stop the process and keep the best placement so far.</DD>

  <dt>-h, --help</dt>
  <dd>The '`-h`' or '`--help`' option prints a brief summary of available options.</dd>

  <dt>-v, --version</dt>
  <dd>The '`-v`' or '`--version`' option prints the current program version and author contact information.</dd>
</dl>

## Copyright &amp; License
Copyright &copy; 2013 <a href="http://provideyourown.com">ProvideYourOwn.com</a>. All Rights Reserved.

This repo is a fork of gerbmerge, version 1.8 from Rugged Circuits LLC:

Copyright &copy; 2011 [Rugged Circuits LLC](http://ruggedcircuits.com). All Rights Reserved.
  mailto: [support@ruggedcircuits.com](support@ruggedcircuits.com?subject=GerbMerge)

GerbMerge comes with ABSOLUTELY NO WARRANTY. This is free software licensed under the terms of the GNU General Public License Version 3. You are welcome to copy, modify and redistribute this software under certain conditions. For more details, see the LICENSE file or visit [The Free Software Foundation](http://www.fsf.org).

## To Do
  1. Accept outputs from more CAD programs
  2. A graphical interface for interactive placement
  3. Better reporting of parse errors in the layout and configuration files
  4. Implement simple primitive for panelizing a single job in an array
  5. More intelligent placement algorithms, possibly based on the fabric cutting problem.
  6. Accept aperture macro parameters and operators

## Credits
Thanks to Jace Browning for major contributions to this code. This help file is based on a template for the help file for mxTools by [M.A. Lemburg](http://starship.python.net/crew/lemburg). This software was created with <A HREF="http://www.vim.org/">VIM</A>; thanks to the authors of this program and special thanks for the Python syntax support. Thanks to M.A. Lemburg for his <A HREF="http://www.egenix.com/files/python/eGenix-mx-Extensions.html">mxBase</A> package, Mike Fletcher for his <A HREF="http://simpleparse.sourceforge.net">SimpleParse</A> package, and the authors of <A HREF="http://gerbv.sourceforge.net">gerbv</A>, a great Gerber file viewer for Linux/Mac OS X, and, of course, to the <A HREF="http://www.python.org">Python</A> developers and support community.

Thanks to Joe Pighetti for making me start writing this program, and to the Grand Valley State University Firefighting Robot Team for making me finish it.

Thanks to Matt Kavalauskas for identifying Eagle's annulus and thermal macros and supporting the development of the aperture macro code.

Thanks to Bohdan Zograf for the <A HREF="http://webhostingrating.com/libs/gerbmerge-be">Belorussian translation</A> of this documentation.

Copyright &copy; 2013 <a href="http://provideyourown.com">ProvideYourOwn.com</a>. All Rights Reserved.

Portions (version 1.8 & prior): Copyright &copy; 2003-2011, Copyright by [Rugged Circuits LLC](http://ruggedcircuits.com); All Rights Reserved. mailto: <A HREF="mailto:support@ruggedcircuits.com?subject=GerbMerge">support@ruggedcircuits.com</A>
