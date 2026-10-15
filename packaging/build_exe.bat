@echo off
REM ============================================================
REM  Build the stand-alone Windows DFCC executable (double-click me)
REM  Needs Python 3.10-3.13 (64 bit) installed (python.org / Anaconda / OSGeo4W...).
REM  Result: dist\DFCC\DFCC.exe   (no arguments = GUI; with arguments = command line)
REM     DFCC.exe run dtm.tif -o out --runout     DFCC.exe fill dtm.tif out.tif     DFCC.exe --version
REM ============================================================
setlocal
cd /d "%~dp0\.."
set PY=
where py >nul 2>nul && set PY=py -3
if "%PY%"=="" where python >nul 2>nul && set PY=python
if "%PY%"=="" ( echo Python 3 not found on PATH. & pause & exit /b 1 )
%PY% -m venv build_venv || ( pause & exit /b 1 )
call build_venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install ".[gui]" pyinstaller || ( pause & exit /b 1 )
cd packaging
pyinstaller --noconfirm --distpath ..\dist --workpath ..\build dfcc.spec || ( pause & exit /b 1 )
cd ..
dist\DFCC\DFCC.exe --version
echo.
echo Done: %cd%\dist\DFCC\DFCC.exe
echo You can zip the folder dist\DFCC and distribute it. QGIS/ArcGIS plugins find it through the DFCC_EXE variable or the PATH.
pause
