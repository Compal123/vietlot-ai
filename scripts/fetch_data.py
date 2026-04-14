#!/usr/bin/env python3
"""
VietLot AI — Data Fetcher
Lấy kết quả từ vietlott.vn qua AjaxPro API và lưu vào data/ dưới dạng JSONL.

Cách dùng:
  python scripts/fetch_data.py                      → tất cả game
  python scripts/fetch_data.py keno bingo18         → chỉ keno + bingo18
  python scripts/fetch_data.py --pages 15           → tất cả game, 15 trang
  python scripts/fetch_data.py power655 --pages 20  → power655, 20 trang
"""
import json, sys, time, pathlib, itertools, random
from datetime import datetime, timezone

# Fix encoding trên Windows terminal
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import requests
from bs4 import BeautifulSoup

# ─── Paths ────────────────────────────────────────────────────────────────────
ROOT = pathlib.Path(__file__).parent.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)

# ─── HTTP config ──────────────────────────────────────────────────────────────
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.5",
    "Content-Type": "text/plain; charset=utf-8",
    "X-AjaxPro-Method": "ServerSideDrawResult",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://vietlott.vn",
    "Referer": "https://vietlott.vn/vi/trung-thuong/ket-qua-trung-thuong/winning-number-655",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}

BASE_URL = "https://vietlott.vn/ajaxpro/"

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

# ─── Proxy pool (dùng khi IP bị chặn 403) ────────────────────────────────────
_proxy_cycle = None
_proxy_mode  = False   # True sau khi phát hiện 403

def _load_proxies():
    """Lấy VN proxy từ 2 nguồn miễn phí."""
    global _proxy_cycle
    proxies = []

    # Nguồn 1: proxyscrape (nhanh, JSON đơn giản)
    try:
        r = requests.get(
            "https://api.proxyscrape.com/v2/?request=getproxies"
            "&protocol=http&timeout=5000&country=VN&ssl=all&anonymity=all",
            timeout=12,
        )
        lines = [l.strip() for l in r.text.splitlines() if ":" in l.strip()]
        proxies += lines
        print(f"  proxyscrape: {len(lines)} proxy VN")
    except Exception as e:
        print(f"  proxyscrape lỗi: {e}")

    # Nguồn 2: geonode (JSON, ưu tiên uptime cao)
    try:
        r = requests.get(
            "https://proxylist.geonode.com/api/proxy-list"
            "?limit=50&page=1&sort_by=lastChecked&sort_type=desc&country=VN&protocols=http",
            timeout=12,
        )
        items = r.json().get("data", [])
        lines = [f"{p['ip']}:{p['port']}" for p in items]
        proxies += lines
        print(f"  geonode: {len(lines)} proxy VN")
    except Exception as e:
        print(f"  geonode lỗi: {e}")

    if proxies:
        random.shuffle(proxies)   # Xáo trộn để không bị hit cùng 1 proxy
        _proxy_cycle = itertools.cycle(proxies)
        print(f"  Tổng: {len(proxies)} proxy sẵn sàng")
        return True
    print("  Không lấy được proxy nào!")
    return False

# ─── Helpers ──────────────────────────────────────────────────────────────────
def ts():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

def to_date(s):
    """dd/mm/yyyy → yyyy-mm-dd"""
    s = (s or "").strip()
    if "/" in s:
        parts = s.split("/")
        if len(parts) == 3:
            d, m, y = parts
            return f"{y.strip()}-{m.strip().zfill(2)}-{d.strip().zfill(2)}"
    return s

def load(fname):
    """Load JSONL file, trả về dict keyed by draw id."""
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
    """Lưu dict → JSONL, sắp xếp theo ngày mới nhất trước."""
    rows = sorted(db.values(), key=lambda x: x["date"], reverse=True)
    p = DATA / fname
    p.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    return len(rows)

def post_api(endpoint, body):
    """POST tới AjaxPro endpoint.
    - Thử direct trước (nhanh, dùng khi IP VN).
    - Nếu 403: tự chuyển sang proxy mode và thử lại.
    """
    global _proxy_mode, _proxy_cycle
    url  = BASE_URL + endpoint
    data = json.dumps(body, ensure_ascii=False)

    # ── Direct (không proxy) ──────────────────────────────────────────────────
    if not _proxy_mode:
        try:
            r = sess.post(url, data=data, timeout=25)
            if r.ok:
                return r.json()
            if r.status_code == 403:
                print(f"    ⚠️  403 từ IP này — chuyển sang proxy mode...")
                _proxy_mode = True
                if _proxy_cycle is None:
                    _load_proxies()
            else:
                print(f"    ❌ HTTP {r.status_code}")
                return None
        except Exception as e:
            print(f"    ❌ Request lỗi: {e}")
            return None

    # ── Proxy mode ────────────────────────────────────────────────────────────
    if _proxy_cycle is None:
        return None

    for attempt in range(10):
        proxy_addr = next(_proxy_cycle)
        proxy = {"http": f"http://{proxy_addr}", "https": f"http://{proxy_addr}"}
        try:
            r = sess.post(url, data=data, timeout=20, proxies=proxy)
            if r.ok:
                return r.json()
            if r.status_code in (403, 407):
                continue   # Proxy bị block, thử cái khác
        except Exception:
            continue       # Proxy chết, thử cái khác

    print(f"    ❌ Hết proxy, bỏ qua endpoint này")
    return None

def get_html(resp):
    """Lấy HtmlContent từ AjaxPro response."""
    if not resp:
        return ""
    val = resp.get("value", {})
    if isinstance(val, dict):
        return val.get("HtmlContent", "")
    return ""

# ─── Power / Mega / Lotto 5/35 ────────────────────────────────────────────────
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
                    db[did] = {"date": date, "id": did, "result": nums}
                    new += 1
                    added += 1
            except Exception as e:
                print(f"    Row lỗi: {e}")

        print(f"    Trang {pg}: {len(rows)} dòng, {added} mới")
        time.sleep(0.5)

    total = save(fname, db)
    print(f"    ✅ {total} tổng, +{new} mới")
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

        header_row = soup.select_one("table tr")
        prize_names = []
        if header_row:
            ths = header_row.find_all(["th", "td"])
            prize_names = [th.get_text(strip=True) for th in ths[2:]]
        if not prize_names:
            prize_names = ["Giải Đặc biệt", "Giải Nhất", "Giải Nhì", "Giải Ba"]

        rows = soup.select("table tr")[1:]
        if not rows:
            break

        added = 0
        for tr in rows:
            tds = tr.find_all("td")
            if len(tds) < 3:
                continue
            try:
                links = tds[0].find_all("a")
                date_txt = links[0].get_text(strip=True) if links else tds[0].get_text(strip=True)
                date = to_date(date_txt.split()[0])
                did = tds[1].get_text(strip=True).zfill(5)

                result = {}
                for i, td in enumerate(tds[2:]):
                    nums = []
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
                    if not nums:
                        for w in td.get_text(" ").split():
                            if len(w) == 3 and w.isdigit():
                                nums.append(w)
                    pname = prize_names[i] if i < len(prize_names) else f"Giải {i+1}"
                    if nums:
                        result[pname] = nums

                if did and date and result and did not in db:
                    db[did] = {"date": date, "id": did, "result": result}
                    new += 1
                    added += 1
            except Exception as e:
                print(f"    Row lỗi: {e}")

        print(f"    Trang {pg}: {len(rows)} dòng, {added} mới")
        time.sleep(0.5)

    total = save(fname, db)
    print(f"    ✅ {total} tổng, +{new} mới")
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
            body,
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
                    db[did] = {"date": date, "id": did, "result": nums}
                    new += 1
                    added += 1
            except Exception as e:
                print(f"    Row lỗi: {e}")

        print(f"    Trang {pg}: {len(rows)} dòng, {added} mới")
        time.sleep(0.5)

    total = save("keno.jsonl", db)
    print(f"    ✅ {total} tổng, +{new} mới")
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
            body,
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
                    db[did] = {"date": date, "id": did, "result": nums}
                    new += 1
                    added += 1
            except Exception as e:
                print(f"    Row lỗi: {e}")

        print(f"    Trang {pg}: {len(rows)} dòng, {added} mới")
        time.sleep(0.5)

    total = save("bingo18.jsonl", db)
    print(f"    ✅ {total} tổng, +{new} mới")
    return new

# ─── Game registry ────────────────────────────────────────────────────────────
def run_power655(pages=5):
    return scrape_power(
        "Vietlott.PlugIn.WebParts.Game655CompareWebPart,Vietlott.PlugIn.WebParts.ashx",
        key="23bbd667", array_rows=5, fname="power655.jsonl", pages=pages,
    )

def run_power645(pages=5):
    return scrape_power(
        "Vietlott.PlugIn.WebParts.Game645CompareWebPart,Vietlott.PlugIn.WebParts.ashx",
        key="8290fce2", array_rows=6, fname="power645.jsonl", pages=pages,
    )

def run_power535(pages=5):
    return scrape_power(
        "Vietlott.PlugIn.WebParts.Game535CompareWebPart,Vietlott.PlugIn.WebParts.ashx",
        key="d0ea794f", array_rows=5, fname="power535.jsonl", pages=pages,
    )

def run_max3d(pages=4):
    return scrape_3d(
        "Vietlott.PlugIn.WebParts.GameMax3DCompareWebPart,Vietlott.PlugIn.WebParts.ashx",
        game_id="5", fname="3d.jsonl", pages=pages,
    )

def run_max3dpro(pages=4):
    return scrape_3d(
        "Vietlott.PlugIn.WebParts.GameMax3DProCompareWebPart,Vietlott.PlugIn.WebParts.ashx",
        game_id="7", fname="3d_pro.jsonl", pages=pages,
    )

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
    args = sys.argv[1:]

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

    import inspect
    grand_total = 0
    for g in targets:
        fn = GAMES[g]
        if pages_override is not None and "pages" in inspect.signature(fn).parameters:
            grand_total += fn(pages=pages_override)
        else:
            grand_total += fn()

    print(f"\n{'=' * 55}")
    print(f"🏆  Hoàn thành! Tổng mới: {grand_total} entries")
    print(f"{'=' * 55}")

if __name__ == "__main__":
    main()
