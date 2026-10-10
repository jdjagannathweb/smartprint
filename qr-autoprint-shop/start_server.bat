@echo off
title Smart QR Auto-Print Shop Server
color 0b
echo ========================================================
echo       SMART QR SCAN, PAY & AUTO-PRINT SERVER
echo ========================================================
echo.
echo Starting Python Backend Server...
start "" http://localhost:8000/admin
python server.py
pause
