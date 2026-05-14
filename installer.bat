@echo off
echo ============================================================
echo   Installation des dependances PIA WG Generator
echo ============================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [!] Python n'est pas installe ou pas dans le PATH.
    echo     Telecharge Python sur https://www.python.org/downloads/
    echo     Coche "Add Python to PATH" lors de l'installation.
    pause
    exit /b 1
)

echo [+] Python detecte.
echo.
echo [ ] Installation des librairies...
pip install -r requirements.txt

echo.
echo [+] Installation terminee. Lance le generateur avec :
echo     python pia_wg_generator.py
echo.
pause
