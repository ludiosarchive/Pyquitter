#!/usr/bin/env python

from distutils.core import setup

import pyquitter

setup(
	name='pyquitter',
	version=pyquitter.__version__,
	description="Detects file modifications for all imported modules; "
		"useful for auto-restarting programs.",
	packages=['pyquitter'],
	scripts=['bin/looper', 'bin/looper-stop'],
)
