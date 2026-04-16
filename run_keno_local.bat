@echo off
chcp 65001 >nul
cd /d "C:\Users\hacke\OneDrive\Máy tính\Claude Code\vietlot-ai"

echo ============================================
echo  VietLot AI - Keno/Bingo18 Auto Scraper
echo  %date% %time%
echo ============================================

:: Scrape keno + bingo18 (3 trang gần nhất)
py scripts\fetch_data.py keno bingo18 --pages 3

:: Git push nếu có data mới
git add data\keno.jsonl data\bingo18.jsonl 2>nul
git diff --staged --quiet
if errorlevel 1 (
    git commit -m "keno/bingo: %date% %time:~0,5%"
    git push origin main
    echo Push thanh cong!
) else (
    echo Khong co data moi.
)

echo Done: %time%
