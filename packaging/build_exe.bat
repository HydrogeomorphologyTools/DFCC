@echo off
REM ============================================================
REM  Build the stand-alone Windows DFCC executable (double-click me)
REM  Needs Python 3.10-3.13 (64 bit) installed (python.org / Anaconda / OSGeo4W...).
REM  Usage:  build_exe.bat [folder / onefile / all]      (default: folder)
REM     folder  -> dist\DFCC\DFCC.exe + dist\DFCC\_internal   (fast start; zip the folder to distribute)
REM     onefile -> dist_onefile\DFCC.exe                       (single file, no folder needed; slower start)
REM     all     -> both
REM  DFCC.exe without arguments = GUI; with arguments = command line
REM     DFCC.exe run dtm.tif -o out --runout     DFCC.exe fill dtm.tif out.tif     DFCC.exe --version
REM ============================================================
setlocal
set MODE=%~1
if "%MODE%"=="" set MODE=folder
if /i not "%MODE%"=="folder" if /i not "%MODE%"=="onefile" if /i not "%MODE%"=="all" ( echo Unknown mode "%MODE%". Use: folder, onefile or all. & pause & exit /b 1 )
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
if /i not "%MODE%"=="onefile" (
  pyinstaller --noconfirm --distpath ..\dist --workpath ..\build dfcc.spec || ( pause & exit /b 1 )
)
if /i not "%MODE%"=="folder" (
  pyinstaller --noconfirm --distpath ..\dist_onefile --workpath ..\build_onefile dfcc_onefile.spec || ( pause & exit /b 1 )
)
cd ..
echo.
if /i not "%MODE%"=="onefile" (
  dist\DFCC\DFCC.exe --version
  echo Done: %cd%\dist\DFCC\DFCC.exe
  echo You can zip the folder dist\DFCC and distribute it.
)
if /i not "%MODE%"=="folder" (
  dist_onefile\DFCC.exe --version
  echo Done: %cd%\dist_onefile\DFCC.exe
  echo Single file: distribute DFCC.exe alone. It unpacks itself to %%TEMP%% at each start, so it starts more slowly.
)
echo QGIS/ArcGIS plugins find the executable through the DFCC_EXE variable or the PATH.
pause
