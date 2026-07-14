#!/usr/bin/env python3
"""
VietLot AI — Trình tạo Bài Viết Phân Tích + Dự Đoán (server-side, dùng Gemini)
──────────────────────────────────────────────────────────────────────────────
Đọc dữ liệu thống kê (data/*.jsonl) + dự đoán công khai (data/predictions.jsonl),
tính NHIỀU góc phân tích (nóng/lạnh, streak liên tiếp, cặp/bộ 3 số đồng hành,
tương quan dự báo kỳ sau, tương quan Số Phụ/Số Cam) rồi "ném" cho Google Gemini
viết một BÀI PHÂN TÍCH CHUYÊN SÂU, KẾT THÚC bằng phần DỰ ĐOÁN kỳ tới.

Tiêu đề bài: "Dự đoán kết quả {tên loại} ngày dd-mm-yyyy" (ngày kỳ quay kế tiếp).

Nguyên tắc "khi nào viết bài mới?":
  • Mỗi bài gắn với KỲ QUAY MỚI NHẤT của từng loại (based_on_id).
  • Đã có bài (cùng schema_version) cho kỳ đó → BỎ QUA (không gọi Gemini).
  • Đổi SCHEMA_VERSION → bài cũ tự được viết lại theo format mới.

API key lấy từ biến môi trường GEMINI_API_KEY (GitHub Secret) → KHÔNG lộ.
Không có key → script bỏ qua êm, workflow vẫn chạy bình thường.
Phạm vi: tất cả loại TRỪ Keno. Chỉ dùng requests. Chạy: python scripts/build_articles.py
"""
import json
import os
import sys
import pathlib
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta, date

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ART_FILE = DATA / "articles.jsonl"
PRED_FILE = DATA / "predictions.jsonl"
VN_TZ = timezone(timedelta(hours=7))

API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"

SCHEMA_VERSION = 2    # bump để buộc viết lại toàn bộ bài theo format mới
FREQ_WINDOW = 150     # số kỳ gần nhất tính tần suất nóng/lạnh/số phụ
MAX_PER_GAME = 60     # giữ tối đa mỗi game trong file
DISCLAIMER = ("Xổ số hoàn toàn ngẫu nhiên — không AI hay hệ thống nào dự đoán chắc chắn được kết quả. "
              "Mọi con số chỉ mang tính thống kê, tham khảo, giải trí. Chơi có trách nhiệm.")

# key -> cấu hình (BỎ Keno)
ACFG = {
    "power655": dict(max=55, pick=6, hasSpec=True,  specMax=55, specName="Số Phụ", isMax3d=False, name="Power 6/55"),
    "power645": dict(max=45, pick=6, hasSpec=False, specMax=0,  specName="",        isMax3d=False, name="Mega 6/45"),
    "power535": dict(max=35, pick=5, hasSpec=True,  specMax=12, specName="Số Cam",  isMax3d=False, name="Lotto 5/35"),
    "max3d":    dict(isMax3d=True, name="Max3D"),
    "max3dpro": dict(isMax3d=True, name="Max3D Pro"),
}
FILES = {"power655": "power655.jsonl", "power645": "power645.jsonl",
         "power535": "power535.jsonl", "max3d": "3d.jsonl", "max3dpro": "3d_pro.jsonl"}

# Lịch quay (Python weekday: Mon=0 … Sun=6) → tính ngày kỳ kế tiếp cho tiêu đề
DRAW_WEEKDAYS = {
    "power655": {1, 3, 5},          # Thứ 3, 5, 7
    "power645": {2, 4, 6},          # Thứ 4, 6, CN
    "power535": set(range(7)),      # Hàng ngày
    "max3d":    {0, 2, 4},          # Thứ 2, 4, 6
    "max3dpro": {1, 3, 5},          # Thứ 3, 5, 7
}
VN_MONTHS = None  # (không dùng — giữ chỗ)


def now_iso():
    return datetime.now(VN_TZ).replace(microsecond=0).isoformat()


def load_jsonl(path):
    rows = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return rows


def pad2(n):
    return str(n).zfill(2)


def pad3(n):
    return str(n).zfill(3)


def adapt(rows, ac):
    out = []
    if ac.get("isMax3d"):
        for r in rows:
            res = r.get("result") or {}
            if not isinstance(res, dict):
                continue
            db = [pad3(n) for n in res.get("Giải Đặc biệt", [])]
            if not db:
                continue
            out.append({
                "date": r.get("date"), "id": r.get("id"), "db": db,
                "nhat": [pad3(n) for n in res.get("Giải Nhất", [])],
                "nhi":  [pad3(n) for n in res.get("Giải Nhì", [])],
                "ba":   [pad3(n) for n in (res.get("Giải Ba") or res.get("Giải ba") or [])],
            })
        return out
    pick = ac["pick"]
    for r in rows:
        res = r.get("result")
        if not isinstance(res, list):
            continue
        nums = res[:pick] if ac["hasSpec"] else list(res)
        spec = res[pick] if (ac["hasSpec"] and len(res) > pick) else None
        out.append({"date": r.get("date"), "id": r.get("id"), "nums": nums, "spec": spec})
    return out


def next_draw_date_str(based_on_date, game):
    try:
        d = date.fromisoformat(based_on_date)
    except Exception:
        return None
    wd = DRAW_WEEKDAYS.get(game, set(range(7)))
    nd = None
    for i in range(1, 8):
        cand = d + timedelta(days=i)
        if cand.weekday() in wd:
            nd = cand
            break
    if nd is None:
        nd = d + timedelta(days=1)
    return nd.strftime("%d-%m-%Y")


# ─── Các phân tích ───────────────────────────────────────────────────────────
def compute_streaks(draws, MAXN):
    """hot = số kỳ liên tiếp gần nhất CÓ mặt; cold = liên tiếp gần nhất VẮNG."""
    hot, cold = {}, {}
    for n in range(1, MAXN + 1):
        h = c = 0
        fh = fc = False
        for d in draws:
            hit = n in d["nums"]
            if not fh:
                if hit:
                    h += 1
                else:
                    fh = True
            if not fc:
                if not hit:
                    c += 1
                else:
                    fc = True
            if fh and fc:
                break
        hot[n] = h
        cold[n] = c
    hl = [(n, s) for n, s in sorted(hot.items(), key=lambda kv: (-kv[1], kv[0]))[:8] if s > 0]
    cl = [(n, s) for n, s in sorted(cold.items(), key=lambda kv: (-kv[1], kv[0]))[:8] if s > 0]
    return hl, cl


def compute_pairs(draws, MAXN, k, topn):
    cnt = Counter()
    for d in draws:
        ns = sorted(x for x in d["nums"] if 1 <= x <= MAXN)
        L = len(ns)
        if k == 2:
            for i in range(L):
                for j in range(i + 1, L):
                    cnt[(ns[i], ns[j])] += 1
        else:
            for i in range(L):
                for j in range(i + 1, L):
                    for l in range(j + 1, L):
                        cnt[(ns[i], ns[j], ns[l])] += 1
    return cnt.most_common(topn)


def compute_next_corr(draws, MAXN):
    """corr[x][y] = số lần: x xuất hiện kỳ này → y xuất hiện kỳ ngay sau."""
    chron = list(reversed(draws))
    corr = defaultdict(Counter)
    for i in range(len(chron) - 1):
        for x in chron[i]["nums"]:
            for y in chron[i + 1]["nums"]:
                if 1 <= y <= MAXN:
                    corr[x][y] += 1
    return corr


def next_draw_forecast(draws, MAXN):
    """Từ bộ số kỳ mới nhất → tổng hợp số được tương quan ưu ái cho kỳ sau."""
    corr = compute_next_corr(draws, MAXN)
    latest = draws[0]["nums"]
    agg = Counter()
    for tn in latest:
        for y, c in corr.get(tn, {}).items():
            agg[y] += c
    top = agg.most_common(10)
    # ví dụ minh hoạ: 3 số "dẫn dắt" mạnh nhất trong kỳ mới nhất
    trig = sorted(latest, key=lambda tn: -sum(corr.get(tn, {}).values()))[:3]
    examples = []
    for tn in trig:
        foll = corr.get(tn, Counter()).most_common(4)
        tot = sum(corr.get(tn, {}).values()) or 1
        examples.append((tn, [(y, round(c / tot * 100)) for y, c in foll]))
    return top, examples


def spec_corr_forecast(draws):
    """Số Phụ/Số Cam kỳ mới nhất → các số chính kỳ sau thường kèm theo."""
    chron = list(reversed(draws))
    corr = defaultdict(Counter)
    for i in range(len(chron) - 1):
        x = chron[i].get("spec")
        if x is None:
            continue
        for y in chron[i + 1]["nums"]:
            corr[x][y] += 1
    sv = draws[0].get("spec")
    if sv is None or sv not in corr:
        return sv, []
    tot = sum(corr[sv].values()) or 1
    top = [(y, round(c / tot * 100)) for y, c in corr[sv].most_common(8)]
    return sv, top


def compute_stats_num(draws, ac):
    MAXN = ac["max"]
    latest = draws[0]
    win = draws[:FREQ_WINDOW]

    freq = Counter()
    for d in win:
        for n in d["nums"]:
            if 1 <= n <= MAXN:
                freq[n] += 1
    hot = sorted(((n, freq.get(n, 0)) for n in range(1, MAXN + 1)),
                 key=lambda x: (-x[1], x[0]))[:10]

    gap = {}
    for n in range(1, MAXN + 1):
        gap[n] = len(draws)
        for i, d in enumerate(draws):
            if n in d["nums"]:
                gap[n] = i
                break
    cold = [(n, gap[n]) for n in sorted(range(1, MAXN + 1), key=lambda n: (-gap[n], n))[:10]]

    hot_streak, cold_streak = compute_streaks(draws, MAXN)
    pairs2 = compute_pairs(draws, MAXN, 2, 10)
    pairs3 = compute_pairs(draws, MAXN, 3, 6)
    nd_top, nd_examples = next_draw_forecast(draws, MAXN)

    spec_hot, spec_val, spec_top = [], None, []
    if ac["hasSpec"]:
        sc = Counter()
        for d in win:
            s = d.get("spec")
            if s is not None and 1 <= s <= ac["specMax"]:
                sc[s] += 1
        spec_hot = sorted(((i, sc.get(i, 0)) for i in range(1, ac["specMax"] + 1)),
                          key=lambda x: (-x[1], x[0]))[:6]
        spec_val, spec_top = spec_corr_forecast(draws)

    return {
        "total_draws": len(draws), "window": len(win),
        "latest": {"id": latest["id"], "date": latest["date"],
                   "nums": latest["nums"], "spec": latest.get("spec")},
        "hot": hot, "cold": cold,
        "hot_streak": hot_streak, "cold_streak": cold_streak,
        "pairs2": [([a, b], c) for (a, b), c in pairs2],
        "pairs3": [([a, b, c2], c) for (a, b, c2), c in pairs3],
        "nd_top": nd_top, "nd_examples": nd_examples,
        "spec_hot": spec_hot, "spec_val": spec_val, "spec_top": spec_top,
    }


def compute_stats_max3d(draws, ac):
    latest = draws[0]
    win = draws[:FREQ_WINDOW]
    freq = Counter()
    for d in win:
        for n in d["db"] + d["nhat"] + d["nhi"] + d["ba"]:
            freq[n] += 1
    hot = freq.most_common(12)
    # tần suất chữ số theo vị trí trên giải Đặc Biệt
    pos = [Counter(), Counter(), Counter()]
    for d in win:
        for s in d["db"]:
            if len(s) == 3:
                for p in range(3):
                    pos[p][s[p]] += 1
    pos_top = [[(dig, c) for dig, c in pos[p].most_common(3)] for p in range(3)]
    return {
        "total_draws": len(draws), "window": len(win),
        "latest": {"id": latest["id"], "date": latest["date"], "db": latest["db"]},
        "hot": [(n, c) for n, c in hot], "pos_top": pos_top,
    }


def latest_prediction(game):
    preds = [p for p in load_jsonl(PRED_FILE) if p.get("game") == game]
    if not preds:
        return None
    live = [p for p in preds if not p.get("result")]
    pool = live or preds
    pool.sort(key=lambda p: str(p.get("based_on_id")), reverse=True)
    p = pool[0]
    return {"picks": p.get("picks"), "spec": p.get("spec"), "based_on_id": p.get("based_on_id")}


# ─── Prompt & gọi Gemini ──────────────────────────────────────────────────────
def build_prompt(game, ac, stats, pred, title, draw_date):
    name = ac["name"]
    L = [
        "Bạn là cây bút phân tích thống kê xổ số cho website VietLot AI.",
        f"Viết một BÀI PHÂN TÍCH CHUYÊN SÂU (900–1500 từ) bằng tiếng Việt, định dạng Markdown, về **{name}**,",
        "dựa HOÀN TOÀN trên DỮ LIỆU THẬT bên dưới. Trọng tâm là PHÂN TÍCH ĐA CHIỀU, không chỉ nóng/lạnh.",
        "",
        "YÊU CẦU BẮT BUỘC:",
        f"- Dòng đầu tiên PHẢI là tiêu đề Markdown chính xác: `# {title}`",
        "- Viết mạch lạc, cuốn hút như bài blog; mỗi góc phân tích một mục `##` riêng, diễn giải Ý NGHĨA con số.",
        "- Khai thác NHIỀU góc: số nóng/lạnh, streak (đang ra/vắng liên tiếp), cặp số & bộ 3 đồng hành, "
        "tương quan dự báo kỳ sau" + (f", tương quan {ac.get('specName')}" if ac.get("hasSpec") else "") + ".",
        "- Dùng số liệu cụ thể (tần suất, số kỳ, %) để lập luận; TUYỆT ĐỐI không bịa số ngoài dữ liệu.",
        f"- KẾT THÚC bằng mục `## 🎯 Dự đoán kết quả {name} ngày {draw_date}`: nêu rõ bộ số dự đoán (dùng gợi ý AI cho sẵn), "
        "giải thích ngắn vì sao dựa trên các phân tích ở trên.",
        f"- Ngay sau phần dự đoán, thêm mục `## ⚠️ Lưu ý` ghi rõ: {DISCLAIMER}",
        "- Giọng khách quan, KHÔNG hứa trúng thưởng, KHÔNG xúi giục đánh nhiều. Chỉ trả về Markdown của bài, không thêm gì khác.",
        "",
        "DỮ LIỆU:",
        f"- Loại: {name} | Tổng số kỳ lịch sử: {stats['total_draws']} | Cửa sổ tần suất: {stats['window']} kỳ gần nhất",
    ]
    lt = stats["latest"]
    if ac.get("isMax3d"):
        L.append(f"- Kỳ mới nhất #{lt['id']} ({lt['date']}) — giải Đặc Biệt: {', '.join(lt['db'])}")
        L.append("- Bộ 3 chữ số xuất hiện nhiều nhất (số:lần): "
                 + ", ".join(f"{n}:{c}" for n, c in stats["hot"]))
        names = ["hàng trăm", "hàng chục", "hàng đơn vị"]
        for p in range(3):
            L.append(f"- Chữ số hay về ở {names[p]} (giải ĐB) (digit:lần): "
                     + ", ".join(f"{dig}:{c}" for dig, c in stats["pos_top"][p]))
    else:
        spec_txt = f", {ac['specName']}: {pad2(lt['spec'])}" if (ac["hasSpec"] and lt.get("spec") is not None) else ""
        L.append(f"- Kỳ mới nhất #{lt['id']} ({lt['date']}) — dãy số: "
                 + ", ".join(pad2(n) for n in lt["nums"]) + spec_txt)
        L.append("- Số NÓNG (số:lần): " + ", ".join(f"{pad2(n)}:{c}" for n, c in stats["hot"]))
        L.append("- Số LẠNH/gan (số:kỳ vắng): " + ", ".join(f"{pad2(n)}:{g}" for n, g in stats["cold"]))
        if stats["hot_streak"]:
            L.append("- Đang RA liên tiếp (số:kỳ): " + ", ".join(f"{pad2(n)}:{s}" for n, s in stats["hot_streak"]))
        if stats["cold_streak"]:
            L.append("- Đang VẮNG liên tiếp (số:kỳ): " + ", ".join(f"{pad2(n)}:{s}" for n, s in stats["cold_streak"]))
        if stats["pairs2"]:
            L.append("- Cặp 2 số hay về cùng kỳ (cặp:lần): "
                     + ", ".join(f"{pad2(a)}-{pad2(b)}:{c}" for (a, b), c in stats["pairs2"]))
        if stats["pairs3"]:
            L.append("- Bộ 3 số hay về cùng kỳ (bộ:lần): "
                     + ", ".join(f"{pad2(a)}-{pad2(b)}-{pad2(c2)}:{c}" for (a, b, c2), c in stats["pairs3"]))
        if stats["nd_top"]:
            L.append("- Tương quan DỰ BÁO KỲ SAU — từ bộ số kỳ mới nhất, số hay theo sau (số:điểm tương quan): "
                     + ", ".join(f"{pad2(n)}:{c}" for n, c in stats["nd_top"]))
        for tn, foll in stats["nd_examples"]:
            if foll:
                L.append(f"  · Số {pad2(tn)} kỳ trước → kỳ sau thường có: "
                         + ", ".join(f"{pad2(y)}({p}%)" for y, p in foll))
        if ac["hasSpec"] and stats["spec_hot"]:
            L.append(f"- {ac['specName']} NÓNG (số:lần): " + ", ".join(f"{pad2(n)}:{c}" for n, c in stats["spec_hot"]))
        if ac["hasSpec"] and stats["spec_val"] is not None and stats["spec_top"]:
            L.append(f"- Tương quan {ac['specName']}={pad2(stats['spec_val'])} (kỳ mới nhất) → số chính kỳ sau thường có (số:%): "
                     + ", ".join(f"{pad2(y)}({p}%)" for y, p in stats["spec_top"]))

    if pred and pred.get("picks"):
        ai = pred["picks"].get("ai") or []
        if ac.get("isMax3d"):
            L.append("- GỢI Ý AI cho kỳ tới (dùng cho phần dự đoán, top bộ số): " + ", ".join(str(x) for x in ai))
        else:
            sp = f", {ac['specName']} gợi ý: {pad2(pred.get('spec'))}" if (ac["hasSpec"] and pred.get("spec")) else ""
            L.append("- GỢI Ý AI cho kỳ tới (dùng cho phần dự đoán): " + ", ".join(pad2(n) for n in ai) + sp)
    return "\n".join(L)


def call_gemini(prompt):
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.9,
            "maxOutputTokens": 8192,
            # gemini-2.5-* bật "thinking" mặc định → ngốn hết output token, cắt cụt bài.
            # Bài viết sáng tạo không cần suy luận nội bộ → tắt để dồn token cho nội dung.
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    r = requests.post(API_URL, params={"key": API_KEY}, json=body, timeout=120)
    if r.status_code != 200:
        raise RuntimeError(f"Gemini HTTP {r.status_code}: {r.text[:300]}")
    data = r.json()
    cands = data.get("candidates") or []
    if not cands:
        raise RuntimeError(f"Gemini không trả candidate: {json.dumps(data)[:300]}")
    parts = cands[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        raise RuntimeError("Gemini trả nội dung rỗng")
    return text


# ─── Build ────────────────────────────────────────────────────────────────────
def build():
    print(f"📝 Building articles (model={MODEL}, schema=v{SCHEMA_VERSION})...")
    if not API_KEY:
        print("⚠ Không có GEMINI_API_KEY — bỏ qua tạo bài viết (workflow vẫn OK).")
        return

    arts = load_jsonl(ART_FILE)
    index = {(a["game"], str(a["based_on_id"])): a for a in arts}
    added = 0

    for game, ac in ACFG.items():
        rows = load_jsonl(DATA / FILES[game])
        rows = [r for r in rows if r.get("date")]
        rows.sort(key=lambda r: (r.get("date", ""), str(r.get("id", ""))), reverse=True)
        draws = adapt(rows, ac)
        if len(draws) < 10:
            print(f"  ⚠ {game}: thiếu dữ liệu, bỏ qua")
            continue

        latest_id = str(draws[0]["id"])
        prev = index.get((game, latest_id))
        if prev and prev.get("schema_version") == SCHEMA_VERSION:
            print(f"  ⏭ {game}: đã có bài (v{SCHEMA_VERSION}) cho kỳ #{latest_id}")
            continue

        draw_date = next_draw_date_str(draws[0]["date"], game) or fmt_ddmmyyyy(draws[0]["date"])
        title = f"Dự đoán kết quả {ac['name']} ngày {draw_date}"
        stats = (compute_stats_max3d(draws, ac) if ac.get("isMax3d") else compute_stats_num(draws, ac))
        pred = latest_prediction(game)
        prompt = build_prompt(game, ac, stats, pred, title, draw_date)

        try:
            content = call_gemini(prompt)
        except Exception as e:
            print(f"  ✗ {game}: lỗi gọi Gemini — {e}")
            continue

        rec = {
            "game": game, "based_on_id": draws[0]["id"], "based_on_date": draws[0]["date"],
            "draw_date": draw_date, "created_at": now_iso(), "model": MODEL,
            "schema_version": SCHEMA_VERSION, "title": title, "content": content,
        }
        index[(game, latest_id)] = rec
        added += 1
        verb = "viết lại" if prev else "tạo"
        print(f"  ✓ {game}: {verb} bài cho kỳ #{latest_id} → \"{title}\" ({len(content)} ký tự)")

    if not added:
        print("✅ Không có kỳ mới → không tạo bài nào.")
        return

    # Giới hạn mỗi game, sắp xếp mới→cũ
    by_game = defaultdict(list)
    for a in index.values():
        by_game[a["game"]].append(a)
    out = []
    for g, lst in by_game.items():
        lst.sort(key=lambda a: str(a["based_on_id"]), reverse=True)
        out.extend(lst[:MAX_PER_GAME])
    out.sort(key=lambda a: (a["game"], str(a["based_on_id"])), reverse=True)

    with ART_FILE.open("w", encoding="utf-8") as f:
        for a in out:
            f.write(json.dumps(a, ensure_ascii=False) + "\n")
    print(f"✅ Đã lưu {len(out)} bài viết (+{added} mới/viết lại) → {ART_FILE.relative_to(ROOT)}")


def fmt_ddmmyyyy(s):
    try:
        y, m, d = s.split("-")
        return f"{d}-{m}-{y}"
    except Exception:
        return s


if __name__ == "__main__":
    build()
