#!/usr/bin/env python

from distutils.core import setup

import pyquitter

setup(
	name='pyquitter',
	version=pyquitter.__version__,
	description="Detects file modifications to any imported module; "
		"useful for auto-restarting during development.",
	packages=['pyquitter'],
	scripts=['bin/looper', 'bin/looper-stop'],
)
