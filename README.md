<div align="center">

<img src="https://img.shields.io/badge/VietLot-AI-7c6ff7?style=for-the-badge&logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCI+PHBhdGggZmlsbD0id2hpdGUiIGQ9Ik0xMiAyQzYuNDggMiAyIDYuNDggMiAxMnM0LjQ4IDEwIDEwIDEwIDEwLTQuNDggMTAtMTBTMTcuNTIgMiAxMiAyek0xMSAxN0g5VjdoMnYxMHptNCAwaC0yVjdoMnYxMHoiLz48L3N2Zz4=" alt="VietLot AI">

# 🎰 VietLot AI

**Hệ thống phân tích & dự đoán xổ số Việt Nam thông minh**

[![GitHub Actions](https://img.shields.io/github/actions/workflow/status/Compal123/vietlot-ai/update-data.yml?style=flat-square&logo=github-actions&label=Auto%20Update)](https://github.com/Compal123/vietlot-ai/actions)
[![Data](https://img.shields.io/badge/Data-200k%2B%20bản%20ghi-00d4d0?style=flat-square&logo=databricks)](./data)
[![Games](https://img.shields.io/badge/Xổ%20số-7%20loại-ff6bb5?style=flat-square&logo=dice-d6)](./data)
[![Python](https://img.shields.io/badge/Python-3.11-4effa3?style=flat-square&logo=python)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-ffcc44?style=flat-square)](LICENSE)

[🌐 **Xem Dashboard**](https://compal123.github.io/vietlot-ai/) · [📊 **Dữ liệu**](./data) · [🐛 **Báo lỗi**](https://github.com/Compal123/vietlot-ai/issues) · [✨ **Đề xuất**](https://github.com/Compal123/vietlot-ai/issues)

</div>

---

## 📌 Giới thiệu

**VietLot AI** là một nền tảng mã nguồn mở giúp:

- 🔄 **Tự động thu thập** kết quả xổ số từ [vietlott.vn](https://vietlott.vn) mỗi ngày
- 🗃️ **Lưu trữ lịch sử** hàng chục nghìn kỳ quay thưởng dưới dạng JSONL
- 📊 **Phân tích thống kê** — tần suất, cặp số, xu hướng theo thời gian
- 🤖 **CI/CD hoàn toàn tự động** qua GitHub Actions (không cần server)
- 🌐 **Dashboard trực quan** chạy ngay trên GitHub Pages, không cần cài đặt

---

## 🎮 Các loại xổ số được hỗ trợ

| # | Tên | File | Tần suất quay | Cấu trúc kết quả |
|---|-----|------|--------------|-----------------|
| 1 | **Power 6/55** | `power655.jsonl` | Thứ 3, 5, 7 (18:00) | 6 số từ 1–55 |
| 2 | **Mega 6/45** | `power645.jsonl` | Thứ 4, 6, CN (18:00) | 6 số từ 1–45 |
| 3 | **Lotto 5/35** | `power535.jsonl` | Hàng ngày (13:00 & 21:00) | 5 số từ 1–35 |
| 4 | **Max3D** | `3d.jsonl` | Thứ 2, 4, 6 (18:00) | Nhiều giải (3 chữ số) |
| 5 | **Max3D Pro** | `3d_pro.jsonl` | Thứ 3, 5, 7 (18:00) | Nhiều giải (3 chữ số) |
| 6 | **Keno** | `keno.jsonl` | Mỗi 10 phút (6:00–22:00) | 20 số từ 1–80 |
| 7 | **Bingo18** | `bingo18.jsonl` | Nhiều lần/ngày | 18 số |

---

## 🌐 Dashboard

Truy cập trực tiếp tại: **[https://compal123.github.io/vietlot-ai/](https://compal123.github.io/vietlot-ai/)**

> Không cần cài đặt, chạy 100% trên trình duyệt.

**Tính năng dashboard:**
- 📈 Biểu đồ tần suất xuất hiện từng con số
- 🔥 Top số "nóng" và số "lạnh"
- 📅 Lịch sử kết quả theo ngày
- 🔍 Kiểm tra bộ số của bạn có từng ra chưa
- 📱 Giao diện responsive, hỗ trợ cả mobile

---

## 📦 Cấu trúc dự án

```
vietlot-ai/
├── 📁 data/                    # Dữ liệu xổ số (JSONL)
│   ├── power655.jsonl          # Power 6/55 (~1,000+ kỳ)
│   ├── power645.jsonl          # Mega 6/45 (~1,000+ kỳ)
│   ├── power535.jsonl          # Lotto 5/35
│   ├── 3d.jsonl                # Max3D
│   ├── 3d_pro.jsonl            # Max3D Pro
│   ├── keno.jsonl              # Keno (~100,000+ kỳ)
│   └── bingo18.jsonl           # Bingo18
│
├── 📁 scripts/
│   ├── fetch_data.py           # Scraper chính (Cloudflare bypass)
│   └── bootstrap.py            # Import dữ liệu lịch sử
│
├── 📁 .github/workflows/       # GitHub Actions CI/CD
│   ├── update-data.yml         # Cập nhật Power/Max3D hàng tối
│   ├── keno-bingo-fast.yml     # Cập nhật Keno/Bingo mỗi 10 phút
│   ├── lotto535-daily.yml      # Cập nhật Lotto 5/35 hàng ngày
│   ├── catchup.yml             # Bù dữ liệu bị thiếu (manual)
│   └── bootstrap.yml           # Import lịch sử (chạy 1 lần)
│
├── index.html                  # Dashboard web
├── run_local.py                # Chạy scrape trên máy cá nhân
├── run_local.bat               # Windows batch wrapper
└── requirements.txt            # Python dependencies
```

---

## ⚙️ Cài đặt & Sử dụng

### Yêu cầu

- Python 3.11+
- IP Việt Nam (hoặc VPN VN) để bypass Cloudflare

### Cài đặt

```bash
git clone https://github.com/Compal123/vietlot-ai.git
cd vietlot-ai
pip install -r requirements.txt
```

### Chạy scrape thủ công

```bash
# Lấy tất cả game (3 trang gần nhất ≈ 2 tuần)
python run_local.py

# Chỉ lấy Keno và Bingo18
python run_local.py keno bingo18

# Lấy nhiều trang hơn (≈ 2 tháng)
python run_local.py --pages 10

# Dùng proxy VN (khi bị block)
USE_PROXY=1 python scripts/fetch_data.py
```

### Khởi tạo dữ liệu lịch sử lần đầu

```bash
# Import toàn bộ lịch sử từ các nguồn mở
python scripts/bootstrap.py
```

---

## 🤖 GitHub Actions — Tự động hóa

Dự án sử dụng **5 workflows** để cập nhật dữ liệu hoàn toàn tự động:

| Workflow | Lịch chạy | Mục đích |
|----------|-----------|---------|
| `update-data.yml` | 18:25 giờ VN hàng ngày | Power655, Power645, Max3D, Max3D Pro |
| `keno-bingo-fast.yml` | Mỗi 10 phút (6:00–22:00) | Keno & Bingo18 |
| `lotto535-daily.yml` | 20:15 & 04:15 UTC | Lotto 5/35 (2 kỳ/ngày) |
| `catchup.yml` | Chạy thủ công | Bù dữ liệu bị thiếu (~3 tháng) |
| `bootstrap.yml` | Chạy thủ công | Import toàn bộ lịch sử (1 lần) |

> **Lưu ý**: GitHub Actions IP có thể bị vietlott.vn chặn. Khi đó dùng `run_local.py` trên máy có IP Việt Nam.

---

## 📊 Định dạng dữ liệu

Mỗi file JSONL gồm các dòng JSON, **sắp xếp theo ngày mới nhất trước**:

```jsonc
// Power 6/55, Mega 6/45, Lotto 5/35
{"date": "2026-04-14", "id": "01500", "result": [3, 12, 25, 31, 42, 55]}

// Keno (20 số)
{"date": "2026-04-14", "id": "#0280000", "result": [2, 5, 8, 11, 14, 17, 20, 23, 26, 29, 32, 35, 38, 41, 44, 47, 50, 53, 56, 59]}

// Max3D (nhiều giải)
{"date": "2026-04-14", "id": "00750", "result": {"Giải Đặc biệt": [123, 456], "Giải Nhất": [789, 012]}}
```

**Trường dữ liệu:**
| Trường | Kiểu | Mô tả |
|--------|------|-------|
| `date` | `string` | Ngày quay (yyyy-mm-dd) |
| `id` | `string` | Mã kỳ quay |
| `result` | `array` hoặc `object` | Kết quả trúng thưởng |
| `process_time` | `string` | Thời điểm scrape (tùy chọn) |

---

## 📈 Thống kê dữ liệu

```
Tổng bản ghi: 200,000+
├── keno.jsonl      ~100,000+ kỳ   (24 MB)
├── bingo18.jsonl    ~40,000+ kỳ   (4.8 MB)
├── 3d.jsonl          ~1,500+ kỳ   (307 KB)
├── 3d_pro.jsonl      ~1,500+ kỳ   (204 KB)
├── power655.jsonl    ~1,000+ kỳ   (139 KB)
├── power645.jsonl    ~1,000+ kỳ   (131 KB)
└── power535.jsonl      ~500+ kỳ   (50 KB)
```

---

## 🔧 Cơ chế chống block Cloudflare

Scraper hỗ trợ **3 phương pháp** theo thứ tự ưu tiên:

1. **Direct request** — Dùng headers giả lập browser (nhanh nhất)
2. **VN Proxy** — Xoay qua proxy Việt Nam từ 3 nguồn (geonode, proxyscrape, free-proxy-list)
3. **Playwright** — Headless Chromium thực sự (chậm nhất, hiệu quả nhất)

---

## 🤝 Đóng góp

Mọi đóng góp đều được chào đón!

1. Fork repo này
2. Tạo branch mới: `git checkout -b feature/ten-tinh-nang`
3. Commit: `git commit -m 'feat: thêm tính năng X'`
4. Push: `git push origin feature/ten-tinh-nang`
5. Mở Pull Request

**Một số ý tưởng cần giúp đỡ:**
- [ ] Thêm mô hình ML dự đoán
- [ ] REST API để query dữ liệu
- [ ] Bot Discord/Telegram thông báo kết quả
- [ ] Thêm biểu đồ phân tích nâng cao

---

## ⚠️ Tuyên bố miễn trừ trách nhiệm

> Dự án này chỉ mang tính **thống kê và giải trí**. Kết quả xổ số là **hoàn toàn ngẫu nhiên** — không có hệ thống hay AI nào có thể dự đoán chính xác. Hãy chơi có trách nhiệm.

---

## 📄 Giấy phép

Phát hành dưới giấy phép [MIT License](LICENSE).

---

<div align="center">

Made with ❤️ in Vietnam

⭐ **Nếu thấy hữu ích, hãy để lại một Star!** ⭐

</div>
