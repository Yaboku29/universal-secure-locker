@echo off
py -m PyInstaller --noconfirm --clean UniversalSecureLocker.spec
if errorlevel 1 exit /b %errorlevel%
echo Build selesai: dist\UniversalSecureLocker.exe
