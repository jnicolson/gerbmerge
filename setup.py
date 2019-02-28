from distutils.core import setup
from gerbmerge.gerbmerge import VERSION_MAJOR, VERSION_MINOR

setup(
  name="gerbmerge",
  license="GPL",
  version="{}.{}".format(VERSION_MAJOR, VERSION_MINOR),
  packages=['gerbmerge'],
  install_requires = ['simpleparse'],
  url = "https://github.com/jnicolson/gerbmerge",
)