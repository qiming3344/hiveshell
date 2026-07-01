@echo off
chcp 65001 >nul
echo ========================================
echo   蜂巢·灵壳 v3.1 安装脚本
echo   HiveShell v3.1 Installer
echo ========================================
echo.

:: 检查 Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.10+
    echo 下载: https://www.python.org/downloads/
    pause
    exit /b 1
)
echo [OK] Python 已安装

:: 安装依赖
echo.
echo 正在安装依赖...
pip install requests -q
if %errorlevel% neq 0 (
    echo [警告] pip install 失败，请手动执行: pip install requests
)
echo [OK] 依赖就绪

:: 检查可选: Ollama
echo.
echo 检查 Ollama (可选)...
ollama list >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Ollama 已安装 - 可使用纯本地模式
    echo   启动: python hiveshell.py --ollama
) else (
    echo [提示] Ollama 未安装（不影响使用）
    echo   云端模式: python hiveshell.py --custom
    echo   安装Ollama: https://ollama.com
)

:: 检查可选: ripgrep
rg --version >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] ripgrep 已安装 - grep_content 工具可用
) else (
    echo [提示] ripgrep 未安装，grep_content 工具不可用
    echo   安装: choco install ripgrep 或访问 https://github.com/BurntSushi/ripgrep
)

echo.
echo ========================================
echo   安装完成！
echo ========================================
echo.
echo 快速开始（选一种）:
echo.
echo   通用模式（推荐）:
echo     set HIVESHELL_API_URL=https://api.deepseek.com/v1/chat/completions
echo     set HIVESHELL_API_KEY=sk-你的密钥
echo     set HIVESHELL_MODEL=deepseek-chat
echo     python hiveshell.py --custom
echo.
echo   DeepSeek官方:
echo     set DEEPSEEK_API_KEY=sk-你的密钥
echo     python hiveshell.py --deepseek
echo.
echo   Ollama纯本地（零成本）:
echo     python hiveshell.py --ollama
echo.
echo   更多选项:
echo     python hiveshell.py --help
echo.
pause
