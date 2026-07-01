@echo off
chcp 65001 >nul
cd /d "%~dp0"

:: 如果没有参数，使用默认SiliconFlow
if "%~1"=="" (
    python hiveshell.py
    goto :end
)

:: 传递所有参数
python hiveshell.py %*

:end
