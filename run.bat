@echo off
cd /d "%~dp0"
echo ================================================
echo   MiriLab - Policy Reaction Simulator
echo   The browser will open shortly...
echo   Press Ctrl+C in this window to stop.
echo ================================================
echo.
python -m streamlit run app.py
echo.
echo ------------------------------------------------
echo App stopped. If this window closed instantly,
echo install first:  run setup.bat
echo            (or)  pip install -r requirements.txt
echo ------------------------------------------------
pause
