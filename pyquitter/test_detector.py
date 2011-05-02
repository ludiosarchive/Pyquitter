from __future__ import with_statement

import sys
import os

from twisted.trial import unittest
from twisted.internet import reactor, defer, protocol
from twisted.python import log

try:
	import pyflakes.checker
	havePyflakes = True
except ImportError:
	log.msg('%s: pyflakes not available; some tests will not be run.')
	havePyflakes = False

# Keep this import here to make import-time failures happen here,
# not in the child process.
from pyquitter.detector import pythonUsesPyo



class WaitForOK(protocol.ProcessProtocol):

	def __init__(self):
		self.done = defer.Deferred()
		self.okToWrite = defer.Deferred()
		self.stdout = ''


	def connectionMade(self):
		self.transport.closeStdin()


	def errReceived(self, data):
		print "stderr:", data


	def killIfData(self, data):
		if 'has SyntaxError' in data or 'Pyflakes says' in data:
			self.transport.signalProcess('KILL')


	def outReceived(self, data):
		# Print only uncommon messages to keep trial output clean
		if not ('Write over me now.' in data or \
			 'Stopping because changes found.' or \
			 'Detected a change in source files '):
			print "stdout:", data
			
		self.stdout += data

		self.killIfData(data)

		# TODO: Don't assume that we'll get the string all at once (?)
		# Does this ever happen?
		if "Write over me now." in data:
			self.okToWrite.callback(None)


	def processEnded(self, statusObject):
		self.done.callback(None)



class DetectorTests(unittest.TestCase):
	stopper = 'detector.ChangeDetector'
	makePycPyoAndDeletePy = False
	extraPyArgs = []

	def getTimeout(self):
		return 12
		

	def cbProcessReady(self, pyFile):
		with open(pyFile, 'wb') as new:
			new.write('# nothing (written by %s)' % (__file__,))

		# makePycPyoAndDeletePy = False means we are not tracking bare
		# pyc and pyo files, so writing something to them should have
		# no effect. Confirm this.
		with open(pyFile + 'c', 'wb') as f:
			f.write('#1')
		with open(pyFile + 'o', 'wb') as f:
			f.write('#2')


	def cbFinalAsserts(self, pp):
		self.assertEqual(1, pp.stdout.count('Write over me now.'), pp.stdout)
		# It might detect a change in more than 1 source file, if the .pyc (.pyo)
		# files for dependencies like Python's Lib are fresh enough.
		self.assertEqual(1, pp.stdout.count('Detected a change in '), pp.stdout)
		self.assertEqual(1, pp.stdout.count(
			'[not detector] Stopping because changes found.'), pp.stdout)


	def test_detector(self):
		baseName = self.mktemp()
		mainFile = baseName + '.py'

		with open(mainFile, 'wb') as main:
			main.write('''\
import %s_importable
	''' % (os.path.split(mainFile)[-1].replace('.py', ''),))

		pyFile = baseName+'_importable.py'
		
		# ugly hack to make the tests pass when pyquitter is not installed
		# (get the parent directory of the directory test_detector.py is in)
		cwd = os.path.split(os.path.split(__file__)[0])[0]
		with open(pyFile, 'wb') as tempFile:
			tempFile.write('''\
import sys
from twisted.python import log
log.startLogging(sys.stdout)

sys.path.insert(0, %s)
from pyquitter import detector
import time

stop = False

def setStop():
	global stop
	stop = True

class MoreTrackingDetector(detector.ChangeDetector):
	alsoTrackPycPyos = True

class NoisyDetector(detector.ChangeDetector):
	noisy = True

stopper = %s(setStop, usePyflakes=True)

stopper.poll()

print "Write over me now."
sys.stdout.flush()

while True:
	stopper.poll()
	if stop:
		print '[not detector] Stopping because changes found.'
		break
	time.sleep(0.01)''' % (repr(cwd), self.stopper))

		if self.makePycPyoAndDeletePy:
			import py_compile
			py_compile.compile(pyFile, pyFile + 'c')
			py_compile.compile(pyFile, pyFile + 'o')
			os.unlink(pyFile)

		d = defer.Deferred()

		def startRealTest():
			# Our CPython prime2 branch supports stripping docstrings
			# in non-optimized mode with the -N flag, and we need to support
			# this here.  In the future, we could not spawn Python at all
			# in these tests.
			try:
				# Note that sys.flags is missing in pypy, and strip_docstrings
				# is missing in CPython trunk.
				strip_docstrings = (sys.flags.strip_docstrings == 1 or
					sys.flags.optimize == 2)
			except AttributeError:
				strip_docstrings = False
			extraNArg = ['-N'] if strip_docstrings else []

			args = [sys.executable] + self.extraPyArgs + extraNArg + [mainFile]

			pp = WaitForOK()
			reactor.spawnProcess(pp, sys.executable, args, {})

			pp.okToWrite.addCallback(lambda _: self.cbProcessReady(pyFile))
			pp.okToWrite.addErrback(d.errback)

			pp.done.addCallback(lambda _: self.cbFinalAsserts(pp))
			pp.done.addCallback(d.callback)
			pp.done.addErrback(d.errback)

		reactor.callWhenRunning(startRealTest)

		return d



class NoisyDetectorTests(DetectorTests):
	stopper = 'NoisyDetector'



class OnlyMtimeChanged(DetectorTests):

	def cbProcessReady(self, pyFile):
		import time
		os.utime(pyFile, (time.time() + 1, time.time() + 1))




class OnlySizeChanged(DetectorTests):

	def cbProcessReady(self, pyFile):
		# We can't set ctime in Python easily?

		stat = os.stat(pyFile)
		mtime = stat.st_mtime
		atime = stat.st_atime
		##print pyFile, os.stat(pyFile)
		with open(pyFile, 'ab') as new:
			new.write('#')
		os.utime(pyFile, (atime, mtime))

		### This is incredibly odd, but these asserts will fail on timestamp-precise filesystems
		### by tiny errors, for example, (1239538521.2763751, 1239538521.2763753)
		### So, this test doesn't really test "just size" on timestamp-precise filesystems,
		### because the mtime changes anyway.
		statAgain = os.stat(pyFile)
		###assert statAgain.st_mtime == mtime, (statAgain.st_mtime, mtime)
		###assert statAgain.st_atime == atime, (statAgain.st_atime, atime)

		##print pyFile, statAgain



class WhenSyntaxError(DetectorTests):
	"""
	Check that file isn't reloaded if there's a syntax error.
	"""
	def cbFinalAsserts(self, pp):
		self.assertEqual(1, pp.stdout.count('Write over me now.'))
		# It might detect a change in more than 1 source file, if the .pyc (.pyo)
		# files for dependencies like Python's Lib are fresh enough.
		self.assertEqual(1, pp.stdout.count('Detected a change in '))
		self.assertEqual(1, pp.stdout.count('has SyntaxError'))
		self.assertEqual(0, pp.stdout.count('[not detector] Stopping because changes found.'))


	def cbProcessReady(self, pyFile):
		with open(pyFile, 'ab') as new:
			new.write('\n\n$%!@*&$!@%$^!$')



class WhenPyflakesMessage(DetectorTests):
	"""
	Check that file isn't reloaded if Pyflakes doesn't like it.
	"""
	if not havePyflakes:
		skip = "Can't run this test without Pyflakes"

	def cbFinalAsserts(self, pp):
		self.assertEqual(1, pp.stdout.count('Write over me now.\n'))
		# It might detect a change in more than 1 source file, if the .pyc (.pyo)
		# files for dependencies like Python's Lib are fresh enough.
		self.assertEqual(1, pp.stdout.count('Detected a change in '))
		self.assertEqual(1, pp.stdout.count('Pyflakes says'))
		self.assertEqual(0, pp.stdout.count('[not detector] Stopping because changes found.'))


	def cbProcessReady(self, pyFile):
		with open(pyFile, 'ab') as new:
			# Make sure this isn't a syntax error
			new.write('\n\nasdfasdfasdf')
			new.close()



class PycOnlyDetectNewPyc(DetectorTests):
	"""
	.pyc loaded at import.
	change the .pyc, confirm its detection.
	"""
	stopper = 'MoreTrackingDetector'
	makePycPyoAndDeletePy = True

	def cbProcessReady(self, pyFile):
		with open(pyFile + 'c', 'ab') as f:
			f.write('#')



class PycOnlyDetectNewPy(DetectorTests):
	"""
	.pyc loaded at import.
	change the .py, confirm its detection.
	"""
	stopper = 'MoreTrackingDetector'
	makePycPyoAndDeletePy = True

	def cbProcessReady(self, pyFile):
		with open(pyFile, 'ab') as f:
			f.write('#')



class PyoOnlyDetectNewPyo(DetectorTests):
	"""
	.pyo loaded at import.
	change the .pyo, confirm its detection.
	"""
	if not pythonUsesPyo:
		skip = "This Python implementation doesn't use .pyo files."

	stopper = 'MoreTrackingDetector'
	makePycPyoAndDeletePy = True
	extraPyArgs = ['-O']

	def cbProcessReady(self, pyFile):
		with open(pyFile + 'o', 'ab') as f:
			f.write('#')



class PyoOnlyDetectNewPyc(DetectorTests):
	"""
	.pyo loaded at import.
	change the .pyc, confirm its detection.
	"""
	if not pythonUsesPyo:
		skip = "This Python implementation doesn't use .pyo files."

	stopper = 'MoreTrackingDetector'
	makePycPyoAndDeletePy = True
	extraPyArgs = ['-O']

	def cbProcessReady(self, pyFile):
		with open(pyFile + 'c', 'ab') as f:
			f.write('#')



class PyoOnlyDetectNewPy(DetectorTests):
	"""
	.pyo loaded at import.
	change the .py, confirm its detection.
	"""
	if not pythonUsesPyo:
		skip = "This Python implementation doesn't use .pyo files."

	stopper = 'MoreTrackingDetector'
	makePycPyoAndDeletePy = True
	extraPyArgs = ['-O']

	def cbProcessReady(self, pyFile):
		with open(pyFile, 'ab') as f:
			f.write('#')
