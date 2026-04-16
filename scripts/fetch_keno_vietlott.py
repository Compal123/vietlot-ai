#!/usr/bin/env python3
"""
VietLot AI — Keno Scraper từ vietlott.vn (endpoint mới)
=========================================================
Sử dụng API: GameKenoCompareWebPart (khác với AjaxPro cũ đã hỏng)
Hỗ trợ: lấy theo ngày, phân trang đầy đủ (~19 trang/ngày)
Chạy được từ máy tính cá nhân, VPS VN.
GitHub Actions có thể bị block IP (dùng fetch_keno_live.py thay thế).

Cách dùng:
  python scripts/fetch_keno_vietlott.py                   → từ ngày thiếu đến hôm nay
  python scripts/fetch_keno_vietlott.py --from 2026-04-01 → từ ngày cụ thể
  python scripts/fetch_keno_vietlott.py --days 7          → 7 ngày gần nhất
"""
import json, sys, re, time, pathlib, argparse
from datetime import date, timedelta, timezone, timedelta as td, datetime

import requests
from bs4 import BeautifulSoup

# ─── Encoding fix ─────────────────────────────────────────────────────────────
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ─── Paths ────────────────────────────────────────────────────────────────────
ROOT = pathlib.Path(__file__).parent.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)

URL = ("https://vietlott.vn/ajaxpro/"
       "Vietlott.PlugIn.WebParts.GameKenoCompareWebPart,"
       "Vietlott.PlugIn.WebParts.ashx")

RENDER = {
    "SiteId": "main.frontend.vi", "SiteAlias": "main.vi",
    "UserSessionId": "", "SiteLang": "vi",
    "IsPageDesign": False, "ExtraParam1": "", "ExtraParam2": "", "ExtraParam3": "",
    "SiteURL": "", "WebPage": None, "SiteName": "Vietlott",
    "OrgPageAlias": None, "PageAlias": None, "RefKey": None, "FullPageAlias": None,
}

# ─── HTTP session ──────────────────────────────────────────────────────────────
sess = requests.Session()
sess.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Content-Type": "text/plain; charset=utf-8",
    "X-AjaxPro-Method": "ServerSideDrawResult",
    "Referer": "https://vietlott.vn/vi/trung-thuong/ket-qua-quay-so/keno",
    "Origin": "https://vietlott.vn",
})

def _init_session():
    """Warm-up request to get cookies."""
    try:
        sess.get("https://vietlott.vn/vi/trung-thuong/ket-qua-quay-so/keno", timeout=15)
    except Exception:
        pass

# ─── JSONL helpers ────────────────────────────────────────────────────────────
def load_db(fname):
    p = DATA / fname
    db = {}
    if p.exists():
        for line in p.read_text("utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    row = json.loads(line)
                    db[row["id"]] = row
                except Exception:
                    pass
    return db

def save_db(fname, db):
    rows = sorted(db.values(), key=lambda x: (x["date"], x.get("time", "")), reverse=True)
    (DATA / fname).write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    return len(rows)

# ─── Parse one API page ────────────────────────────────────────────────────────
def _parse_html(html: str) -> list[dict]:
    """
    Parse HTML from GameKenoCompareWebPart response.
    Table row format:
      td[0]: "DD/MM/YYYY#DRAWID"
      td[1]: numbers concatenated as 2-digit strings "0206071316..."
      td[2]: Chẵn/Lẻ
      td[3]: Lớn/Nhỏ
    """
    soup = BeautifulSoup(html, "lxml")
    results = []
    for row in soup.select("table tr"):
        tds = row.find_all("td")
        if not tds:
            continue
        cell0 = tds[0].get_text(strip=True)
        # Format: "01/04/2026#0275979"
        m = re.match(r"(\d{2}/\d{2}/\d{4})(#\d+)", cell0)
        if not m:
            continue
        date_raw, draw_id = m.group(1), m.group(2)
        d, mo, y = date_raw.split("/")
        draw_date = f"{y}-{mo}-{d}"

        # Numbers: concatenated 2-digit string
        num_str = tds[1].get_text(strip=True) if len(tds) > 1 else ""
        nums = [int(num_str[i:i+2]) for i in range(0, len(num_str), 2)
                if num_str[i:i+2].isdigit()]
        if len(nums) != 20:
            continue

        results.append({
            "id": draw_id.lstrip("#").zfill(7),
            "date": draw_date,
            "result": nums,
        })
    return results

# ─── Fetch one day (all pages) ────────────────────────────────────────────────
def fetch_day(day: date, db: dict) -> int:
    date_str = f"{day.day:02d}/{day.month:02d}/{day.year}"
    new = 0

    for pg in range(1, 25):  # max 25 pages/day (safe upper bound)
        body = json.dumps({
            "DrawDate": date_str, "GameDrawNo": "",
            "GameId": "6", "ORenderInfo": RENDER,
            "OddEven": 2, "PageIndex": pg, "ProcessType": 0,
            "TotalRow": 999999, "UpperLower": 2, "number": "",
        })
        try:
            r = sess.post(URL, data=body.encode("utf-8"), timeout=25)
        except Exception as e:
            print(f"      Page {pg}: lỗi {e}")
            break

        if not r.ok:
            print(f"      Page {pg}: HTTP {r.status_code}")
            break

        try:
            payload = r.json()
            html = payload.get("value", {}).get("HtmlContent", "")
        except Exception:
            break

        if not html or "Không có dữ liệu" in html:
            break

        draws = _parse_html(html)
        if not draws:
            break

        # Check if all draws on this page are already in db
        already_seen = sum(1 for d in draws if d["id"] in db)
        for d in draws:
            if d["id"] not in db:
                db[d["id"]] = d
                new += 1

        if already_seen == len(draws):
            # All draws already in db → stop paging for this date
            break

        time.sleep(0.3)  # polite delay

    return new

# ─── Date range helpers ────────────────────────────────────────────────────────
def missing_dates_in_db(db: dict) -> list[date]:
    """Return dates that have 0 entries in db, from earliest gap to today."""
    VN = timezone(td(hours=7))
    today = datetime.now(VN).date()

    # Find range: last 180 days (practical limit)
    start = today - timedelta(days=180)
    dates_in_db = set()
    for row in db.values():
        try:
            dates_in_db.add(date.fromisoformat(row["date"]))
        except Exception:
            pass

    missing = []
    d = start
    while d <= today:
        if d not in dates_in_db:
            missing.append(d)
        d += timedelta(days=1)
    return missing

# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Keno backfill từ vietlott.vn")
    ap.add_argument("--from", dest="from_date", help="Ngày bắt đầu (YYYY-MM-DD)")
    ap.add_argument("--days", type=int, help="Số ngày gần nhất")
    args = ap.parse_args()

    VN = timezone(td(hours=7))
    today = datetime.now(VN).date()

    # Determine date range
    if args.from_date:
        start = date.fromisoformat(args.from_date)
        end = today
    elif args.days:
        start = today - timedelta(days=args.days - 1)
        end = today
    else:
        # Auto: find all missing dates in last 30 days
        start = today - timedelta(days=30)
        end = today

    print("=" * 55)
    print(f"🎰  Keno Backfill — vietlott.vn")
    print(f"⏰  {datetime.now(VN).strftime('%Y-%m-%d %H:%M:%S')} (VN)")
    print(f"📅  Từ {start} đến {end}")
    print("=" * 55)

    _init_session()

    db = load_db("keno.jsonl")
    print(f"  📂 Hiện có: {len(db):,} kỳ")

    grand_new = 0
    d = start
    while d <= end:
        # Count existing for this date
        existing = sum(1 for row in db.values() if row.get("date") == str(d))
        # Skip if already has good data (>80 draws = full day)
        if existing >= 80:
            print(f"  ⏭  {d}: {existing} kỳ (đủ, skip)")
            d += timedelta(days=1)
            continue

        print(f"  🔄  {d}: {existing} kỳ sẵn có...", end=" ", flush=True)
        new = fetch_day(d, db)
        grand_new += new
        total_now = sum(1 for row in db.values() if row.get("date") == str(d))
        print(f"+{new} kỳ mới → {total_now} tổng")

        if new > 0:
            save_db("keno.jsonl", db)
            print(f"      💾 Đã lưu")

        d += timedelta(days=1)
        time.sleep(0.5)

    total = save_db("keno.jsonl", db)
    print(f"\n{'=' * 55}")
    print(f"✅  Xong! +{grand_new:,} kỳ mới | keno.jsonl: {total:,} tổng")
    print(f"{'=' * 55}")


if __name__ == "__main__":
    main()
