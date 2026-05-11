#!/usr/bin/env python3
"""
VietLot AI — Chạy cục bộ: Scrape + Push lên GitHub
====================================================
Chạy script này trên máy của bạn để:
  1. Lấy kết quả mới nhất từ ketquadientoan.com
  2. Push data lên GitHub tự động (cần đã cấu hình git)

Cách dùng:
  python run_local.py                    → tất cả game
  python run_local.py power535           → chỉ lotto 5/35
  python run_local.py --days 14          → tất cả game, 14 ngày gần nhất
  python run_local.py power655 --days 30 → power655, 30 ngày
"""
import sys, pathlib, subprocess, time, json
from datetime import datetime

ROOT = pathlib.Path(__file__).parent

# ─── Cấu hình ────────────────────────────────────────────────────────────────
DEFAULT_GAMES = []   # [] = tất cả game
DEFAULT_DAYS  = 7    # số ngày lấy về mặc định

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

    # Parse --days N
    days = DEFAULT_DAYS
    games_args = []
    i = 0
    while i < len(args):
        if args[i] == "--days" and i + 1 < len(args):
            try:
                days = int(args[i + 1])
            except ValueError:
                pass
            i += 2
        else:
            games_args.append(args[i])
            i += 1

    games = games_args if games_args else DEFAULT_GAMES

    banner(f"🎰 VietLot AI — Local Runner  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  📄 Days   : {days}")
    print(f"  🎯 Games  : {'tất cả' if not games else ' '.join(games)}")
    print(f"  📁 Data   : {ROOT / 'data'}")

    # ── 1. Thống kê trước khi chạy ──
    before = count_data()

    # ── 2. Chạy scraper ──
    banner("⏳ Bước 1/3 — Scrape kết quả từ ketquadientoan.com")
    fetch_cmd = [sys.executable, str(ROOT / "scripts" / "fetch_ketqua.py")]
    if games:
        fetch_cmd += games
    fetch_cmd += ["--days", str(days)]

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
    total_updated = 0
    print("\n  📊 Kết quả:")
    for fname in sorted(set(list(before.keys()) + list(after.keys()))):
        b = before.get(fname, {}).get("count", 0)
        a = after.get(fname, {}).get("count", 0)
        lat = after.get(fname, {}).get("latest", "?")
        new = a - b
        total_new += max(new, 0)
        mark = f"  +{new} mới" if new > 0 else "  (không đổi)"
        print(f"    {fname:<20} {a:>5} bản ghi | mới nhất: {lat}{mark}")

    # ── 4. Fetch Jackpot ──
    banner("💰 Bước 2/3 — Fetch Jackpot tích lũy")
    jp_cmd = [sys.executable, str(ROOT / "scripts" / "fetch_jackpots.py")]
    run(jp_cmd)

    # ── 5. Push lên GitHub ──
    banner("☁️  Bước 3/3 — Push lên GitHub")
    run(["git", "add", "data/"])
    diff = subprocess.run(["git", "diff", "--staged", "--quiet"])
    if diff.returncode == 0:
        print("\n  ℹ️  Không có thay đổi — bỏ qua push.")
        banner("✅ Xong (không có dữ liệu mới)")
        return

    # Commit
    msg = f"data: cập nhật local {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    run(["git", "commit", "-m", msg])

    # Pull rebase rồi push
    for attempt in range(1, 4):
        pull = subprocess.run(["git", "pull", "--rebase", "origin", "main"])
        push = subprocess.run(["git", "push", "origin", "main"])
        if push.returncode == 0:
            break
        print(f"  ⚠️  Push thất bại lần {attempt}, thử lại...")
        time.sleep(5)

    banner(f"✅ Hoàn thành! Đã push lên GitHub")

if __name__ == "__main__":
    main()
