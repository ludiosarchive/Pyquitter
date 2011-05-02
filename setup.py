#!/usr/bin/env python

from distutils.core import setup

import modsniffer

setup(
	name='modsniffer',
	version=modsniffer.__version__,
	description="aka Imported Module Sniffer; detects file changes in imported modules",
	packages=['modsniffer'],
	scripts=['bin/looper', 'bin/looper-stop'],
)
