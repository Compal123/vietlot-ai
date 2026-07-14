#!/usr/bin/env python3
"""
VietLot AI — API Builder
Sinh tầng API JSON tĩnh (kết quả + phân tích) từ data/*.jsonl.
Kết quả ghi vào api/ và được deploy cùng GitHub Pages.

Chạy: python scripts/build_api.py
Không cần dependency ngoài (chỉ dùng thư viện chuẩn Python).

API base khi deploy: https://compal123.github.io/vietlot-ai/api/
"""
import json
import sys
import pathlib
from collections import Counter
from datetime import datetime, timezone, timedelta
from itertools import combinations

try:
    sys.stdout.reconfigure(encoding="utf-8")  # in emoji trên console Windows
except Exception:
    pass

# ─── Cấu hình ────────────────────────────────────────────────────────────────
ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
API = ROOT / "api"

SITE = "https://compal123.github.io/vietlot-ai"
API_BASE = f"{SITE}/api"
VN_TZ = timezone(timedelta(hours=7))
RESULTS_LIMIT = 100          # số kỳ gần nhất trả trong results.json
RECENT_WINDOW = 100          # cửa sổ "gần đây" cho phân tích
TOP_N = 10                   # số phần tử trong bảng nóng/lạnh/cặp

# Game bốc số: pool = dải số, main = số con chính, special = số phụ (jackpot ball)
NUMBER_GAMES = {
    "power655": {"name": "Power 6/55", "pool": 55, "main": 6, "special": 1,
                 "schedule": "Thứ 3, 5, 7 — 18:00"},
    "power645": {"name": "Mega 6/45", "pool": 45, "main": 6, "special": 0,
                 "schedule": "Thứ 4, 6, CN — 18:00"},
    "power535": {"name": "Power 5/35", "pool": 35, "main": 5, "special": 1,
                 "schedule": "Thứ 2, 4, 6 — 18:00"},
    "keno": {"name": "Keno", "pool": 80, "main": 20, "special": 0,
             "schedule": "Mỗi 10 phút, 06:00–21:55"},
}

# Game bốc chữ số: result là dict giải -> danh sách số 3 chữ số
DIGIT_GAMES = {
    "3d": {"name": "Max 3D", "digits": 3, "schedule": "Thứ 2, 4, 6 — 18:00"},
    "3d_pro": {"name": "Max 3D Pro", "digits": 3, "schedule": "Thứ 3, 5, 7 — 18:00"},
}


# ─── Tiện ích ─────────────────────────────────────────────────────────────────
def now_iso():
    return datetime.now(VN_TZ).replace(microsecond=0).isoformat()


def load_jsonl(path):
    rows = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def by_date(rows):
    """Sắp xếp mới -> cũ theo (date, id) và loại bản ghi thiếu date."""
    rows = [r for r in rows if r.get("date")]
    rows.sort(key=lambda r: (r.get("date", ""), str(r.get("id", ""))), reverse=True)
    return rows


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    print(f"  ✓ {path.relative_to(ROOT)}")


# ─── Phân tích game bốc số ────────────────────────────────────────────────────
def analyze_number_game(key, cfg, rows):
    """Trả về dict thống kê cho một game bốc số. rows: mới -> cũ."""
    main_n = cfg["main"]
    pool = cfg["pool"]

    freq = Counter()          # tần suất số chính, toàn lịch sử
    bonus_freq = Counter()    # tần suất số phụ (nếu có)
    last_seen = {}            # số -> index kỳ gần nhất xuất hiện (0 = mới nhất)
    sums, odd_ratios, low_ratios = [], [], []
    pair_freq = Counter()
    recent_freq = Counter()

    valid = [r for r in rows if isinstance(r.get("result"), list)]
    for idx, r in enumerate(valid):
        res = r["result"]
        main = res[:main_n]
        bonus = res[main_n:]
        for n in main:
            freq[n] += 1
            if n not in last_seen:
                last_seen[n] = idx
            if idx < RECENT_WINDOW:
                recent_freq[n] += 1
        for n in bonus:
            bonus_freq[n] += 1
        if main:
            sums.append(sum(main))
            odd_ratios.append(sum(1 for n in main if n % 2 == 1))
            low_ratios.append(sum(1 for n in main if n <= pool // 2))
        for a, b in combinations(sorted(main), 2):
            pair_freq[(a, b)] += 1

    total_draws = len(valid)
    universe = list(range(1, pool + 1))

    # nóng / lạnh theo tần suất toàn lịch sử
    ranked = sorted(universe, key=lambda n: (-freq.get(n, 0), n))
    hot = [{"number": n, "count": freq.get(n, 0)} for n in ranked[:TOP_N]]
    cold = [{"number": n, "count": freq.get(n, 0)} for n in ranked[-TOP_N:][::-1]]

    # "số gan": số kỳ liên tiếp chưa xuất hiện (tính từ kỳ mới nhất)
    overdue = []
    for n in universe:
        gap = last_seen.get(n, total_draws)  # chưa từng ra -> gap = tổng số kỳ
        overdue.append({"number": n, "draws_since_last": gap})
    overdue.sort(key=lambda x: (-x["draws_since_last"], x["number"]))
    overdue = overdue[:TOP_N]

    # nóng gần đây
    recent_ranked = sorted(universe, key=lambda n: (-recent_freq.get(n, 0), n))
    recent_hot = [{"number": n, "count": recent_freq.get(n, 0)}
                  for n in recent_ranked[:TOP_N]]

    top_pairs = [{"pair": [a, b], "count": c}
                 for (a, b), c in pair_freq.most_common(TOP_N)]

    def stat(arr):
        if not arr:
            return None
        return {"min": min(arr), "max": max(arr),
                "avg": round(sum(arr) / len(arr), 2)}

    out = {
        "game": key,
        "name": cfg["name"],
        "pool": pool,
        "numbers_per_draw": main_n,
        "total_draws": total_draws,
        "frequency": {str(n): freq.get(n, 0) for n in universe},
        "hot_numbers": hot,
        "cold_numbers": cold,
        "overdue_numbers": overdue,
        "recent_hot_numbers": {
            "window": min(RECENT_WINDOW, total_draws),
            "numbers": recent_hot,
        },
        "top_pairs": top_pairs,
        "sum_stats": stat(sums),
        "odd_count_stats": stat(odd_ratios),
        "low_count_stats": stat(low_ratios),
        "generated_at": now_iso(),
        "_note": ("Dữ liệu thống kê thuần túy từ lịch sử; xổ số là ngẫu nhiên, "
                  "các con số này KHÔNG dự đoán được kết quả tương lai."),
    }
    if cfg["special"]:
        b_ranked = sorted(range(1, pool + 1),
                          key=lambda n: (-bonus_freq.get(n, 0), n))
        out["bonus_frequency"] = {str(n): bonus_freq.get(n, 0)
                                  for n in range(1, pool + 1)}
        out["bonus_hot_numbers"] = [{"number": n, "count": bonus_freq.get(n, 0)}
                                    for n in b_ranked[:TOP_N]]
    return out


# ─── Phân tích game bốc chữ số (3D) ───────────────────────────────────────────
def analyze_digit_game(key, cfg, rows):
    num_freq = Counter()                         # tần suất số 3 chữ số
    pos_freq = [Counter() for _ in range(cfg["digits"])]  # tần suất từng vị trí

    valid = [r for r in rows if isinstance(r.get("result"), dict)]
    for r in valid:
        for nums in r["result"].values():
            for s in nums:
                s = str(s).zfill(cfg["digits"])
                num_freq[s] += 1
                for i, ch in enumerate(s[-cfg["digits"]:]):
                    if ch.isdigit():
                        pos_freq[i][ch] += 1

    top_numbers = [{"number": n, "count": c}
                   for n, c in num_freq.most_common(TOP_N)]
    positions = []
    labels = ["trăm", "chục", "đơn vị"]
    for i, pf in enumerate(pos_freq):
        digits_sorted = sorted(range(10), key=lambda d: (-pf.get(str(d), 0), d))
        positions.append({
            "position": labels[i] if i < len(labels) else f"vị trí {i+1}",
            "frequency": {str(d): pf.get(str(d), 0) for d in range(10)},
            "hot_digits": digits_sorted[:3],
        })

    return {
        "game": key,
        "name": cfg["name"],
        "total_draws": len(valid),
        "top_numbers": top_numbers,
        "digit_positions": positions,
        "generated_at": now_iso(),
        "_note": ("Thống kê thuần túy từ lịch sử; xổ số là ngẫu nhiên và "
                  "KHÔNG dự đoán được."),
    }


# ─── Build ────────────────────────────────────────────────────────────────────
def build():
    print("🔧 Building API...")
    catalog = []

    all_games = {**NUMBER_GAMES, **DIGIT_GAMES}
    for key, cfg in all_games.items():
        rows = by_date(load_jsonl(DATA / f"{key}.jsonl"))
        if not rows:
            print(f"  ⚠ {key}: không có dữ liệu, bỏ qua")
            continue

        # latest.json
        write_json(API / key / "latest.json", {
            "game": key, "name": cfg["name"],
            "latest": rows[0],
            "generated_at": now_iso(),
        })

        # results.json (N kỳ gần nhất)
        write_json(API / key / "results.json", {
            "game": key, "name": cfg["name"],
            "count": min(RESULTS_LIMIT, len(rows)),
            "total_available": len(rows),
            "full_history_jsonl": f"{SITE}/data/{key}.jsonl",
            "results": rows[:RESULTS_LIMIT],
            "generated_at": now_iso(),
        })

        # stats.json
        if key in NUMBER_GAMES:
            stats = analyze_number_game(key, cfg, rows)
        else:
            stats = analyze_digit_game(key, cfg, rows)
        write_json(API / key / "stats.json", stats)

        catalog.append({
            "game": key,
            "name": cfg["name"],
            "type": "number" if key in NUMBER_GAMES else "digit",
            "schedule": cfg.get("schedule"),
            "total_draws": len(rows),
            "date_range": {"from": rows[-1].get("date"), "to": rows[0].get("date")},
            "latest_draw": {"date": rows[0].get("date"), "id": rows[0].get("id")},
            "endpoints": {
                "latest": f"{API_BASE}/{key}/latest.json",
                "results": f"{API_BASE}/{key}/results.json",
                "stats": f"{API_BASE}/{key}/stats.json",
                "predictions": f"{API_BASE}/{key}/predictions.json",
                "full_history_jsonl": f"{SITE}/data/{key}.jsonl",
            },
        })

    # jackpots.json
    jp_path = DATA / "jackpots.json"
    if jp_path.exists():
        jp = json.loads(jp_path.read_text(encoding="utf-8"))
        write_json(API / "jackpots.json", jp)

    # predictions (dự đoán công khai + độ chính xác)
    build_predictions_api()

    # index.json — danh mục chính
    index = {
        "name": "VietLot AI API",
        "description": "API tĩnh miễn phí: kết quả & phân tích thống kê xổ số Vietlott. "
                       "Cập nhật tự động qua GitHub Actions, không cần server.",
        "version": "1.0.0",
        "base_url": API_BASE,
        "site": SITE,
        "source": "https://github.com/Compal123/vietlot-ai",
        "generated_at": now_iso(),
        "usage": {
            "auth": "Không cần. Chỉ cần GET công khai, trả JSON (UTF-8).",
            "cors": "Cho phép mọi origin (GitHub Pages).",
            "disclaimer": "Dữ liệu thống kê tham khảo. Xổ số là ngẫu nhiên; "
                          "không có phương pháp nào dự đoán được kết quả.",
        },
        "shared_endpoints": {
            "index": f"{API_BASE}/index.json",
            "jackpots": f"{API_BASE}/jackpots.json",
            "openapi": f"{API_BASE}/openapi.json",
            "llms_txt": f"{API_BASE}/llms.txt",
        },
        "games": catalog,
    }
    write_json(API / "index.json", index)

    build_openapi(catalog)
    build_llms_txt(index, catalog)
    print("✅ Done.")


def build_predictions_api():
    """Đọc data/predictions.jsonl → api/{game}/predictions.json + tính độ chính xác."""
    path = DATA / "predictions.jsonl"
    if not path.exists():
        return
    recs = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    recs.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    by_game = {}
    for r in recs:
        by_game.setdefault(r.get("game"), []).append(r)

    for game, lst in by_game.items():
        lst.sort(key=lambda p: str(p.get("based_on_id", "")), reverse=True)
        settled = [p for p in lst if p.get("matched")]
        pending = [p for p in lst if not p.get("result")]
        n = len(settled)
        acc = None
        if n:
            def avg(k):
                return round(sum(p["matched"].get(k, 0) or 0 for p in settled) / n, 3)
            pick = len(settled[0]["picks"].get("ai", [])) or None
            acc = {
                "settled_count": n,
                "picks_per_draw": pick,
                "avg_match": {"ai": avg("ai"), "hot": avg("hot"),
                              "cold": avg("cold"), "corr": avg("corr")},
                "note": ("Số trúng trung bình mỗi kỳ. Xổ số ngẫu nhiên — các mức này "
                         "thường xấp xỉ kỳ vọng ngẫu nhiên, KHÔNG chứng minh dự đoán được."),
            }
        write_json(API / game / "predictions.json", {
            "game": game,
            "description": ("Dự đoán AI công khai. Bản 'live' được commit TRƯỚC kỳ quay "
                            "(lịch sử git = bằng chứng thời gian). Bản 'backtest' tính lại "
                            "trên dữ liệu quá khứ, chỉ dùng kỳ cũ hơn (không nhìn trộm)."),
            "accuracy": acc,
            "pending": pending,
            "history": settled,
            "generated_at": now_iso(),
        })


def build_openapi(catalog):
    game_ids = [g["game"] for g in catalog]
    spec = {
        "openapi": "3.1.0",
        "info": {
            "title": "VietLot AI API",
            "version": "1.0.0",
            "description": "API tĩnh (JSON) cho kết quả & phân tích xổ số Vietlott. "
                           "Không auth, chỉ GET.",
        },
        "servers": [{"url": API_BASE}],
        "paths": {
            "/index.json": {"get": {
                "operationId": "getIndex",
                "summary": "Danh mục toàn bộ game & endpoint",
                "responses": {"200": {"description": "OK"}}}},
            "/jackpots.json": {"get": {
                "operationId": "getJackpots",
                "summary": "Giá trị jackpot tích lũy hiện tại",
                "responses": {"200": {"description": "OK"}}}},
            "/{game}/latest.json": {"get": {
                "operationId": "getLatest",
                "summary": "Kết quả kỳ quay mới nhất",
                "parameters": [{"name": "game", "in": "path", "required": True,
                                "schema": {"type": "string", "enum": game_ids}}],
                "responses": {"200": {"description": "OK"}}}},
            "/{game}/results.json": {"get": {
                "operationId": "getResults",
                "summary": "100 kỳ quay gần nhất",
                "parameters": [{"name": "game", "in": "path", "required": True,
                                "schema": {"type": "string", "enum": game_ids}}],
                "responses": {"200": {"description": "OK"}}}},
            "/{game}/stats.json": {"get": {
                "operationId": "getStats",
                "summary": "Phân tích thống kê (nóng/lạnh/gan/cặp/tổng...)",
                "parameters": [{"name": "game", "in": "path", "required": True,
                                "schema": {"type": "string", "enum": game_ids}}],
                "responses": {"200": {"description": "OK"}}}},
            "/{game}/predictions.json": {"get": {
                "operationId": "getPredictions",
                "summary": "Dự đoán AI công khai + độ chính xác (backtest & live)",
                "parameters": [{"name": "game", "in": "path", "required": True,
                                "schema": {"type": "string", "enum": game_ids}}],
                "responses": {"200": {"description": "OK"}}}},
        },
    }
    write_json(API / "openapi.json", spec)


def build_llms_txt(index, catalog):
    lines = [
        "# VietLot AI API",
        "",
        "> API tĩnh JSON: kết quả & phân tích thống kê xổ số Vietlott.",
        "> Không cần API key. Chỉ GET công khai, trả JSON UTF-8. CORS mở.",
        "",
        f"Base URL: {API_BASE}",
        f"Cập nhật: {index['generated_at']} (giờ VN, tự động qua GitHub Actions)",
        "",
        "## Bắt đầu",
        f"- GET {API_BASE}/index.json  → danh mục toàn bộ game & endpoint (đọc cái này trước)",
        f"- GET {API_BASE}/openapi.json → OpenAPI 3.1 spec",
        f"- GET {API_BASE}/jackpots.json → jackpot tích lũy hiện tại",
        "",
        "## Endpoint cho từng game",
        "Thay {game} bằng một trong: " + ", ".join(g["game"] for g in catalog),
        "",
        f"- GET {API_BASE}/{{game}}/latest.json   → kỳ quay mới nhất",
        f"- GET {API_BASE}/{{game}}/results.json  → 100 kỳ gần nhất",
        f"- GET {API_BASE}/{{game}}/stats.json    → phân tích (nóng/lạnh/số gan/cặp/tổng/chẵn-lẻ)",
        f"- GET {index['site']}/data/{{game}}.jsonl → toàn bộ lịch sử (JSONL)",
        "",
        "## Các game",
    ]
    for g in catalog:
        lines.append(f"- {g['game']} ({g['name']}): {g['total_draws']} kỳ, "
                     f"{g['date_range']['from']} → {g['date_range']['to']}. Lịch: {g['schedule']}")
    lines += [
        "",
        "## Lưu ý cho AI",
        "Đây là dữ liệu thống kê tham khảo. Xổ số hoàn toàn ngẫu nhiên — số",
        "'nóng/lạnh/gan' KHÔNG có giá trị dự đoán kết quả tương lai. Đừng khẳng",
        "định với người dùng rằng các con số này sẽ trúng.",
        "",
    ]
    path = API / "llms.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  ✓ {path.relative_to(ROOT)}")


if __name__ == "__main__":
    build()
