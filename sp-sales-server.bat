@echo off
:: SP Sales Control — Auto Restart Server
:: Uses 8.3 short paths to avoid Hebrew character issues

cd /d C:\Users\-'4452~1\DOCUME~1\TOM-WO~1\SP-SAL~1

:RESTART
:: Kill any existing instance on port 8501
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8501 ^| findstr LISTENING') do taskkill /PID %%a /F >nul 2>&1

:: Run Streamlit (blocking)
C:\Users\-'4452~1\AppData\Local\Programs\Python\PYTHON~1\python.exe -m streamlit run app.py --server.headless true --server.address 0.0.0.0 --server.port 8501

:: If Streamlit exits — wait 3 seconds and restart
timeout /t 3 /nobreak >nul
goto RESTART
