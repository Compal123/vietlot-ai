#!/usr/bin/env python3
"""
VietLot AI — Scraper từ ketquadientoan.com
==========================================
Nguồn backup khi vietlott.vn bị chặn IP (GitHub Actions).
GET theo từng ngày, không cần proxy, không bị block.

Hỗ trợ: power655, power645, power535, max3d, max3dpro
(Keno/Bingo18 quay quá nhiều lần/ngày nên dùng vietlott.vn)

Cách dùng:
  python scripts/fetch_ketqua.py                    → từ ngày cuối đến hôm nay
  python scripts/fetch_ketqua.py --days 14          → 14 ngày gần nhất
  python scripts/fetch_ketqua.py --from 2026-04-01  → từ ngày cụ thể
  python scripts/fetch_ketqua.py power655 max3d     → chỉ game đó
"""
import json, sys, re, time, pathlib
from datetime import date, timedelta, datetime

import requests
from bs4 import BeautifulSoup

# ─── Encoding fix (Windows terminal) ─────────────────────────────────────────
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
}

sess = requests.Session()
sess.headers.update(HEADERS)

# ─── Game config ──────────────────────────────────────────────────────────────
# draw_days: set ngày có quay (0=Mon…6=Sun), None = mỗi ngày
GAMES = {
    "power655": {
        "slug": "power-655",
        "file": "power655.jsonl",
        "draw_days": {1, 3, 5},    # Thứ 3, 5, 7
        "type": "power",
    },
    "power645": {
        "slug": "mega-6-45",
        "file": "power645.jsonl",
        "draw_days": {2, 4, 6},    # Thứ 4, 6, CN
        "type": "power",
    },
    "power535": {
        "slug": "lotto-535",
        "file": "power535.jsonl",
        "draw_days": None,         # Mỗi ngày (2 kỳ/ngày)
        "type": "power",
    },
    "max3d": {
        "slug": "max-3d",
        "file": "3d.jsonl",
        "draw_days": {0, 2, 4},    # Thứ 2, 4, 6
        "type": "3d",
    },
    "max3dpro": {
        "slug": "max3d-pro",
        "file": "3d_pro.jsonl",
        "draw_days": {1, 3, 5},    # Thứ 3, 5, 7
        "type": "3d",
    },
}

# ─── JSONL helpers ────────────────────────────────────────────────────────────
def load(fname):
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

def save(fname, db):
    # Sort: date DESC, id DESC (kỳ lớn hơn = kỳ sau = đứng trên trong cùng ngày)
    rows = sorted(db.values(), key=lambda x: (x["date"], x["id"]), reverse=True)
    (DATA / fname).write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    return len(rows)

def get_last_date(fname):
    """Ngày mới nhất trong file, hoặc 30 ngày trước nếu trống."""
    p = DATA / fname
    if not p.exists():
        return date.today() - timedelta(days=30)
    for line in p.read_text("utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                d_str = json.loads(line).get("date", "")
                return datetime.strptime(d_str, "%Y-%m-%d").date()
            except Exception:
                pass
    return date.today() - timedelta(days=30)

# ─── HTTP fetch ───────────────────────────────────────────────────────────────
def fetch_page(slug, d):
    """GET trang kết quả cho game/ngày. Trả về soup hoặc None."""
    url = f"{BASE}/ket-qua-xo-so-dien-toan-{slug}/{d.strftime('%d-%m-%Y')}.html"
    try:
        r = sess.get(url, timeout=20)
        if r.status_code == 404:
            return None
        if not r.ok:
            print(f"    HTTP {r.status_code}: {url}")
            return None
        r.encoding = "utf-8"
        return BeautifulSoup(r.text, "lxml")
    except Exception as e:
        print(f"    Lỗi: {e}")
        return None

# ─── Helpers parse ────────────────────────────────────────────────────────────
def _extract_id(text):
    """Trích ID từ 'Kỳ vé #01331 | ...' → '01331'."""
    m = re.search(r"#(\d{4,6})", text)
    return m.group(1).zfill(5) if m else None

def _extract_date(text):
    """Trích ngày từ '...ngày 11/04/2026' → '2026-04-11'."""
    m = re.search(r"(\d{2}/\d{2}/\d{4})", text)
    if m:
        d, mo, y = m.group(1).split("/")
        return f"{y}-{mo}-{d}"
    return None

# ─── Parser: Power / Mega / Lotto ─────────────────────────────────────────────
# HTML structure:
#   <div class="box_kqxsdt box_kqxs_power">
#     <div class="title_tt">Kỳ vé #01331 | Thứ bảy, ngày 11/04/2026</div>
#     <div class="box_ketqua">
#       <span class="ball ball_power">13</span> × 6
#       <span class="ball ball_power2">07</span>   ← power ball
#     </div>
#   </div>
def _parse_winner_tables(soup):
    """Trả về dict: draw_id → {prize_name: winner_count}"""
    wmap = {}
    for t in soup.find_all("table"):
        if "SL" not in t.get_text():
            continue
        prev_box = t.find_previous("div", class_="box_kqxsdt")
        if not prev_box:
            continue
        title_el = prev_box.select_one("div.title_tt")
        if not title_el or "Kỳ vé" not in title_el.get_text():
            continue
        draw_id = _extract_id(title_el.get_text())
        if not draw_id:
            continue
        winners = {}
        for tr in t.find_all("tr")[1:]:        # bỏ header
            tds = tr.find_all("td")
            if len(tds) < 3:
                continue
            prize = tds[0].get_text(strip=True)
            cnt_s = tds[2].get_text(strip=True).replace(".", "").replace(",", "")
            if not prize or not cnt_s.lstrip("-").isdigit():
                continue
            winners[prize] = int(cnt_s)
        if winners:
            wmap[draw_id] = winners
    return wmap

def parse_power(soup):
    winner_map = _parse_winner_tables(soup)
    results = []
    for box in soup.select("div.box_kqxsdt"):
        title = box.select_one("div.title_tt")
        if not title or "Kỳ vé" not in title.get_text():
            continue
        text     = title.get_text(" ", strip=True)
        draw_id  = _extract_id(text)
        draw_date = _extract_date(text)
        if not draw_id or not draw_date:
            continue

        nums = [int(sp.get_text(strip=True))
                for sp in box.select("span.ball")
                if sp.get_text(strip=True).isdigit()]
        if not nums:
            continue

        row = {"date": draw_date, "id": draw_id, "result": nums}
        if draw_id in winner_map:
            row["winners"] = winner_map[draw_id]
        results.append(row)
    return results

# ─── Parser: Max3D / Max3D Pro ────────────────────────────────────────────────
# HTML structure:
#   <div class="kyve">Kỳ vé #01066 | Thứ hai, Ngày 13/04/2026</div>
#   ...
#   <table class="tblMax3d">
#     <tr>
#       <td><strong>Đặc biệt<br/><span>1Tr</span>: <span>23</span></strong></td>
#       <td class="max3d_number max3d_g1">
#         <div><span>9</span><span>7</span><span>7</span></div>
#         <div><span>9</span><span>1</span><span>5</span></div>
#       </td>
#     </tr>
#   </table>
PRIZE_MAP = {
    "đặc biệt": "Giải Đặc biệt",
    "nhất":     "Giải Nhất",
    "nhì":      "Giải Nhì",
    "ba":       "Giải Ba",
}

def _normalize_prize(text):
    t = text.lower()
    for k, v in PRIZE_MAP.items():
        if k in t:
            return v
    return None

def parse_3d(soup):
    results = []

    # Tìm tất cả div.kyve (mỗi ngày có thể có 1 kết quả, nhưng page thường 1 kỳ)
    for kyve_div in soup.select("div.kyve"):
        text     = kyve_div.get_text(" ", strip=True)
        draw_id  = _extract_id(text)
        draw_date = _extract_date(text)
        if not draw_id or not draw_date:
            continue

        # Tìm bảng kết quả tiếp theo
        table = kyve_div.find_next("table", class_=re.compile(r"tblMax3d|max3d", re.I))
        if not table:
            continue

        result = {}
        for tr in table.select("tbody tr"):
            tds = tr.find_all("td")
            if len(tds) < 2:
                continue

            # Tên giải (cột 1 — cột Max3D, không phải Max3D+)
            prize_text = tds[0].get_text(" ", strip=True)
            prize_name = _normalize_prize(prize_text)
            if not prize_name:
                continue

            # Số 3 chữ số từ cột giữa (index 1)
            num_td = tds[1]
            nums_3d = []
            for div in num_td.find_all("div"):
                digits = [sp.get_text(strip=True) for sp in div.find_all("span")
                          if sp.get_text(strip=True).isdigit()]
                if len(digits) == 3:
                    nums_3d.append("".join(digits))

            if nums_3d:
                result[prize_name] = nums_3d

        if result:
            results.append({"date": draw_date, "id": draw_id, "result": result})
    return results

PARSERS = {
    "power": parse_power,
    "3d":    parse_3d,
}

# ─── Scrape một game theo date range ─────────────────────────────────────────
def scrape_game(game_key, from_date=None, days_back=None):
    cfg    = GAMES[game_key]
    fname  = cfg["file"]
    slug   = cfg["slug"]
    gtype  = cfg["type"]
    parser = PARSERS[gtype]
    dd     = cfg["draw_days"]

    db    = load(fname)
    # Luôn re-check từ ngày cuối (không +1) để bắt kỳ 2 cùng ngày bị bỏ sót
    start = from_date or get_last_date(fname)
    end   = date.today()

    if days_back:
        start = end - timedelta(days=days_back - 1)

    if start > end:
        print(f"    Đã cập nhật đến hôm nay.")
        return 0

    new = 0
    d   = start
    while d <= end:
        if dd is not None and d.weekday() not in dd:
            d += timedelta(days=1)
            continue

        soup  = fetch_page(slug, d)
        time.sleep(0.7)

        if soup is None:
            d += timedelta(days=1)
            continue

        draws = parser(soup)
        added = 0
        updated = 0
        for row in draws:
            if row["id"] not in db:
                db[row["id"]] = row
                new   += 1
                added += 1
            elif "winners" in row and "winners" not in db[row["id"]]:
                # Bổ sung dữ liệu người trúng vào kỳ đã có
                db[row["id"]]["winners"] = row["winners"]
                updated += 1

        if added or updated:
            note = f"+{added} mới" + (f", +{updated} cập nhật winners" if updated else "")
            print(f"    {d.strftime('%Y-%m-%d')} {note}")

        d += timedelta(days=1)

    total = save(fname, db)
    print(f"    ✅ {fname}: {total} tổng, +{new} mới")
    return new

# ─── CLI ──────────────────────────────────────────────────────────────────────
def main():
    args = sys.argv[1:]

    from_date = None
    days_back = None
    game_keys = []

    i = 0
    while i < len(args):
        if args[i] == "--from" and i + 1 < len(args):
            try:
                from_date = datetime.strptime(args[i+1], "%Y-%m-%d").date()
            except ValueError:
                print(f"❌ Ngày sai định dạng: {args[i+1]} (dùng YYYY-MM-DD)")
                sys.exit(1)
            i += 2
        elif args[i] == "--days" and i + 1 < len(args):
            try:
                days_back = int(args[i+1])
            except ValueError:
                pass
            i += 2
        else:
            game_keys.append(args[i])
            i += 1

    targets = game_keys if game_keys else list(GAMES.keys())
    invalid = [g for g in targets if g not in GAMES]
    if invalid:
        print(f"❌ Game không hợp lệ: {invalid}")
        print(f"   Hợp lệ: {list(GAMES.keys())}")
        sys.exit(1)

    print("=" * 55)
    print(f"🌐  VietLot AI — Fetch từ ketquadientoan.com")
    print(f"⏰  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🎯  Games: {', '.join(targets)}")
    if from_date:
        print(f"📅  Từ ngày: {from_date} → hôm nay")
    elif days_back:
        print(f"📅  {days_back} ngày gần nhất")
    else:
        print(f"📅  Tự động từ ngày cuối trong file")
    print("=" * 55)

    grand_total = 0
    for g in targets:
        print(f"\n  ▶ {GAMES[g]['file']}")
        grand_total += scrape_game(g, from_date=from_date, days_back=days_back)

    print(f"\n{'=' * 55}")
    print(f"🏆  Hoàn thành! Tổng mới: {grand_total} entries")
    print(f"{'=' * 55}")

if __name__ == "__main__":
    main()
