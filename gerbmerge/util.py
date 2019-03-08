"""
Various utility functions
"""

# Copyright (C) 2019 Jarl Nicolson <jarl@jmn.id.au>
# Copyright (C) 2013 ProvideYourOwn.com http://provideyourown.com
# Copyright (C) 2003-2011 Rugged Circuits LLC http://ruggedcircuits.com/gerbmerge
#
# gerbmerge is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Foobar is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Foobar.  If not, see <https://www.gnu.org/licenses/>.

from . import config


def in2gerb(value):
    # add metric support (1/1000 mm vs. 1/100,000 inch)
    if config.Config['measurementunits'] == 'inch':
        """Convert inches to 2.5 Gerber units"""
        return int(round(value * 1e5))
    else:  # convert mm to 5.3 Gerber units
        return int(round(value * 1e3))


def gerb2in(value):
    # add metric support (1/1000 mm vs. 1/100,000 inch)
    if config.Config['measurementunits'] == 'inch':
        """Convert 2.5 Gerber units to inches"""
        return float(value) * 1e-5
    else:  # convert 5.3 Gerber units to mm
        return float(value) * 1e-3
