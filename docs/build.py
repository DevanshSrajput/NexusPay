#!/usr/bin/env python3
"""Markdown → production docs site for NexusPay.

One command turns the repo's Markdown into a static, SEO-ready, SPA-fast,
AI-ready documentation website.

    python docs/build.py            # builds ./site

Output:
  * Pre-rendered HTML per page (crawlable; meta, Open Graph, JSON-LD, sitemap).
  * A client-side SPA layer (assets/app.js) for instant navigation.
  * Raw .md per page + llms.txt / llms-full.txt for AI agents.
"""

import html
import re
import shutil
from pathlib import Path

import markdown
from pygments.formatters import HtmlFormatter

ROOT = Path(__file__).resolve().parent.parent
THEME = Path(__file__).resolve().parent / "theme"
OUT = ROOT / "site"

# ── Site config ───────────────────────────────────────────────────────────
SITE_TITLE = "NexusPay"
SITE_DESC = ("Autonomous AI agent that buys the data it needs, pays per call with "
             "the x402 protocol, and synthesizes the answer — budget-aware and auditable.")
BASE_URL = "https://devanshsrajput.github.io/NexusPay/"
GITHUB_URL = "https://github.com/DevanshSrajput/NexusPay"

PAGES = [
    {"slug": "", "out": "index.html", "kind": "home", "nav": "Home", "title": SITE_TITLE},
    {"slug": "overview", "out": "overview/index.html", "kind": "doc", "nav": "Overview",
     "src": "README.md", "title": "Overview", "raw": "overview.md"},
    {"slug": "documentation", "out": "documentation/index.html", "kind": "doc", "nav": "Documentation",
     "src": "DOCUMENTATION.md", "title": "Documentation", "raw": "documentation.md"},
]

# ── SVG icon set (no emoji) ────────────────────────────────────────────────
LOGO = (Path(THEME / "favicon.svg").read_text()
        .replace('<svg ', '<svg width="28" height="28" '))
IC = {
    "github": '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2A10 10 0 0 0 2 12c0 4.42 2.87 8.17 6.84 9.5.5.09.66-.22.66-.48v-1.7c-2.78.6-3.37-1.34-3.37-1.34-.45-1.16-1.11-1.47-1.11-1.47-.91-.62.07-.6.07-.6 1 .07 1.53 1.03 1.53 1.03.89 1.53 2.34 1.09 2.91.83.09-.65.35-1.09.63-1.34-2.22-.25-4.55-1.11-4.55-4.94 0-1.09.39-1.98 1.03-2.68-.1-.25-.45-1.27.1-2.65 0 0 .84-.27 2.75 1.02a9.6 9.6 0 0 1 5 0c1.91-1.29 2.75-1.02 2.75-1.02.55 1.38.2 2.4.1 2.65.64.7 1.03 1.59 1.03 2.68 0 3.84-2.34 4.69-4.57 4.94.36.31.68.92.68 1.85v2.74c0 .27.16.58.67.48A10 10 0 0 0 22 12 10 10 0 0 0 12 2Z"/></svg>',
    "sun": '<svg class="sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>',
    "moon": '<svg class="moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z"/></svg>',
    "menu": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 6h18M3 12h18M3 18h18"/></svg>',
    "bolt": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2 3 14h7l-1 8 10-12h-7l1-8Z"/></svg>',
    "coin": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v10M9.5 9.5h4a1.5 1.5 0 0 1 0 3h-3a1.5 1.5 0 0 0 0 3h4"/></svg>',
    "shield": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 5 6v6c0 4 3 7 7 9 4-2 7-5 7-9V6l-7-3Z"/><path d="m9 12 2 2 4-4"/></svg>',
    "list": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/></svg>',
    "arrow": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg>',
    "book": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2Z"/></svg>',
}


def md_engine():
    return markdown.Markdown(
        extensions=["fenced_code", "tables", "toc", "codehilite",
                    "attr_list", "sane_lists", "md_in_html"],
        extension_configs={
            "codehilite": {"guess_lang": False, "css_class": "codehilite"},
            "toc": {"permalink": True, "permalink_title": "Link to this section"},
        },
    )


def relroot(depth: int) -> str:
    return "" if depth <= 0 else "../" * depth


def first_para_desc(html_body: str, fallback: str) -> str:
    m = re.search(r"<p>(.*?)</p>", html_body, re.DOTALL)
    if not m:
        return fallback
    text = re.sub(r"<[^>]+>", "", m.group(1))
    text = html.unescape(re.sub(r"\s+", " ", text)).strip()
    if len(text) > 155:
        text = text[:152].rsplit(" ", 1)[0] + "…"
    return text or fallback


def preprocess_md(src: str) -> str:
    """Let Markdown render inside centered wrapper divs.

    READMEs often wrap a hero in `<div align="center">`; without `markdown="1"`
    the `md_in_html` extension passes the inner heading/badges through as literal
    text. Convert those to a centered class that opts into Markdown parsing.
    """
    return re.sub(r'<div\s+align="center"\s*>',
                  '<div class="md-center" markdown="1">', src)


def rewrite_links(body: str, r: str) -> str:
    """Rewrite source-relative Markdown links for the built site.

    README.md / DOCUMENTATION.md → their rendered pages (keeping #anchors);
    any other repo-relative path → a GitHub blob/tree URL.
    """
    def repl(m):
        href = m.group(1)
        if href.startswith(("http://", "https://", "#", "mailto:", "data:")):
            return m.group(0)
        path, _, anchor = href.partition("#")
        anchor = ("#" + anchor) if anchor else ""
        low = path.lower()
        if low in ("readme.md", "./readme.md"):
            return f'href="{r}overview/index.html{anchor}"'
        if low in ("documentation.md", "./documentation.md"):
            return f'href="{r}documentation/index.html{anchor}"'
        kind = "tree" if path.endswith("/") else "blob"
        return f'href="{GITHUB_URL}/{kind}/main/{path}{anchor}"'

    return re.sub(r'href="([^"]+)"', repl, body)


def flat_toc(tokens):
    """Flatten markdown toc_tokens to a list of (level, id, name) for h2/h3."""
    out = []

    def walk(items):
        for it in items:
            if it["level"] in (2, 3):
                out.append((it["level"], it["id"], it["name"]))
            walk(it.get("children", []))
    walk(tokens)
    return out


# ── HTML templates ─────────────────────────────────────────────────────────
def head(page, desc, depth, toc_alt=None):
    r = relroot(depth)
    canonical = BASE_URL + page["slug"] + ("/" if page["slug"] else "")
    og_type = "website" if page["kind"] == "home" else "article"
    alt = (f'<link rel="alternate" type="text/markdown" href="{r}{toc_alt}">'
           if toc_alt else "")
    if page["kind"] == "home":
        ldjson = (f'{{"@context":"https://schema.org","@type":"SoftwareApplication",'
                  f'"name":"{SITE_TITLE}","applicationCategory":"DeveloperApplication",'
                  f'"operatingSystem":"Cross-platform","description":"{html.escape(SITE_DESC)}",'
                  f'"url":"{canonical}","codeRepository":"{GITHUB_URL}",'
                  f'"author":{{"@type":"Person","name":"Devansh Singh"}}}}')
    else:
        ldjson = (f'{{"@context":"https://schema.org","@type":"TechArticle",'
                  f'"headline":"{page["title"]} — {SITE_TITLE}",'
                  f'"description":"{html.escape(desc)}","url":"{canonical}",'
                  f'"author":{{"@type":"Person","name":"Devansh Singh"}}}}')
    title = (SITE_TITLE if page["kind"] == "home"
             else f'{page["title"]} · {SITE_TITLE}')
    return f"""<!doctype html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(desc)}">
<link rel="canonical" href="{canonical}">
<meta name="theme-color" content="#0F172A">
<meta property="og:type" content="{og_type}">
<meta property="og:site_name" content="{SITE_TITLE}">
<meta property="og:title" content="{html.escape(title)}">
<meta property="og:description" content="{html.escape(desc)}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{BASE_URL}assets/favicon.svg">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="{html.escape(title)}">
<meta name="twitter:description" content="{html.escape(desc)}">
<link rel="icon" type="image/svg+xml" href="{r}assets/favicon.svg">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
{alt}
<link rel="stylesheet" href="{r}assets/styles.css">
<link rel="stylesheet" href="{r}assets/pygments.css">
<script>(function(){{try{{var t=localStorage.getItem('np-theme');if(!t)t=matchMedia('(prefers-color-scheme: light)').matches?'light':'dark';document.documentElement.setAttribute('data-theme',t);}}catch(e){{}}}})();</script>
<script type="application/ld+json">{ldjson}</script>
</head>
<body>
<a class="skip-link" href="#main">Skip to content</a>"""


def topbar(depth, active_slug):
    r = relroot(depth)
    links = ""
    for p in PAGES:
        href = r + p["out"]
        cur = ' aria-current="page"' if p["slug"] == active_slug else ""
        links += f'<a href="{href}"{cur}>{p["nav"]}</a>'
    return f"""<header class="topbar">
  <a class="brand" href="{r}index.html">{LOGO}<span>NexusPay<span class="v"> · docs</span></span></a>
  <nav class="topnav" aria-label="Primary">{links}</nav>
  <div class="topbar-actions">
    <button class="icon-btn" id="menu-btn" type="button" aria-label="Toggle navigation">{IC['menu']}</button>
    <button class="icon-btn" id="theme-btn" type="button" aria-label="Toggle theme">{IC['sun']}{IC['moon']}</button>
    <a class="icon-btn" href="{GITHUB_URL}" target="_blank" rel="noopener" aria-label="GitHub repository">{IC['github']}</a>
  </div>
</header>"""


def sidebar(depth, active_slug, doc_sections):
    r = relroot(depth)
    items = ""
    for p in PAGES:
        href = r + p["out"]
        cls = " class=\"active\"" if p["slug"] == active_slug else ""
        items += f'<a href="{href}"{cls}>{p["nav"]}</a>'
        if p["slug"] == "documentation" and doc_sections:
            for _lvl, sid, name in doc_sections:
                items += f'<a class="sub" href="{r}documentation/index.html#{sid}">{html.escape(name)}</a>'
    return f"""<aside class="sidebar" aria-label="Docs navigation">
    <h4>Navigation</h4>
    <nav>{items}</nav>
    <h4>Links</h4>
    <nav><a href="{GITHUB_URL}" target="_blank" rel="noopener" data-no-spa>GitHub →</a>
    <a href="{GITHUB_URL}/issues" target="_blank" rel="noopener" data-no-spa>Issues →</a></nav>
  </aside>"""


def toc_rail(sections):
    if not sections:
        return ""
    links = ""
    for lvl, sid, name in sections:
        cls = "h3" if lvl == 3 else "h2"
        links += f'<a class="{cls}" href="#{sid}">{html.escape(name)}</a>'
    return f'<nav class="toc" aria-label="On this page"><h4>On this page</h4>{links}</nav>'


def footer():
    return f"""<footer class="footer">
  <div class="inner">
    <span class="built">Built by <b>Devansh Singh</b> · static HTML for SEO · SPA for speed · AI-ready by default</span>
    <span><a href="{GITHUB_URL}" target="_blank" rel="noopener" data-no-spa>GitHub</a> · <a href="{R}llms.txt" data-no-spa>llms.txt</a></span>
  </div>
</footer>
<div class="sidebar-scrim"></div>
<script src="{R}assets/app.js" defer></script>
</body></html>"""


# module-level relative-root prefix, set per page before rendering
R = ""
rel_assets = "assets/"


def render_doc_page(page, body_html, sections, doc_sections):
    global rel_assets, R
    depth = page["out"].count("/")
    R = relroot(depth)
    rel_assets = R + "assets/"
    desc = first_para_desc(body_html, SITE_DESC)
    parts = [head(page, desc, depth, toc_alt=page.get("raw"))]
    parts.append(topbar(depth, page["slug"]))
    has_toc = bool(sections)
    shell_cls = "shell" if has_toc else "shell no-toc"
    parts.append(f'<div class="{shell_cls}">')
    parts.append(sidebar(depth, page["slug"], doc_sections))
    parts.append(f'<main class="content" id="main"><article class="doc animate">{body_html}</article></main>')
    parts.append(toc_rail(sections))
    parts.append("</div>")
    parts.append(footer())
    return "\n".join(parts)


def render_home():
    global rel_assets, R
    page = PAGES[0]
    depth = 0
    R = ""
    rel_assets = "assets/"
    parts = [head(page, SITE_DESC, depth)]
    parts.append(topbar(depth, ""))
    parts.append('<div class="shell landing-shell"><main id="main">')
    parts.append(HOME_HTML)
    parts.append("</main></div>")
    parts.append(footer())
    return "\n".join(parts)


HOME_HTML = f"""<div class="landing">
  <section class="hero">
    <span class="eyebrow"><span class="dot"></span> x402 · testnet USDC · Gemini</span>
    <h1>The agent that buys its own data</h1>
    <p class="lead">NexusPay takes a natural-language question, decides which paid sources are worth
      buying, pays per call over the x402 protocol, and synthesizes the answer — inside a strict budget,
      with every payment logged.</p>
    <div class="cta">
      <a class="btn primary" href="overview/index.html">Get started {IC['arrow']}</a>
      <a class="btn" href="documentation/index.html">{IC['book']} Read the docs</a>
      <a class="btn" href="{GITHUB_URL}" target="_blank" rel="noopener" data-no-spa>{IC['github']} GitHub</a>
    </div>
    <div class="hero-code">
      <div class="bar"><i></i><i></i><i></i><span>terminal</span></div>
<pre><span class="c-com"># one command brings up the whole thing</span>
<span class="c-acc">$</span> make ui
<span class="c-com"># or ask the agent directly</span>
<span class="c-acc">$</span> curl -X POST localhost:8000/query -d <span class="c-str">'{{"query":"sentiment on open source LLMs"}}'</span>
<span class="c-acc">→</span> plan · pay /sentiment <span class="c-str">$0.002</span> · pay /news <span class="c-str">$0.001</span> · answer ✓</pre>
    </div>
  </section>

  <section class="section">
    <div class="section-h"><h2>Why NexusPay</h2><p>A reference implementation for autonomous, pay-per-call data pipelines.</p></div>
    <div class="grid">
      <div class="card"><span class="ic">{IC['bolt']}</span><h3>Autonomous decisioning</h3><p>An LLM reads your query and the source catalog, then picks exactly which sources to buy.</p></div>
      <div class="card"><span class="ic">{IC['coin']}</span><h3>Machine-native payments</h3><p>Each purchase settles over the x402 HTTP protocol with testnet USDC — no subscriptions, no human approval.</p></div>
      <div class="card"><span class="ic">{IC['shield']}</span><h3>Budget discipline</h3><p>Per-query and daily caps are enforced before any money moves. The agent cannot overspend.</p></div>
      <div class="card"><span class="ic">{IC['list']}</span><h3>Fully auditable</h3><p>Every payment attempt — success or failure — is written to SQLite with its reasoning.</p></div>
    </div>
  </section>

  <section class="section">
    <div class="section-h"><h2>How it works</h2><p>One POST request travels through five stages.</p></div>
    <div class="steps">
      <div class="step"><h4>Plan</h4><p>Gemini selects the sources worth buying for your question.</p></div>
      <div class="step"><h4>Budget</h4><p>Per-query and daily caps are checked before any call.</p></div>
      <div class="step"><h4>Pay</h4><p>Each source is paid for over x402: 402 → sign → verify → 200.</p></div>
      <div class="step"><h4>Synthesize</h4><p>The purchased data becomes one coherent answer.</p></div>
      <div class="step"><h4>Log</h4><p>Every settlement lands in the spend log for audit.</p></div>
    </div>
  </section>

  <section class="section">
    <div class="cta-band">
      <h2>Read the documentation</h2>
      <p>Architecture, the x402 handshake, every module, and the algorithms behind it.</p>
      <div class="cta" style="justify-content:center">
        <a class="btn primary" href="documentation/index.html">Open the docs {IC['arrow']}</a>
        <a class="btn" href="overview/index.html">Quickstart</a>
      </div>
      <div class="aiready">
        <span class="pill"><b>Static</b> HTML for SEO</span>
        <span class="pill"><b>SPA</b> for speed</span>
        <span class="pill"><b>AI-ready</b> · llms.txt + raw markdown</span>
      </div>
    </div>
  </section>
</div>"""


# ── Build ──────────────────────────────────────────────────────────────────
def build():
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "assets").mkdir(parents=True)

    # assets
    shutil.copy(THEME / "styles.css", OUT / "assets" / "styles.css")
    shutil.copy(THEME / "app.js", OUT / "assets" / "app.js")
    shutil.copy(THEME / "favicon.svg", OUT / "assets" / "favicon.svg")

    # pygments stylesheet: dark default + light override
    dark = HtmlFormatter(style="monokai").get_style_defs(".codehilite")
    light = HtmlFormatter(style="friendly").get_style_defs('[data-theme="light"] .codehilite')
    (OUT / "assets" / "pygments.css").write_text(
        "/* generated by docs/build.py */\n" + dark + "\n" + light + "\n")

    # render doc pages first to capture documentation's section list for the sidebar
    rendered = {}
    doc_sections_for_sidebar = []
    raw_pages = []
    for page in PAGES:
        if page["kind"] != "doc":
            continue
        src = preprocess_md((ROOT / page["src"]).read_text())
        md = md_engine()
        body = md.convert(src)
        body = rewrite_links(body, relroot(page["out"].count("/")))
        sections = flat_toc(md.toc_tokens)
        rendered[page["slug"]] = (page, body, sections)
        raw_pages.append((page, src))
        if page["slug"] == "documentation":
            doc_sections_for_sidebar = [s for s in sections if s[0] == 2]

    # write doc pages
    for slug, (page, body, sections) in rendered.items():
        out_path = OUT / page["out"]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(render_doc_page(page, body, sections, doc_sections_for_sidebar))
        # raw markdown next to root (AI-ready)
        (OUT / page["raw"]).write_text((ROOT / page["src"]).read_text())

    # home
    (OUT / "index.html").write_text(render_home())

    # AI-ready indexes
    write_llms(raw_pages)
    # SEO
    write_sitemap()
    (OUT / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {BASE_URL}sitemap.xml\n")
    (OUT / ".nojekyll").write_text("")

    print(f"Built {len([p for p in PAGES])} pages → {OUT.relative_to(ROOT)}/")
    for p in PAGES:
        print(f"  · {p['out']}")
    print("  · llms.txt · llms-full.txt · sitemap.xml · robots.txt")


def write_llms(raw_pages):
    lines = [f"# {SITE_TITLE}", "", f"> {SITE_DESC}", "",
             "Documentation site. Raw markdown is available for each page.", "",
             "## Docs"]
    for page, _src in raw_pages:
        lines.append(f"- [{page['title']}]({BASE_URL}{page['raw']}): "
                     f"{'Setup, quickstart, API and configuration.' if page['slug']=='overview' else 'Architecture, x402 flow, file-by-file reference, algorithms.'}")
    lines += ["", "## Source", f"- Repository: {GITHUB_URL}", ""]
    (OUT / "llms.txt").write_text("\n".join(lines))

    full = [f"# {SITE_TITLE} — full documentation", ""]
    for page, src in raw_pages:
        full += [f"\n\n---\n\n# {page['title']}\n", src]
    (OUT / "llms-full.txt").write_text("\n".join(full))


def write_sitemap():
    urls = []
    for p in PAGES:
        loc = BASE_URL + p["slug"] + ("/" if p["slug"] else "")
        urls.append(f"  <url><loc>{loc}</loc><changefreq>weekly</changefreq></url>")
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
           + "\n".join(urls) + "\n</urlset>\n")
    (OUT / "sitemap.xml").write_text(xml)


if __name__ == "__main__":
    build()
