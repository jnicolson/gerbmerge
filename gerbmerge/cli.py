"""CLI Definition."""

import argparse
import sys


class CustomFormatter(argparse.ArgumentDefaultsHelpFormatter, argparse.RawTextHelpFormatter, argparse.RawDescriptionHelpFormatter):
    pass


epilog = """If a layout file is not specified, automatic placement is performed. If the
placement is read from a file, then no automatic placement is performed and
the layout file (if any) is ignored.\n\nNOTE: The dimensions of each job are determined solely by the maximum extent of
the board outline layer for each job."""


class DefaultHelpParser(argparse.ArgumentParser):
    def error(self, message):
        sys.stderr.write('error: {}\n'.format(message))
        self.print_help()
        sys.exit(2)


parser = DefaultHelpParser(
    prog='gerbmerge',
    description='%(prog)s is a utility to combine various gerber + excellon files into a single file',
    usage='%(prog)s [options] configfile [layoutfile]',
    epilog=epilog,
    formatter_class=CustomFormatter)

parser.add_argument("configfile", help="config file to read (see help for format)")

searchGroup = parser.add_mutually_exclusive_group(required=True)
searchGroup.add_argument("layoutfile", help="file containing layout of gerbers defined in config file", nargs='?')
searchGroup.add_argument("--random-search", help="Automatic placement using random search", action="store_true")
searchGroup.add_argument("--full-search", help="Automatic placement using exhaustive search", action="store_true")

parser.add_argument("--place-file", help="Read placement from file")
parser.add_argument("--rs-fsjobs", help="When using random search, exhaustively search N jobs for each random placement", type=int, default=2)
parser.add_argument("--search-timeout", help="When using random search, search for T seconds for best random placement", type=int, default=0)
parser.add_argument("--no-trim-gerber", help="Do not attempt to trim Gerber data to extents of board", action="store_true")
parser.add_argument("--no-trim-excellon", help="Do not attempt to trim Excellon data to extents of board", action="store_true")
parser.add_argument("--octagons", help="Generate octagons in two different styles depending on the value:\n 'rotate' :  0.0 rotation\n 'normal' : 22.5 rotation", choices=['rotate', 'normal'], default='normal')
parser.add_argument("-s", "--skipdisclaimer", help="Skip disclaimer dialog", action="store_true")
parser.add_argument("-v", "--version", action='version', version='1')


def get_args():
    return parser.parse_args()
