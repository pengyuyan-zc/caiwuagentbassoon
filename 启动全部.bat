@echo off
chcp 65001 >nul
title 财务智能体 - LangGraph ReAct Agent

echo.
echo ==================================================
echo   财务智能体 - LangGraph ReAct Agent
echo   模型: qwen-turbo
echo ==================================================
echo.

:: 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.10+
    pause
    exit /b 1
)

:: 安装依赖（如果未安装）
call conda activate py311 >nul 2>&1
pip show langgraph >nul 2>&1
if errorlevel 1 (
    echo [提示] 正在安装依赖...
    pip install -r requirements.txt -q
)

:: 启动后端
echo [启动] 后端服务 (http://127.0.0.1:5001) ...
start "财务智能体-API" cmd /k "cd /d %~dp0 && call conda activate py311 >nul 2>&1 && python -m agent.server"

:: 等待后端启动
timeout /t 3 /nobreak >nul

:: 启动前端
echo [启动] 前端服务 (http://localhost:3000) ...
cd /d "%~dp0web"
if exist "node_modules" (
    start "财务智能体-前端" cmd /k "npm run dev"
) else (
    echo [提示] 正在安装前端依赖...
    call npm install
    start "财务智能体-前端" cmd /k "npm run dev"
)

echo.
echo ==================================================
echo   启动完成！
echo   后端 API: http://127.0.0.1:5001
echo   前端界面: http://localhost:3000
echo   API 文档: http://127.0.0.1:5001/docs
echo ==================================================
echo.
echo 提示：关闭此窗口不会停止服务，可直接关闭各命令行窗口
pause
