@echo off
REM StealthCard 一键构建脚本（对应开发计划文档 4.4）
REM 在纯净虚拟环境中打包，避免全局无关包被卷入 EXE
setlocal
cd /d "%~dp0"

python -m venv build_env
call build_env\Scripts\activate.bat
pip install PyQt5 openpyxl PyYAML pynput watchdog psutil pyinstaller
if errorlevel 1 goto :error

pyinstaller --clean build.spec
if errorlevel 1 goto :error

if exist dist\config rmdir /s /q dist\config
if exist dist\data rmdir /s /q dist\data
xcopy /E /I /Y config dist\config >nul
xcopy /E /I /Y data dist\data >nul

echo.
echo 构建完成：dist\RuntimeBrokerHost.exe
pause
exit /b 0

:error
echo.
echo 构建失败，请检查上方输出。
pause
exit /b 1
