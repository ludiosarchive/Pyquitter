import os
import sys
import time
import _ast
import pprint

from pypycpyo.logplex import log

try:
	import pyflakes.checker
	havePyflakes = True
except ImportError:
	log.msg('%s: pyflakes not available; install it for slightly safer detection' % __name__)
	havePyflakes = False

# Does this Python implementation use .pyo files?
# CPython does, pypy doesn't.
pythonUsesPyo = not hasattr(sys, 'pypy_version_info')


class SourceChangesDetector(object):
	"""
	I call L{callable} if any of the running program's source files or
	compiled-module files have changed, unless the source files have
	syntax errors or important pyflakes messages.


	I have two modes of operation with subtle consequences.

	After I have taken some initial readings, I will notice if any imported module
	has changed (even modules imported sometime later during program execution)
	In Mode 1, I can even guess if modules have changed before taking the
	initial readings.

	Mode 1 is recommended. To use it, pass an accurate pyLaunchTime,
		as described in the snippet below.

	Mode 2 is useful if you expect to dynamically import modules with mtimes
	above the start time of the program, without me executing the callable.
	To use Mode 2, pass 2**31 for pyLaunchTime.
	The disadvantage of Mode 2 is that I cannot guess if modules were changed
	before I took the initial mtime/ctime/size readings.


	A recommended L{callable} is one that exits the program,
	as long as another process is restarting this program in a loop.

	Check the example/ directory to see how to use me with Twisted
	(if you are not using twistd). If you are using twistd, see the reloadingService
	decorator in this file.

	Important note for Mode 1:
	If you expect me to catch source changes before I take the initial readings,
	and the source is located on network drives, all local and remote clocks
	must be accurate to ~10ms or better.
	In the future, SourceChangesDetector *could* check the clock drift on each
	drive (especially network drives), but this is a bit beyond its scope.

	Important: if your os.stat resolution on source files is bad (1 second), and you change
	a file without changing the file size, this could (very, very rarely) miss a source change.
	"""

	# Print extra messages?
	noisy = False

	# Track changes in .pyc/.pyo files too?
	#	Only set to True if your .pyc/.pyo files are updating, with possibly no .py files present.
	alsoTrackPycPyos = False

	def __init__(self, callable, pyLaunchTime, usePyflakes=False):
		"""
		When any module that the program has loaded changes,
		I'll call L{callable} with no arguments.

		L{pyLaunchTime} is a unix timestamp that you should get yourself before importing
		anything. A good pyLaunchTime is taken at the very beginning of program execution,
		and looks like this:
		C{
			import time
			pyLaunchTime = time.time()-time.clock()-0.01
		}
		If modules are stored on network drives, it might be safer to use
			time.time()-time.clock()-(1.01)
		to avoid missing a possible change (applies only to changes around program start).

		"""
		self._times = {}
		self._alreadyCheckedOnce = set()
		self.callable = callable
		self.pyLaunchTime = pyLaunchTime
		self.usePyflakes = usePyflakes

		# _unresolvedSourceProblems exists because checking
		# every imported file for syntax errors and Pyflakes messages would be bad.
		# I'll remember which updated files have errors, and if
		# all errors are resolved by even-newer versions, I'll know to call the callback.
		self._unresolvedSourceProblems = set()


	def _sourcePaths(self):
		while True:
			try:
				for moduleName, m in sys.modules.iteritems():
					if m is None:
						continue # some modules (maybe just some encodings.*) are None
					if getattr(m, '__file__', None) is None:
						continue # some modules (maybe just sys?) don't have a __file__

					# Even though this uses .lower(), do not assume that this will work
					# properly with upper-case .PY / .PYC / .PYO files.
					lowered = m.__file__.lower()
					if pythonUsesPyo and lowered.endswith('.pyo'):
						# Python checks for .py first, .pyc second, .pyo last.
						# So if the __file__ is a .pyo, an updated .py or .pyc could supercede it.
						# But, don't actually track the compiled versions unless the user wants to,
						# because any sane person has updated .py files instead, and those
						# are the ones that should usually be tracked.
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
				break
			except RuntimeError:
				# sys.modules.iteritems() will occasionally result in:
				# exceptions.RuntimeError: dictionary changed size during iteration
				#
				# but it doesn't happen often enough to change iteritems -> items
				log.msg('Harmless warning: (probably) sys.modules changed while iterating over it.')


	def checkForChanges(self):
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
					log.msg('''
Could not stat file %s; maybe it is gone.
If you have .pyo files, but no .pyc and .py files,
or maybe .pyc files, but no .py files, this message may appear a lot.''' % (repr(f),))
				# Carefully note how this avoids the pyLaunchTime logic.
				important = (-1, -1, -1)

			howMany += 1
			if f not in self._times:
				self._times[f] = important

			# Detect any *any* mtime/ctime/size change, or if mtime >= pyLaunchTime
			# Note: NTFS keeps 1s resolution mtimes.
			# But over SMB to a Linux system with XFS/JFS,
			#	we seem to get mtimes with ~10ms resolution.

			##print stat.st_mtime, self.pyLaunchTime
			##mtimes_debug.append(stat.st_mtime)
			if self._times[f] != important:
				self._times[f] = important
				whichChanged.add(f)
			elif stat.st_mtime >= self.pyLaunchTime and f not in self._alreadyCheckedOnce:
				log.msg('''
File %s triggered the pyLaunchTime condition.
This means that the file may have changed before I took the
initial mtime/ctime/size readings.

During normal operation, this may cause one "unnecessary"
execution of the callable. If this triggers repeatedly, the system
clock is many seconds slower than the filesystem's timestamps.''' % f)
				whichChanged.add(f)
			# If the file was already checked for the pyLaunchTime condition,
			# don't let the pyLaunchTime condition trigger.
			# (else, if the clock jumps back, there could be a problem)
			self._alreadyCheckedOnce.add(f)
		##print sorted(mtimes_debug), self.pyLaunchTime
		if self.noisy:
			log.msg('Checked %d files for changes in %f seconds.' % (howMany, time.time()-start))

		if whichChanged:
			self.sourceFilesChanged(whichChanged)


	def sourceFilesChanged(self, whichFiles):
		log.msg('Detected a change in %d source files %s' % (len(whichFiles), repr(whichFiles),))

		for f in self._unresolvedSourceProblems:
			assert isinstance(f, str)

		self._updateProblems(whichFiles)

		for f in self._unresolvedSourceProblems:
			assert isinstance(f, str)

		if len(self._unresolvedSourceProblems) == 0:
			self.callable()
		else:
			log.msg('Not calling because of unresolved problems in:\n%s' %
				(pprint.pformat(self._unresolvedSourceProblems),))


	def _updateProblems(self, whichFiles):
		# TODO: test all _unresolvedSourceProblems logic
		for f in whichFiles:
			if f.lower().endswith('.py'):
				# We can only check for syntax errors and pyflakes messages in .py files.
				# .so, .pyc, .pyo files are not checked for validity.
				didParse = False
				try:
					try:
						# TODO: test for old regression, where too many FDs were kept open
						fh = file(f, 'U')
						# Python thinks no terminating newline is a SyntaxError, so always add one.
						# This matches what Pyflakes does.
						contents = fh.read() + '\n'
						fh.close()
					except (OSError, IOError):
						# The file may have been deleted, before the stat, or after the stat.
						# Assume the file is gone for a while, or will be parseable soon
						# (do no further checks)
						self._unresolvedSourceProblems.discard(f)
					else:
						compile(contents, f, "exec")
						didParse = True
				except SyntaxError:
					log.err()
					log.msg('File %s has SyntaxError, so not calling callable.' % (f,))
					self._unresolvedSourceProblems.add(f)
				else:
					# If Pyflakes is available, `f' could get re-.add()ed
					# very soon by the logic below.
					self._unresolvedSourceProblems.discard(f)

				if self.usePyflakes and havePyflakes and didParse:
					havePyflakesError = False
					tree = compile(contents, f, "exec", _ast.PyCF_ONLY_AST)
					for message in pyflakes.checker.Checker(tree, f).messages:
						log.msg('Pyflakes:', message)
						if not isinstance(message,
						(pyflakes.messages.UnusedImport, pyflakes.messages.UnusedVariable)):
							# Unused imports or local variables aren't bad enough to abort a reload,
							# but any other message is bad.
							#	(see Pyflakes/pyflakes/messages.py)
							log.msg('Pyflakes says file %s is bad, so not calling callable.' % (f,))
							havePyflakesError = True

					if not havePyflakesError:
						self._unresolvedSourceProblems.discard(f)
					else:
						self._unresolvedSourceProblems.add(f)



def reloadingService(interval):
	"""
	Twisted-specific 'makeService' method decorator.

	Use like this in your .tap / twisted plugin:

	@detector.reloadingService(2.5)
	def makeService(self, options):
		...

	"""

	def intervalizedWrapper(makeServiceMethod):

		def replacementMethod(*args, **kwargs):

			pyLaunchTime = time.time()-time.clock()-0.01

			from twisted.internet import task
			from twisted.internet import reactor

			service = makeServiceMethod(*args, **kwargs)

			stopper = SourceChangesDetector(lambda: reactor.callWhenRunning(reactor.stop), pyLaunchTime)
			looping = task.LoopingCall(stopper.checkForChanges)
			looping.start(interval, now=True)

			return service

		return replacementMethod

	return intervalizedWrapper
