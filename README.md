Modsniffer overview
==============

So, you've got a program that you're working on, and you're tired of
hitting Ctrl-C, Up, Enter.  You'd like it to just restart every time you
make a change.  Here's how Modsniffer helps you solve this problem:

1.	Early in your program startup, you instantiate
	`modsniffer.detector.ModulesChangeDetector` with a 0-arg callable
	(one that quits your program).

2.	In addition, you set up a timer to call `yourModulesChangeDetector.checkForChanges()`
	every few seconds.  If any of your imported modules have changed,
	the `callable` you passed in earlier will be called.

3.	Your callable quits your program. (`sys.exit()`, or if using Twisted, `reactor.stop()`)

4.	A parent process keeps restarting your program in a loop.  You can use
	the included `bin/looper` if it suits your needs.


Installation
========
`python setup.py install`

This installs the module `modsniffer` as well as the binaries `looper` and `looper-stop`.


Sample use
========
This example uses Twisted, but there's nothing Twisted-specific in Modsniffer.

```
# demo.py

import sys
from twisted.python import log
log.startLogging(sys.stdout)

from twisted.internet import task
from twisted.internet import reactor
from modsniffer.detector import ModulesChangeDetector

stopper = ModulesChangeDetector(
	lambda: reactor.callWhenRunning(reactor.stop),
	logCallable=log.msg)
	# logCallable is optional; if not passed, it uses print.

looping = task.LoopingCall(stopper.checkForChanges)
looping.start(1.0, now=True) # check every 1 sec

reactor.run()
```

Run the above program with `looper`, which will restart it every time it quits:

```
looper python demo.py
```

If you modify demo.py or any module it has imported, you'll see the program restart.


Running the tests
=============

Install Twisted, then `trial modsniffer`.


Wishlist
=====
*	Detect changes to modules outside of the process.  Feed a list of files
	to some parent process that monitors the modules for the often-restarting child.
	This would fix a race condition where a module is changed before
	`ModulesChangeDetector` takes a look at it.

*	Rewrite the tests; don't spawn child `python`s.

*	Document optional use of Pyflakes (see the source for now).
