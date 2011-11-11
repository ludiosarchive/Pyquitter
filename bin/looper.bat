@echo off

:: Starts a process in an infinite loop.

:: Sample usage:
:: looper ls -l
:: looper python script.py --some-args

:runonce
	echo [%date%%time%] starting: %*
	%*
	echo Process exited. Starting again in 1 second...
	ping -n 2 localhost >nul 2>&1

goto runonce
