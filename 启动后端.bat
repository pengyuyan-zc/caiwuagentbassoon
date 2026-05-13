@echo off
chcp 65001 >nul
title 财务智能体 - 后端 API

echo.
echo ==================================================
echo   财务智能体 - LangGraph ReAct Agent 后端
echo   访问 http://127.0.0.1:5001/docs 查看 API 文档
echo ==================================================
echo.

call conda activate py311 >nul 2>&1
cd /d %~dp0
python -m agent.server

pause
