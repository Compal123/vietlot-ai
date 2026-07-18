#!/usr/bin/env python3
"""
VietLot AI — SEO Builder
Sinh TRANG HTML TĨNH cho từng bài dự đoán (Google đọc được ngay, không cần JS)
từ data/articles.jsonl, kèm sitemap.xml + robots.txt.

Vì sao cần: dashboard là SPA (nội dung do JS vẽ trong tab) → Googlebot gần như
không thấy chữ nào. Trang tĩnh có <title>/<meta>/Open Graph/JSON-LD riêng + toàn
văn bài trong HTML → đủ điều kiện được index & xuất hiện trên tìm kiếm.

Cấu trúc sinh ra (deploy tại https://compal123.github.io/vietlot-ai/):
  du-doan/index.html                 → trang tổng "Dự đoán xổ số Vietlott hôm nay"
  du-doan/{slug}/index.html          → bài MỚI NHẤT của loại (URL "hôm nay")
  du-doan/{slug}/ky-{id}.html        → bài lưu trữ từng kỳ cũ (URL cố định)
  sitemap.xml, robots.txt            → giúp Google tìm & crawl

Chạy lúc deploy trong pages.yml (như build_api.py). Chỉ dùng thư viện chuẩn.
Chạy: python scripts/build_seo.py
"""
import html
import json
import re
import sys
import pathlib
from datetime import datetime, timezone, timedelta

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ART_FILE = DATA / "articles.jsonl"
OUT_DIR = ROOT / "du-doan"
SITE = "https://compal123.github.io/vietlot-ai"
VN_TZ = timezone(timedelta(hours=7))

GAME_META = {
    "power655": {"name": "Power 6/55", "slug": "power-6-55"},
    "power645": {"name": "Mega 6/45",  "slug": "mega-6-45"},
    "power535": {"name": "Lotto 5/35", "slug": "lotto-5-35"},
    "max3d":    {"name": "Max3D",      "slug": "max-3d"},
    "max3dpro": {"name": "Max3D Pro",  "slug": "max-3d-pro"},
}
# thứ tự hiển thị ở trang hub
GAME_ORDER = ["power655", "power645", "power535", "max3d", "max3dpro"]


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


# ─── Markdown → HTML (subset, an toàn) ────────────────────────────────────────
def md_inline(s):
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"__([^_]+)__", r"<strong>\1</strong>", s)
    s = re.sub(r"(^|[^*])\*([^*\n]+)\*", r"\1<em>\2</em>", s)
    s = re.sub(r"\[([^\]]+)\]\((https?:[^)\s]+)\)", r'<a href="\2" rel="noopener">\1</a>', s)
    return s


def md_to_html(md):
    lines = (md or "").replace("\r\n", "\n").split("\n")
    out, para, i = [], [], 0

    def flush():
        if para:
            out.append("<p>" + md_inline(" ".join(para)) + "</p>")
            para.clear()

    while i < len(lines):
        t = lines[i].strip()
        if not t:
            flush(); i += 1; continue
        if re.match(r"^(-{3,}|\*{3,}|_{3,})$", t):
            flush(); out.append("<hr>"); i += 1; continue
        hm = re.match(r"^(#{1,6})\s+(.*)$", t)
        if hm:
            flush(); lv = len(hm.group(1))
            out.append(f"<h{lv}>{md_inline(hm.group(2))}</h{lv}>"); i += 1; continue
        if re.match(r"^>\s?", t):
            flush(); buf = []
            while i < len(lines) and re.match(r"^>\s?", lines[i].strip()):
                buf.append(re.sub(r"^>\s?", "", lines[i].strip())); i += 1
            out.append("<blockquote>" + md_inline(" ".join(buf)) + "</blockquote>"); continue
        if re.match(r"^[-*•]\s+", t):
            flush(); items = []
            while i < len(lines) and re.match(r"^[-*•]\s+", lines[i].strip()):
                items.append("<li>" + md_inline(re.sub(r"^[-*•]\s+", "", lines[i].strip())) + "</li>"); i += 1
            out.append("<ul>" + "".join(items) + "</ul>"); continue
        if re.match(r"^\d+[.)]\s+", t):
            flush(); items = []
            while i < len(lines) and re.match(r"^\d+[.)]\s+", lines[i].strip()):
                items.append("<li>" + md_inline(re.sub(r"^\d+[.)]\s+", "", lines[i].strip())) + "</li>"); i += 1
            out.append("<ol>" + "".join(items) + "</ol>"); continue
        para.append(t); i += 1
    flush()
    return "\n".join(out)


def make_description(md, fallback):
    """Mô tả ~155 ký tự cho <meta> — bỏ tiêu đề/markdown, lấy văn xuôi đầu bài."""
    parts = []
    for line in (md or "").split("\n"):
        s = line.strip()
        if not s or s.startswith("#") or s.startswith(">") or s[:1] in "-*•":
            continue
        s = re.sub(r"[*`_]", "", s)
        parts.append(s)
        if len(" ".join(parts)) > 170:
            break
    text = re.sub(r"\s+", " ", " ".join(parts)).strip() or fallback
    if len(text) > 158:
        text = text[:157].rsplit(" ", 1)[0] + "…"
    return text


def esc(s):
    return html.escape(str(s or ""), quote=True)


# ─── Template ─────────────────────────────────────────────────────────────────
CSS = """*{box-sizing:border-box}body{margin:0;background:#07091a;color:#c7cbe0;
font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;line-height:1.85;font-size:16px}
a{color:#00d4d0}.wrap{max-width:760px;margin:0 auto;padding:0 20px 60px}
header.site{border-bottom:1px solid rgba(124,111,247,.18);margin-bottom:26px}
.site-in{max-width:760px;margin:0 auto;padding:16px 20px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.brand{font-weight:800;font-size:18px;background:linear-gradient(120deg,#fff 30%,#00d4d0);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;text-decoration:none}
nav.top{display:flex;gap:14px;flex-wrap:wrap;margin-left:auto;font-size:13.5px}
nav.top a{color:#9aa0c2;text-decoration:none}nav.top a:hover{color:#fff}
.crumb{font-size:12.5px;color:#6b7099;margin-bottom:14px}.crumb a{color:#9aa0c2;text-decoration:none}
h1{font-size:27px;line-height:1.3;font-weight:800;color:#fff;margin:8px 0 18px}
h2{font-size:20px;font-weight:800;color:#7c6ff7;margin:30px 0 10px;padding-left:12px;border-left:3px solid #7c6ff7}
h3{font-size:17px;color:#fff;margin:20px 0 8px}p{margin:0 0 14px}
ul,ol{margin:0 0 15px;padding-left:24px}li{margin-bottom:7px}
strong,b{color:#fff}em{color:#00d4d0;font-style:normal}code{background:#192040;padding:1px 6px;border-radius:5px;color:#00d4d0;font-size:14px}
blockquote{border-left:3px solid #2c336a;padding:6px 14px;margin:0 0 14px;color:#8b90b5;background:#111531;border-radius:0 8px 8px 0}
hr{border:0;border-top:1px solid rgba(124,111,247,.18);margin:20px 0}
.meta{display:flex;flex-wrap:wrap;gap:8px 14px;font-size:13px;color:#6b7099;margin-bottom:18px;padding-bottom:14px;border-bottom:1px solid rgba(124,111,247,.18)}
.badge{font-weight:800;color:#00d4d0;background:rgba(0,212,208,.1);border:1px solid rgba(0,212,208,.35);border-radius:20px;padding:2px 11px}
.related{margin-top:38px;border-top:1px solid rgba(124,111,247,.18);padding-top:22px}
.related h2{border:0;padding:0;font-size:15px;color:#9aa0c2;margin:0 0 12px}
.rgrid{display:flex;flex-wrap:wrap;gap:10px}
.rgrid a{display:inline-block;background:#111531;border:1px solid rgba(124,111,247,.2);border-radius:10px;padding:9px 14px;color:#c7cbe0;text-decoration:none;font-size:13.5px;font-weight:600}
.rgrid a:hover{border-color:#7c6ff7;color:#fff}
.arch{margin-top:16px;font-size:13.5px}.arch a{color:#9aa0c2;text-decoration:none;display:inline-block;margin:0 12px 8px 0}.arch a:hover{color:#00d4d0}
footer{margin-top:40px;font-size:12.5px;color:#6b7099;border-top:1px solid rgba(124,111,247,.18);padding-top:18px}
.cta{display:inline-block;margin-top:6px;background:linear-gradient(135deg,#7c6ff7,#00d4d0);color:#fff;text-decoration:none;font-weight:700;padding:10px 18px;border-radius:10px;font-size:14px}
@media(max-width:600px){h1{font-size:23px}body{font-size:15.5px}}"""


def render_page(title, description, canonical, body_inner, jsonld=None, og_type="article"):
    jl = ("<script type=\"application/ld+json\">" + json.dumps(jsonld, ensure_ascii=False) + "</script>") if jsonld else ""
    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<link rel="canonical" href="{esc(canonical)}">
<meta name="robots" content="index, follow, max-image-preview:large">
<meta property="og:type" content="{og_type}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:url" content="{esc(canonical)}">
<meta property="og:site_name" content="VietLot AI">
<meta property="og:locale" content="vi_VN">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(description)}">
{jl}
<style>{CSS}</style>
</head>
<body>
<header class="site"><div class="site-in">
  <a class="brand" href="{SITE}/">🎰 VietLot AI</a>
  <nav class="top">
    <a href="{SITE}/">Dashboard</a>
    <a href="{SITE}/du-doan/">Bài viết dự đoán</a>
  </nav>
</div></header>
<div class="wrap">
{body_inner}
</div>
<script data-goatcounter="https://cvcagv.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>
</body>
</html>"""


def article_body(art, gm, related_games, archive_links):
    date_txt = art.get("draw_date") or art.get("based_on_date") or ""
    created = art.get("created_at", "")
    created_disp = ""
    if created:
        try:
            created_disp = datetime.fromisoformat(created).strftime("%d/%m/%Y %H:%M")
        except Exception:
            created_disp = created[:16].replace("T", " ")
    rel = "".join(
        f'<a href="{SITE}/du-doan/{GAME_META[g]["slug"]}/">Dự đoán {GAME_META[g]["name"]}</a>'
        for g in related_games)
    arch = ""
    if archive_links:
        arch = ('<div class="arch"><b style="color:#9aa0c2">Các kỳ trước:</b><br>'
                + "".join(f'<a href="{u}">Kỳ #{i}</a>' for u, i in archive_links) + "</div>")
    crumb = (f'<div class="crumb"><a href="{SITE}/">Trang chủ</a> › '
             f'<a href="{SITE}/du-doan/">Dự đoán</a> › {esc(gm["name"])}</div>')
    body_html = md_to_html(art.get("content", ""))
    return f"""{crumb}
<div class="meta">
  <span class="badge">📊 {esc(gm['name'])}</span>
  <span>Kỳ #{esc(art.get('based_on_id'))}{(' · ' + esc(art.get('based_on_date'))) if art.get('based_on_date') else ''}</span>
  {f'<span>🕐 Cập nhật {esc(created_disp)}</span>' if created_disp else ''}
  <span style="margin-left:auto;color:#7c6ff7">✨ Phân tích bằng AI</span>
</div>
<article>{body_html}</article>
<div style="margin-top:26px">
  <a class="cta" href="{SITE}/">🎲 Xem dữ liệu &amp; công cụ phân tích đầy đủ →</a>
</div>
<div class="related">
  <h2>Dự đoán các loại khác</h2>
  <div class="rgrid">{rel}</div>
  {arch}
</div>
<footer>
  ⚠️ Xổ số hoàn toàn ngẫu nhiên — không AI hay hệ thống nào dự đoán chắc chắn được kết quả.
  Nội dung chỉ mang tính thống kê, tham khảo, giải trí. Chơi có trách nhiệm.<br>
  © VietLot AI — dữ liệu &amp; phân tích mã nguồn mở.
</footer>"""


def article_jsonld(art, canonical, description):
    return {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": art.get("title", ""),
        "description": description,
        "datePublished": art.get("created_at", ""),
        "dateModified": art.get("created_at", ""),
        "inLanguage": "vi-VN",
        "author": {"@type": "Organization", "name": "VietLot AI", "url": SITE},
        "publisher": {"@type": "Organization", "name": "VietLot AI"},
        "mainEntityOfPage": {"@type": "WebPage", "@id": canonical},
    }


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ─── Build ────────────────────────────────────────────────────────────────────
def build():
    print("🔎 Building SEO pages...")
    arts = load_jsonl(ART_FILE)
    if not arts:
        print("⚠ Chưa có bài viết (data/articles.jsonl trống) — bỏ qua.")
        return

    by_game = {}
    for a in arts:
        by_game.setdefault(a["game"], []).append(a)
    for g in by_game:
        by_game[g].sort(key=lambda a: str(a["based_on_id"]), reverse=True)

    sitemap = []  # (loc, lastmod, changefreq, priority)
    n_pages = 0

    def lastmod(a):
        d = a.get("created_at") or a.get("based_on_date") or ""
        return d[:10]

    for game in GAME_ORDER:
        lst = by_game.get(game)
        if not lst:
            continue
        gm = GAME_META[game]
        related = [g for g in GAME_ORDER if g != game and by_game.get(g)]

        # archive links (các kỳ cũ, trừ kỳ mới nhất)
        archive_pairs = [(f'{SITE}/du-doan/{gm["slug"]}/ky-{esc(a["based_on_id"])}.html', a["based_on_id"])
                         for a in lst[1:]]

        # 1) Trang MỚI NHẤT: /du-doan/{slug}/
        latest = lst[0]
        canonical = f"{SITE}/du-doan/{gm['slug']}/"
        desc = make_description(latest.get("content"), latest.get("title", ""))
        body = article_body(latest, gm, related, archive_pairs[:8])
        write(OUT_DIR / gm["slug"] / "index.html",
              render_page(latest.get("title") + " | VietLot AI", desc, canonical, body,
                          article_jsonld(latest, canonical, desc)))
        sitemap.append((canonical, lastmod(latest), "daily", "0.9"))
        n_pages += 1

        # 2) Trang lưu trữ từng kỳ cũ: /du-doan/{slug}/ky-{id}.html
        for a in lst[1:]:
            canonical_a = f"{SITE}/du-doan/{gm['slug']}/ky-{a['based_on_id']}.html"
            desc_a = make_description(a.get("content"), a.get("title", ""))
            # related archive cho trang cũ: vài kỳ gần nó
            arch_a = [(u, i) for u, i in archive_pairs if i != a["based_on_id"]][:6]
            body_a = article_body(a, gm, related, arch_a)
            write(OUT_DIR / gm["slug"] / f"ky-{a['based_on_id']}.html",
                  render_page(a.get("title") + " | VietLot AI", desc_a, canonical_a, body_a,
                              article_jsonld(a, canonical_a, desc_a)))
            sitemap.append((canonical_a, lastmod(a), "monthly", "0.5"))
            n_pages += 1

    # 3) Trang hub /du-doan/
    cards = []
    for game in GAME_ORDER:
        lst = by_game.get(game)
        if not lst:
            continue
        gm = GAME_META[game]
        a = lst[0]
        d = make_description(a.get("content"), a.get("title", ""))
        cards.append(
            f'<a href="{SITE}/du-doan/{gm["slug"]}/" '
            f'style="display:block;background:#111531;border:1px solid rgba(124,111,247,.2);'
            f'border-radius:12px;padding:16px 18px;margin-bottom:12px;text-decoration:none">'
            f'<div style="font-weight:800;color:#fff;font-size:16px;margin-bottom:5px">{esc(a.get("title"))}</div>'
            f'<div style="color:#9aa0c2;font-size:13.5px;line-height:1.6">{esc(d)}</div></a>')
    hub_body = f"""<div class="crumb"><a href="{SITE}/">Trang chủ</a> › Dự đoán</div>
<h1>Dự đoán kết quả xổ số Vietlott hôm nay</h1>
<p>Tổng hợp bài phân tích &amp; dự đoán cho từng loại xổ số Vietlott — cập nhật tự động sau mỗi kỳ quay,
dựa trên thống kê tần suất, số nóng/lạnh, cặp số đồng hành và tương quan kỳ trước.</p>
{''.join(cards)}
<div style="margin-top:22px"><a class="cta" href="{SITE}/">🎲 Mở dashboard phân tích đầy đủ →</a></div>
<footer>⚠️ Xổ số hoàn toàn ngẫu nhiên — nội dung chỉ mang tính tham khảo, giải trí. Chơi có trách nhiệm.</footer>"""
    hub_desc = "Dự đoán kết quả Power 6/55, Mega 6/45, Lotto 5/35, Max3D, Max3D Pro hôm nay — phân tích thống kê tự động, cập nhật sau mỗi kỳ quay."
    write(OUT_DIR / "index.html",
          render_page("Dự đoán kết quả xổ số Vietlott hôm nay | VietLot AI",
                      hub_desc, f"{SITE}/du-doan/", hub_body, og_type="website"))
    sitemap.insert(0, (f"{SITE}/du-doan/", datetime.now(VN_TZ).strftime("%Y-%m-%d"), "daily", "0.8"))
    sitemap.insert(0, (f"{SITE}/", datetime.now(VN_TZ).strftime("%Y-%m-%d"), "daily", "1.0"))
    n_pages += 1

    # 4) sitemap.xml
    urls = "".join(
        f"<url><loc>{esc(loc)}</loc><lastmod>{esc(lm)}</lastmod>"
        f"<changefreq>{cf}</changefreq><priority>{pr}</priority></url>"
        for loc, lm, cf, pr in sitemap)
    sm = ('<?xml version="1.0" encoding="UTF-8"?>'
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + urls + "</urlset>")
    write(ROOT / "sitemap.xml", sm)

    # 5) robots.txt
    write(ROOT / "robots.txt",
          "User-agent: *\nAllow: /\n\nSitemap: %s/sitemap.xml\n" % SITE)

    print(f"✅ Đã sinh {n_pages} trang tĩnh + sitemap.xml ({len(sitemap)} URL) + robots.txt → {OUT_DIR.relative_to(ROOT)}/")


if __name__ == "__main__":
    build()
