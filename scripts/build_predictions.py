#!/usr/bin/env python3
"""
VietLot AI — Public Prediction Engine (minh bạch, chống sửa)
────────────────────────────────────────────────────────────
Sinh & lưu dự đoán AI vào data/predictions.jsonl — commit qua GitHub Actions.
Ý nghĩa minh bạch:
  • Dự đoán "live" cho kỳ TỚI được tạo & commit TRƯỚC khi quay
    → lịch sử git chứng minh dự đoán có trước kết quả, không thể sửa lén.
  • Sau khi kết quả kỳ đó xuất hiện, script tự điền kết quả thật + số trúng.
  • Lần chạy đầu backtest 60 kỳ gần nhất (chỉ dùng dữ liệu CŨ hơn kỳ đích
    → không nhìn trộm tương lai) để có ngay lịch sử & thống kê độ chính xác.

Thuật toán chấm điểm port y hệt hàm predComputeScores trong index.html.
Chỉ dùng thư viện chuẩn Python. Chạy: python scripts/build_predictions.py
"""
import json
import sys
import pathlib
from datetime import datetime, timezone, timedelta

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PRED_FILE = DATA / "predictions.jsonl"
VN_TZ = timezone(timedelta(hours=7))

HISTORY_CAP = 1000   # số kỳ tối đa dùng để chấm điểm (hot chỉ cần 50; giữ nhanh)
BACKFILL = 60        # số kỳ gần nhất backtest lần đầu
MAX_PER_GAME = 400   # giữ tối đa mỗi game trong file

# key: (max, pick, hasSpec, specMax, isKeno, isMax3d, name)
ACFG = {
    "power655": dict(max=55, pick=6, hasSpec=True,  specMax=55, isKeno=False, isMax3d=False, name="Power 6/55"),
    "power645": dict(max=45, pick=6, hasSpec=False, specMax=0,  isKeno=False, isMax3d=False, name="Mega 6/45"),
    "power535": dict(max=35, pick=5, hasSpec=True,  specMax=12, isKeno=False, isMax3d=False, name="Lotto 5/35"),
    "keno":     dict(max=80, pick=20, hasSpec=False, specMax=0, isKeno=True,  isMax3d=False, name="Keno"),
    "max3d":    dict(isMax3d=True, name="Max3D"),
    "max3dpro": dict(isMax3d=True, name="Max3D Pro"),
}
FILES = {"power655": "power655.jsonl", "power645": "power645.jsonl",
         "power535": "power535.jsonl", "keno": "keno.jsonl",
         "max3d": "3d.jsonl", "max3dpro": "3d_pro.jsonl"}


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


def pad3(n):
    return str(n).zfill(3)


def adapt(rows, ac):
    """rows (mới→cũ) → list {date,id,nums,spec} hoặc {date,id,db,nhat,nhi,ba}."""
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


# ─── Scoring (port y hệt predComputeScores) ──────────────────────────────────
def compute_scores(draws, ac):
    MAX = ac["max"]
    WINDOW = min(50, len(draws))
    sc = {i: {"hot": 0.0, "gap": len(draws), "corr": 0.0} for i in range(1, MAX + 1)}

    for di in range(WINDOW):
        w = (WINDOW - di) / WINDOW
        for n in draws[di]["nums"]:
            if 1 <= n <= MAX:
                sc[n]["hot"] += w
    for i in range(1, MAX + 1):
        for di, d in enumerate(draws):
            if i in d["nums"]:
                sc[i]["gap"] = di
                break
    # correlation với bộ số kỳ trước
    chron = list(reversed(draws))
    corr = {}
    for i in range(len(chron) - 1):
        for x in chron[i]["nums"]:
            m = corr.setdefault(x, {})
            for y in chron[i + 1]["nums"]:
                m[y] = m.get(y, 0) + 1
    for ln in draws[0]["nums"]:
        for n, v in corr.get(ln, {}).items():
            if 1 <= n <= MAX:
                sc[n]["corr"] += v

    def norm(key):
        mx = max([1.0] + [sc[i][key] for i in sc])
        for i in sc:
            sc[i][key + "N"] = sc[i][key] / mx
    norm("hot"); norm("gap"); norm("corr")
    for i in sc:
        sc[i]["ai"] = 0.38 * sc[i]["hotN"] + 0.27 * sc[i]["gapN"] + 0.35 * sc[i]["corrN"]

    spec_sc = None
    if ac["hasSpec"]:
        SM = ac["specMax"]
        spec_sc = {i: {"hot": 0.0, "gap": len(draws)} for i in range(1, SM + 1)}
        for di in range(WINDOW):
            w = (WINDOW - di) / WINDOW
            s = draws[di]["spec"]
            if s is not None and 1 <= s <= SM:
                spec_sc[s]["hot"] += w
        for i in range(1, SM + 1):
            for di, d in enumerate(draws):
                if d["spec"] == i:
                    spec_sc[i]["gap"] = di
                    break

        def norms(key):
            mx = max([1.0] + [spec_sc[i][key] for i in spec_sc])
            for i in spec_sc:
                spec_sc[i][key + "N"] = spec_sc[i][key] / mx
        norms("hot"); norms("gap")
        for i in spec_sc:
            spec_sc[i]["ai"] = 0.55 * spec_sc[i]["hotN"] + 0.45 * spec_sc[i]["gapN"]
    return sc, spec_sc


def pick_top(sc, max_n, count, key):
    return sorted(range(1, max_n + 1), key=lambda n: (-sc[n][key], n))[:count]


def predict_num(hist, ac):
    """hist = danh sách kỳ (mới→cũ, đã cắt HISTORY_CAP). Trả picks + spec."""
    sc, spec_sc = compute_scores(hist, ac)
    count = 10 if ac["isKeno"] else ac["pick"]
    picks = {
        "ai":   pick_top(sc, ac["max"], count, "ai"),
        "hot":  pick_top(sc, ac["max"], count, "hot"),
        "cold": pick_top(sc, ac["max"], count, "gap"),
        "corr": pick_top(sc, ac["max"], count, "corr"),
    }
    spec = None
    if ac["hasSpec"] and spec_sc:
        spec = sorted(range(1, ac["specMax"] + 1), key=lambda n: (-spec_sc[n]["ai"], n))[0]
    return picks, spec


def predict_max3d(hist):
    freq = {}
    for d in hist:
        for n in d["db"] + d["nhat"] + d["nhi"] + d["ba"]:
            freq[n] = freq.get(n, 0) + 1
    top5 = [n for n, _ in sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))[:5]]
    return {"ai": top5, "hot": top5, "cold": [], "corr": []}, None


def match_num(picks, spec, target, ac):
    nums = set(target["nums"])
    m = {k: sum(1 for n in picks.get(k, []) if n in nums) for k in ("ai", "hot", "cold", "corr")}
    m["spec"] = (spec == target["spec"]) if (ac["hasSpec"] and spec is not None) else None
    return m


def match_max3d(picks, target):
    allnums = set(target["db"] + target["nhat"] + target["nhi"] + target["ba"])
    got = sum(1 for n in picks.get("ai", []) if n in allnums)
    return {"ai": got, "hot": got, "cold": 0, "corr": 0, "spec": None}


def result_of(target, ac):
    if ac.get("isMax3d"):
        return {"id": target["id"], "date": target["date"],
                "nums": target["db"], "allNums": target["db"] + target["nhat"] + target["nhi"] + target["ba"]}
    return {"id": target["id"], "date": target["date"], "nums": target["nums"], "spec": target["spec"]}


# ─── Build ────────────────────────────────────────────────────────────────────
def build():
    print("🔮 Building public predictions...")
    preds = load_jsonl(PRED_FILE)
    # index: (game, based_on_id) -> record
    index = {(p["game"], p["based_on_id"]): p for p in preds}

    for game, ac in ACFG.items():
        rows = load_jsonl(DATA / FILES[game])
        rows = [r for r in rows if r.get("date")]
        rows.sort(key=lambda r: (r.get("date", ""), str(r.get("id", ""))), reverse=True)
        draws = adapt(rows, ac)
        if len(draws) < 10:
            print(f"  ⚠ {game}: thiếu dữ liệu, bỏ qua")
            continue

        def make(based, target, mode, hist):
            """Tạo 1 record dự đoán (nếu chưa có). target có thể None (chưa quay)."""
            k = (game, based["id"])
            if k in index:
                return 0
            if ac.get("isMax3d"):
                picks, spec = predict_max3d(hist)
            else:
                picks, spec = predict_num(hist, ac)
            rec = {
                "game": game, "based_on_id": based["id"], "based_on_date": based["date"],
                "created_at": now_iso() if mode == "live" else None,
                "mode": mode, "picks": picks, "spec": spec,
                "result": None, "matched": None,
            }
            if target is not None:
                rec["result"] = result_of(target, ac)
                rec["matched"] = (match_max3d(picks, target) if ac.get("isMax3d")
                                  else match_num(picks, spec, target, ac))
            index[k] = rec
            preds.append(rec)
            return 1

        added_bt = 0
        # Backtest: dự đoán kỳ draws[j] dựa trên draws[j+1] (chỉ dữ liệu cũ hơn)
        for j in range(min(BACKFILL, len(draws) - 2)):
            based = draws[j + 1]
            target = draws[j]
            hist = draws[j + 1: j + 1 + HISTORY_CAP]
            if len(hist) >= 10:
                added_bt += make(based, target, "backtest", hist)

        # Live: dự đoán kỳ TỚI dựa trên kỳ mới nhất (chưa có kết quả)
        added_live = make(draws[0], None, "live", draws[:HISTORY_CAP])

        # Điền kết quả cho các record còn treo (kỳ đích nay đã xuất hiện)
        id2idx = {str(d["id"]): i for i, d in enumerate(draws)}
        filled = 0
        for p in preds:
            if p["game"] != game or p["result"] is not None:
                continue
            i = id2idx.get(str(p["based_on_id"]))
            if i is not None and i > 0:      # kỳ liền sau nằm ngay trước trong mảng
                target = draws[i - 1]
                p["result"] = result_of(target, ac)
                p["matched"] = (match_max3d(p["picks"], target) if ac.get("isMax3d")
                                else match_num(p["picks"], p.get("spec"), target, ac))
                filled += 1
        print(f"  ✓ {game}: +{added_bt} backtest, +{added_live} live, điền {filled} kết quả")

    # Giới hạn mỗi game, sắp xếp mới→cũ theo based_on_id
    by_game = {}
    for p in preds:
        by_game.setdefault(p["game"], []).append(p)
    out = []
    for g, lst in by_game.items():
        lst.sort(key=lambda p: str(p["based_on_id"]), reverse=True)
        out.extend(lst[:MAX_PER_GAME])
    out.sort(key=lambda p: (p["game"], str(p["based_on_id"])), reverse=True)

    with PRED_FILE.open("w", encoding="utf-8") as f:
        for p in out:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(f"✅ Đã lưu {len(out)} dự đoán → {PRED_FILE.relative_to(ROOT)}")


if __name__ == "__main__":
    build()
