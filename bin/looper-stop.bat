@echo off

:: Starts a process in an infinite loop; it is just like `looper.bat` except it
:: stops after getting a non-zero exit code from the child process.

:: Sample usage:
:: looper-stop ls -l
:: looper-stop python script.py --some-args

:runonce
	echo [%date%%time%] starting: %*
	%*
	if %errorlevel% neq 0 exit /b %errorlevel%
	echo Process exited. Starting again in 1 second...
	ping -n 2 localhost >nul 2>&1

goto runonce
