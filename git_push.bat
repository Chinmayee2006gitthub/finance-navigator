@echo off
cd /d "%~dp0"

echo [1/7] Copying generated assets to project directory...
if not exist assets mkdir assets
copy /y "C:\Users\LENOVO\.gemini\antigravity-ide\brain\ecb62713-a892-4483-9869-503686901f6b\architecture_diagram_1783096957398.png" "assets\architecture_diagram.png"
copy /y "C:\Users\LENOVO\.gemini\antigravity-ide\brain\ecb62713-a892-4483-9869-503686901f6b\cover_page_banner_1783097079176.png" "assets\cover_page_banner.png"
copy /y "C:\Users\LENOVO\.gemini\antigravity-ide\brain\ecb62713-a892-4483-9869-503686901f6b\project_thumbnail_1783331540170.png" "assets\project_thumbnail.png"

echo [2/7] Initializing local Git repository...
git init

echo [3/7] Configuring local git identity...
git config user.email "chinmayee@example.com"
git config user.name "Chinmayee"

echo [4/7] Staging files...
git add .

echo [5/7] Committing changes...
git commit -m "Add workflow diagram and cover banner assets"

echo [6/7] Setting up branch and remote...
git branch -M main
git remote remove origin 2>nul
git remote add origin https://github.com/Chinmayee2006gitthub/finance-navigator.git

echo [7/7] Pushing files to GitHub...
git push -u origin main

echo.
echo ===================================================
echo Done! Your code and assets have been pushed.
echo ===================================================
pause
