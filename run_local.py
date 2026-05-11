#!/usr/bin/env python3
"""
VietLot AI — Chạy cục bộ: Scrape + Upload lên GitHub
=====================================================
Chạy script này trên máy của bạn (IP Việt Nam) để:
  1. Lấy kết quả mới nhất từ vietlott.vn
  2. Upload data lên GitHub tự động

Cách dùng:
  python run_local.py                    → tất cả game
  python run_local.py keno               → chỉ keno
  python run_local.py --pages 20         → tất cả game, nhiều trang hơn
"""
import sys, pathlib, subprocess, time, json
from datetime import datetime

ROOT = pathlib.Path(__file__).parent

# ─── Cấu hình ────────────────────────────────────────────────────────────────
# Game nào chạy mặc định nếu không truyền args
DEFAULT_GAMES = []   # [] = tất cả game

# Số trang mặc định (mỗi trang ~5 kỳ):
#   2 trang  ≈ 2 tuần gần nhất  (nhanh, dùng cho cron ngắn)
#  10 trang  ≈ 2 tháng          (dùng khi thiếu nhiều)
DEFAULT_PAGES = 3

# ─── Helpers ─────────────────────────────────────────────────────────────────
def banner(text):
    print(f"\n{'='*55}")
    print(f"  {text}")
    print(f"{'='*55}")

def run(cmd, **kw):
    print(f"  $ {' '.join(str(c) for c in cmd)}")
    return subprocess.run(cmd, **kw)

def count_data():
    """Thống kê số bản ghi mỗi file."""
    data_dir = ROOT / "data"
    if not data_dir.exists():
        return {}
    result = {}
    for f in sorted(data_dir.glob("*.jsonl")):
        lines = [l for l in f.read_text("utf-8").splitlines() if l.strip()]
        latest = ""
        if lines:
            try:
                latest = json.loads(lines[0]).get("date", "")
            except Exception:
                pass
        result[f.name] = {"count": len(lines), "latest": latest}
    return result

# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    args = sys.argv[1:]

    # Parse --pages N
    pages = DEFAULT_PAGES
    games_args = []
    i = 0
    while i < len(args):
        if args[i] == "--pages" and i + 1 < len(args):
            try:
                pages = int(args[i + 1])
            except ValueError:
                pass
            i += 2
        else:
            games_args.append(args[i])
            i += 1

    games = games_args if games_args else DEFAULT_GAMES

    banner(f"🎰 VietLot AI — Local Runner  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  📄 Pages  : {pages}")
    print(f"  🎯 Games  : {'tất cả' if not games else ' '.join(games)}")
    print(f"  📁 Data   : {ROOT / 'data'}")

    # ── 1. Thống kê trước khi chạy ──
    before = count_data()

    # ── 2. Chạy scraper ──
    banner("⏳ Bước 1/2 — Scrape từ vietlott.vn")
    fetch_cmd = [sys.executable, str(ROOT / "scripts" / "fetch_data.py")]
    if games:
        fetch_cmd += games
    fetch_cmd += ["--pages", str(pages)]

    t0 = time.time()
    result = run(fetch_cmd)
    elapsed = time.time() - t0

    if result.returncode != 0:
        print(f"\n❌ Scrape thất bại (exit {result.returncode})")
        sys.exit(1)

    print(f"\n  ⏱  Hoàn thành trong {elapsed:.1f}s")

    # ── 3. Thống kê sau khi chạy ──
    after = count_data()
    total_new = 0
    print("\n  📊 Kết quả:")
    for fname in sorted(set(list(before.keys()) + list(after.keys()))):
        b = before.get(fname, {}).get("count", 0)
        a = after.get(fname, {}).get("count", 0)
        lat = after.get(fname, {}).get("latest", "?")
        new = a - b
        total_new += new
        mark = f"  +{new} mới" if new > 0 else "  (không đổi)"
        print(f"    {fname:<20} {a:>5} bản ghi | mới nhất: {lat}{mark}")

    if total_new == 0:
        print("\n  ℹ️  Không có dữ liệu mới — bỏ qua upload.")
        banner("✅ Xong (không có dữ liệu mới)")
        return

    # ── 4. Upload lên GitHub ──
    banner(f"☁️  Bước 2/2 — Upload {total_new} bản ghi mới lên GitHub")
    upload_cmd = [sys.executable, str(ROOT / "upload_to_github.py"), "--data"]
    result = run(upload_cmd)
    if result.returncode != 0:
        print(f"\n❌ Upload thất bại (exit {result.returncode})")
        sys.exit(1)

    banner(f"✅ Hoàn thành! +{total_new} bản ghi mới đã lên GitHub")

if __name__ == "__main__":
    main()
