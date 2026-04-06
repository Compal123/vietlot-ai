@echo off
REM =====================================================
REM  VietLot AI — Tự động cập nhật dữ liệu
REM  Thêm file này vào Windows Task Scheduler để chạy tự động
REM =====================================================

REM Đường dẫn đến thư mục dự án (sửa nếu khác)
cd /d "%~dp0"

REM Chạy script
python run_local.py --pages 3

REM Giữ cửa sổ nếu chạy thủ công (xóa dòng này nếu dùng Task Scheduler)
REM pause
