#!/usr/bin/env python3
"""
Bootstrap: Tải dữ liệu lịch sử từ vietvudanh/vietlott-data
và merge vào data/ của dự án này.

Chạy 1 lần để có dữ liệu ban đầu.
"""
import json, pathlib, sys, time
try:
    import requests
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "requests"])
    import requests

DATA = pathlib.Path("data")
DATA.mkdir(exist_ok=True)

SRC  = "https://raw.githubusercontent.com/vietvudanh/vietlott-data/master/data/"

# Mapping: tên file nguồn → tên file đích của chúng ta
# vietvudanh dùng: 3d.jsonl, 3d_pro.jsonl (KHÔNG phải max3d/max3dpro)
FILE_MAP = [
    ("power655.jsonl",  "power655.jsonl"),
    ("power645.jsonl",  "power645.jsonl"),
    ("power535.jsonl",  "power535.jsonl"),
    ("3d.jsonl",        "3d.jsonl"),       # ← FIX: max3d.jsonl không tồn tại
    ("3d_pro.jsonl",    "3d_pro.jsonl"),   # ← FIX: max3dpro.jsonl không tồn tại
    ("keno.jsonl",      "keno.jsonl"),
    ("bingo18.jsonl",   "bingo18.jsonl"),
]

def load_local(fname):
    """Load JSONL hiện tại, trả về dict keyed by id."""
    p = DATA / fname
    db = {}
    if p.exists():
        for line in p.read_text("utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                key = str(row.get("id", "")).zfill(5)
                db[key] = row
            except Exception:
                pass
    return db

def save_local(fname, db):
    rows = sorted(db.values(), key=lambda x: x.get("date",""), reverse=True)
    p = DATA / fname
    p.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8"
    )
    return len(rows)

def normalize_row(raw):
    """
    Chuẩn hoá 1 record từ vietvudanh sang format của chúng ta:
    {"date": "yyyy-mm-dd", "id": "00001", "result": [...], "process_time": "..."}

    vietvudanh dùng nhiều format khác nhau qua các năm, cần xử lý linh hoạt.
    """
    if not isinstance(raw, dict):
        return None

    # --- date ---
    date = raw.get("date") or raw.get("draw_date") or ""
    if not date:
        return None
    # Normalize dd/mm/yyyy → yyyy-mm-dd nếu cần
    date = str(date).strip()
    if "/" in date:
        parts = date.split("/")
        if len(parts) == 3:
            d, m, y = parts[0].strip(), parts[1].strip(), parts[2].strip()
            date = f"{y}-{m.zfill(2)}-{d.zfill(2)}"
    # Cắt phần thời gian nếu có: "2024-01-15T..."
    if "T" in date:
        date = date.split("T")[0]

    # --- id ---
    did = str(raw.get("id") or raw.get("draw_id") or raw.get("period") or "").strip().zfill(5)
    if not did or did == "00000":
        return None

    # --- result ---
    result = raw.get("result") or raw.get("numbers") or raw.get("drawn_numbers")

    # Một số phiên bản cũ lưu: {"main": [...], "special": [...]}
    if result is None:
        main    = raw.get("main") or raw.get("regular") or []
        special = raw.get("special") or raw.get("extra") or raw.get("power") or []
        if isinstance(special, int):
            special = [special]
        if main:
            result = list(main) + list(special)

    # Giữ nguyên dict (Max3D: {"Giải Đặc biệt": ["015","517"], ...})
    if isinstance(result, dict):
        if not result:          # dict rỗng → bỏ qua
            return None
        # giữ nguyên, không convert
    elif isinstance(result, list):
        if not result:          # list rỗng → bỏ qua
            return None
        # Số thường → int; số 3 chữ số (Max3D dạng list) → giữ string
        first = result[0]
        if isinstance(first, str) and len(first) == 3 and first.isdigit():
            pass  # giữ list string ["023","145"...]
        else:
            try:
                result = [int(x) for x in result]
            except Exception:
                pass  # giữ nguyên nếu không convert được
    else:
        return None

    return {
        "date": date,
        "id":   did,
        "result": result,
        "process_time": "bootstrap",
    }

def fetch_and_merge(src_name, dst_name):
    url = SRC + src_name
    print(f"  ↓ {src_name} → {dst_name} ...", end=" ", flush=True)
    try:
        r = requests.get(url, timeout=30)
        if r.status_code == 404:
            print(f"⚠️  404 — bỏ qua")
            return 0, 0
        r.raise_for_status()
    except Exception as e:
        print(f"❌ Lỗi tải: {e}")
        return 0, 0

    local_db = load_local(dst_name)
    before   = len(local_db)
    added    = 0

    for line in r.text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except Exception:
            continue
        row = normalize_row(raw)
        if row is None:
            continue
        key = row["id"]
        if key not in local_db:
            local_db[key] = row
            added += 1

    total = save_local(dst_name, local_db)
    print(f"✅ {added} mới / {total} tổng")
    return added, total

def main():
    print("=" * 60)
    print("📦  Bootstrap — Tải dữ liệu lịch sử từ vietvudanh")
    print("🌐  Nguồn: github.com/vietvudanh/vietlott-data")
    print("=" * 60)

    grand = 0
    for src, dst in FILE_MAP:
        added, _ = fetch_and_merge(src, dst)
        grand += added
        time.sleep(0.5)

    print(f"\n{'=' * 60}")
    print(f"✅ Hoàn thành! Đã thêm {grand} bản ghi mới tổng cộng.")
    print("=" * 60)

if __name__ == "__main__":
    main()
