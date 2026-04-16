@echo off
chcp 65001 >nul
cd /d "C:\Users\hacke\OneDrive\Máy tính\Claude Code\vietlot-ai"

echo ================================================
echo  VietLot AI - Keno Backfill (vietlott.vn)
echo  %date% %time%
echo ================================================
echo.

:: Backfill tat ca cac ngay con thieu trong 30 ngay gan nhat
py scripts\fetch_keno_vietlott.py

echo.
git add data\keno.jsonl
git diff --staged --quiet
if errorlevel 1 (
    git commit -m "keno: backfill local %date%"
    git push origin main
    echo Da push len GitHub!
) else (
    echo Khong co du lieu moi.
)

echo.
echo Done: %time%
pause
