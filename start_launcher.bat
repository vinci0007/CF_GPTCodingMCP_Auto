@echo off
setlocal

cd /d "%~dp0"

echo.
echo Coding Tools MCP Launcher
echo Project: %CD%
echo.

echo [1/5] Checking project runtime directories...
if not exist ".runtime" mkdir ".runtime"
if not exist ".runtime\logs" mkdir ".runtime\logs"
if not exist ".runtime\state" mkdir ".runtime\state"
if not exist ".runtime\bin" mkdir ".runtime\bin"

if not exist ".venv\Scripts\python.exe" (
    echo [2/5] Creating project virtual environment...
    where uv >nul 2>nul
    if errorlevel 1 (
        echo ERROR: uv was not found in PATH.
        echo Please install uv first, or add it to PATH.
        pause
        exit /b 1
    )
    uv venv .venv
    if errorlevel 1 (
        echo ERROR: Failed to create .venv.
        pause
        exit /b 1
    )
) else (
    echo [2/5] Project virtual environment exists.
)

echo [3/5] Checking coding-tools-mcp...
if not exist ".venv\Scripts\coding-tools-mcp.exe" (
    echo Installing coding-tools-mcp into project .venv...
    where uv >nul 2>nul
    if errorlevel 1 (
        echo ERROR: uv was not found in PATH.
        echo Please install uv first, or add it to PATH.
        pause
        exit /b 1
    )
    uv pip install --python ".venv\Scripts\python.exe" --upgrade pip
    if errorlevel 1 (
        echo ERROR: Failed to upgrade pip.
        pause
        exit /b 1
    )
    uv pip install --python ".venv\Scripts\python.exe" --upgrade coding-tools-mcp pyjwt
    if errorlevel 1 (
        echo ERROR: Failed to install coding-tools-mcp.
        echo If your network needs a proxy before the GUI opens, run this first:
        echo set HTTP_PROXY=http://127.0.0.1:20100
        echo set HTTPS_PROXY=http://127.0.0.1:20100
        echo After the GUI opens, proxy can be configured freely in the Proxy panel.
        pause
        exit /b 1
    )
) else (
    echo coding-tools-mcp already installed.
)

echo [4/5] Checking GUI files...
if not exist "app.py" (
    echo ERROR: app.py was not found.
    pause
    exit /b 1
)

where cloudflared >nul 2>nul
if errorlevel 1 (
    echo NOTE: cloudflared was not found in PATH.
    echo       Local Codex mode can still work.
    echo       ChatGPT Web Mode can auto-download cloudflared into .runtime\bin.
)

echo [5/5] Starting desktop launcher...
".venv\Scripts\python.exe" app.py

endlocal
