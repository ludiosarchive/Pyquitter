from __future__ import with_statement

import os
import sys
import time
import _ast
import pprint
import traceback

try:
	import pyflakes.checker
	havePyflakes = True
except ImportError:
	print '%s: pyflakes not available; install it for slightly safer detection' % (__name__,)
	havePyflakes = False

# Does this Python implementation use .pyo files?
# CPython does, pypy doesn't.
pythonUsesPyo = not hasattr(sys, 'pypy_version_info')


def _print(x):
	print x


class ChangeDetector(object):
	"""
	This object calls L{callable} if any of the running program's source files
	or compiled-module files have changed, unless the source files have
	syntax errors or important pyflakes messages.  You must call
	C{.poll} periodically to check for changes in imported modules.

	For L{callable}, you should probably pass one that exits the program.
	A parent process should be restarting your program in a loop.  See the
	example/ directory.

	Note that this will sometimes miss a change, if your source modules
	change before ChangeDetector first takes a look at them.  This
	is very rare but can happen early in your program startup.
	"""

	# Print extra messages?
	noisy = False

	# Track changes in .pyc/.pyo files too?  Only set to True if your
	# .pyc/.pyo files are updating, with possibly no .py files present.
	alsoTrackPycPyos = False

	def __init__(self, callable, logCallable=_print, usePyflakes=False):
		"""
		C{callable} is the 0-arg callable to call when any of the imported
			modules have changed.

		C{logCallable} (optional) is the 1-arg callable to call with log messages.
			If not passed, uses print.

		C{usePyflakes} (optional) determines whether to check for serious
			errors in the new module with Pyflakes first.  If such errors are
			found, C{callable} will not be called.
		"""
		self._times = {}
		self.callable = callable
		self._logCallable = logCallable
		self.usePyflakes = usePyflakes

		# _unresolvedSourceProblems exists because checking
		# every imported file for syntax errors and Pyflakes messages would
		# be bad.  Instead, remember which updated files have errors, and if
		# all errors are resolved by even-newer versions, I'll know to call
		# the callback.
		self._unresolvedSourceProblems = set()


	def _sourcePaths(self):
		# .items() because it may change during iteration
		for moduleName, m in sys.modules.items():
			if m is None:
				continue # some modules (maybe just some encodings.*) are None
			if getattr(m, '__file__', None) is None:
				continue # some modules (maybe just sys?) don't have a __file__

			# Even though this uses .lower(), do not assume that this will work
			# properly with upper-case .PY / .PYC / .PYO files.
			lowered = m.__file__.lower()
			if pythonUsesPyo and lowered.endswith('.pyo'):
				# Python checks for .py first, .pyc second, .pyo last.
				# So if the __file__ is a .pyo, an updated .py or .pyc
				# could supercede it.  But, don't actually track the
				# compiled versions unless the user wants to, because
				# any sane person has updated .py files instead, and
				# those are the ones that should usually be tracked.
				if self.alsoTrackPycPyos:
					yield m.__file__
					yield m.__file__.rsplit('.', 1)[0] + '.pyc'
				yield m.__file__.rsplit('.', 1)[0] + '.py'
			elif lowered.endswith('.pyc'):
				if self.alsoTrackPycPyos:
					yield m.__file__
				yield m.__file__.rsplit('.', 1)[0] + '.py'
			else:
				# could be .py or .so or anything else
				yield m.__file__


	def poll(self):
		"""
		Call this to check for changes.
		"""
		start = time.time()
		howMany = 0
		whichChanged = set()
		##mtimes_debug = []
		for f in self._sourcePaths():
			try:
				stat = os.stat(f)
				important = (stat.st_mtime, stat.st_ctime, stat.st_size)
			except (OSError, IOError):
				# if file isn't there, it has no source problems
				self._unresolvedSourceProblems.discard(f)
				if self.noisy:
					self._logCallable('''
Could not stat file %s; maybe it is gone.
If you have .pyo files, but no .pyc and .py files,
or maybe .pyc files, but no .py files, this message may appear a lot.''' % (repr(f),))
				important = (-1, -1, -1)

			howMany += 1
			if f not in self._times:
				self._times[f] = important

			# Detect any *any* mtime/ctime/size change.  Note that
			# mtime/ctime resolution may be as bad as 1 second.

			##mtimes_debug.append(stat.st_mtime)
			if self._times[f] != important:
				self._times[f] = important
				whichChanged.add(f)
		##print sorted(mtimes_debug)
		if self.noisy:
			self._logCallable('Checked %d files for changes in %f seconds.' % (
				howMany, time.time() - start))

		if whichChanged:
			self._sourceFilesChanged(whichChanged)


	def _sourceFilesChanged(self, whichFiles):
		self._logCallable('Detected a change in %d source files %s' % (
			len(whichFiles), repr(whichFiles),))

		for f in self._unresolvedSourceProblems:
			assert isinstance(f, basestring), type(f)

		self._updateProblems(whichFiles)

		for f in self._unresolvedSourceProblems:
			assert isinstance(f, basestring), type(f)

		if len(self._unresolvedSourceProblems) == 0:
			self.callable()
		else:
			self._logCallable('Not calling because of unresolved problems in:\n%s' % (
				pprint.pformat(self._unresolvedSourceProblems),))


	def _updateProblems(self, whichFiles):
		# TODO: test all _unresolvedSourceProblems logic
		for f in whichFiles:
			if f.lower().endswith('.py'):
				# We can only check for syntax errors and pyflakes messages in .py files.
				# .so, .pyc, .pyo files are not checked for validity.
				didParse = False
				try:
					try:
						with file(f, 'U') as fh:
							# Python thinks no terminating newline is a
							# SyntaxError, so always add one.  This is
							# what Pyflakes does.
							contents = fh.read() + '\n'
					except (OSError, IOError):
						# The file may have been deleted, before the stat, or after the stat.
						# Assume the file is gone for a while, or will be parseable soon
						# (do no further checks)
						self._unresolvedSourceProblems.discard(f)
					else:
						compile(contents, f, "exec")
						didParse = True
				except SyntaxError:
					tb = traceback.format_exc()
					self._logCallable('File %s has SyntaxError, '
						'so not calling callable:\n\n%s' % (f, tb))
					self._unresolvedSourceProblems.add(f)
				else:
					# If Pyflakes is available, `f' could get re-.add()ed
					# very soon by the logic below.
					self._unresolvedSourceProblems.discard(f)

				if self.usePyflakes and havePyflakes and didParse:
					havePyflakesError = False
					tree = compile(contents, f, "exec", _ast.PyCF_ONLY_AST)
					for message in pyflakes.checker.Checker(tree, f).messages:
						self._logCallable('Pyflakes:%s' % (message,))
						if not isinstance(message, (
						pyflakes.messages.UnusedImport,
						pyflakes.messages.UnusedVariable)):
							# Unused imports or local variables aren't bad
							# enough to abort a reload, but any other
							# message is bad.  See Pyflakes/pyflakes/messages.py
							self._logCallable('Pyflakes says file %s is bad, '
								'so not calling callable.' % (f,))
							havePyflakesError = True

					if not havePyflakesError:
						self._unresolvedSourceProblems.discard(f)
					else:
						self._unresolvedSourceProblems.add(f)
