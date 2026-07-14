<div align="center">

# 🎰 VietLot AI

**Thu thập & phân tích thống kê xổ số Vietlott — Tự động, mã nguồn mở**

[![Auto Update](https://img.shields.io/github/actions/workflow/status/Compal123/vietlot-ai/update-data.yml?style=flat-square&logo=github-actions&label=Auto%20Update&color=4effa3)](https://github.com/Compal123/vietlot-ai/actions)
[![Keno Live](https://img.shields.io/github/actions/workflow/status/Compal123/vietlot-ai/keno-live.yml?style=flat-square&logo=github-actions&label=Keno%20Live&color=00d4d0)](https://github.com/Compal123/vietlot-ai/actions)
[![Records](https://img.shields.io/badge/Dữ%20liệu-160k%2B%20kỳ%20quay-ff6bb5?style=flat-square&logo=databricks)](./data)
[![Python](https://img.shields.io/badge/Python-3.11-4effa3?style=flat-square&logo=python)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-ffcc44?style=flat-square)](LICENSE)

[🌐 **Mở Dashboard**](https://compal123.github.io/vietlot-ai/) &nbsp;·&nbsp; [📊 **Xem Dữ liệu**](./data) &nbsp;·&nbsp; [🐛 **Báo lỗi**](https://github.com/Compal123/vietlot-ai/issues)

</div>

---

## 📌 Giới thiệu

**VietLot AI** là dự án mã nguồn mở thu thập và phân tích thống kê kết quả xổ số Vietlott. Dữ liệu được cập nhật **tự động nhiều lần mỗi ngày** qua GitHub Actions — không cần server, không cần cài đặt.

| Tính năng | Chi tiết |
|-----------|---------|
| 🔄 **Tự động hoàn toàn** | GitHub Actions cập nhật kết quả + jackpot mỗi 5–10 phút |
| 🗃️ **160,000+ kỳ quay** | Lịch sử đầy đủ từ khi ra mắt từng loại |
| 👥 **Số người trúng** | Thống kê người trúng từng giải theo kỳ |
| 📊 **Phân tích nâng cao** | Tần suất, streak số nóng/lạnh, cặp số đồng xuất hiện |
| 🌐 **Dashboard không cần server** | Chạy 100% trên GitHub Pages / trình duyệt |

> ⚠️ **Tuyên bố miễn trách nhiệm**: Dự án chỉ mang tính **thống kê và nghiên cứu**. Kết quả xổ số là **hoàn toàn ngẫu nhiên** — không có hệ thống hay AI nào dự đoán được. Không liên kết với Vietlott hay bất kỳ tổ chức nào.

---

## 🎮 Các loại xổ số được hỗ trợ

| # | Tên | File | Lịch quay | Kết quả |
|---|-----|------|----------|---------|
| 1 | **Power 6/55** | `power655.jsonl` | Thứ 3, 5, 7 — 18:00 | 6 số (1–55) + Jackpot 1 & 2 |
| 2 | **Mega 6/45** | `power645.jsonl` | Thứ 4, 6, CN — 18:00 | 6 số (1–45) + Jackpot |
| 3 | **Lotto 5/35** | `power535.jsonl` | Hàng ngày — 13:00 & 21:00 | 5 số (1–35) + Độc Đắc |
| 4 | **Max3D** | `3d.jsonl` | Thứ 2, 4, 6 — 18:00 | 4 giải × 3 chữ số |
| 5 | **Max3D Pro** | `3d_pro.jsonl` | Thứ 3, 5, 7 — 18:00 | 8 giải × 3 chữ số |
| 6 | **Keno** | `keno.jsonl` | Mỗi ~8 phút (06:00–22:00) | 20 số (1–80) |

---

## 🌐 Dashboard

👉 **[https://compal123.github.io/vietlot-ai/](https://compal123.github.io/vietlot-ai/)**

Không cần cài đặt, chạy 100% trên trình duyệt.

**Tính năng dashboard:**

| Tab | Mô tả |
|-----|-------|
| 📋 **Kết Quả** | Kỳ mới nhất + jackpot tích lũy trực tiếp, số người trúng từng giải |
| 📊 **Phân Tích** | Tần suất xuất hiện, top số nóng/lạnh, streak liên tiếp, cặp số |
| 🏆 **Giải Thưởng** | Cơ cấu giải, xác suất, jackpot live, người trúng kỳ gần nhất |
| 🤖 **AI Bot** | Gợi ý bộ số theo phân tích thống kê |
| 🔮 **AI Dự Đoán** | Dự đoán công khai minh bạch + độ chính xác backtest |
| 📰 **Bài Viết** | Bài phân tích chuyên sâu do AI (Gemini) tự viết sau mỗi kỳ quay — tổng hợp số nóng/lạnh, streak, cặp số, dự đoán |
| 📅 **Lịch Sử** | Toàn bộ kết quả, lọc theo tháng/năm, tìm kiếm bộ số |

---

## 📦 Cấu trúc dự án

```
vietlot-ai/
│
├── 📁 data/                        # Dữ liệu xổ số (JSONL, mới nhất trước)
│   ├── power655.jsonl              # Power 6/55     (~1,343 kỳ)
│   ├── power645.jsonl              # Mega 6/45      (~1,311 kỳ)
│   ├── power535.jsonl              # Lotto 5/35     (~634 kỳ)
│   ├── 3d.jsonl                    # Max3D          (~1,076 kỳ)
│   ├── 3d_pro.jsonl                # Max3D Pro      (~721 kỳ)
│   ├── keno.jsonl                  # Keno           (~155,000 kỳ)
│   ├── jackpots.json               # Jackpot tích lũy (cập nhật mỗi 5 phút)
│   ├── predictions.jsonl           # Dự đoán AI công khai (có mốc thời gian)
│   └── articles.jsonl              # Bài viết phân tích do Gemini sinh (mỗi kỳ mới)
│
├── 📁 scripts/
│   ├── fetch_ketqua.py             # Scraper chính — Power/Max3D/Lotto (ketquadientoan.com)
│   ├── fetch_keno_live.py          # Keno live (ketquadientoan.com, dùng trong GitHub Actions)
│   ├── fetch_keno_vietlott.py      # Keno backfill theo ngày (vietlott.vn, chạy local)
│   ├── fetch_jackpots.py           # Jackpot tích lũy (minhchinh.com)
│   ├── fetch_data.py               # Scraper dự phòng — AjaxPro vietlott.vn (IP VN)
│   ├── build_predictions.py        # Sinh dự đoán công khai (minh bạch, chống sửa)
│   ├── build_articles.py           # Sinh bài viết phân tích bằng Gemini (khi có kỳ mới)
│   └── bootstrap.py                # Tải lịch sử từ vietvudanh/vietlott-data (1 lần)
│
├── 📁 .github/workflows/
│   ├── update-data.yml             # Power/Max3D — hàng ngày 19:05 VN
│   ├── lotto535-daily.yml          # Lotto 5/35 + Jackpot — mỗi 5 phút
│   ├── keno-live.yml               # Keno — mỗi 10 phút (06:00–22:00 VN)
│   ├── pages.yml                   # Deploy GitHub Pages — on push + mỗi 5 phút
│   ├── catchup.yml                 # Bù dữ liệu thiếu (thủ công)
│   └── bootstrap.yml               # Bootstrap lịch sử (thủ công, 1 lần)
│
├── index.html                      # Dashboard web (vanilla JS, không cần build)
├── run_local.py                    # Chạy local: scrape + push GitHub
├── run_local.bat                   # Wrapper Windows cho run_local.py
├── run_keno_local.bat              # Backfill Keno từ máy Windows (IP VN)
└── requirements.txt                # Python dependencies
```

---

## 🤖 GitHub Actions — Lịch chạy tự động

| Workflow | Tần suất | Mục đích |
|----------|---------|---------|
| `lotto535-daily.yml` | **Mỗi 5 phút** | Lotto 5/35 (2 kỳ/ngày) + **Jackpot tích lũy** |
| `keno-live.yml` | **Mỗi 10 phút** | Keno — bắt kỳ mới trong vòng 10 phút |
| `update-data.yml` | **19:05 VN** hàng ngày | Power 6/55, Mega 6/45, Max3D, Max3D Pro + Keno backup |
| `pages.yml` | On push + mỗi 5 phút | Deploy Dashboard lên GitHub Pages |
| `catchup.yml` | **Thủ công** | Bù dữ liệu thiếu theo ngày/game tuỳ chọn |
| `bootstrap.yml` | **Thủ công (1 lần)** | Tải dữ liệu lịch sử từ vietvudanh/vietlott-data |

---

## 📰 Bài Viết AI (Gemini) — thiết lập

Tab **Bài Viết** tự sinh một bài phân tích chuyên sâu cho mỗi loại (trừ Keno) **mỗi khi có kỳ quay mới**. Script `scripts/build_articles.py` gom dữ liệu thống kê (số nóng/lạnh, streak, cặp số, dự đoán AI) rồi gọi **Google Gemini** viết bài, lưu vào `data/articles.jsonl`. Chỉ sinh bài khi xuất hiện kỳ mới (đã có bài cho kỳ đó → bỏ qua, không tốn quota).

**Cần 1 secret** để workflow gọi được Gemini:

1. Vào **Settings → Secrets and variables → Actions → New repository secret**
2. Tên: `GEMINI_API_KEY` — Giá trị: API key Gemini của bạn (lấy free tại [aistudio.google.com](https://aistudio.google.com/apikey))
3. (Tuỳ chọn) đổi model qua secret/variable `GEMINI_MODEL` — mặc định `gemini-2.5-flash`

> Không có secret → bước tạo bài tự bỏ qua êm, các workflow khác vẫn chạy bình thường. Key **chỉ nằm trong secret**, không lộ ra frontend.

---

## 🔌 API (cho AI & lập trình viên)

Toàn bộ kết quả và phân tích được xuất ra **API JSON tĩnh**, sinh tự động mỗi lần deploy (`scripts/build_api.py`). **Không cần API key, không giới hạn, CORS mở** — bất kỳ ứng dụng hay AI nào cũng GET được.

**Base URL:** `https://compal123.github.io/vietlot-ai/api/`

| Endpoint | Mô tả |
|----------|-------|
| [`/api/index.json`](https://compal123.github.io/vietlot-ai/api/index.json) | Danh mục toàn bộ game & endpoint (**đọc trước**) |
| [`/api/llms.txt`](https://compal123.github.io/vietlot-ai/api/llms.txt) | Hướng dẫn dạng text cho AI agent |
| [`/api/openapi.json`](https://compal123.github.io/vietlot-ai/api/openapi.json) | OpenAPI 3.1 spec (nạp vào tool/GPT/agent) |
| [`/api/jackpots.json`](https://compal123.github.io/vietlot-ai/api/jackpots.json) | Jackpot tích lũy hiện tại |
| `/api/{game}/latest.json` | Kết quả kỳ quay mới nhất |
| `/api/{game}/results.json` | 100 kỳ gần nhất |
| `/api/{game}/stats.json` | Phân tích: nóng/lạnh, số gan, cặp số, tổng, chẵn/lẻ |
| `/api/{game}/predictions.json` | Dự đoán AI công khai + độ chính xác (có mốc thời gian, chống sửa) |
| `/data/{game}.jsonl` | Toàn bộ lịch sử (JSONL) |

`{game}` ∈ `power655`, `power645`, `power535`, `keno`, `3d`, `3d_pro`.

```bash
# Ví dụ: lấy kỳ Power 6/55 mới nhất
curl https://compal123.github.io/vietlot-ai/api/power655/latest.json

# Số nóng / lạnh / gan của Mega 6/45
curl https://compal123.github.io/vietlot-ai/api/power645/stats.json
```

> ⚠️ **Lưu ý:** Đây là dữ liệu thống kê tham khảo. Xổ số hoàn toàn ngẫu nhiên — số "nóng/lạnh/gan" **không** có giá trị dự đoán kết quả tương lai.

## 📊 Định dạng dữ liệu

Mỗi file JSONL gồm các dòng JSON, **sắp xếp theo ngày + kỳ mới nhất trước**:

```jsonc
// Power 6/55, Mega 6/45, Lotto 5/35 — kèm số người trúng từng giải
{
  "date": "2026-05-09",
  "id": "01500",
  "result": [3, 12, 25, 31, 42, 55],
  "winners": { "Jackpot 1": 0, "Jackpot 2": 1, "Giải Ba": 42, "Giải Tư": 1820 }
}

// Max3D / Max3D Pro — kết quả dạng object theo giải
{
  "date": "2026-05-11",
  "id": "01078",
  "result": {
    "Giải Đặc biệt": ["139", "046"],
    "Giải Nhất": ["669", "523", "747", "445"],
    "Giải Nhì": ["206", "963", "384", "920", "031", "400"],
    "Giải Ba": ["738", "904", "746", "821", "180", "896", "689", "849"]
  },
  "winners": { "Đặc biệt": 36, "Giải nhất": 79, "Giải nhì": 105, "Giải ba": 96 }
}

// Keno — 20 số, có timestamp giờ quay
{
  "id": "0277767",
  "date": "2026-05-11",
  "time": "21:52",
  "result": [1, 2, 10, 17, 21, 32, 33, 36, 40, 41, 47, 53, 54, 60, 61, 67, 68, 71, 74, 76]
}
```

| Trường | Kiểu | Có trong |
|--------|------|---------|
| `date` | `YYYY-MM-DD` | Tất cả |
| `id` | `string` (zero-padded) | Tất cả |
| `time` | `HH:MM` | Keno |
| `result` | `number[]` hoặc `object` | Tất cả |
| `winners` | `object` (tên giải → số người) | Power/Max3D (từ 2025-10) |

---

## 📈 Thống kê dữ liệu (05/2026)

```
Tổng: ~160,000+ kỳ quay
├── keno.jsonl        ~155,000 kỳ   (từ 12/2022 — cập nhật mỗi 10 phút)
├── 3d.jsonl           ~1,076 kỳ    (từ 01/2019)
├── 3d_pro.jsonl         ~721 kỳ    (từ 06/2020)
├── power655.jsonl     ~1,343 kỳ    (từ 07/2017)
├── power645.jsonl     ~1,311 kỳ    (từ 07/2017)
└── power535.jsonl       ~634 kỳ    (từ 06/2025 — toàn bộ có winners)
```

---

## 🛠️ Chạy local

```bash
# Cài dependencies
pip install -r requirements.txt

# Lấy 7 ngày gần nhất, tất cả game, rồi push GitHub
python run_local.py

# Chỉ lấy Lotto 5/35, 14 ngày
python run_local.py power535 --days 14

# Backfill dữ liệu thiếu từ ngày cụ thể
python scripts/fetch_ketqua.py power655 --from 2025-01-01

# Backfill Keno (cần IP Việt Nam)
python scripts/fetch_keno_vietlott.py --days 30

# Fetch jackpot tích lũy thủ công
python scripts/fetch_jackpots.py
```

---

## 📄 Giấy phép

Phát hành dưới [MIT License](LICENSE).

---

<div align="center">

Made with ❤️ in Vietnam

⭐ **Nếu thấy hữu ích, hãy để lại một Star!** ⭐

</div>
