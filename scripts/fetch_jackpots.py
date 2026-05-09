#!/usr/bin/env python3
"""
VietLot AI — Fetch Jackpot tích lũy
=====================================
Nguồn 1 (chính): vietlott.vn — trang game chính thức, luôn hiển thị jackpot hiện tại
Nguồn 2 (backup): ketquadientoan.com — trang kết quả gần nhất

Lưu vào data/jackpots.json:
{
  "updated": "2026-05-09T20:26:38+07:00",
  "power655": {"jackpot1": 91889389200, "jackpot2": 3454813850},
  "power645": {"jackpot": 15047545500},
  "power535": {"jackpot": 7776732500}
}
"""
import json, re, pathlib, sys
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
OUT  = DATA / "jackpots.json"

VN_TZ = timezone(timedelta(hours=7))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
}
sess = requests.Session()
sess.headers.update(HEADERS)

# ─── Game config ──────────────────────────────────────────────────────────────
GAMES = {
    "power655": {
        "vietlott_url": "https://vietlott.vn/vi/trung-thuong/ket-qua-quay-so/power-6-55",
        "kqdt_slug":    "power-655",
        "kqdt_days":    {1, 3, 5},   # Tue Thu Sat (Python weekday Mon=0)
        "keys":         ["jackpot1", "jackpot2"],
    },
    "power645": {
        "vietlott_url": "https://vietlott.vn/vi/trung-thuong/ket-qua-quay-so/mega-6-45",
        "kqdt_slug":    "mega-6-45",
        "kqdt_days":    {2, 4, 6},   # Wed Fri Sun
        "keys":         ["jackpot"],
    },
    "power535": {
        "vietlott_url": "https://vietlott.vn/vi/trung-thuong/ket-qua-quay-so/lotto-5-35",
        "kqdt_slug":    "lotto-535",
        "kqdt_days":    None,        # daily
        "keys":         ["jackpot"],
    },
}

# ─── Money parser ─────────────────────────────────────────────────────────────
def _parse_vnd(text):
    """'91.889.389.200 đồng' or '91,889,389,200' → 91889389200"""
    text = re.sub(r"[đồng\s]", "", text)
    text = text.replace(",", "").replace(".", "")
    m = re.search(r"\d{6,}", text)   # ít nhất 6 chữ số (~100k đ trở lên)
    v = int(m.group()) if m else 0
    return v if v >= 1_000_000 else 0  # bỏ qua số quá nhỏ

# ─── SOURCE 1: vietlott.vn ────────────────────────────────────────────────────
def _fetch_vietlott(game_id, url):
    """Scrape jackpot từ trang chính thức vietlott.vn."""
    try:
        r = sess.get(url, timeout=25)
        if not r.ok:
            print(f"  vietlott.vn HTTP {r.status_code}")
            return {}
        r.encoding = "utf-8"
        soup = BeautifulSoup(r.text, "lxml")
        result = {}

        # Cách 1: tìm trong <table> — vietlott thường dùng table giải thưởng
        for tr in soup.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 2:
                continue
            label = tds[0].get_text(" ", strip=True).lower()
            money_td = tds[-1].get_text(" ", strip=True)
            val = _parse_vnd(money_td)
            if not val:
                continue
            if game_id == "power655":
                if re.search(r"jackpot\s*1", label): result["jackpot1"] = val
                elif re.search(r"jackpot\s*2", label): result["jackpot2"] = val
            else:
                if re.search(r"jackpot|độc\s*đắc", label): result["jackpot"] = val

        # Cách 2: regex trên toàn bộ text (fallback)
        if not result:
            text = soup.get_text(" ", strip=True)
            result = _regex_extract(text, game_id)

        if result:
            print(f"  ✅ [vietlott.vn] {game_id}: {result}")
        return result
    except Exception as e:
        print(f"  vietlott.vn lỗi: {e}")
        return {}

# ─── SOURCE 2: ketquadientoan.com (fallback) ──────────────────────────────────
def _kqdt_draw_dates(draw_days, today, n_past=7):
    """Trả về n_past kỳ quay gần nhất (ngược về quá khứ)."""
    result = []
    for delta in range(0, 30):
        d = today - timedelta(days=delta)
        if draw_days is None or d.weekday() in draw_days:
            result.append(d)
        if len(result) >= n_past:
            break
    return result

def _fetch_kqdt(game_id, slug, draw_days):
    """Fallback: scrape ketquadientoan.com theo ngày quay gần nhất."""
    today = datetime.now(VN_TZ).date()
    base  = "https://www.ketquadientoan.com"
    for d in _kqdt_draw_dates(draw_days, today):
        url = f"{base}/ket-qua-xo-so-dien-toan-{slug}/{d.strftime('%d-%m-%Y')}.html"
        try:
            r = sess.get(url, timeout=20)
            if r.status_code == 404:
                continue
            if not r.ok:
                continue
            r.encoding = "utf-8"
            soup = BeautifulSoup(r.text, "lxml")
            result = _extract_kqdt(soup, game_id)
            if result:
                print(f"  ✅ [ketquadientoan.com {d}] {game_id}: {result}")
                return result
        except Exception as e:
            print(f"  kqdt lỗi {d}: {e}")
    return {}

def _extract_kqdt(soup, game_id):
    result = {}
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if not tds:
            continue
        first = tds[0].get_text(strip=True).lower()
        if game_id == "power655":
            if "jackpot 1" in first or "jackpot1" in first:
                val = _find_money_in_tds(tds)
                if val: result["jackpot1"] = val
            elif "jackpot 2" in first or "jackpot2" in first:
                val = _find_money_in_tds(tds)
                if val: result["jackpot2"] = val
        else:
            if "jackpot" in first or "độc đắc" in first:
                val = _find_money_in_tds(tds)
                if val: result["jackpot"] = val
    if not result:
        result = _regex_extract(soup.get_text(" ", strip=True), game_id)
    return result

def _find_money_in_tds(tds):
    for td in reversed(tds):
        v = _parse_vnd(td.get_text(strip=True))
        if v: return v
    return 0

# ─── Regex fallback ───────────────────────────────────────────────────────────
def _regex_extract(text, game_id):
    result = {}
    pats = {
        "jackpot1": [r"[Jj]ackpot\s*1[^0-9]{0,10}([0-9][0-9.,]{5,})"],
        "jackpot2": [r"[Jj]ackpot\s*2[^0-9]{0,10}([0-9][0-9.,]{5,})"],
        "jackpot":  [
            r"[Jj]ackpot[^0-9]{0,10}([0-9][0-9.,]{5,})",
            r"[Đđ]ộc\s*[Đđ]ắc[^0-9]{0,10}([0-9][0-9.,]{5,})",
        ],
    }
    keys = ["jackpot1", "jackpot2"] if game_id == "power655" else ["jackpot"]
    for key in keys:
        for pat in pats.get(key, []):
            m = re.search(pat, text)
            if m:
                v = _parse_vnd(m.group(1))
                if v: result[key] = v; break
    return result

# ─── Main fetch ───────────────────────────────────────────────────────────────
def fetch_jackpot(game_id, cfg):
    # Thử vietlott.vn trước (luôn có jackpot hiện tại)
    result = _fetch_vietlott(game_id, cfg["vietlott_url"])
    if result:
        return result
    print(f"  ⚠️  vietlott.vn không có dữ liệu, thử ketquadientoan.com...")
    return _fetch_kqdt(game_id, cfg["kqdt_slug"], cfg["kqdt_days"])

# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    print("🎰 Đang lấy jackpot tích lũy (vietlott.vn → ketquadientoan.com)...")
    now_str = datetime.now(VN_TZ).isoformat(timespec="seconds")
    data = {"updated": now_str}

    for game_id, cfg in GAMES.items():
        print(f"\n📊 {game_id}...")
        data[game_id] = fetch_jackpot(game_id, cfg)

    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ Đã lưu → {OUT}")
    print(json.dumps(data, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
