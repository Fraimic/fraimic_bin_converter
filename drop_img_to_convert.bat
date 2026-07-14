@echo off
setlocal

cd /d "%~dp0"

if "%~1"=="" (
    echo Drop one or more images onto this BAT file.
    echo You can also drop a folder to process all the images it contains.
    echo.
    echo Usage:
    echo   - Drag one or more images onto this file
    echo   - Then choose fit mode and dithering
    echo.
    echo Supported input formats:
    echo   .jpg, .jpeg, .png, .tiff, .tif, .webp, .gif
    echo   .heic too, if pillow-heif is installed.
    echo.
    pause
    exit /b 1
)

set "FIT=crop"
set "DITHER=atkinson"

echo.
echo ========================================
echo Image fit mode
echo ========================================
echo [L] letterbox = fit whole image, black bars, no cropping
echo [R] rotate    = rotate landscape images upright, then letterbox
echo [C] crop      = fill frame fully, crop overflow
echo.
set /p "FITCHOICE=Choose fit mode [C]: "

if /i "%FITCHOICE%"=="L" set "FIT=letterbox"
if /i "%FITCHOICE%"=="R" set "FIT=rotate"
if /i "%FITCHOICE%"=="C" set "FIT=crop"

echo.
echo ========================================
echo Dithering
echo ========================================
echo [A] atkinson = best color accuracy, slower ^(~20-30 sec/image^)
echo [F] fs       = floyd-steinberg (almost instant, slightly less accurate)
echo.
set /p "DITHERCHOICE=Choose dithering [A]: "

if /i "%DITHERCHOICE%"=="A" set "DITHER=atkinson"
if /i "%DITHERCHOICE%"=="F" set "DITHER=fs"

echo.
echo Running:
echo   fit     = %FIT%
echo   dither  = %DITHER%
echo.

".venv\Scripts\python.exe" "convert_to_bin_spectra6.py" --fit %FIT% --dither %DITHER% %*

if errorlevel 1 (
    echo.
    echo ERROR
)

echo.
echo DONE!

ping 127.0.0.1 -n 3 >nul