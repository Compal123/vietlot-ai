#!/usr/bin/env python3
"""
VietLot AI — Trình tạo Bài Viết Phân Tích (server-side, dùng Gemini)
────────────────────────────────────────────────────────────────────
Đọc dữ liệu thống kê đã có (data/*.jsonl) + dự đoán công khai
(data/predictions.jsonl), tính các chỉ số phân tích rồi "ném" cho
Google Gemini để viết một bài phân tích chuyên sâu. Kết quả lưu vào
data/articles.jsonl và được commit qua GitHub Actions.

Nguyên tắc "khi nào viết bài mới?":
  • Mỗi bài gắn với KỲ QUAY MỚI NHẤT của từng loại (based_on_id).
  • Nếu đã có bài cho kỳ đó rồi → BỎ QUA (không gọi Gemini, không tốn quota).
  • Chỉ khi xuất hiện kỳ mới (id mới) mới sinh 1 bài viết mới.

API key lấy từ biến môi trường GEMINI_API_KEY (GitHub Secret) → KHÔNG lộ.
Không có key → script bỏ qua êm, workflow vẫn chạy bình thường.

Phạm vi: tất cả loại TRỪ Keno (Keno quay quá dày, không hợp bài viết).
Chỉ dùng requests (đã có trong requirements.txt). Chạy: python scripts/build_articles.py
"""
import json
import os
import sys
import pathlib
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta

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

FREQ_WINDOW = 120     # số kỳ gần nhất dùng tính tần suất nóng/lạnh
PAIR_WINDOW = 200     # số kỳ gần nhất dùng tính cặp số
MAX_PER_GAME = 60     # giữ tối đa mỗi game trong file
DISCLAIMER = ("Xổ số hoàn toàn ngẫu nhiên — không AI hay hệ thống nào dự đoán được kết quả. "
              "Bài viết chỉ mang tính thống kê, giải trí, tham khảo.")

# key -> cấu hình (khớp getACFG / ACFG bên các file khác), BỎ Keno
ACFG = {
    "power655": dict(max=55, pick=6, hasSpec=True,  specMax=55, specName="Số Phụ", isMax3d=False, name="Power 6/55"),
    "power645": dict(max=45, pick=6, hasSpec=False, specMax=0,  specName="",        isMax3d=False, name="Mega 6/45"),
    "power535": dict(max=35, pick=5, hasSpec=True,  specMax=12, specName="Số Cam",  isMax3d=False, name="Lotto 5/35"),
    "max3d":    dict(isMax3d=True, name="Max3D"),
    "max3dpro": dict(isMax3d=True, name="Max3D Pro"),
}
FILES = {"power655": "power655.jsonl", "power645": "power645.jsonl",
         "power535": "power535.jsonl", "max3d": "3d.jsonl", "max3dpro": "3d_pro.jsonl"}


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
    """rows (mới→cũ) → list chuẩn hoá."""
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


# ─── Tính chỉ số phân tích (rút gọn để đưa cho Gemini) ────────────────────────
def compute_stats_num(draws, ac):
    MAXN = ac["max"]
    latest = draws[0]
    win = draws[:FREQ_WINDOW]

    freq = Counter()
    for d in win:
        for n in d["nums"]:
            if 1 <= n <= MAXN:
                freq[n] += 1
    all_nums = [(n, freq.get(n, 0)) for n in range(1, MAXN + 1)]
    hot = sorted(all_nums, key=lambda x: (-x[1], x[0]))[:10]

    # gap = số kỳ kể từ lần gần nhất số xuất hiện (0 = có trong kỳ mới nhất)
    gap = {}
    for n in range(1, MAXN + 1):
        gap[n] = None
        for i, d in enumerate(draws):
            if n in d["nums"]:
                gap[n] = i
                break
        if gap[n] is None:
            gap[n] = len(draws)
    cold = sorted(range(1, MAXN + 1), key=lambda n: (-gap[n], n))[:10]
    cold = [(n, gap[n]) for n in cold]

    # streak nóng: số xuất hiện trong nhiều kỳ MỚI NHẤT liên tiếp
    streak = {}
    for n in range(1, MAXN + 1):
        c = 0
        for d in draws:
            if n in d["nums"]:
                c += 1
            else:
                break
        streak[n] = c
    hot_streak = sorted([(n, s) for n, s in streak.items() if s >= 2],
                        key=lambda x: (-x[1], x[0]))[:8]

    # cặp số đồng hành (trong PAIR_WINDOW kỳ)
    pair_cnt = Counter()
    for d in draws[:PAIR_WINDOW]:
        ns = sorted(x for x in d["nums"] if 1 <= x <= MAXN)
        for i in range(len(ns)):
            for j in range(i + 1, len(ns)):
                pair_cnt[(ns[i], ns[j])] += 1
    top_pairs = pair_cnt.most_common(8)

    spec_hot = []
    if ac["hasSpec"]:
        sc = Counter()
        for d in win:
            s = d.get("spec")
            if s is not None and 1 <= s <= ac["specMax"]:
                sc[s] += 1
        spec_hot = sorted([(i, sc.get(i, 0)) for i in range(1, ac["specMax"] + 1)],
                          key=lambda x: (-x[1], x[0]))[:6]

    return {
        "total_draws": len(draws),
        "window": len(win),
        "latest": {"id": latest["id"], "date": latest["date"],
                   "nums": latest["nums"], "spec": latest.get("spec")},
        "hot": hot, "cold": cold, "hot_streak": hot_streak,
        "top_pairs": [([a, b], c) for (a, b), c in top_pairs],
        "spec_hot": spec_hot,
    }


def compute_stats_max3d(draws, ac):
    latest = draws[0]
    win = draws[:FREQ_WINDOW]
    freq = Counter()
    for d in win:
        for n in d["db"] + d["nhat"] + d["nhi"] + d["ba"]:
            freq[n] += 1
    hot = freq.most_common(12)
    return {
        "total_draws": len(draws),
        "window": len(win),
        "latest": {"id": latest["id"], "date": latest["date"], "db": latest["db"]},
        "hot": [(n, c) for n, c in hot],
    }


def latest_prediction(game):
    """Lấy dự đoán 'live' (kỳ tới) mới nhất từ predictions.jsonl."""
    preds = [p for p in load_jsonl(PRED_FILE) if p.get("game") == game]
    if not preds:
        return None
    live = [p for p in preds if not p.get("result")]
    pool = live or preds
    pool.sort(key=lambda p: str(p.get("based_on_id")), reverse=True)
    p = pool[0]
    return {"picks": p.get("picks"), "spec": p.get("spec"),
            "based_on_id": p.get("based_on_id")}


# ─── Prompt & gọi Gemini ──────────────────────────────────────────────────────
def build_prompt(game, ac, stats, pred):
    name = ac["name"]
    lines = [
        f"Bạn là một cây bút chuyên phân tích thống kê xổ số cho website VietLot AI.",
        f"Hãy viết một BÀI VIẾT PHÂN TÍCH CHUYÊN SÂU (khoảng 800–1400 từ) bằng tiếng Việt,",
        f"định dạng Markdown, về loại xổ số **{name}**, dựa TRÊN DỮ LIỆU THẬT bên dưới.",
        "",
        "YÊU CẦU:",
        "- Viết tự nhiên, cuốn hút, mạch lạc như một bài blog phân tích (KHÔNG liệt kê khô khan).",
        "- Bắt đầu bằng tiêu đề Markdown `#` hấp dẫn, rồi các mục `##` rõ ràng.",
        "- Bám sát và diễn giải Ý NGHĨA các con số: kỳ mới nhất, số nóng/lạnh, streak, cặp số đồng hành, xu hướng.",
        "- Có một mục nhận định về gợi ý AI cho kỳ tới (nếu có dữ liệu dự đoán).",
        "- Chèn dữ liệu cụ thể (số kỳ, con số, tần suất) để bài đáng tin, KHÔNG bịa số ngoài dữ liệu.",
        "- Giọng văn khách quan, trung lập, KHÔNG hứa hẹn trúng thưởng, KHÔNG xúi giục đánh nhiều.",
        f"- KẾT THÚC bằng một mục `## Lưu ý` nhắc rõ: {DISCLAIMER}",
        "- Chỉ trả về nội dung bài viết Markdown, KHÔNG thêm lời dẫn hay giải thích ngoài bài.",
        "",
        "DỮ LIỆU:",
        f"- Loại: {name}",
        f"- Tổng số kỳ trong lịch sử: {stats['total_draws']}",
        f"- Cửa sổ thống kê tần suất: {stats['window']} kỳ gần nhất",
    ]
    lt = stats["latest"]
    if ac.get("isMax3d"):
        lines.append(f"- Kỳ mới nhất: #{lt['id']} ngày {lt['date']}, giải Đặc Biệt: {', '.join(lt['db'])}")
        lines.append("- Bộ số 3 chữ số xuất hiện nhiều nhất (số:lần): "
                     + ", ".join(f"{n}:{c}" for n, c in stats["hot"]))
    else:
        spec_txt = f", {ac['specName']}: {lt['spec']}" if ac["hasSpec"] and lt.get("spec") is not None else ""
        lines.append(f"- Kỳ mới nhất: #{lt['id']} ngày {lt['date']}, dãy số: "
                     + ", ".join(pad2(n) for n in lt["nums"]) + spec_txt)
        lines.append("- Số NÓNG nhất (số:lần xuất hiện): "
                     + ", ".join(f"{pad2(n)}:{c}" for n, c in stats["hot"]))
        lines.append("- Số LẠNH nhất (số:số kỳ vắng mặt): "
                     + ", ".join(f"{pad2(n)}:{g}" for n, g in stats["cold"]))
        if stats["hot_streak"]:
            lines.append("- Số đang ra liên tiếp (số:số kỳ liên tiếp): "
                         + ", ".join(f"{pad2(n)}:{s}" for n, s in stats["hot_streak"]))
        if stats["top_pairs"]:
            lines.append("- Cặp số hay về cùng nhau (cặp:lần): "
                         + ", ".join(f"{pad2(a)}-{pad2(b)}:{c}" for (a, b), c in stats["top_pairs"]))
        if stats["spec_hot"]:
            lines.append(f"- {ac['specName']} nóng (số:lần): "
                         + ", ".join(f"{pad2(n)}:{c}" for n, c in stats["spec_hot"]))
    if pred and pred.get("picks"):
        ai = pred["picks"].get("ai") or []
        if ac.get("isMax3d"):
            lines.append("- Gợi ý AI cho kỳ tới (top bộ số): " + ", ".join(str(x) for x in ai))
        else:
            sp = f", {ac['specName']} gợi ý: {pred.get('spec')}" if ac["hasSpec"] and pred.get("spec") else ""
            lines.append("- Gợi ý AI cho kỳ tới: " + ", ".join(pad2(n) for n in ai) + sp)
    return "\n".join(lines)


def call_gemini(prompt):
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.9, "maxOutputTokens": 4096},
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


def extract_title(md):
    for line in md.splitlines():
        line = line.strip()
        if line.startswith("#"):
            return line.lstrip("#").strip()
    return None


# ─── Build ────────────────────────────────────────────────────────────────────
def build():
    print(f"📝 Building articles (model={MODEL})...")
    if not API_KEY:
        print("⚠ Không có GEMINI_API_KEY — bỏ qua tạo bài viết (workflow vẫn OK).")
        return

    arts = load_jsonl(ART_FILE)
    existing = {(a["game"], str(a["based_on_id"])) for a in arts}
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
        if (game, latest_id) in existing:
            print(f"  ⏭ {game}: đã có bài cho kỳ #{latest_id}")
            continue

        stats = (compute_stats_max3d(draws, ac) if ac.get("isMax3d")
                 else compute_stats_num(draws, ac))
        pred = latest_prediction(game)
        prompt = build_prompt(game, ac, stats, pred)

        try:
            content = call_gemini(prompt)
        except Exception as e:
            print(f"  ✗ {game}: lỗi gọi Gemini — {e}")
            continue

        rec = {
            "game": game,
            "based_on_id": draws[0]["id"],
            "based_on_date": draws[0]["date"],
            "created_at": now_iso(),
            "model": MODEL,
            "title": extract_title(content) or f"Phân tích {ac['name']} kỳ #{latest_id}",
            "content": content,
        }
        arts.append(rec)
        existing.add((game, latest_id))
        added += 1
        print(f"  ✓ {game}: đã tạo bài cho kỳ #{latest_id} ({len(content)} ký tự)")

    if not added:
        print("✅ Không có kỳ mới → không tạo bài nào.")
        return

    # Giới hạn mỗi game, sắp xếp mới→cũ
    by_game = defaultdict(list)
    for a in arts:
        by_game[a["game"]].append(a)
    out = []
    for g, lst in by_game.items():
        lst.sort(key=lambda a: str(a["based_on_id"]), reverse=True)
        out.extend(lst[:MAX_PER_GAME])
    out.sort(key=lambda a: (a["game"], str(a["based_on_id"])), reverse=True)

    with ART_FILE.open("w", encoding="utf-8") as f:
        for a in out:
            f.write(json.dumps(a, ensure_ascii=False) + "\n")
    print(f"✅ Đã lưu {len(out)} bài viết (+{added} mới) → {ART_FILE.relative_to(ROOT)}")


if __name__ == "__main__":
    build()
