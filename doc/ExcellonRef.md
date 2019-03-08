# Excellon Reference

This document just lists the main parts of the Excellon format seen output from various EDA packages.  It doesn't even try to cover most aspects of the actual specification as that has a lot of commands for actual control of the drilling machines and most EDA packages don't output that.

Ideally all EDA packages would output XNC (a subset of the specification which the Excellon format uses) but as they don't I needed a handy reference of the main commands.

## General
* M48 - Start of Header
* INCH|METRIC - Set Units of Measure
* ICI - Incremental Input Mode
* G90 - Set absolute mode
* FMAT,2 - Set Format 2 mode
* M95 - End of Header
* T<number>C<size> - Define tool with number <number> (normally 2 digits, starting at 01) with size <size> (Unit of Measure defines if this is in inch or mm)
* M30 - End of program

## Body
* G00 - Route Mode
* G01 - Linear Mode
* G02 - Circular CW Mode
* G03 - Circular CCW Mode
* G04 - Variable Dwell
* G05 - Drill Mode (Format 1: G81)
* G07 - Override current tool feed or speed
* M00 - End of Program (Format 1: M02)
* M01 - End of Pattern (Format 1: M24)
* M02 - Repeat Pattern Offset (followed by X Y coords) (Format 1: M26)
* M06 - Optional Stop (Format 1: M01)
* M08 - End of Step and Repeat (Format 1: M27)
* M09 - Stop for Inspection (Format 1: M00)

# Sources
https://gist.githubusercontent.com/katyo/5692b935abc085b1037e/raw/32879038a55e1e7019902d8d073d6f5d6d2e45ff/excellon.md