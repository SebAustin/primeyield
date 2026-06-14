# ruff: noqa: E501 — embedded CSS/HTML template lines exceed the line limit
"""Server-rendered portfolio + provenance dashboard (Day 6-7).

Renders a single self-contained HTML page (no external assets, so it works
offline during the demo). It reads the same sources as the JSON API:
  - state/deployments.json  -> vault + token allocation
  - agent/db.load_decisions -> the decision / provenance log

The decisions table auto-refreshes from GET /portfolio/decisions so a live
agent cycle shows up without reloading the page.
"""

from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

ROOT = Path(__file__).resolve().parents[2]
DEPLOYMENTS_PATH = ROOT / "state" / "deployments.json"

router = APIRouter(tags=["dashboard"])

_EXPLORER = {
    5003: "https://sepolia.mantlescan.xyz",
    5000: "https://mantlescan.xyz",
}


def _load_deployments() -> dict[str, Any]:
    if not DEPLOYMENTS_PATH.exists():
        return {}
    try:
        return json.loads(DEPLOYMENTS_PATH.read_text())
    except json.JSONDecodeError:
        return {}


def _explorer_base(chain_id: int | None) -> str | None:
    return _EXPLORER.get(chain_id or 0)


def _addr_cell(addr: str | None, base: str | None) -> str:
    if not addr:
        return '<span class="muted">not deployed</span>'
    short = f"{addr[:8]}…{addr[-6:]}"
    if base:
        return f'<a href="{base}/address/{escape(addr)}" target="_blank" rel="noopener">{short}</a>'
    return f"<code>{short}</code>"


def _network_label(chain_id: int | None) -> str:
    return {5003: "Mantle Sepolia", 5000: "Mantle Mainnet", 31337: "Local (anvil)"}.get(
        chain_id or 0, f"chain {chain_id}" if chain_id else "no deployment"
    )


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard() -> str:
    from agent.db import load_decisions

    deps = _load_deployments()
    chain_id = deps.get("chainId")
    base = _explorer_base(chain_id)
    tokens = deps.get("tokens", {}) or {}
    decisions = load_decisions()

    token_cards = "".join(
        f"""<article class="token">
              <span class="token__sym">{escape(sym)}</span>
              <span class="token__addr">{_addr_cell(addr, base)}</span>
            </article>"""
        for sym, addr in tokens.items()
    ) or '<p class="muted">No tokens deployed yet — run <code>make day7</code>.</p>'

    rows = _render_rows(decisions, base)

    return _PAGE.format(
        network=escape(_network_label(chain_id)),
        chain_id=escape(str(chain_id) if chain_id is not None else "—"),
        vault=_addr_cell(deps.get("vault"), base),
        decision_log=_addr_cell(deps.get("decisionLog"), base),
        token_cards=token_cards,
        decision_count=len(decisions),
        rows=rows,
    )


def _render_rows(decisions: list[dict[str, Any]], base: str | None) -> str:
    if not decisions:
        return (
            '<tr><td colspan="5" class="muted center">'
            "No decisions recorded yet — run an agent cycle to populate the log."
            "</td></tr>"
        )
    out = []
    for rec in reversed(decisions[-25:]):  # newest first, cap for display
        did = escape(str(rec.get("decision_id", "—")))
        status = escape(str(rec.get("approval_status", "—")))
        rhash = str(rec.get("rationale_hash") or "")
        hash_cell = f"<code>{rhash[:12]}…</code>" if rhash else '<span class="muted">—</span>'
        swaps = _fmt_swaps(rec.get("plan_json"))
        txs = rec.get("onchain_txs") or []
        tx_cell = _fmt_txs(txs, base)
        out.append(
            f"<tr>"
            f'<td><code>{did}</code></td>'
            f'<td><span class="pill pill--{status}">{status}</span></td>'
            f"<td>{swaps}</td>"
            f"<td>{hash_cell}</td>"
            f"<td>{tx_cell}</td>"
            f"</tr>"
        )
    return "".join(out)


def _fmt_swaps(plan_json: dict[str, Any] | None) -> str:
    if not plan_json:
        return '<span class="muted">—</span>'
    swaps = plan_json.get("swaps", []) or []
    if not swaps:
        return '<span class="muted">no swaps</span>'
    parts = []
    for s in swaps:
        src = escape(str(s.get("from_asset", s.get("from", "?"))))
        dst = escape(str(s.get("to", "?")))
        pct = s.get("amount_pct", "?")
        try:
            pct = f"{float(pct) * 100:.0f}%"
        except (TypeError, ValueError):
            pct = escape(str(pct))
        parts.append(f'<span class="swap">{src}<span class="arrow">→</span>{dst} {pct}</span>')
    return " ".join(parts)


def _fmt_txs(txs: list[Any], base: str | None) -> str:
    if not txs:
        return '<span class="muted">—</span>'
    links = []
    for t in txs:
        s = str(t)
        tx = s.rsplit("/tx/", 1)[-1] if "/tx/" in s else s
        short = f"{tx[:8]}…"
        if base:
            links.append(
                f'<a href="{base}/tx/{escape(tx)}" target="_blank" rel="noopener">{short}</a>'
            )
        else:
            links.append(f"<code>{short}</code>")
    return " ".join(links)


# --- single self-contained page; {placeholders} filled above -----------------
_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>PrimeYield — Control Room</title>
<style>
  :root {{
    --bg: oklch(16% 0.02 260);
    --surface: oklch(21% 0.025 260);
    --surface-2: oklch(25% 0.03 260);
    --line: oklch(32% 0.03 260);
    --text: oklch(96% 0.01 260);
    --muted: oklch(68% 0.02 260);
    --accent: oklch(78% 0.16 160);
    --accent-2: oklch(72% 0.15 250);
    --warn: oklch(80% 0.15 85);
    --space: clamp(1rem, 0.6rem + 2vw, 2.5rem);
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: var(--bg); color: var(--text);
    font: 16px/1.5 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
    -webkit-font-smoothing: antialiased;
  }}
  .wrap {{ max-width: 1100px; margin: 0 auto; padding: var(--space); }}
  header.top {{
    display: flex; align-items: baseline; justify-content: space-between;
    gap: 1rem; flex-wrap: wrap; margin-bottom: 2rem;
  }}
  .brand {{ display: flex; align-items: baseline; gap: 0.6rem; }}
  .brand h1 {{
    font-size: clamp(1.6rem, 1rem + 2vw, 2.4rem); margin: 0; letter-spacing: -0.02em;
    font-weight: 800;
  }}
  .brand .dot {{ color: var(--accent); }}
  .badge {{
    font-size: 0.8rem; color: var(--accent); border: 1px solid var(--line);
    background: var(--surface); padding: 0.3rem 0.7rem; border-radius: 999px;
    display: inline-flex; align-items: center; gap: 0.45rem;
  }}
  .badge::before {{
    content: ""; width: 7px; height: 7px; border-radius: 50%;
    background: var(--accent); box-shadow: 0 0 0 0 var(--accent);
    animation: pulse 2.4s infinite;
  }}
  @keyframes pulse {{
    0% {{ box-shadow: 0 0 0 0 oklch(78% 0.16 160 / 0.5); }}
    70% {{ box-shadow: 0 0 0 8px oklch(78% 0.16 160 / 0); }}
    100% {{ box-shadow: 0 0 0 0 oklch(78% 0.16 160 / 0); }}
  }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1rem; }}
  .card {{
    background: var(--surface); border: 1px solid var(--line);
    border-radius: 14px; padding: 1.1rem 1.2rem;
  }}
  .card h2 {{
    font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.12em;
    color: var(--muted); margin: 0 0 0.7rem; font-weight: 600;
  }}
  .card .big {{ font-size: 1.5rem; font-weight: 700; }}
  .tokens {{ display: flex; flex-wrap: wrap; gap: 0.6rem; }}
  .token {{
    display: flex; flex-direction: column; gap: 0.2rem; background: var(--surface-2);
    border: 1px solid var(--line); border-radius: 10px; padding: 0.6rem 0.8rem; min-width: 130px;
  }}
  .token__sym {{ font-weight: 700; color: var(--accent-2); }}
  .token__addr {{ font-size: 0.8rem; }}
  section.log {{ margin-top: 2rem; }}
  section.log h2 {{
    font-size: 1.1rem; margin: 0 0 0.2rem; display: flex; align-items: baseline; gap: 0.6rem;
  }}
  section.log .sub {{ color: var(--muted); font-size: 0.85rem; margin: 0 0 1rem; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.9rem; }}
  thead th {{
    text-align: left; color: var(--muted); font-weight: 600; font-size: 0.72rem;
    text-transform: uppercase; letter-spacing: 0.08em;
    padding: 0.5rem 0.7rem; border-bottom: 1px solid var(--line);
  }}
  tbody td {{ padding: 0.7rem; border-bottom: 1px solid var(--surface-2); vertical-align: top; }}
  tbody tr:hover {{ background: var(--surface); }}
  code {{ font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: 0.82em; color: var(--accent-2); }}
  a {{ color: var(--accent); text-decoration: none; border-bottom: 1px solid transparent; transition: border-color .15s; }}
  a:hover {{ border-color: var(--accent); }}
  .muted {{ color: var(--muted); }}
  .center {{ text-align: center; padding: 2rem 0.7rem; }}
  .swap {{ white-space: nowrap; }}
  .swap .arrow {{ color: var(--accent); margin: 0 0.2rem; }}
  .pill {{
    font-size: 0.72rem; padding: 0.18rem 0.55rem; border-radius: 999px;
    border: 1px solid var(--line); text-transform: capitalize;
  }}
  .pill--approved, .pill--auto {{ color: var(--accent); border-color: var(--accent); }}
  .pill--pending {{ color: var(--warn); border-color: var(--warn); }}
  .pill--rejected {{ color: oklch(70% 0.16 25); border-color: oklch(70% 0.16 25); }}
  footer {{ margin-top: 2.5rem; color: var(--muted); font-size: 0.8rem; }}
</style>
</head>
<body>
<div class="wrap">
  <header class="top">
    <div class="brand">
      <h1>PrimeYield<span class="dot">.</span></h1>
      <span class="muted">RWA yield-rotation agent</span>
    </div>
    <span class="badge">{network} · chainId {chain_id}</span>
  </header>

  <div class="grid">
    <div class="card">
      <h2>Vault (ERC-4626)</h2>
      <div class="big">{vault}</div>
    </div>
    <div class="card">
      <h2>DecisionLog</h2>
      <div class="big">{decision_log}</div>
    </div>
    <div class="card">
      <h2>Decisions recorded</h2>
      <div class="big" id="count">{decision_count}</div>
    </div>
  </div>

  <div class="card" style="margin-top:1rem">
    <h2>Rotation assets</h2>
    <div class="tokens">{token_cards}</div>
  </div>

  <section class="log">
    <h2>Decision &amp; provenance log</h2>
    <p class="sub">Each decision commits <code>keccak256(rationale)</code> on-chain — auto-refreshes every 10s.</p>
    <table>
      <thead>
        <tr><th>Decision</th><th>Approval</th><th>Swaps</th><th>Rationale hash</th><th>On-chain tx</th></tr>
      </thead>
      <tbody id="rows">{rows}</tbody>
    </table>
  </section>

  <footer>
    Endpoints: <a href="/docs">/docs</a> ·
    <a href="/portfolio/allocation">/portfolio/allocation</a> ·
    <a href="/portfolio/decisions">/portfolio/decisions</a>
  </footer>
</div>

<script>
  // Lightweight live refresh of the decision count from the JSON API.
  async function refresh() {{
    try {{
      const r = await fetch('/portfolio/decisions');
      if (!r.ok) return;
      const data = await r.json();
      const el = document.getElementById('count');
      if (el && typeof data.total === 'number') el.textContent = data.total;
    }} catch (e) {{ /* offline / server restarting — keep last view */ }}
  }}
  setInterval(refresh, 10000);
</script>
</body>
</html>"""
