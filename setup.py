#!/usr/bin/env python

import os
from distutils.core import setup

import pyquitter

scripts = ['bin/looper', 'bin/looper-stop']
if os.name == 'nt':
	# On Windows, install all 4 scripts because the non-bat
	# scripts might be useful in an msys/cygwin environment.
	scripts += ['bin/looper.bat', 'bin/looper-stop.bat']

# Note: For reasons unknown to me, distutils (2.7.2) and pip
# install the .bat files on non-Windows OSes as well.  This
# is not intended; don't count on these .bat files being present
# in the future.

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
	scripts=scripts,
)
