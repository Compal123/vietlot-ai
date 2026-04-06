#!/usr/bin/env python3
"""
VietLot AI — Data Fetcher
Tự động lấy kết quả từ vietlott.vn và lưu vào data/ dưới dạng JSONL.
Chạy: python scripts/fetch_data.py
"""
import json, sys, time, pathlib, re, os
from datetime import datetime, timezone
from io import StringIO

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "requests", "beautifulsoup4", "lxml"])
    import requests
    from bs4 import BeautifulSoup

# ─── Setup ────────────────────────────────────────────────────────────────────
DATA = pathlib.Path("data")
DATA.mkdir(exist_ok=True)

HEADERS = {
    "Host": "vietlott.vn",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/117.0",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Content-Type": "text/plain; charset=utf-8",
    "Cache-Control": "no-cache",
    "X-AjaxPro-Method": "ServerSideDrawResult",
    "Origin": "https://vietlott.vn",
    "Connection": "keep-alive",
    "Referer": "https://vietlott.vn/vi/trung-thuong/ket-qua-trung-thuong/winning-number-655",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "TE": "trailers",
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
sess.headers.update(HEADERS)

# ─── Cookie + Proxy Setup ─────────────────────────────────────────────────────
_use_proxy = os.environ.get("USE_PROXY", "").lower() in ("1", "true", "yes")
_proxies: list = []          # list of "ip:port" strings
_active_proxy: dict = {}     # {"http":..., "https":...} của proxy đang dùng

def get_vn_proxies():
    """Lấy danh sách proxy Việt Nam từ free-proxy-list.net."""
    try:
        import pandas as pd
        resp = requests.get("https://free-proxy-list.net/", timeout=20)
        resp.raise_for_status()
        df = pd.read_html(StringIO(resp.text))[0]
        vn = df[df["Code"] == "VN"][["IP Address", "Port"]].head(15)
        proxies = [f"{row['IP Address']}:{int(row['Port'])}" for _, row in vn.iterrows()]
        print(f"  🌐 Tìm thấy {len(proxies)} VN proxy: {proxies[:3]}...")
        return proxies
    except Exception as e:
        print(f"  ⚠️  Không lấy được proxy list: {e}")
        return []

def find_working_proxy(proxy_list: list) -> dict:
    """Thử từng proxy, trả về proxy đầu tiên kết nối được vietlott.vn."""
    test_url = "https://vietlott.vn/ajaxpro/"
    for p in proxy_list:
        proxy = {"http": p, "https": p}
        try:
            r = requests.get(test_url, proxies=proxy, timeout=10)
            if r.status_code < 500:
                print(f"  ✅ Proxy hoạt động: {p} (HTTP {r.status_code})")
                return proxy
        except Exception:
            pass
    return {}

def get_vietlott_cookie(proxy: dict = {}):
    """Lấy session cookie từ vietlott.vn."""
    try:
        res = requests.get(
            "https://vietlott.vn/ajaxpro/",
            headers={"User-Agent": HEADERS["User-Agent"]},
            proxies=proxy or None,
            timeout=20,
        )
        # Cách 1: cookie trong JS  document.cookie="KEY=VALUE"
        match = re.search(r'document\.cookie\s*=\s*["\']([^"\']+)["\']', res.text)
        if match:
            raw = match.group(1).split(";")[0].strip()   # bỏ phần expires...
            if "=" in raw:
                k, v = raw.split("=", 1)
                sess.cookies.set(k.strip(), v.strip())
                print(f"  🍪 Cookie JS: {k.strip()}={v.strip()[:8]}...")
                return True

        # Cách 2: Set-Cookie header
        if res.cookies:
            for c in res.cookies:
                sess.cookies.set(c.name, c.value)
            names = [c.name for c in res.cookies]
            print(f"  🍪 Cookie header: {names}")
            return True

        print(f"  ⚠️  Không tìm thấy cookie (status={res.status_code})")
        return False
    except Exception as e:
        print(f"  ⚠️  Cookie request lỗi: {e}")
        return False

def init_session():
    """Khởi tạo cookie và proxy (gọi 1 lần trước khi scrape)."""
    global _proxies, _active_proxy

    if _use_proxy:
        print("  🌐 Proxy mode: ON — đang tìm VN proxy...")
        _proxies = get_vn_proxies()
        _active_proxy = find_working_proxy(_proxies)
        if not _active_proxy:
            print("  ⚠️  Không có proxy hoạt động, thử trực tiếp")

    # Lấy cookie (qua proxy nếu có)
    ok = get_vietlott_cookie(proxy=_active_proxy)
    if not ok and _proxies and not _active_proxy:
        # Thử tìm proxy và lấy cookie lại
        _active_proxy = find_working_proxy(_proxies)
        if _active_proxy:
            get_vietlott_cookie(proxy=_active_proxy)

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
    """POST to AjaxPro endpoint."""
    url  = BASE + endpoint
    data = json.dumps(body, ensure_ascii=False)
    proxy = _active_proxy or None

    try:
        r = sess.post(url, data=data, timeout=25, proxies=proxy)
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
