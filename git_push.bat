@echo off
cd /d "%~dp0"

echo [1/6] Initializing local Git repository...
git init

echo [2/6] Configuring local git identity...
git config user.email "chinmayee@example.com"
git config user.name "Chinmayee"

echo [3/6] Staging files...
git add .

echo [4/6] Creating first commit...
git commit -m "Initial commit: Complete secure multi-agent Finance Navigator"

echo [5/6] Setting up branch and remote...
git branch -M main
git remote remove origin 2>nul
git remote add origin https://github.com/Chinmayee2006gitthub/finance-navigator.git

echo [6/6] Pushing files to GitHub...
git push -u origin main

echo.
echo ===================================================
echo Done! Your code has been pushed to GitHub.
echo ===================================================
pause
