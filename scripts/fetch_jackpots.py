#!/usr/bin/env python3
"""
VietLot AI — Fetch Jackpot tích lũy từ ketquadientoan.com
=========================================================
Lấy giá trị jackpot hiện tại của:
  - Power 6/55  → jackpot1, jackpot2
  - Mega 6/45   → jackpot
  - Lotto 5/35  → jackpot (Độc Đắc)

Lưu vào data/jackpots.json:
{
  "updated": "2026-04-17T10:30:00+07:00",
  "power655": {"jackpot1": 91889389200, "jackpot2": 3454813850},
  "power645": {"jackpot": 14929490000},
  "power535": {"jackpot": 22370500000}
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

BASE = "https://www.ketquadientoan.com"
VN_TZ = timezone(timedelta(hours=7))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9",
}
sess = requests.Session()
sess.headers.update(HEADERS)

# ─── Game config ──────────────────────────────────────────────────────────────
GAMES = {
    "power655": {"slug": "power-655",  "keys": ["jackpot1", "jackpot2"]},
    "power645": {"slug": "mega-6-45",  "keys": ["jackpot"]},
    "power535": {"slug": "lotto-535",  "keys": ["jackpot"]},
}

# ─── Parser ───────────────────────────────────────────────────────────────────
def _parse_vnd(text):
    """'91.889.389.200 đồng' → 91889389200"""
    text = text.replace("đồng", "").replace(",", "").replace(".", "").strip()
    m = re.search(r"\d+", text)
    return int(m.group()) if m else 0

def fetch_jackpot(game_id, slug):
    """Fetch trang hôm nay (hoặc hôm qua nếu 404), trả về dict jackpot."""
    now = datetime.now(VN_TZ)
    for delta in [0, -1, -2, -3]:  # thử hôm nay → 3 ngày trước
        d = now.date() if delta == 0 else (now + timedelta(days=delta)).date()
        url = f"{BASE}/ket-qua-xo-so-dien-toan-{slug}/{d.strftime('%d-%m-%Y')}.html"
        try:
            r = sess.get(url, timeout=20)
            if r.status_code == 404:
                continue
            if not r.ok:
                print(f"  HTTP {r.status_code}: {url}")
                continue
            r.encoding = "utf-8"
            soup = BeautifulSoup(r.text, "lxml")
            result = _extract_jackpots(soup, game_id)
            if result:
                print(f"  ✅ {game_id}: {result} (từ {d})")
                return result
        except Exception as e:
            print(f"  Lỗi {url}: {e}")
    return {}

def _extract_jackpots(soup, game_id):
    """Parse jackpot từ bảng 'Giá trị giải' trên trang."""
    result = {}

    # Cách 1: tìm text "Jackpot 1", "Jackpot 2" trong table rows
    # Cấu trúc: <td>Jackpot 1</td><td>...</td><td>...</td><td>91.889.389.200 đồng</td>
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
            # Mega / Lotto: tìm dòng "Jackpot" hoặc "Độc đắc"
            if "jackpot" in first or "độc đắc" in first or "doc dac" in first:
                val = _find_money_in_tds(tds)
                if val: result["jackpot"] = val

    # Cách 2: nếu chưa tìm được, dùng regex trên toàn bộ text
    if not result:
        text = soup.get_text(" ", strip=True)
        result = _regex_extract(text, game_id)

    return result

def _find_money_in_tds(tds):
    """Tìm giá trị tiền trong các <td>, ưu tiên td cuối cùng."""
    for td in reversed(tds):
        t = td.get_text(strip=True)
        if re.search(r"\d[\d.,]{4,}", t):  # ít nhất 5 chữ số
            return _parse_vnd(t)
    return 0

def _regex_extract(text, game_id):
    """Fallback: dùng regex tìm pattern 'Jackpot X: 91.889.389.200'."""
    result = {}
    patterns = {
        "jackpot1": [
            r"[Jj]ackpot\s*1[:\s]+([0-9][0-9.,]+)\s*đ",
            r"[Jj]ackpot\s+1[:\s]+([0-9][0-9.,]+)",
        ],
        "jackpot2": [
            r"[Jj]ackpot\s*2[:\s]+([0-9][0-9.,]+)\s*đ",
            r"[Jj]ackpot\s+2[:\s]+([0-9][0-9.,]+)",
        ],
        "jackpot": [
            r"[Jj]ackpot[:\s]+([0-9][0-9.,]+)\s*đ",
            r"[Đđ]ộc\s*[Đđ]ắc[:\s]+([0-9][0-9.,]+)\s*đ",
            r"[Jj]ackpot[:\s]+([0-9][0-9.,]+)",
        ],
    }

    if game_id == "power655":
        keys = ["jackpot1", "jackpot2"]
    else:
        keys = ["jackpot"]

    for key in keys:
        for pat in patterns.get(key, []):
            m = re.search(pat, text)
            if m:
                result[key] = _parse_vnd(m.group(1))
                break

    return result

# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    print("🎰 Đang lấy jackpot tích lũy...")
    now_str = datetime.now(VN_TZ).isoformat(timespec="seconds")

    data = {"updated": now_str}

    for game_id, cfg in GAMES.items():
        print(f"\n📊 {game_id}...")
        jp = fetch_jackpot(game_id, cfg["slug"])
        data[game_id] = jp

    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ Đã lưu → {OUT}")
    print(json.dumps(data, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
