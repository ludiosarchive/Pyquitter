#!/usr/bin/env python

from distutils.core import setup

import pyquitter

setup(
	name='Pyquitter',
	version=pyquitter.__version__,
	description="Detects file modifications to any imported module; "
		"useful for auto-restarting during development.",
	url="https://github.com/ludios/Pyquitter",
	author="Ivan Kozik",
	author_email="ivan@ludios.org",
	classifiers=[
		'Programming Language :: Python :: 2',
		'Development Status :: 4 - Beta',
		'Operating System :: OS Independent',
		'Intended Audience :: Developers',
		'License :: OSI Approved :: MIT License',
	],
	packages=['pyquitter'],
	scripts=['bin/looper', 'bin/looper-stop'],
)
