#!/usr/bin/env python3
"""
VietLot AI — Fetch Jackpot tích lũy
=====================================
Nguồn 1 (chính): minhchinh.com — hiển thị jackpot kỳ tới (luôn mới nhất)
Nguồn 2 (backup): ketquadientoan.com — jackpot từ kỳ quay gần nhất

URLs đã xác nhận hoạt động:
  power655: https://www.minhchinh.com/xstd/power655.htm
  mega645:  https://www.minhchinh.com/xo-so-dien-toan-mega-645.html
  lotto535: https://www.minhchinh.com/xo-so-dien-toan-lotto-535.html

Lưu vào data/jackpots.json.
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
    "Accept-Language": "vi-VN,vi;q=0.9",
}
sess = requests.Session()
sess.headers.update(HEADERS)

# ─── Game config ──────────────────────────────────────────────────────────────
GAMES = {
    "power655": {
        # Nguồn chính: minhchinh.com
        "mc_url":    "https://www.minhchinh.com/xstd/power655.htm",
        "mc_type":   "power655",   # parser type
        # Backup: ketquadientoan.com
        "kqdt_slug": "power-655",
        "kqdt_days": {1, 3, 5},    # Tue Thu Sat
        "keys":      ["jackpot1", "jackpot2"],
    },
    "power645": {
        "mc_url":    "https://www.minhchinh.com/xo-so-dien-toan-mega-645.html",
        "mc_type":   "single",
        "kqdt_slug": "mega-6-45",
        "kqdt_days": {2, 4, 6},    # Wed Fri Sun
        "keys":      ["jackpot"],
    },
    "power535": {
        "mc_url":    "https://www.minhchinh.com/xo-so-dien-toan-lotto-535.html",
        "mc_type":   "lotto535",   # dùng "Độc Đắc" thay vì "Jackpot"
        "kqdt_slug": "lotto-535",
        "kqdt_days": None,         # daily
        "keys":      ["jackpot"],
    },
}

# ─── Money parser ─────────────────────────────────────────────────────────────
def _parse_vnd(text):
    text = re.sub(r"[^\d]", "", str(text))
    v = int(text) if text else 0
    return v if v >= 1_000_000 else 0

# ─── SOURCE 1: minhchinh.com ──────────────────────────────────────────────────
def _fetch_minhchinh(game_id, url, mc_type):
    try:
        r = sess.get(url, timeout=20)
        if not r.ok:
            print(f"  minhchinh HTTP {r.status_code}")
            return {}
        r.encoding = "utf-8"
        text = BeautifulSoup(r.text, "lxml").get_text(" ", strip=True)

        result = {}
        if mc_type == "power655":
            # "Giá trị Jackpot 1 54,255,066,600 Giá trị Jackpot 2 5,091,761,800"
            m1 = re.search(r"[Jj]ackpot\s*1\s+([\d,]+)", text)
            m2 = re.search(r"[Jj]ackpot\s*2\s+([\d,]+)", text)
            if m1: result["jackpot1"] = _parse_vnd(m1.group(1))
            if m2: result["jackpot2"] = _parse_vnd(m2.group(1))

        elif mc_type == "lotto535":
            # "Độc Đắc 8,411,695,000"
            m = re.search(r"[Đđ]ộc\s*[Đđ]ắc\s+([\d,]+)", text)
            if m: result["jackpot"] = _parse_vnd(m.group(1))
            # fallback: từ khóa Jackpot
            if not result:
                m = re.search(r"[Jj]ackpot\s+([\d,]+)", text)
                if m: result["jackpot"] = _parse_vnd(m.group(1))

        else:  # single jackpot (mega645)
            # "Jackpot 22,163,871,500"
            m = re.search(r"[Jj]ackpot\s+([\d,]+)", text)
            if m: result["jackpot"] = _parse_vnd(m.group(1))

        if result:
            print(f"  ✅ [minhchinh.com] {game_id}: {result}")
        return result
    except Exception as e:
        print(f"  minhchinh lỗi: {e}")
        return {}

# ─── SOURCE 2: ketquadientoan.com (backup) ────────────────────────────────────
def _kqdt_draw_dates(draw_days, today, n=5):
    result = []
    for delta in range(0, 60):
        d = today - timedelta(days=delta)
        if draw_days is None or d.weekday() in draw_days:
            result.append(d)
        if len(result) >= n:
            break
    return result

def _fetch_kqdt(game_id, slug, draw_days):
    today = datetime.now(VN_TZ).date()
    base  = "https://www.ketquadientoan.com"
    for d in _kqdt_draw_dates(draw_days, today):
        url = f"{base}/ket-qua-xo-so-dien-toan-{slug}/{d.strftime('%d-%m-%Y')}.html"
        try:
            r = sess.get(url, timeout=20)
            if not r.ok: continue
            r.encoding = "utf-8"
            soup = BeautifulSoup(r.text, "lxml")
            result = _extract_kqdt(soup, game_id)
            if result:
                print(f"  ✅ [ketquadientoan {d}] {game_id}: {result}")
                return result
        except Exception:
            continue
    return {}

def _extract_kqdt(soup, game_id):
    result = {}
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if not tds: continue
        first = tds[0].get_text(strip=True).lower()
        if game_id == "power655":
            if "jackpot 1" in first or "jackpot1" in first:
                v = max((_parse_vnd(td.get_text()) for td in tds), default=0)
                if v: result["jackpot1"] = v
            elif "jackpot 2" in first or "jackpot2" in first:
                v = max((_parse_vnd(td.get_text()) for td in tds), default=0)
                if v: result["jackpot2"] = v
        else:
            if "jackpot" in first or "độc đắc" in first:
                v = max((_parse_vnd(td.get_text()) for td in tds), default=0)
                if v: result["jackpot"] = v
    if not result:
        text = soup.get_text(" ", strip=True)
        if game_id == "power655":
            m1 = re.search(r"[Jj]ackpot\s*1[^\d]{0,8}([\d.]{9,})", text)
            m2 = re.search(r"[Jj]ackpot\s*2[^\d]{0,8}([\d.]{9,})", text)
            if m1: result["jackpot1"] = _parse_vnd(m1.group(1))
            if m2: result["jackpot2"] = _parse_vnd(m2.group(1))
        else:
            m = re.search(r"(?:[Jj]ackpot|[Đđ]ộc\s*[Đđ]ắc)[^\d]{0,8}([\d.]{9,})", text)
            if m: result["jackpot"] = _parse_vnd(m.group(1))
    return result

# ─── Main fetch ───────────────────────────────────────────────────────────────
def fetch_jackpot(game_id, cfg):
    result = _fetch_minhchinh(game_id, cfg["mc_url"], cfg["mc_type"])
    if result:
        return result
    print(f"  ⚠️  minhchinh.com thất bại, thử ketquadientoan.com...")
    return _fetch_kqdt(game_id, cfg["kqdt_slug"], cfg["kqdt_days"])

# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    print("🎰 Đang lấy jackpot (minhchinh.com → ketquadientoan.com)...")
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
