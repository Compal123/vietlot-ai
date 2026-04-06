#!/usr/bin/env python3
"""
VietLot AI — Data Fetcher
Tự động lấy kết quả từ vietlott.vn và lưu vào data/ dưới dạng JSONL.
Chạy: python scripts/fetch_data.py
"""
import json, sys, time, pathlib, re, os, subprocess
from datetime import datetime, timezone
from io import StringIO

# ─── Cài dependencies (tự động nếu thiếu) ────────────────────────────────────
def _ensure(*pkgs):
    import importlib
    import importlib.util  # phải import explicit
    missing = [p for p in pkgs if importlib.util.find_spec(p.split(">=")[0].replace("-","_")) is None]
    if missing:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q"] + missing, check=False)

_ensure("requests", "beautifulsoup4", "lxml", "pandas")

import requests
from bs4 import BeautifulSoup

# ─── Setup ────────────────────────────────────────────────────────────────────
DATA = pathlib.Path("data")
DATA.mkdir(exist_ok=True)

# Headers cho GET (lấy cookie từ Cloudflare challenge page)
HEADERS_GET = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}

# Headers cho AjaxPro POST
HEADERS_POST = {
    "Content-Type": "text/plain; charset=utf-8",
    "X-AjaxPro-Method": "ServerSideDrawResult",
    "Origin": "https://vietlott.vn",
    "Referer": "https://vietlott.vn/vi/trung-thuong/ket-qua-trung-thuong/winning-number-655",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
}

BASE = "https://vietlott.vn/ajaxpro/"

RENDER = {
    "isDebugMode": False,
    "CurrentCulture": "vi-VN",
    "CurrentUICulture": "vi-VN",
    "timeZone": 7,
    "language": "vi-VN",
    "pagemMode": 0,
}

sess = requests.Session()
sess.headers.update(HEADERS_POST)

# ─── Session Setup (VN Proxy + Cookie, giống thanhnhu/vietlott) ──────────────
_use_proxy = os.environ.get("USE_PROXY", "").lower() in ("1", "true", "yes")
_active_proxy: dict = {}
_cookies: dict = {}

def get_vn_proxies():
    """Lấy danh sách VN proxy từ nhiều nguồn."""
    import importlib.util
    proxies = []

    # Nguồn 1: geonode API (JSON, có filter theo country + lastChecked)
    try:
        resp = requests.get(
            "https://proxylist.geonode.com/api/proxy-list"
            "?limit=50&page=1&sort_by=lastChecked&sort_type=desc"
            "&country=VN&protocols=http%2Chttps",
            timeout=15, headers=HEADERS_GET
        )
        data = resp.json()
        new = [f"{p['ip']}:{p['port']}" for p in data.get("data", [])]
        proxies.extend(new)
        print(f"  🌐 geonode: {len(new)} VN proxy")
    except Exception as e:
        print(f"  ⚠️  geonode: {e}")

    # Nguồn 2: proxyscrape API
    try:
        resp = requests.get(
            "https://api.proxyscrape.com/v2/?request=getproxies"
            "&protocol=http&timeout=5000&country=VN&ssl=all&anonymity=all",
            timeout=15, headers=HEADERS_GET
        )
        lines = [l.strip() for l in resp.text.splitlines() if ":" in l.strip()]
        proxies.extend(lines[:30])
        print(f"  🌐 proxyscrape: {len(lines[:30])} VN proxy")
    except Exception as e:
        print(f"  ⚠️  proxyscrape: {e}")

    # Nguồn 3: free-proxy-list.net (backup)
    try:
        import pandas as pd
        resp = requests.get("https://free-proxy-list.net/", timeout=20, headers=HEADERS_GET)
        df = pd.read_html(StringIO(resp.text))[0]
        vn = df[df["Code"] == "VN"][["IP Address", "Port"]].head(20)
        new = [f"{row['IP Address']}:{int(row['Port'])}" for _, row in vn.iterrows()]
        # Chỉ thêm proxy chưa có
        new = [p for p in new if p not in proxies]
        proxies.extend(new)
        print(f"  🌐 free-proxy-list: {len(new)} VN proxy (mới)")
    except Exception as e:
        print(f"  ⚠️  free-proxy-list: {e}")

    # Loại bỏ duplicate
    proxies = list(dict.fromkeys(proxies))
    print(f"  🌐 Tổng: {len(proxies)} VN proxy để thử")
    return proxies

def _try_get_cookie(proxy: dict) -> dict:
    """GET vietlott.vn/ajaxpro/ qua proxy, extract cookie từ Cloudflare challenge."""
    try:
        res = requests.get(
            "https://vietlott.vn/ajaxpro/",
            headers=HEADERS_GET,
            proxies=proxy or None,
            timeout=15,
        )
        # Cách 1: Cloudflare JS challenge có dạng: document.cookie="cf_clearance=..."
        match = re.search(r'document\.cookie\s*=\s*["\']([^"\']+)["\']', res.text)
        if match:
            raw = match.group(1).split(";")[0].strip()
            if "=" in raw:
                k, v = raw.split("=", 1)
                return {k.strip(): v.strip()}
        # Cách 2: Set-Cookie header trả về trực tiếp
        if res.cookies:
            return dict(res.cookies)
        # Cách 3: Không có challenge, trang trả về OK luôn
        if res.status_code == 200 and "Just a moment" not in res.text:
            return {"__ok__": "1"}
    except Exception:
        pass
    return {}

def _init_via_playwright() -> bool:
    """Dùng Playwright (browser thật) để lấy Cloudflare cookie — reliable nhất."""
    global _cookies
    try:
        import importlib.util
        if importlib.util.find_spec("playwright") is None:
            return False
        from playwright.sync_api import sync_playwright
        print("  🎭 Playwright: khởi động Chromium...")
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = ctx.new_page()
            page.goto("https://vietlott.vn/", wait_until="networkidle", timeout=40000)
            # Đợi thêm để Cloudflare xử lý xong
            page.wait_for_timeout(3000)
            cookies = ctx.cookies()
            browser.close()
        cf = {c["name"]: c["value"] for c in cookies}
        if cf:
            _cookies = cf
            print(f"  ✅ Playwright OK — cookies: {list(cf.keys())}")
            return True
        print("  ⚠️  Playwright: không lấy được cookie")
        return False
    except Exception as e:
        print(f"  ⚠️  Playwright error: {e}")
        return False

def init_session():
    """Khởi tạo session:
    1. Thử VN proxy + cookie extract (giống thanhnhu/vietlott)
    2. Fallback: Playwright (browser thật, qua Cloudflare 100%)
    3. Fallback cuối: direct (chỉ dùng khi local không bị block)
    """
    global sess, _active_proxy, _cookies
    sess = requests.Session()
    sess.headers.update(HEADERS_POST)

    # ── Bước 1: VN proxy ──────────────────────────────────────────────────────
    print("  🌐 Bước 1: Tìm VN proxy + Cloudflare cookie...")
    proxy_list = get_vn_proxies()
    for p in proxy_list:
        proxy = {"http": p, "https": p}
        ck = _try_get_cookie(proxy)
        if ck:
            _active_proxy = proxy
            _cookies = {k: v for k, v in ck.items() if k != "__ok__"}
            print(f"  ✅ Proxy OK: {p} | Cookie: {list(ck.keys())[0] if ck else 'none'}")
            return

    # ── Bước 2: Playwright fallback ───────────────────────────────────────────
    print("  🎭 Bước 2: VN proxy thất bại — thử Playwright...")
    if _init_via_playwright():
        return

    # ── Bước 3: Direct (chỉ hoạt động khi không bị Cloudflare block) ─────────
    print("  ⚠️  Bước 3: Thử kết nối trực tiếp (có thể thất bại trên GitHub Actions)...")
    ck = _try_get_cookie({})
    if ck:
        _cookies = {k: v for k, v in ck.items() if k != "__ok__"}
        print(f"  ✅ Direct OK, cookie: {list(ck.keys())}")
    else:
        print(f"  ❌ Tất cả cách đều thất bại — POST requests sẽ bị 403")

# ─── Helpers ──────────────────────────────────────────────────────────────────
def ts():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")

def to_date(s):
    """dd/mm/yyyy → yyyy-mm-dd"""
    s = (s or "").strip()
    if "/" in s:
        parts = s.split("/")
        if len(parts) == 3:
            d, m, y = parts[0].strip(), parts[1].strip(), parts[2].strip()
            return f"{y}-{m.zfill(2)}-{d.zfill(2)}"
    return s

def load(fname):
    """Load JSONL file, return dict keyed by draw id."""
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
    """Save dict to JSONL sorted by date desc."""
    rows = sorted(db.values(), key=lambda x: x["date"], reverse=True)
    p = DATA / fname
    p.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8"
    )
    return len(rows)

def post_api(endpoint, body):
    """POST to AjaxPro endpoint, dùng VN proxy + Cloudflare cookie."""
    url  = BASE + endpoint
    data = json.dumps(body, ensure_ascii=False)

    try:
        r = sess.post(url, data=data, timeout=25,
                      proxies=_active_proxy or None,
                      cookies=_cookies or None)
        if r.ok:
            return r.json()
        print(f"    ❌ HTTP {r.status_code}")
        return None
    except Exception as e:
        print(f"    ❌ Request lỗi: {e}")
        return None

def get_html(resp):
    """Lấy HtmlContent từ response AjaxPro."""
    if not resp:
        return ""
    val = resp.get("value", {})
    if isinstance(val, dict):
        return val.get("HtmlContent", "")
    return ""

# ─── Power / Mega / Lotto ─────────────────────────────────────────────────────
def scrape_power(endpoint, key, array_rows, fname, pages=5):
    print(f"\n  ▶ {fname}")
    db = load(fname)
    new = 0

    for pg in range(pages):
        body = {
            "ORenderInfo": RENDER,
            "Key": key,
            "GameDrawId": "",
            "ArrayNumbers": [[""] * 18 for _ in range(array_rows)],
            "CheckMulti": False,
            "PageIndex": pg,
        }
        html = get_html(post_api(endpoint, body))
        if not html:
            print(f"    Trang {pg}: không có dữ liệu, dừng.")
            break

        soup = BeautifulSoup(html, "lxml")
        rows = soup.select("table tr")[1:]
        if not rows:
            break

        added = 0
        for tr in rows:
            tds = tr.find_all("td")
            if len(tds) < 3:
                continue
            try:
                raw_date = tds[0].get_text(" ", strip=True).split()[0]
                date = to_date(raw_date)
                did = tds[1].get_text(strip=True).zfill(5)
                nums = [
                    int(sp.get_text(strip=True))
                    for sp in tds[2].find_all("span")
                    if sp.get_text(strip=True).isdigit()
                ]
                if did and date and nums and did not in db:
                    db[did] = {"date": date, "id": did, "result": nums, "process_time": ts()}
                    new += 1
                    added += 1
            except Exception as e:
                print(f"    Row lỗi: {e}")

        print(f"    Trang {pg}: {len(rows)} dòng, {added} mới")
        time.sleep(0.7)

    total = save(fname, db)
    print(f"    ✅ {total} tổng cộng, {new} mới thêm")
    return new

# ─── Max3D / Max3D Pro ────────────────────────────────────────────────────────
def scrape_3d(endpoint, game_id, fname, pages=4):
    print(f"\n  ▶ {fname}")
    db = load(fname)
    new = 0

    for pg in range(1, pages + 1):
        body = {
            "ORenderInfo": RENDER,
            "GameId": game_id,
            "CheckMulti": 0,
            "PageIndex": pg,
        }
        html = get_html(post_api(endpoint, body))
        if not html:
            print(f"    Trang {pg}: không có dữ liệu, dừng.")
            break

        soup = BeautifulSoup(html, "lxml")

        # Lấy tên giải từ header
        header_row = soup.select_one("table tr")
        prize_names = []
        if header_row:
            ths = header_row.find_all(["th", "td"])
            prize_names = [th.get_text(strip=True) for th in ths[2:]]
        if not prize_names:
            prize_names = ["Giải Đặc biệt", "Giải Nhất", "Giải Nhì", "Giải ba"]

        rows = soup.select("table tr")[1:]
        if not rows:
            break

        added = 0
        for tr in rows:
            tds = tr.find_all("td")
            if len(tds) < 3:
                continue
            try:
                # Ngày từ link hoặc text
                links = tds[0].find_all("a")
                date_txt = links[0].get_text(strip=True) if links else tds[0].get_text(strip=True)
                date = to_date(date_txt.split()[0])
                did = tds[1].get_text(strip=True).zfill(5)

                result = {}
                for i, td in enumerate(tds[2:]):
                    nums = []
                    # Thu thập text từ spans
                    spans = td.find_all("span")
                    buf = ""
                    for sp in spans:
                        t = sp.get_text(strip=True).replace("|", "")
                        buf += t
                        while len(buf) >= 3:
                            chunk = buf[:3]
                            if chunk.isdigit():
                                nums.append(chunk)
                            buf = buf[3:]
                    # Fallback: lấy từ text thô
                    if not nums:
                        for w in td.get_text(" ").split():
                            if len(w) == 3 and w.isdigit():
                                nums.append(w)
                    pname = prize_names[i] if i < len(prize_names) else f"Giải {i+1}"
                    if nums:
                        result[pname] = nums

                if did and date and result and did not in db:
                    db[did] = {"date": date, "id": did, "result": result, "process_time": ts()}
                    new += 1
                    added += 1
            except Exception as e:
                print(f"    Row lỗi: {e}")

        print(f"    Trang {pg}: {len(rows)} dòng, {added} mới")
        time.sleep(0.7)

    total = save(fname, db)
    print(f"    ✅ {total} tổng cộng, {new} mới thêm")
    return new

# ─── Keno ─────────────────────────────────────────────────────────────────────
def scrape_keno(pages=3):
    print("\n  ▶ keno.jsonl")
    db = load("keno.jsonl")
    new = 0

    for pg in range(1, pages + 1):
        body = {
            "ORenderInfo": RENDER,
            "GameId": "6",
            "ProcessType": 0,
            "PageIndex": pg,
            "TotalRow": 999999,
            "OddEven": 2,
            "UpperLower": 2,
        }
        html = get_html(post_api(
            "Vietlott.PlugIn.WebParts.GameKenoCompareWebPart,Vietlott.PlugIn.WebParts.ashx",
            body
        ))
        if not html:
            break

        soup = BeautifulSoup(html, "lxml")
        rows = soup.select("table tr")[1:]
        if not rows:
            break

        added = 0
        for tr in rows:
            tds = tr.find_all("td")
            if len(tds) < 3:
                continue
            try:
                date = to_date(tds[0].get_text(strip=True).split()[0])
                did = tds[1].get_text(strip=True).zfill(5)
                nums = [
                    int(sp.get_text(strip=True))
                    for sp in tds[2].find_all("span")
                    if sp.get_text(strip=True).isdigit()
                ]
                if did and date and nums and did not in db:
                    db[did] = {"date": date, "id": did, "result": nums, "process_time": ts()}
                    new += 1
                    added += 1
            except Exception as e:
                print(f"    Row lỗi: {e}")

        print(f"    Trang {pg}: {len(rows)} dòng, {added} mới")
        time.sleep(0.7)

    total = save("keno.jsonl", db)
    print(f"    ✅ {total} tổng cộng, {new} mới thêm")
    return new

# ─── Bingo18 ──────────────────────────────────────────────────────────────────
def scrape_bingo18(pages=3):
    print("\n  ▶ bingo18.jsonl")
    db = load("bingo18.jsonl")
    new = 0

    for pg in range(1, pages + 1):
        body = {
            "ORenderInfo": RENDER,
            "GameId": "8",
            "ProcessType": 0,
            "PageIndex": pg,
            "TotalRow": 999999,
        }
        html = get_html(post_api(
            "Vietlott.PlugIn.WebParts.GameBingoCompareWebPart,Vietlott.PlugIn.WebParts.ashx",
            body
        ))
        if not html:
            break

        soup = BeautifulSoup(html, "lxml")
        rows = soup.select("table tr")[1:]
        if not rows:
            break

        added = 0
        for tr in rows:
            tds = tr.find_all("td")
            if len(tds) < 2:
                continue
            try:
                links = tds[0].find_all("a")
                date_txt = links[0].get_text(strip=True) if links else tds[0].get_text(strip=True)
                date = to_date(date_txt.split()[0])
                did_txt = links[1].get_text(strip=True) if len(links) > 1 else tds[1].get_text(strip=True)
                did = did_txt.zfill(5)
                nums = [
                    int(sp.get_text(strip=True))
                    for sp in tr.find_all("span")
                    if sp.get_text(strip=True).isdigit()
                ]
                if did and date and nums and did not in db:
                    db[did] = {"date": date, "id": did, "result": nums, "process_time": ts()}
                    new += 1
                    added += 1
            except Exception as e:
                print(f"    Row lỗi: {e}")

        print(f"    Trang {pg}: {len(rows)} dòng, {added} mới")
        time.sleep(0.7)

    total = save("bingo18.jsonl", db)
    print(f"    ✅ {total} tổng cộng, {new} mới thêm")
    return new

# ─── Game registry ────────────────────────────────────────────────────────────
# Mỗi game: (function, args...)
def run_power655(pages=5):
    return scrape_power("Vietlott.PlugIn.WebParts.Game655CompareWebPart,Vietlott.PlugIn.WebParts.ashx",
                        key="23bbd667", array_rows=5, fname="power655.jsonl", pages=pages)

def run_power645(pages=5):
    return scrape_power("Vietlott.PlugIn.WebParts.Game645CompareWebPart,Vietlott.PlugIn.WebParts.ashx",
                        key="8290fce2", array_rows=6, fname="power645.jsonl", pages=pages)

def run_power535(pages=5):
    return scrape_power("Vietlott.PlugIn.WebParts.Game535CompareWebPart,Vietlott.PlugIn.WebParts.ashx",
                        key="d0ea794f", array_rows=5, fname="power535.jsonl", pages=pages)

def run_max3d(pages=4):
    return scrape_3d("Vietlott.PlugIn.WebParts.GameMax3DCompareWebPart,Vietlott.PlugIn.WebParts.ashx",
                     game_id="5", fname="3d.jsonl", pages=pages)

def run_max3dpro(pages=4):
    return scrape_3d("Vietlott.PlugIn.WebParts.GameMax3DProCompareWebPart,Vietlott.PlugIn.WebParts.ashx",
                     game_id="7", fname="3d_pro.jsonl", pages=pages)

def run_keno(pages=2):
    return scrape_keno(pages=pages)

def run_bingo18(pages=2):
    return scrape_bingo18(pages=pages)

GAMES = {
    "power655": run_power655,
    "power645": run_power645,
    "power535": run_power535,
    "max3d":    run_max3d,
    "max3dpro": run_max3dpro,
    "keno":     run_keno,
    "bingo18":  run_bingo18,
}

# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    """
    Cách dùng:
      python fetch_data.py                      → tất cả game, pages mặc định
      python fetch_data.py keno bingo18         → chỉ keno + bingo18
      python fetch_data.py --pages 15           → tất cả game, 15 trang
      python fetch_data.py power655 --pages 20  → power655, 20 trang
    """
    args = sys.argv[1:]

    # Tách --pages N ra khỏi danh sách game
    pages_override = None
    filtered = []
    i = 0
    while i < len(args):
        if args[i] == "--pages" and i + 1 < len(args):
            try:
                pages_override = int(args[i + 1])
            except ValueError:
                pass
            i += 2
        else:
            filtered.append(args[i])
            i += 1

    targets = filtered if filtered else list(GAMES.keys())
    invalid = [g for g in targets if g not in GAMES]
    if invalid:
        print(f"❌ Game không hợp lệ: {invalid}")
        print(f"   Hợp lệ: {list(GAMES.keys())}")
        sys.exit(1)

    print("=" * 55)
    print(f"🎰  VietLot AI — Data Fetcher")
    print(f"⏰  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🎯  Games: {', '.join(targets)}")
    if pages_override:
        print(f"📄  Pages: {pages_override} (override)")
    print("=" * 55)

    # Khởi tạo cookie + proxy trước khi scrape
    print("\n🔧 Khởi tạo session...")
    init_session()
    time.sleep(1)

    import inspect
    grand_total = 0
    for g in targets:
        fn = GAMES[g]
        if pages_override is not None:
            sig = inspect.signature(fn)
            if "pages" in sig.parameters:
                grand_total += fn(pages=pages_override)
            else:
                grand_total += fn()
        else:
            grand_total += fn()

    print(f"\n{'=' * 55}")
    print(f"🏆  Hoàn thành! Tổng mới: {grand_total} entries")
    print(f"{'=' * 55}")

if __name__ == "__main__":
    main()
