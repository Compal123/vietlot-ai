#!/usr/bin/env python3
"""
VietLot AI — Keno Live Scraper từ ketquadientoan.com
=====================================================
Scrape trang trực tiếp Keno, lấy ~6 kỳ gần nhất.
Chạy thường xuyên (mỗi 30 phút) để không bỏ sót kỳ nào.
Keno quay mỗi ~8 phút → 30 phút đủ bắt hết.

Bingo18: không có trên ketquadientoan.com,
         dùng vietlott.vn nếu máy VN hoặc bỏ qua.

Cách dùng:
  python scripts/fetch_keno_live.py           → lấy Keno
  python scripts/fetch_keno_live.py keno      → chỉ Keno
"""
import json, sys, re, time, pathlib
from datetime import datetime, timezone, timedelta

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

BASE = "https://www.ketquadientoan.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9",
    "Referer": f"{BASE}/truc-tiep-xo-so-dien-toan-keno.html",
}

sess = requests.Session()
sess.headers.update(HEADERS)

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

# ─── Parse Keno draws from fullviewtructiep HTML ──────────────────────────────
def parse_keno_html(html):
    """
    Parses Keno draw table from ketquadientoan.com fullviewtructiep endpoint.
    Each draw spans 2 rows:
      Row 1: <td>#DRAWID</td> <td>DD/MM/YY|HH:MM</td> <td>num1</td>...<td>num10</td>
      Row 2: <td>num11</td>...<td>num20</td>
    Returns list of dicts: {id, date, time, result}
    """
    soup = BeautifulSoup(html, "lxml")
    draws = []
    current = None

    for row in soup.select("tr"):
        tds = row.find_all("td")
        if not tds:
            continue

        first = tds[0].get_text(strip=True)
        if re.match(r"#\d{5,6}", first):
            draw_id = first.lstrip("#").zfill(6)
            # Date/time in second td: "DD/MM/YY" and "HH:MM" in separate divs
            dt_td = tds[1] if len(tds) > 1 else None
            if dt_td:
                dt_text = dt_td.get_text(separator="|", strip=True)
            else:
                dt_text = ""

            # Parse date: DD/MM/YY or DD/MM/YYYY
            date_str = ""
            time_str = ""
            date_m = re.search(r"(\d{2})/(\d{2})/(\d{2,4})", dt_text)
            time_m = re.search(r"(\d{2}:\d{2})", dt_text)
            if date_m:
                d, m, y = date_m.groups()
                if len(y) == 2:
                    y = "20" + y
                date_str = f"{y}-{m}-{d}"
            if time_m:
                time_str = time_m.group(1)

            nums = [int(td.get_text(strip=True)) for td in tds[2:]
                    if td.get_text(strip=True).isdigit()]

            current = {
                "id": draw_id,
                "date": date_str,
                "time": time_str,
                "result": nums,
            }
            draws.append(current)

        elif current is not None:
            # Continuation row — more numbers
            more = [int(td.get_text(strip=True)) for td in tds
                    if td.get_text(strip=True).isdigit()]
            current["result"].extend(more)

    # Keep only draws with exactly 20 numbers
    return [d for d in draws if len(d["result"]) == 20]


# ─── Fetch Keno live ──────────────────────────────────────────────────────────
def fetch_keno():
    url = f"{BASE}/ajax/fullviewtructiep.php?loaixs=keno"
    try:
        r = sess.get(url, timeout=25)
        if not r.ok:
            print(f"    HTTP {r.status_code}: {url}")
            return 0
        r.encoding = "utf-8"
        draws = parse_keno_html(r.text)
    except Exception as e:
        print(f"    Lỗi: {e}")
        return 0

    if not draws:
        print("    Không có kỳ nào trong response.")
        return 0

    db = load_db("keno.jsonl")
    new = 0
    for d in draws:
        if d["id"] not in db:
            db[d["id"]] = d
            new += 1
            print(f"    +1 kỳ #{d['id']} | {d['date']} {d['time']}")

    total = save_db("keno.jsonl", db)
    print(f"    ✅ keno.jsonl: {total} tổng, +{new} mới (lần này: {len(draws)} kỳ)")
    return new


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    VN = timezone(timedelta(hours=7))
    now = datetime.now(VN)

    print("=" * 55)
    print(f"🎰  VietLot AI — Keno Live Scraper")
    print(f"⏰  {now.strftime('%Y-%m-%d %H:%M:%S')} (VN)")
    print(f"🌐  Source: ketquadientoan.com/ajax/fullviewtructiep.php")
    print("=" * 55)

    grand = 0
    print("\n  ▶ Keno")
    grand += fetch_keno()

    print(f"\n{'=' * 55}")
    print(f"🏆  Hoàn thành! Tổng mới: {grand} kỳ")
    print(f"{'=' * 55}")


if __name__ == "__main__":
    main()
