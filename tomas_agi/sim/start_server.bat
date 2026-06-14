@echo off
REM TOMAS 后端启动脚本
REM 使用 Python 虚拟环境

set PYTHON=C:\Users\1\.workbuddy\binaries\python\envs\tomas\Scripts\python.exe
cd /d %~dp0

echo 🚀 启动 TOMAS 后端服务器...
echo 数据库: D:/tomas-data/tomas.db
echo.

%PYTHON% server.py
pause
