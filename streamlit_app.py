"""NexusPay — Streamlit control center.

A single-process UI that runs the mock data server in a background thread and
drives the agent pipeline in-process, so it works locally and on Streamlit Cloud.

Run locally:   streamlit run streamlit_app.py
"""

import asyncio
import html as _html
import os
import threading
import time

import streamlit as st

# ── Bridge Streamlit Cloud secrets into the environment BEFORE settings load ──
try:  # st.secrets raises if no secrets file is present (e.g. pure local .env)
    for _k in (
        "GEMINI_API_KEY", "GEMINI_MODEL", "MOCK_PAYMENTS",
        "DAILY_CAP_USDC", "PER_QUERY_CAP_USDC", "AGENT_PRIVATE_KEY",
        "AGENT_WALLET_ADDRESS", "NETWORK", "FACILITATOR_URL", "DATA_SERVER_PAY_TO",
    ):
        if _k in st.secrets and _k not in os.environ:
            os.environ[_k] = str(st.secrets[_k])
except Exception:
    pass

from config.settings import settings  # noqa: E402
from db.database import init_db  # noqa: E402
from db.queries import get_all_logs  # noqa: E402
from agent.registry import registry  # noqa: E402
from agent.pipeline import (  # noqa: E402
    budget_snapshot, endpoint_path, execute_stage, new_query_id,
    plan_stage, synthesize_stage,
)
from payment.wallet import wallet  # noqa: E402


# ──────────────────────────────────────────────────────────────────────────
# Infrastructure: background data server + async runner
# ──────────────────────────────────────────────────────────────────────────

def _run_async(coro):
    """Run a coroutine to completion in a fresh event loop."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@st.cache_resource(show_spinner=False)
def bootstrap() -> bool:
    """Start the mock data server in a daemon thread and init the DB (once)."""
    import uvicorn
    import httpx
    from data_servers.server import app as data_app

    config = uvicorn.Config(
        data_app, host="127.0.0.1", port=settings.data_server_port,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()

    # Wait for the server to accept connections.
    base = f"http://127.0.0.1:{settings.data_server_port}/health"
    for _ in range(50):
        try:
            if httpx.get(base, timeout=0.5).status_code == 200:
                break
        except Exception:
            time.sleep(0.1)

    _run_async(init_db())
    return True


# ──────────────────────────────────────────────────────────────────────────
# Theme / CSS  (Dark Mode OLED · Fira Code/Sans · green accent · subtle glow)
# ──────────────────────────────────────────────────────────────────────────

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600;700&family=Fira+Sans:wght@300;400;500;600;700&display=swap');

:root{
  --bg:#0F172A; --surface:#1E293B; --surface-2:#172033; --muted:#272F42;
  --border:#334155; --border-2:#475569; --fg:#F8FAFC; --fg-dim:#94A3B8;
  --accent:#22C55E; --accent-dim:#16A34A; --danger:#EF4444; --warn:#F59E0B; --info:#38BDF8;
}

.stApp{ background:
  radial-gradient(1200px 600px at 15% -10%, rgba(34,197,94,.10), transparent 60%),
  radial-gradient(1000px 500px at 100% 0%, rgba(56,189,248,.08), transparent 55%),
  var(--bg);
  color:var(--fg); font-family:'Fira Sans',sans-serif; }

#MainMenu, header, footer{ visibility:hidden; }
.block-container{ padding-top:1.4rem; max-width:1180px; }

h1,h2,h3,h4{ font-family:'Fira Code',monospace; letter-spacing:-.5px; }
code, .mono, .np-txn, .np-num{ font-family:'Fira Code',monospace; font-variant-numeric:tabular-nums; }

@keyframes npFadeUp{ from{opacity:0; transform:translateY(14px);} to{opacity:1; transform:none;} }
@keyframes npPulse{ 0%,100%{opacity:.55;} 50%{opacity:1;} }
@keyframes npGrad{ 0%{background-position:0% 50%;} 100%{background-position:200% 50%;} }
@keyframes npSpin{ to{ transform:rotate(360deg);} }
@keyframes npGlow{ 0%,100%{box-shadow:0 0 0 1px var(--border), 0 0 22px rgba(34,197,94,.10);} 50%{box-shadow:0 0 0 1px var(--accent), 0 0 30px rgba(34,197,94,.28);} }

@media (prefers-reduced-motion: reduce){
  *{ animation:none !important; transition:none !important; }
}

/* Hero */
.np-hero{ position:relative; border:1px solid var(--border); border-radius:20px;
  padding:26px 28px; margin-bottom:18px; overflow:hidden;
  background:linear-gradient(135deg, rgba(30,41,59,.9), rgba(15,23,42,.6));
  animation:npFadeUp .5s ease-out both; }
.np-hero::before{ content:""; position:absolute; inset:0; padding:1px; border-radius:20px;
  background:linear-gradient(120deg,#22C55E55,#38BDF855,#22C55E55); background-size:200% 100%;
  -webkit-mask:linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  -webkit-mask-composite:xor; mask-composite:exclude; animation:npGrad 6s linear infinite; opacity:.5; }
.np-brand{ display:flex; align-items:center; gap:14px; }
.np-logo{ width:46px; height:46px; flex:none; filter:drop-shadow(0 0 10px rgba(34,197,94,.5)); }
.np-title{ font-size:30px; font-weight:700; margin:0; line-height:1;
  background:linear-gradient(90deg,#F8FAFC,#22C55E 120%); -webkit-background-clip:text;
  background-clip:text; -webkit-text-fill-color:transparent; }
.np-tag{ color:var(--fg-dim); font-size:14px; margin-top:6px; }
.np-chips{ display:flex; flex-wrap:wrap; gap:8px; margin-top:16px; }
.np-pill{ display:inline-flex; align-items:center; gap:7px; font-family:'Fira Code',monospace;
  font-size:11.5px; color:var(--fg-dim); background:rgba(15,23,42,.6);
  border:1px solid var(--border); border-radius:999px; padding:6px 11px; }
.np-dot{ width:7px; height:7px; border-radius:50%; background:var(--accent);
  box-shadow:0 0 8px var(--accent); animation:npPulse 1.8s ease-in-out infinite; }
.np-dot.amber{ background:var(--warn); box-shadow:0 0 8px var(--warn); }

/* Cards */
.np-card{ background:linear-gradient(180deg,var(--surface),var(--surface-2));
  border:1px solid var(--border); border-radius:16px; padding:18px 20px; margin:10px 0;
  animation:npFadeUp .45s ease-out both; }
.np-card.glow{ animation:npFadeUp .45s ease-out both, npGlow 2.4s ease-in-out infinite; }
.np-eyebrow{ font-family:'Fira Code',monospace; font-size:11px; letter-spacing:1.5px;
  text-transform:uppercase; color:var(--fg-dim); margin-bottom:8px; }
.np-answer{ font-size:16px; line-height:1.7; color:var(--fg); white-space:pre-wrap; }

/* Source / payment cards */
.np-src{ display:flex; align-items:center; gap:14px; padding:14px 16px; margin:9px 0;
  border:1px solid var(--border); border-left:4px solid var(--border-2); border-radius:13px;
  background:rgba(23,32,51,.8); animation:npFadeUp .4s ease-out both; }
.np-src.ok{ border-left-color:var(--accent); }
.np-src.fail{ border-left-color:var(--danger); }
.np-src.skip{ border-left-color:var(--warn); }
.np-src .ico{ width:30px; height:30px; flex:none; display:grid; place-items:center;
  border-radius:9px; background:rgba(34,197,94,.12); color:var(--accent); }
.np-src.fail .ico,.np-src.skip .ico{ background:rgba(239,68,68,.12); color:var(--danger); }
.np-src.skip .ico{ background:rgba(245,158,11,.12); color:var(--warn); }
.np-src .meta{ flex:1; min-width:0; }
.np-src .ep{ font-family:'Fira Code',monospace; font-weight:600; font-size:14px; color:var(--fg); }
.np-src .txn{ font-family:'Fira Code',monospace; font-size:11px; color:var(--fg-dim);
  overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.np-cost{ font-family:'Fira Code',monospace; font-weight:600; color:var(--accent); font-size:14px; }
.np-cost.zero{ color:var(--fg-dim); }

/* Stepper */
.np-step{ display:flex; align-items:center; gap:10px; font-family:'Fira Code',monospace;
  font-size:12.5px; color:var(--fg-dim); padding:5px 0; animation:npFadeUp .35s ease-out both; }
.np-step .s{ width:22px; height:22px; border-radius:50%; flex:none; display:grid; place-items:center;
  border:1px solid var(--border-2); font-size:11px; }
.np-step.active{ color:var(--fg); }
.np-step.active .s{ border-color:var(--accent); color:var(--accent); box-shadow:0 0 12px rgba(34,197,94,.35); }
.np-spin{ width:13px; height:13px; border:2px solid var(--border-2); border-top-color:var(--accent);
  border-radius:50%; animation:npSpin .7s linear infinite; }

/* Gauge */
.np-gauge-track{ height:10px; border-radius:999px; background:var(--muted);
  overflow:hidden; border:1px solid var(--border); }
.np-gauge-fill{ height:100%; border-radius:999px;
  background:linear-gradient(90deg,var(--accent),var(--info)); transition:width .8s cubic-bezier(.2,.8,.2,1); }
.np-gauge-fill.hot{ background:linear-gradient(90deg,var(--warn),var(--danger)); }
.np-stat{ font-family:'Fira Code',monospace; }
.np-stat .v{ font-size:22px; font-weight:700; color:var(--fg); }
.np-stat .l{ font-size:11px; color:var(--fg-dim); text-transform:uppercase; letter-spacing:1px; }

/* Native widget theming */
.stTextArea textarea{ background:var(--surface-2) !important; color:var(--fg) !important;
  border:1px solid var(--border) !important; border-radius:13px !important;
  font-family:'Fira Sans',sans-serif !important; font-size:15px !important; }
.stTextArea textarea:focus{ border-color:var(--accent) !important;
  box-shadow:0 0 0 2px rgba(34,197,94,.25) !important; }
.stButton>button, .stFormSubmitButton>button{ border-radius:11px !important; font-weight:600 !important;
  font-family:'Fira Code',monospace !important; border:1px solid var(--border) !important;
  background:var(--surface) !important; color:var(--fg) !important; transition:all .2s ease !important; }
.stButton>button:hover{ border-color:var(--accent) !important; transform:translateY(-1px);
  box-shadow:0 6px 18px rgba(0,0,0,.35) !important; }
button[kind="primary"], .stButton>button[data-testid="baseButton-primary"]{
  background:linear-gradient(90deg,var(--accent),var(--accent-dim)) !important;
  color:#05210f !important; border:none !important; }
button[kind="primary"]:hover{ box-shadow:0 0 22px rgba(34,197,94,.45) !important; transform:translateY(-1px); }
section[data-testid="stSidebar"]{ background:linear-gradient(180deg,#111B2E,#0C1424); border-right:1px solid var(--border); }
[data-testid="stMetricValue"]{ font-family:'Fira Code',monospace !important; }
.stDataFrame{ border-radius:12px; overflow:hidden; }
hr{ border-color:var(--border) !important; }
</style>
"""

LOGO_SVG = """
<svg class="np-logo" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
  <rect x="3" y="3" width="42" height="42" rx="12" fill="#0F172A" stroke="#22C55E" stroke-width="1.5"/>
  <path d="M16 32V16l16 16V16" stroke="#22C55E" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="16" cy="16" r="2.6" fill="#38BDF8"/>
  <circle cx="32" cy="32" r="2.6" fill="#22C55E"/>
</svg>
"""


def esc(s: str) -> str:
    return _html.escape(str(s))


def icon(name: str) -> str:
    paths = {
        "check": '<path d="M5 12l4 4L19 7" stroke="currentColor" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
        "x": '<path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"/>',
        "skip": '<path d="M12 8v5M12 16h.01" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>',
    }
    return (f'<svg width="16" height="16" viewBox="0 0 24 24" fill="none" '
            f'xmlns="http://www.w3.org/2000/svg" aria-hidden="true">{paths[name]}</svg>')


# ──────────────────────────────────────────────────────────────────────────
# App
# ──────────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="NexusPay", page_icon="🛰️", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)
bootstrap()

if "history" not in st.session_state:
    st.session_state.history = []
if "query_input" not in st.session_state:
    st.session_state.query_input = ""

snap = _run_async(budget_snapshot())
key_set = bool(settings.gemini_api_key)

# ── Hero ──
short_wallet = wallet.address[:6] + "…" + wallet.address[-4:]
pay_label = "MOCK · free" if settings.mock_payments else "LIVE · testnet"
pay_dot = "" if settings.mock_payments else " amber"
llm_label = f"Gemini · {esc(settings.gemini_model)}" if key_set else "Keyword fallback"
st.markdown(f"""
<div class="np-hero">
  <div class="np-brand">
    {LOGO_SVG}
    <div>
      <div class="np-title">NexusPay</div>
      <div class="np-tag">Autonomous agent that buys the data it needs, pays per call with x402, and answers you.</div>
    </div>
  </div>
  <div class="np-chips">
    <span class="np-pill"><span class="np-dot{pay_dot}"></span> {pay_label}</span>
    <span class="np-pill">LLM · {llm_label}</span>
    <span class="np-pill">wallet · {esc(short_wallet)}</span>
    <span class="np-pill">net · {esc(settings.network)}</span>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Sidebar: Mission Control ──
with st.sidebar:
    st.markdown('<div class="np-eyebrow">Mission Control</div>', unsafe_allow_html=True)
    pct = 0 if snap.daily_cap <= 0 else min(100, snap.spent_today / snap.daily_cap * 100)
    hot = "hot" if pct >= 80 else ""
    st.markdown(f"""
    <div class="np-stat" style="display:flex; justify-content:space-between; align-items:end;">
      <div><div class="v">${snap.spent_today:.4f}</div><div class="l">spent today</div></div>
      <div style="text-align:right; color:var(--fg-dim);" class="mono">/ ${snap.daily_cap:.2f} cap</div>
    </div>
    <div class="np-gauge-track" style="margin:10px 0 4px;">
      <div class="np-gauge-fill {hot}" style="width:{pct:.1f}%;"></div>
    </div>
    <div class="mono" style="color:var(--fg-dim); font-size:11px;">${snap.remaining:.4f} remaining</div>
    """, unsafe_allow_html=True)

    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown('<div class="np-eyebrow">Spend controls</div>', unsafe_allow_html=True)
    max_spend = st.slider("Max spend for this query (USDC)", 0.001,
                          float(settings.per_query_cap_usdc), float(settings.per_query_cap_usdc),
                          step=0.001, format="%.3f")

    with st.expander("Force specific sources"):
        all_ids = [s.id for s in registry.get_all()]
        forced = st.multiselect("Override the planner", all_ids, default=[],
                                format_func=lambda i: f"{i}  (${registry.get_by_id(i).price_usdc:.3f})")
    forced = forced or None

    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown('<div class="np-eyebrow">Catalog</div>', unsafe_allow_html=True)
    for s in registry.get_all():
        st.markdown(
            f'<div class="mono" style="font-size:12px; display:flex; justify-content:space-between; '
            f'padding:3px 0; color:var(--fg-dim);"><span style="color:var(--fg);">{esc(s.id)}</span>'
            f'<span style="color:var(--accent);">${s.price_usdc:.3f}</span></div>',
            unsafe_allow_html=True)

# ── Query input ──
st.markdown('<div class="np-eyebrow" style="margin-top:6px;">Ask the agent</div>', unsafe_allow_html=True)
query = st.text_area("query", key="query_input", height=92, label_visibility="collapsed",
                     placeholder="e.g. What is the sentiment around open source LLMs, and the latest news?")

examples = [
    "What is the sentiment around open source LLMs this week?",
    "Give me the latest breaking news on AI hardware.",
    "Deep analysis of agentic payments and stablecoins.",
]
ex_cols = st.columns(len(examples))
for col, ex in zip(ex_cols, examples):
    if col.button(ex, key=f"ex_{ex[:12]}", width="stretch"):
        st.session_state.query_input = ex
        st.rerun()

run = st.button("◢  Run agent", type="primary", width="stretch")

# ── Run pipeline ──
if run and query.strip():
    qid = new_query_id()
    stepper = st.empty()

    def steps(active: int, labels):
        rows = []
        for i, lab in enumerate(labels):
            cls = "active" if i == active else ("" if i > active else "active")
            mark = ('<span class="np-spin"></span>' if i == active
                    else (icon("check") if i < active else f'{i+1}'))
            rows.append(f'<div class="np-step {cls}"><span class="s">{mark}</span>{esc(lab)}</div>')
        return '<div class="np-card">' + "".join(rows) + "</div>"

    labels = ["Planning — selecting data sources", "Budget pre-check",
              "Executing x402 payments", "Synthesizing the answer"]

    stepper.markdown(steps(0, labels), unsafe_allow_html=True)
    plan_res = _run_async(plan_stage(qid, query.strip(), max_spend, forced))

    if plan_res.error:
        e = plan_res.error
        stepper.empty()
        st.markdown(f"""
        <div class="np-card" style="border-color:var(--danger);">
          <div class="np-eyebrow" style="color:var(--danger);">⛔ {esc(e.error)}</div>
          <div style="color:var(--fg); font-size:15px;">{esc(e.message)}</div>
          <div class="mono" style="color:var(--fg-dim); font-size:12px; margin-top:8px;">
            spent ${e.daily_spent:.4f} / cap ${e.daily_cap:.2f} · ${e.remaining:.4f} remaining</div>
        </div>""", unsafe_allow_html=True)
        st.stop()

    plan = plan_res.plan
    time.sleep(0.25)
    stepper.markdown(steps(2, labels), unsafe_allow_html=True)

    # Plan card
    chosen = " ".join(
        f'<span class="np-pill" style="color:var(--fg);"><span class="np-dot"></span>{esc(sid)} '
        f'· ${registry.get_by_id(sid).price_usdc:.3f}</span>'
        for sid in plan.sources if registry.get_by_id(sid))
    st.markdown(f"""
    <div class="np-card glow">
      <div class="np-eyebrow">Plan · estimated ${plan.estimated_cost:.4f}</div>
      <div style="color:var(--fg); line-height:1.6; margin-bottom:10px;">{esc(plan.reasoning)}</div>
      <div class="np-chips">{chosen}</div>
    </div>""", unsafe_allow_html=True)

    # Execute (animate result cards progressively)
    outcome = _run_async(execute_stage(plan))
    st.markdown('<div class="np-eyebrow" style="margin-top:6px;">x402 settlements</div>',
                unsafe_allow_html=True)
    feed = st.empty()
    cards = ""
    for r in outcome.results:
        if r.success:
            cls, ic = "ok", "check"
            txn = f'txn {esc(r.txn_hash)}' if r.txn_hash else "delivered"
        elif r.error and r.error.startswith("skipped_budget"):
            cls, ic = "skip", "skip"
            txn = "skipped · budget guard"
        else:
            cls, ic = "fail", "x"
            txn = esc((r.error or "failed")[:60])
        cost_cls = "zero" if r.cost_usdc == 0 or not r.success else ""
        cards += f"""
        <div class="np-src {cls}">
          <div class="ico">{icon(ic)}</div>
          <div class="meta"><div class="ep">{esc(endpoint_path(r.endpoint))}</div>
            <div class="txn">{txn}</div></div>
          <div class="np-cost {cost_cls}">${r.cost_usdc:.3f}</div>
        </div>"""
        feed.markdown(cards, unsafe_allow_html=True)
        time.sleep(0.35)

    # Synthesize
    time.sleep(0.2)
    stepper.markdown(steps(3, labels), unsafe_allow_html=True)
    synthesis, status = _run_async(
        synthesize_stage(qid, query.strip(), outcome, len(plan.sources)))
    stepper.empty()

    status_color = {"complete": "var(--accent)", "partial": "var(--warn)",
                    "failed": "var(--danger)"}.get(status, "var(--accent)")
    st.markdown(f"""
    <div class="np-card glow">
      <div class="np-eyebrow" style="color:{status_color};">
        ◆ Answer · {esc(status)} · total ${outcome.total_cost:.4f} · confidence {esc(synthesis.confidence)}</div>
      <div class="np-answer">{esc(synthesis.answer)}</div>
    </div>""", unsafe_allow_html=True)

    st.session_state.history.insert(0, {
        "query": query.strip(), "cost": outcome.total_cost,
        "sources": len([r for r in outcome.results if r.success]), "status": status,
    })

# ── Activity log ──
st.markdown("<hr>", unsafe_allow_html=True)
col_a, col_b = st.columns([3, 2])

with col_a:
    st.markdown('<div class="np-eyebrow">Spend log</div>', unsafe_allow_html=True)
    logs = _run_async(get_all_logs(limit=12))
    if logs:
        rows = [{
            "endpoint": r["endpoint"],
            "cost": f'${r["cost_usdc"]:.3f}',
            "ok": "✓" if r["success"] else "✗",
            "txn": (r["txn_hash"] or "—")[:16] + ("…" if r["txn_hash"] else ""),
            "time": r["created_at"][11:19],
        } for r in logs]
        st.dataframe(rows, width="stretch", hide_index=True)
    else:
        st.markdown('<div class="np-card" style="color:var(--fg-dim);">No spend yet — run a query above.</div>',
                    unsafe_allow_html=True)

with col_b:
    st.markdown('<div class="np-eyebrow">This session</div>', unsafe_allow_html=True)
    total = sum(h["cost"] for h in st.session_state.history)
    st.markdown(f"""
    <div class="np-card np-stat">
      <div class="v">${total:.4f}</div><div class="l">spent this session</div>
      <div style="height:10px;"></div>
      <div class="v">{len(st.session_state.history)}</div><div class="l">queries run</div>
    </div>""", unsafe_allow_html=True)
