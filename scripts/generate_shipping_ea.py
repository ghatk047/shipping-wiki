#!/usr/bin/env python3
"""
generate_shipping_ea.py — 10 enterprise-architecture diagrams for the Shipping Process Wiki.

Run after the process wiki is populated:
    python3 scripts/generate_shipping_ea.py            # all 10
    python3 scripts/generate_shipping_ea.py --id ea-03 # one
    python3 scripts/generate_shipping_ea.py --no-verify

Shares config, sanitiser, GitHub helpers and the sidebar builder with
generate_shipping_wiki.py, so both files must sit in the same scripts/ folder.
Token comes from the environment:  export GITHUB_TOKEN=ghp_xxx
"""

import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from generate_shipping_wiki import (  # noqa: E402
    EA_DIAGRAMS, EA_DIR_SLUG, PAGES_BASE, SITE_TITLE,
    EA_W, EA_H, DIAGRAM_DIR, IMG_DIR, DATA_DIR,
    DEPTH_EA, DEPTH_EA_IDX,
    SYSTEM_PROMPT, SYSTEM_PROMPT_JSON, dump_raw, ollama_call, extract_json, sanitise_mermaid, render_mermaid,
    gh_push_file, push_deploy, verify_live, page_shell, esc, sys_tags, prefix,
    finalize_svg,
    log, load_tracker, PRIMARY_MODEL, FALLBACK_MODEL,
)

EA_JSON_SHAPE = """{
  "description": "3-4 sentence architecture description in the Maersk context",
  "systems": ["Navis N4", "SAP S/4HANA", "Microsoft Azure"],
  "layers": ["External Feeds", "Booking", "Operations Control", "Data"]
}"""

# Form reference — a diagram from a different industry, so the model copies the
# CONSTRUCT and not the content.
FORM_EXAMPLE = """%%{init: {'theme':'base','themeVariables':{'fontSize':'13px','fontFamily':'Inter, Arial, sans-serif'}}}%%
flowchart TB

  subgraph EXT["\U0001F310 External Feeds"]
    direction LR
    FAA["FAA SWIM\\nNOTAMs - TFRs - Slots"]
    WX["Jeppesen WSI\\nWeather - Winds - SIGMETs"]
  end

  subgraph DISPATCH["\U0001F4CB Dispatch and Flight Planning"]
    direction TB
    FP["NAVBLUE Lido\\nFlight plan - Fuel calc"]
    WB["Weight and Balance\\nLoad control - ZFW calc"]
    FAA -->|"NOTAMs - flow programs"| FP
    FP -->|"fuel load"| WB
  end

  subgraph NOC["\U0001F5A5 Operations Control"]
    direction TB
    SCOUT["Avtec Scout NOC\\nFlight watch - Gate - Crew"]
    DELAY["Delay Management\\nRoot cause - OTP tracking"]
    SCOUT -->|"delay codes"| DELAY
  end

  WX -->|"meteorological data"| SCOUT
  WB -->|"final load"| SCOUT

  classDef ext  fill:#e0f2fe,stroke:#0284c7,color:#0c4a6e
  classDef disp fill:#fff7ed,stroke:#ea580c,color:#7c2d12
  classDef noc  fill:#003366,color:#fff,stroke:#003366
  classDef key  fill:#ff6600,color:#fff,stroke:#ff6600

  class FAA,WX ext
  class FP,WB disp
  class SCOUT noc
  class DELAY key"""


def ea_prompt(ea_id, title, scope):
    return (
        f"{SYSTEM_PROMPT}\n\n"
        f"Produce an enterprise architecture diagram for A.P. Moller-Maersk.\n"
        f"  Diagram ID : {ea_id.upper()}\n"
        f"  Title      : {title}\n"
        f"  Scope      : {scope}\n\n"
        "STRUCTURE — copy this construct exactly. It is from a different industry, so take\n"
        "the FORM and none of the content:\n\n"
        f"{FORM_EXAMPLE}\n\n"
        "REQUIREMENTS:\n"
        "- flowchart TB at the top level. Every subgraph declares its own direction TB or LR.\n"
        "- 5 to 7 subgraphs named for architecture layers or stages, each title starting with\n"
        "  one emoji, e.g. External Parties, Booking and Commercial, Terminal and Vessel,\n"
        "  Customs and Compliance, Finance, Data and Analytics.\n"
        "- 22 to 30 nodes. EVERY node label is two lines: real vendor or product name, then\n"
        "  a literal backslash-n, then 2 or 3 capabilities separated by hyphens.\n"
        "  Example: NAVIS[\"Navis N4 TOS\\nYard plan - Crane sequencing - Gate moves\"]\n"
        "- EVERY arrow carries a label naming the data that flows, in the form\n"
        "  A -->|\"booking confirmation\"| B. Unlabelled arrows are not acceptable.\n"
        "- Intra-layer arrows go inside their subgraph. Cross-layer arrows go after the last\n"
        "  subgraph closes.\n"
        "- Finish with 5 to 7 classDef lines and matching class assignment lines. Use\n"
        "  fill:#002b5c,color:#fff,stroke:#002b5c for the single most important Maersk system\n"
        "  and a lighter palette for the rest.\n"
        "- Use only real systems: Navis N4, SAP S/4HANA, Veson Nautical IMOS, CargOPTIMIZER,\n"
        "  Maersk.com, CargoSphere, Salesforce, Manhattan WMS, Senator TMS, Descartes,\n"
        "  MIC Customs, Remote Container Management, NavTOR, SHIPNET Amos, COMPAS, Synergi\n"
        "  Life, Workday, Microsoft Azure, Power BI, MarineTraffic AIS, port community\n"
        "  systems, customs authority systems, alliance partner systems.\n"
        "- Node IDs start with a letter. No parentheses, ampersands or angle brackets\n"
        "  anywhere in a label. Never use <br/> — use a literal backslash-n.\n\n"
        f"Return exactly this JSON shape and nothing else:\n{EA_JSON_SHAPE}\n"
    )


def generate_ea(ea_id, title, scope):
    """Call 1 — narrative and systems only."""
    prompt = (
        f"{SYSTEM_PROMPT_JSON}\n\n"
        f"Describe the enterprise architecture for A.P. Moller-Maersk.\n"
        f"  Diagram ID : {ea_id.upper()}\n  Title : {title}\n  Scope : {scope}\n\n"
        "Name 8 to 12 real systems that appear in this architecture.\n"
        "Do NOT include a mermaid field — the diagram is requested separately.\n\n"
        f"Return exactly this JSON shape and nothing else:\n{EA_JSON_SHAPE}\n"
    )
    for i, model in enumerate((PRIMARY_MODEL, PRIMARY_MODEL, FALLBACK_MODEL)):
        try:
            raw = ollama_call(prompt, model, temperature=0.25 + 0.1 * i)
            data = extract_json(raw, required=("systems",))
            if data and data.get("systems"):
                return data
            dump_raw(f"{ea_id}-json-{i+1}", raw)
            log(f"{ea_id}: unusable JSON from {model} (try {i+1}/3)", "WARN")
        except Exception as exc:
            log(f"{ea_id}: Ollama error on {model} — {exc}", "WARN")
        time.sleep(2)
    return None


def generate_ea_mermaid(ea_id, title, scope, data, attempt=0):
    """Call 2 — raw Mermaid only."""
    sys_list = ", ".join(str(s) for s in data.get("systems", [])[:12])
    prompt = ea_prompt(ea_id, title, scope) + (
        f"\n\nSystems that must appear as nodes: {sys_list}\n"
        "Output the raw Mermaid and nothing else. No JSON, no fences, no commentary.\n"
    )
    models = [PRIMARY_MODEL, PRIMARY_MODEL, FALLBACK_MODEL]
    model = models[min(attempt, len(models) - 1)]
    try:
        return sanitise_mermaid(fix_breaks(ollama_call(prompt, model,
                                                       temperature=0.2 + 0.1 * attempt)))
    except Exception as exc:
        log(f"{ea_id}: mermaid call failed on {model} — {exc}", "WARN")
        return None


def ea_richness(mmd):
    if not mmd:
        return 0, {}
    m = {
        "nodes":     len(re.findall(r'^\s*\w+\[', mmd, flags=re.MULTILINE)),
        "labelled":  mmd.count("-->|"),
        "subgraphs": mmd.count("subgraph"),
        "classdefs": mmd.count("classDef"),
    }
    score = (m["nodes"] >= 18) + (m["labelled"] >= 12) + (m["subgraphs"] >= 4) \
            + (m["classdefs"] >= 4)
    return score, m


def fix_breaks(mmd):
    """Convert HTML line breaks to Mermaid's \\n before the label sanitiser strips < >."""
    if not mmd:
        return mmd
    for tag in ("<br/>", "<br />", "<br>"):
        mmd = mmd.replace(tag, "\\n")
    return mmd


def render_ea(ea_id, title, scope, data):
    """Score up to 3 drafts, publish SVG for display and a PNG for download."""
    mmd_path = DIAGRAM_DIR / f"{ea_id}.mmd"
    svg_path = IMG_DIR / f"{ea_id}.svg"
    png_path = IMG_DIR / f"{ea_id}.png"

    best, best_score = None, -1
    for attempt in range(3):
        cand = generate_ea_mermaid(ea_id, title, scope, data, attempt=attempt)
        score, metrics = ea_richness(cand)
        if cand and score > best_score:
            best, best_score = cand, score
        log(f"  {ea_id} draft {attempt+1}: score {score}/4 {metrics}")
        if score >= 3:
            break
    if not best:
        return None, None
    if best_score < 2:
        log(f"  {ea_id}: diagram is thin (score {best_score}/4) — publishing anyway", "WARN")

    svg_ok = False
    for attempt in range(1, 4):
        svg_ok, info = render_mermaid(best, mmd_path, svg_path, EA_W, EA_H)
        if svg_ok:
            finalize_svg(svg_path)
            log(f"  {ea_id} rendered as SVG ({info})")
            break
        log(f"  {ea_id} SVG render attempt {attempt}/3 failed: {info}", "WARN")
        retry = generate_ea_mermaid(ea_id, title, scope, data, attempt=attempt)
        if retry:
            best = retry
    if not svg_ok:
        return None, None

    # PNG is best-effort: it only backs the download button
    png_out = None
    for w, h, scale in [(EA_W, EA_H, 2), (EA_W, EA_H, 1), (2560, 1440, 2)]:
        ok, info = render_mermaid(best, mmd_path, png_path, w, h, scale=scale)
        if ok:
            log(f"  {ea_id} PNG fallback at {w}x{h} scale {scale} ({info})")
            png_out = png_path
            break
    return svg_path, png_out


def build_ea_page(ea_id, title, scope, data):
    p = prefix(DEPTH_EA)
    main = f"""      <div class="page-header">
        <div class="breadcrumb">
          <a href="{p}index.html">Home</a> &rsaquo;
          <a href="../index.html">Enterprise Architecture</a>
        </div>
        <h1><span class="pid-badge org-badge-corp">EA</span> {ea_id.upper()} &mdash; {esc(title)}</h1>
        <p>{esc(scope)}</p>
      </div>

      <div class="card">
        <div class="card-header">&#x1F5FA; Architecture Diagram &mdash; 4K, click to zoom</div>
        <div class="card-body">
          <div class="diagram-wrap">
            <a href="{p}assets/img/{ea_id}.svg" data-lightbox data-title="{ea_id.upper()} {esc(title)}">
              <img src="{p}assets/img/{ea_id}.svg" alt="{ea_id.upper()} {esc(title)}">
            </a>
            <p>Vector diagram &mdash; stays sharp at any zoom &bull; Scroll to zoom &bull; Drag to pan
               &bull; <a href="{p}assets/img/{ea_id}.svg" download>Download SVG</a>
               &bull; <a href="{p}assets/img/{ea_id}.png" download>Download PNG</a></p>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">&#x1F4CB; Diagram Details</div>
        <div class="card-body">
          <table class="attr-table">
            <tr><th>Diagram ID</th><td>{ea_id.upper()}</td></tr>
            <tr><th>Title</th><td>{esc(title)}</td></tr>
            <tr><th>Scope</th><td>{esc(scope)}</td></tr>
            <tr><th>Key Systems</th><td>{sys_tags(data.get('systems'))}</td></tr>
            <tr><th>Description</th><td>{esc(data.get('description', scope))}</td></tr>
          </table>
        </div>
      </div>
"""
    return page_shell(f"{ea_id.upper()} &mdash; {esc(title)}", "Enterprise Architecture",
                      DEPTH_EA, main, active_ea=ea_id)


def build_ea_index():
    cards = []
    for ea_id, title, scope in EA_DIAGRAMS:
        cards.append(f"""    <div class="ea-card">
      <h4><a href="{ea_id}/index.html">{ea_id.upper()} &mdash; {esc(title)}</a></h4>
      <p>{esc(scope)}</p>
    </div>""")
    main = f"""      <div class="page-header">
        <div class="breadcrumb"><a href="{prefix(DEPTH_EA_IDX)}index.html">Home</a></div>
        <h1>&#x1F5FA; Enterprise Architecture</h1>
        <p>System landscape and data flow diagrams for the Maersk ocean, logistics and
           terminal estate. Every diagram renders at 4K &mdash; click to zoom.</p>
      </div>
      <div class="ea-grid">
{chr(10).join(cards)}
      </div>
"""
    return page_shell("Enterprise Architecture", "Enterprise Architecture",
                      DEPTH_EA_IDX, main, active_ea="index")


def main():
    ap = argparse.ArgumentParser(description="Shipping wiki EA diagram generator")
    ap.add_argument("--id", help="single diagram, e.g. ea-03")
    ap.add_argument("--no-verify", action="store_true")
    args = ap.parse_args()

    for d in (DATA_DIR, DIAGRAM_DIR, IMG_DIR):
        d.mkdir(parents=True, exist_ok=True)

    targets = EA_DIAGRAMS
    if args.id:
        wanted = args.id.lower()
        targets = [d for d in EA_DIAGRAMS if d[0] == wanted]
        if not targets:
            sys.exit(f"Unknown diagram {args.id}. Valid: {', '.join(d[0] for d in EA_DIAGRAMS)}")

    done, failed = [], []
    try:
        for ea_id, title, scope in targets:
            log(f"── {ea_id.upper()} — {title}")
            data = generate_ea(ea_id, title, scope)
            if not data:
                failed.append(ea_id)
                continue
            svg, png = render_ea(ea_id, title, scope, data)
            if not svg:
                log(f"{ea_id}: diagram failed after 3 attempts — skipped", "ERROR")
                failed.append(ea_id)
                continue
            if not gh_push_file(f"assets/img/{ea_id}.svg", svg.read_bytes(),
                                f"Add {ea_id.upper()} diagram"):
                failed.append(ea_id)
                continue
            if png:
                gh_push_file(f"assets/img/{ea_id}.png", png.read_bytes(),
                             f"Add {ea_id.upper()} PNG download")
            if not gh_push_file(f"{EA_DIR_SLUG}/{ea_id}/index.html",
                                build_ea_page(ea_id, title, scope, data),
                                f"Add {ea_id.upper()} {title}"):
                failed.append(ea_id)
                continue
            done.append(ea_id)
            log(f"  pushed {ea_id}")
    except KeyboardInterrupt:
        log("interrupted — publishing what is done", "WARN")

    gh_push_file(f"{EA_DIR_SLUG}/index.html", build_ea_index(), "Update EA index")
    push_deploy()

    if done and not args.no_verify:
        url = f"{PAGES_BASE}/{EA_DIR_SLUG}/{done[-1]}/index.html"
        log("verified live: " + url if verify_live(url) else f"could not verify {url}")

    log(f"EA run complete — {len(done)} published, {len(failed)} failed"
        + (f" ({', '.join(failed)})" if failed else ""))


if __name__ == "__main__":
    main()
