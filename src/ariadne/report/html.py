"""Self-contained interactive workup report (ADR-0017).

Renders a single offline ``report.html`` from a persisted workup's artifacts
(``note.md`` + ``provenance.jsonl`` + ``citations.json`` + optional
``tradecraft.json`` / ``governance.json``). No server, no network, no runtime
deps — CSS + JS + data are embedded inline so the file opens with a double-click
and survives an air-gap. The note stays the source of truth; this is a *view*.

Design: provenance is the hero. Every ``[cite:gN]`` is a clickable chip that
reveals the exact query that grounds it; a radial "thread" graph ties the entity
to its evidence by source. Structured on Shneiderman's overview -> zoom/filter ->
details-on-demand.
"""

from __future__ import annotations

import html as _html
import json
import re
from pathlib import Path
from typing import Any

from ariadne.evaluation.reconcile import _CONFLICT_CUES, _CORROBORATION_CUES
from ariadne.evaluation.utilization import context_utilization
from ariadne.provenance.hook import _source_label

_CITE_RE = re.compile(r"\[cite:(g\d+)\]")
_HEADER_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET_RE = re.compile(r"^[-*]\s+(.*)$")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def _extract_reconciliation(note: str) -> dict[str, list[str]]:
    """Classify note sentences as cross-store corroboration vs conflict.

    Uses the same cue vocabularies as the reconciliation eval (``reconcile.py``)
    so the panel reflects the scored criterion. Conflict cues win over
    corroboration when a sentence carries both (flag disagreements).
    """
    corroborations: list[str] = []
    conflicts: list[str] = []
    text = _CITE_RE.sub("", note).replace("**", "").replace("\n", " ")
    for raw in _SENTENCE_RE.split(text):
        s = raw.strip().lstrip("#-* ").strip()
        if not s:
            continue
        low = s.lower()
        if any(cue in low for cue in _CONFLICT_CUES):
            conflicts.append(s)
        elif any(cue in low for cue in _CORROBORATION_CUES):
            corroborations.append(s)
    return {"corroborations": corroborations, "conflicts": conflicts}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _read_ledger(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _inline(text: str) -> str:
    """Escape one line of note prose, then re-introduce bold/italic + cite chips."""
    s = _html.escape(text)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", s)
    return _CITE_RE.sub(
        lambda m: f'<button class="cite" data-cite="{m.group(1)}">{m.group(1)}</button>', s
    )


def _render_note_html(note: str) -> str:
    """Minimal, dependency-free Markdown -> HTML, split into collapsible sections.

    Each ``##`` heading becomes a ``<details>`` so the (often very long) note breaks
    into per-section components the analyst can fold. The verbose "Provenance"
    section defaults collapsed (it's redundant with the evidence drawer + trajectory).
    """
    pre: list[str] = []  # content before the first H2 (the H1 title)
    sections: list[dict] = []
    in_ul = False

    def buf() -> list[str]:
        return sections[-1]["body"] if sections else pre

    def close_ul() -> None:
        nonlocal in_ul
        if in_ul:
            buf().append("</ul>")
            in_ul = False

    for raw in note.splitlines():
        line = raw.rstrip()
        if not line.strip():
            close_ul()
            continue
        header = _HEADER_RE.match(line)
        if header:
            close_ul()
            level, txt = len(header.group(1)), header.group(2)
            if level == 2:  # section boundary
                sections.append(
                    {"title": _inline(txt), "collapsed": "provenance" in txt.lower(), "body": []}
                )
            else:
                buf().append(f"<h{level}>{_inline(txt)}</h{level}>")
            continue
        bullet = _BULLET_RE.match(line)
        if bullet:
            if not in_ul:
                buf().append("<ul>")
                in_ul = True
            buf().append(f"<li>{_inline(bullet.group(1))}</li>")
            continue
        close_ul()
        buf().append(f"<p>{_inline(line)}</p>")
    close_ul()

    html = ["".join(pre)] if any(p.strip() for p in pre) else []
    for s in sections:
        op = "" if s["collapsed"] else " open"
        html.append(
            f'<details class="nsec"{op}><summary>{s["title"]}</summary>'
            f'<div class="nbody">{"".join(s["body"])}</div></details>'
        )
    return "\n".join(html)


def extract_report_data(workup_dir: str | Path) -> dict[str, Any]:
    """Read a persisted workup directory into a JSON-serializable report payload."""
    d = Path(workup_dir)
    note = (d / "note.md").read_text(encoding="utf-8") if (d / "note.md").exists() else ""
    cites = _load_json(d / "citations.json") or {}
    entity = cites.get("entity") or d.name
    ledger = []
    for e in _read_ledger(d / "provenance.jsonl"):
        tool = e.get("tool", "")
        tool_input = e.get("tool_input", {}) or {}
        query = (
            tool_input.get("query")
            or tool_input.get("sql")
            or json.dumps(tool_input, ensure_ascii=False)
        )
        ledger.append(
            {
                "id": e.get("id", ""),
                "tool": tool,
                "source": _source_label(tool),
                "query": query,
                "excerpt": str(e.get("response_excerpt", "")),
            }
        )
    return {
        "entity": entity,
        "note_html": _render_note_html(note),
        "citations": {
            k: cites.get(k)
            for k in ("ok", "cited", "dangling", "unused", "unsupported", "uncited", "coverage")
        },
        "ledger": ledger,
        "tradecraft": _load_json(d / "tradecraft.json"),
        "governance": _load_json(d / "governance.json"),
        "subgraph": _load_json(d / "subgraph.json"),
        "reconciliation": _extract_reconciliation(note),
        "utilization": context_utilization(note, ledger),
        # Optional, present only when `ariadne eval` / `ariadne rubric` were run.
        "evaluation": _load_json(d / "eval.json"),
        "rubric": _load_json(d / "rubric.json"),
    }


def render_report(workup_dir: str | Path) -> str:
    """Return the full self-contained HTML report for ``workup_dir``."""
    data = extract_report_data(workup_dir)
    # Guard the JSON against premature </script> termination inside the data island.
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    title = _html.escape(str(data["entity"]))
    return _TEMPLATE.replace("__ENTITY_TITLE__", title).replace("/*__REPORT_DATA__*/", payload)


def write_report(workup_dir: str | Path) -> Path:
    """Write ``report.html`` into ``workup_dir`` and return its path."""
    out = Path(workup_dir) / "report.html"
    out.write_text(render_report(workup_dir), encoding="utf-8")
    return out


_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ariadne · __ENTITY_TITLE__</title>
<script>
/* Set the theme before paint (no flash). Default: saved choice, else OS preference. */
(function(){try{var t=localStorage.getItem("ariadne-theme")||
 (matchMedia&&matchMedia("(prefers-color-scheme: light)").matches?"light":"dark");
 document.documentElement.dataset.theme=t;}catch(e){document.documentElement.dataset.theme="dark";}})();
</script>
<style>
:root{
  --bg:#0b0d12; --bg2:#0e1118; --panel:#13161f; --panel2:#171b26;
  --line:#242a38; --ink:#e9e5d8; --soft:#b9bdc9; --muted:#7c8190;
  --thread:#e0a73c; --graph:#69b6d6; --relational:#b58ce0; --text:#76d3a4;
  --ok:#76d3a4; --bad:#e8746e;
  --serif:"Iowan Old Style","Palatino Linotype",Palatino,"Book Antiqua",Georgia,serif;
  --sans:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Helvetica,Arial,sans-serif;
  --mono:ui-monospace,"SF Mono","JetBrains Mono",Menlo,Consolas,monospace;
  --grain:#fff; --grainOp:.035; --qbg:#0a0c11;
}
/* Light theme — warm parchment "dossier in daylight"; same gold thread accent. */
:root[data-theme=light]{
  --bg:#f1ece0; --bg2:#faf6ec; --panel:#fcf9f1; --panel2:#f4eee1;
  --line:#dcd4c2; --ink:#20222b; --soft:#4c4f59; --muted:#6c7079;
  --thread:#a9741a; --graph:#1f6f93; --relational:#7a4fb0; --text:#1f8a5b;
  --ok:#1f8a5b; --bad:#bf463e; --grain:#000; --grainOp:.045; --qbg:#fbf7ee;
}
*{box-sizing:border-box}
html,body{margin:0;height:100%}
body{
  background:
    radial-gradient(1200px 600px at 80% -10%, #15324022, transparent 60%),
    radial-gradient(900px 500px at -10% 10%, #2a1f3a22, transparent 55%),
    var(--bg);
  color:var(--ink); font-family:var(--sans); line-height:1.5;
  -webkit-font-smoothing:antialiased;
}
body::before{content:"";position:fixed;inset:0;pointer-events:none;opacity:var(--grainOp);z-index:1;
  background-image:radial-gradient(var(--grain) 1px,transparent 1px);background-size:3px 3px;}
a{color:var(--thread)}
.wrap{max-width:1280px;margin:0 auto;padding:0 28px 80px}

/* Masthead */
header.top{position:sticky;top:0;z-index:20;backdrop-filter:blur(8px);
  background:linear-gradient(#0b0d12ee,#0b0d12bb);border-bottom:1px solid var(--line)}
.top .row{max-width:1280px;margin:0 auto;padding:16px 28px;display:flex;align-items:baseline;gap:18px;flex-wrap:wrap}
.mark{font-family:var(--serif);font-size:15px;letter-spacing:.42em;text-transform:uppercase;color:var(--thread)}
.mark b{font-weight:600}
.crumb{color:var(--muted);font-size:12px;letter-spacing:.22em;text-transform:uppercase}
.tgl{margin-left:auto;font-family:var(--mono);font-size:11.5px;letter-spacing:.08em;
  color:var(--soft);background:var(--panel2);border:1px solid var(--line);border-radius:999px;
  padding:6px 14px;cursor:pointer;transition:all .18s}
.tgl:hover{color:var(--ink);border-color:var(--thread);box-shadow:0 0 0 3px #e0a73c1f}
h1.entity{font-family:var(--serif);font-weight:600;font-size:30px;letter-spacing:.01em;margin:0}
.entity small{display:block;font-family:var(--sans);font-size:11px;letter-spacing:.32em;
  text-transform:uppercase;color:var(--muted);margin-bottom:4px;font-weight:600}

/* Dashboard */
.dash{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin:26px 0 8px}
.stat{background:linear-gradient(180deg,var(--panel),var(--bg2));border:1px solid var(--line);
  border-radius:14px;padding:16px 18px;position:relative;overflow:hidden}
.stat .k{font-size:10.5px;letter-spacing:.24em;text-transform:uppercase;color:var(--muted);font-weight:700}
.stat .v{font-family:var(--serif);font-size:30px;margin-top:8px;line-height:1}
.stat .sub{font-size:11.5px;color:var(--soft);margin-top:6px}
.stat{cursor:pointer} .stat:hover{border-color:var(--muted)}
.stat .info{color:var(--muted);font-size:10px;vertical-align:middle}
.stat:hover .info{color:var(--thread)}
.statdef{font-size:11.5px;color:var(--soft);line-height:1.5;margin-top:0;max-height:0;overflow:hidden;
  opacity:0;transition:max-height .3s ease,opacity .3s,margin-top .3s}
.stat.open .statdef{max-height:200px;opacity:1;margin-top:11px}
.stat.open{border-color:var(--thread)}
.stat .rail{position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--thread)}
.stat.ok .rail{background:var(--ok)} .stat.bad .rail{background:var(--bad)}
.pill{display:inline-flex;align-items:center;gap:6px;font-size:11px;font-weight:700;
  letter-spacing:.06em;padding:3px 9px;border-radius:999px;border:1px solid currentColor}
.pill.ok{color:var(--ok)} .pill.bad{color:var(--bad)}

/* Layout */
/* single-column report: full-width bands stack cleanly (no tall-left / blank-right) */
.grid{display:flex;flex-direction:column;gap:24px;margin-top:24px}
#graph,#netgraph{max-height:62vh}
/* fullscreen graph */
#graph-card.fs{position:fixed;inset:18px;z-index:60;margin:0;max-width:none;overflow:auto;
  box-shadow:0 40px 90px #000a}
#graph-card.fs #graph,#graph-card.fs #netgraph{max-height:84vh}
.gscrim{position:fixed;inset:0;background:#000a;opacity:0;pointer-events:none;transition:opacity .25s;z-index:55}
.gscrim.open{opacity:1;pointer-events:auto}
.fsbtn{font-family:var(--mono);font-size:12px;color:var(--soft);background:var(--panel2);
  border:1px solid var(--line);border-radius:8px;width:30px;height:24px;cursor:pointer;margin-left:6px;
  vertical-align:middle;transition:all .16s}
.fsbtn:hover{color:var(--thread);border-color:var(--thread)}
.card{background:linear-gradient(180deg,var(--panel),var(--bg2));border:1px solid var(--line);border-radius:16px}
.card>h2{font-family:var(--sans);font-size:11px;letter-spacing:.28em;text-transform:uppercase;
  color:var(--muted);font-weight:700;margin:0;padding:16px 22px;border-bottom:1px solid var(--line)}
.note{padding:6px 26px 26px;font-family:var(--serif);font-size:17px;color:var(--ink);
  max-width:900px;margin:0 auto}  /* readable measure within the full-width card */
.note h1,.note h2,.note h3{font-family:var(--serif);color:var(--ink);line-height:1.25;margin:26px 0 8px}
.note h1{font-size:24px} .note h2{font-size:20px;color:var(--thread)} .note h3{font-size:17px;letter-spacing:.02em}
.note p{margin:10px 0} .note ul{margin:8px 0 8px 2px;padding-left:20px} .note li{margin:6px 0}
.nsec{border-top:1px solid var(--line)} .nsec:first-of-type{border-top:none}
.nsec>summary{list-style:none;cursor:pointer;display:flex;align-items:center;gap:10px;
  font-family:var(--serif);font-size:20px;font-weight:600;color:var(--thread);padding:16px 0 6px}
.nsec>summary::-webkit-details-marker{display:none}
.nsec>summary::before{content:"\25B8";font-size:13px;color:var(--muted);transition:transform .2s;flex:none}
.nsec[open]>summary::before{transform:rotate(90deg)}
.nsec>summary:hover{color:var(--ink)} .nsec>summary:hover::before{color:var(--thread)}
.nbody{padding:2px 0 8px 2px}
.note-all{float:right;font-family:var(--sans);font-size:10px;letter-spacing:.12em;text-transform:uppercase;
  font-weight:700;color:var(--muted);background:transparent;border:1px solid var(--line);
  border-radius:999px;padding:4px 11px;cursor:pointer;transition:all .16s}
.note-all:hover{color:var(--thread);border-color:var(--thread)}
.note strong{color:var(--ink);font-weight:700} .note em{color:var(--soft)}
.note .blk-hot{background:#e0a73c14;box-shadow:inset 3px 0 0 var(--thread);border-radius:4px;
  transition:background .25s}
/* Uncited-claim spotlight — the citation gate flagged these. WCAG 1.4.1: never
   colour alone — red rail + a ⚠ tag + a title, all grayscale-legible; the pulse
   runs a few times then settles, and only when motion is allowed. */
.note .uncited-claim{background:#e8746e14;box-shadow:inset 3px 0 0 var(--bad);
  border-radius:5px;padding:4px 12px;margin:8px -12px}
.note .uncited-tag{display:inline-block;font-family:var(--sans);font-size:9px;font-weight:800;
  letter-spacing:.13em;color:var(--bad);border:1px solid var(--bad);border-radius:999px;
  padding:1px 8px;margin-right:9px;vertical-align:middle;text-transform:uppercase;white-space:nowrap}
@media (prefers-reduced-motion:no-preference){
  .note .uncited-claim{animation:uncitedPulse 2.4s ease-in-out 3}
  @keyframes uncitedPulse{0%,100%{box-shadow:inset 3px 0 0 var(--bad),0 0 0 0 #e8746e00}
    50%{box-shadow:inset 3px 0 0 var(--bad),0 0 16px 1px #e8746e66}}
}

/* Cite chips */
.cite{font-family:var(--mono);font-size:11px;font-weight:600;color:var(--thread);
  background:#e0a73c14;border:1px solid #e0a73c44;border-radius:6px;padding:1px 6px;margin:0 1px;
  cursor:pointer;vertical-align:baseline;transition:all .15s;letter-spacing:.02em}
.cite:hover,.cite.sel{background:var(--thread);color:#1a1205;border-color:var(--thread);
  box-shadow:0 0 0 3px #e0a73c33}

/* Graph */
.gtabs{float:right;display:inline-flex;gap:6px}
.gtab{font-family:var(--sans);font-size:10px;letter-spacing:.12em;text-transform:uppercase;font-weight:700;
  color:var(--muted);background:transparent;border:1px solid var(--line);border-radius:999px;
  padding:4px 11px;cursor:pointer;transition:all .16s}
.gtab:hover{color:var(--ink)} .gtab.on{color:var(--thread);border-color:var(--thread);background:#e0a73c14}
.graphwrap{padding:10px 14px 18px}
#graph,#netgraph{width:100%;height:auto;display:block}
.nlabel{font-family:var(--sans);font-size:10px;fill:var(--ink)}
.elabel{font-family:var(--mono);font-size:8.5px;fill:var(--muted);letter-spacing:.04em}
.elabel-bg{fill:var(--panel);opacity:.86}
.legend{display:flex;gap:16px;flex-wrap:wrap;padding:0 22px 16px;font-size:11px;color:var(--soft)}
.legend i{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;vertical-align:middle}
.node{cursor:pointer}
.node circle{transition:r .15s,opacity .2s,stroke-width .15s}
.node text{font-family:var(--mono);font-size:10px;fill:var(--soft);pointer-events:none}
.edge{fill:none;stroke:var(--line);stroke-width:1.4;transition:stroke .2s,stroke-width .2s,opacity .2s}
.edge.hot{stroke:var(--thread);stroke-width:2.4}
.dim{opacity:.16}
.nlabel{transition:opacity .16s}
.node.lab-min .nlabel{opacity:0}
.node.lab-min:hover .nlabel,.node.nbr .nlabel,.node.foc .nlabel{opacity:1}
.node.dim .nlabel{opacity:0}
.node.nbr circle,.node:hover circle{stroke-width:2.6}
.node.foc circle{stroke-width:2.8}
.elabelg{transition:opacity .15s}
.elabelg:not(.show){opacity:0;pointer-events:none}
.leg-rel{font-family:var(--mono);color:var(--thread);letter-spacing:.05em;font-size:10.5px}
#netgraph{cursor:grab}
.node.match circle{stroke-width:2.8}
.node.match .nlabel{opacity:1}
.gsearch{background:var(--panel);border:1px solid var(--line);color:var(--ink);font:inherit;
  font-size:12px;padding:3px 10px;border-radius:6px;width:118px;outline:none;
  transition:border-color .15s,width .2s}
.gsearch::placeholder{color:var(--muted)}
.gsearch:focus{border-color:var(--thread);width:158px}

/* Evidence drawer */
.drawer{position:fixed;right:0;top:0;bottom:0;width:min(460px,92vw);z-index:40;
  background:linear-gradient(180deg,var(--panel),var(--bg2));border-left:1px solid var(--line);
  box-shadow:-30px 0 60px #0009;transform:translateX(100%);transition:transform .32s cubic-bezier(.22,1,.36,1);
  display:flex;flex-direction:column}
.drawer.open{transform:none}
.drawer .dh{padding:18px 22px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:12px}
.drawer .dh .gid{font-family:var(--mono);font-size:18px;color:var(--thread);font-weight:700}
.drawer .x{margin-left:auto;background:none;border:1px solid var(--line);color:var(--soft);
  border-radius:8px;width:32px;height:32px;cursor:pointer;font-size:16px}
.drawer .x:hover{color:var(--ink);border-color:var(--muted)}
.drawer .body{padding:20px 22px;overflow:auto}
.srcbadge{font-size:10px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;
  padding:3px 9px;border-radius:999px}
.lbl{font-size:10.5px;letter-spacing:.24em;text-transform:uppercase;color:var(--muted);
  font-weight:700;margin:18px 0 7px}
.qbox{font-family:var(--mono);font-size:12.5px;line-height:1.55;color:var(--graph);white-space:pre-wrap;
  background:var(--qbg);border:1px solid var(--line);border-radius:10px;padding:14px;overflow:auto}
.exbox{font-family:var(--mono);font-size:12px;line-height:1.55;color:var(--soft);white-space:pre-wrap;
  background:var(--qbg);border:1px solid var(--line);border-radius:10px;padding:14px;max-height:240px;overflow:auto}
.scrim{position:fixed;inset:0;background:#0008;opacity:0;pointer-events:none;transition:opacity .3s;z-index:35}
.scrim.open{opacity:1;pointer-events:auto}

/* Entity detail drawer (network node -> attributes + relationships) */
.attr{display:flex;justify-content:space-between;gap:14px;font-size:13px;line-height:1.4;
  padding:9px 12px;border:1px solid var(--line);border-radius:9px;background:var(--qbg);margin-bottom:7px}
.attr .ak{color:var(--muted);font-family:var(--mono);font-size:11px;letter-spacing:.06em;
  text-transform:uppercase;flex:none}
.attr .av{color:var(--ink);text-align:right;word-break:break-word}
.rel{display:flex;align-items:center;gap:10px;font-size:13px;padding:9px 12px;border:1px solid var(--line);
  border-radius:9px;background:var(--panel2);margin-bottom:7px;cursor:pointer;
  transition:border-color .16s,transform .16s;width:100%;text-align:left}
.rel:hover{border-color:var(--thread);transform:translateX(2px)}
.rel .rd{color:var(--thread);font-size:15px;flex:none;font-family:var(--mono)}
.rel .rt{font-family:var(--mono);font-size:10px;color:var(--soft);letter-spacing:.04em}
.rel .rn{color:var(--ink);font-weight:600}
.rel .rl{color:var(--muted);font-size:10.5px;margin-left:auto;flex:none;
  text-transform:uppercase;letter-spacing:.1em}
.drawer-empty{color:var(--muted);font-size:12.5px;font-style:italic;padding:2px 2px 10px}

/* Reconciliation */
.recon{display:grid;grid-template-columns:1fr 1fr;gap:18px;padding:18px 22px}
@media(max-width:760px){.recon{grid-template-columns:1fr}}
.recol h3{font-family:var(--sans);font-size:11px;letter-spacing:.16em;text-transform:uppercase;
  font-weight:700;margin:0 0 11px}
.recol.corr h3{color:var(--ok)} .recol.conf h3{color:var(--bad)}
.rec-item{font-family:var(--serif);font-size:14.5px;color:var(--ink);line-height:1.5;
  padding:10px 13px;border-radius:9px;background:var(--panel2);margin-bottom:8px;border-left:3px solid var(--line)}
.recol.corr .rec-item{border-left-color:var(--ok)} .recol.conf .rec-item{border-left-color:var(--bad)}
.rec-empty{color:var(--muted);font-size:12.5px;font-style:italic}

/* Analytic evaluation panel (eval.json + rubric.json, present only when scored) */
.evsub{font-family:var(--sans);font-size:10.5px;letter-spacing:.18em;text-transform:uppercase;
  color:var(--muted);font-weight:700;padding:16px 22px 0}
.evgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(116px,1fr));gap:12px;padding:11px 22px 4px}
.evm{background:var(--panel2);border:1px solid var(--line);border-radius:11px;padding:11px 13px}
.evm .ek{font-size:9.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);font-weight:700}
.evm .ev{font-family:var(--serif);font-size:21px;margin-top:6px;line-height:1}
.evm .ev .pill{font-size:11px;vertical-align:middle}
.rubricw{padding:6px 22px 20px}
.rov{font-family:var(--serif);font-size:15px;color:var(--soft);margin:4px 0 14px}
.rov b{color:var(--thread);font-size:22px}
.rdim{border:1px solid var(--line);border-radius:10px;padding:11px 14px;margin-bottom:9px;background:var(--panel2)}
.rdim .rh{display:flex;align-items:center;gap:10px}
.rdim .rk{font-family:var(--sans);font-weight:700;font-size:12px;letter-spacing:.03em;text-transform:capitalize}
.rdim .rs{margin-left:auto;font-family:var(--mono);font-size:12px;color:var(--thread);font-weight:700}
.rdim .rr{font-size:12.5px;color:var(--soft);line-height:1.5;margin-top:7px}
.rbar{height:5px;border-radius:3px;background:var(--line);margin-top:9px;overflow:hidden}
.rbar i{display:block;height:100%;background:var(--thread)}

/* Trajectory */
.traj{display:flex;gap:0;align-items:stretch;overflow-x:auto;padding:18px 22px}
.step{min-width:118px;border:1px solid var(--line);border-radius:12px;padding:11px 13px;margin-right:10px;
  cursor:pointer;background:var(--panel2);transition:border-color .2s,transform .2s;flex:0 0 auto}
.step:hover{border-color:var(--thread);transform:translateY(-2px)}
.step .sg{font-family:var(--mono);font-weight:700;color:var(--thread);font-size:13px}
.step .ss{font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin-top:5px}
.step .sq{font-family:var(--mono);font-size:10.5px;color:var(--soft);margin-top:7px;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.foot{color:var(--muted);font-size:11px;text-align:center;margin-top:40px;letter-spacing:.06em}
[data-src=graph]{color:var(--graph)} [data-src=relational]{color:var(--relational)}
[data-src=text]{color:var(--text)} [data-src=evidence]{color:var(--soft)}
.bgs-graph{background:#69b6d622;color:var(--graph)} .bgs-relational{background:#b58ce022;color:var(--relational)}
.bgs-text{background:#76d3a422;color:var(--text)} .bgs-evidence{background:#7c819022;color:var(--soft)}
.reveal{opacity:0;transform:translateY(10px);animation:rise .6s cubic-bezier(.22,1,.36,1) forwards}
@keyframes rise{to{opacity:1;transform:none}}
</style>
</head>
<body>
<header class="top"><div class="row">
  <span class="mark"><b>ARIADNE</b></span>
  <span class="crumb">analytic workup · provenance-grounded</span>
  <button id="theme-toggle" class="tgl" aria-pressed="false" title="Toggle light / dark">◑ Light</button>
</div></header>

<div class="wrap">
  <div class="reveal" style="margin-top:30px">
    <h1 class="entity"><small>Target entity</small><span id="entity">__ENTITY_TITLE__</span></h1>
  </div>

  <section class="dash reveal" id="dash" style="animation-delay:.05s"></section>

  <div class="grid">
    <section class="card reveal" style="animation-delay:.12s">
      <h2>Analytic note · click a <span style="color:var(--thread)">cite</span> to trace it
        <button class="note-all" id="note-all">Collapse all</button></h2>
      <div class="note" id="note"></div>
    </section>
    <section class="card reveal" id="graph-card" style="animation-delay:.18s">
      <h2>Graph
        <span class="gtabs" id="gtabs">
          <input id="net-search" class="gsearch" type="search" placeholder="Find a node…"
            aria-label="Search the entity network" autocomplete="off" spellcheck="false">
          <button class="gtab" data-view="net">Entity network</button>
          <button class="gtab" data-view="prov">Provenance</button>
          <button class="fsbtn" id="fs-btn" title="Fullscreen (Esc to exit)" aria-label="Toggle fullscreen graph">&#9974;</button>
        </span>
      </h2>
      <div class="graphwrap">
        <svg id="netgraph" preserveAspectRatio="xMidYMid meet"></svg>
        <svg id="graph" preserveAspectRatio="xMidYMid meet" style="display:none"></svg>
      </div>
      <div class="legend" id="legend"></div>
    </section>
  </div>

  <section class="card reveal" id="recon-card" style="margin-top:24px;animation-delay:.22s">
    <h2>Reconciliation · where the stores agree vs. disagree</h2>
    <div class="recon" id="recon"></div>
  </section>

  <section class="card reveal" id="eval-card" style="margin-top:24px;display:none">
    <h2>Analytic evaluation · scored against ground truth</h2>
    <div id="eval-body"></div>
  </section>

  <section class="card reveal" style="margin-top:24px;animation-delay:.24s">
    <h2>Evidence trajectory · the order the agent gathered ground truth</h2>
    <div class="traj" id="traj"></div>
  </section>

  <div class="foot">Self-contained · offline · generated by Ariadne from note.md + provenance.jsonl — the note is the source of truth.</div>
</div>

<div class="gscrim" id="gscrim"></div>
<div class="scrim" id="scrim"></div>
<aside class="drawer" id="drawer" aria-hidden="true">
  <div class="dh"><span class="gid" id="d-gid"></span><span class="srcbadge" id="d-src"></span>
    <button class="x" id="d-x" aria-label="Close">×</button></div>
  <div class="body">
    <div class="lbl">Evidence query</div><div class="qbox" id="d-q"></div>
    <div class="lbl">Returned excerpt</div><div class="exbox" id="d-ex"></div>
  </div>
</aside>
<aside class="drawer" id="edrawer" aria-hidden="true">
  <div class="dh"><span class="gid" id="e-name"></span><span class="srcbadge" id="e-type"></span>
    <button class="x" id="e-x" aria-label="Close">×</button></div>
  <div class="body">
    <div class="lbl">Attributes</div><div id="e-attrs"></div>
    <div class="lbl">Relationships</div><div id="e-rels"></div>
  </div>
</aside>

<script id="ariadne-report-data" type="application/json">/*__REPORT_DATA__*/</script>
<script>
"use strict";
const DATA = JSON.parse(document.getElementById("ariadne-report-data").textContent);
const byId = Object.fromEntries(DATA.ledger.map(e => [e.id, e]));
const $ = s => document.querySelector(s);

// Which gN are actually cited in the note, and how often (for node weight).
const citeCounts = {};
document.getElementById("note").innerHTML = DATA.note_html || "<p style='color:var(--muted)'>No note.</p>";
document.querySelectorAll("#note .cite").forEach(b => {
  const id = b.dataset.cite; citeCounts[id] = (citeCounts[id]||0)+1;
  b.addEventListener("click", () => selectEvidence(id, b));
});
// Expand / collapse all note sections
const noteAll=$("#note-all");
if(noteAll){
  const secs=()=>document.querySelectorAll("#note .nsec");
  const sync=()=>{noteAll.textContent=[...secs()].some(d=>!d.open)?"Expand all":"Collapse all";};
  noteAll.addEventListener("click",()=>{const open=[...secs()].some(d=>!d.open);
    secs().forEach(d=>{d.open=open;}); sync();});
  secs().forEach(d=>d.addEventListener("toggle",sync));
  sync();
}
// A cite inside a collapsed section: open it so the highlight is visible
document.querySelectorAll("#note .cite").forEach(b=>b.addEventListener("click",()=>{
  const det=b.closest("details.nsec"); if(det&&!det.open) det.open=true;}));

// ---- Spotlight uncited claims so the analyst sees WHICH claim the gate flagged ----
(function(){
  const uncited=(DATA.citations&&DATA.citations.uncited)||[];
  if(!uncited.length) return;
  const norm=s=>(s||"").toLowerCase().replace(/\[cite:g\d+\]/g,"").replace(/[^a-z0-9]+/g," ").trim();
  const targets=uncited.map(norm).filter(t=>t.length>8);
  document.querySelectorAll("#note p, #note li, #note h1, #note h2, #note h3").forEach(el=>{
    if(!targets.some(u=>norm(el.textContent).includes(u))) return;
    el.classList.add("uncited-claim");
    el.setAttribute("title","No [cite] resolves this claim — flagged by the citation gate.");
    const tag=document.createElement("span"); tag.className="uncited-tag"; tag.textContent="⚠ Uncited";
    el.insertBefore(tag, el.firstChild);
    const det=el.closest("details.nsec"); if(det&&!det.open) det.open=true;  // reveal if collapsed
  });
})();

// ---- Dashboard ----
const c = DATA.citations || {};
const nCited=(c.cited||[]).length, nUncited=(c.uncited||[]).length,
      nDangling=(c.dangling||[]).length, nUnsup=(c.unsupported||[]).length;
const gov = DATA.governance || null, tc = DATA.tradecraft || null;
const govOk = gov ? gov.ok !== false : null;
function stat(cls, k, v, sub, def){return `<div class="stat ${cls}" tabindex="0" role="button"
  aria-label="${k} — click for definition"><div class="rail"></div>
  <div class="k">${k} <span class="info">&#9432;</span></div><div class="v">${v}</div>
  <div class="sub">${sub}</div><div class="statdef">${def}</div></div>`;}
const cov = c.coverage || null;
let covStat = "";
if(cov && cov.after!=null){
  const after = Math.round(cov.after*100);
  let headline, sub;
  if(cov.before!=null && cov.gain!=null){
    const gain = Math.round(cov.gain*100);
    const passTxt = cov.passes!=null ? ` from ${cov.passes} repair pass${cov.passes===1?"":"es"}` : "";
    headline = `${Math.round(cov.before*100)}% &rarr; ${after}%`;
    sub = gain===0 ? `no change${passTxt}` : `${gain>0?"+":""}${gain} pts${passTxt}`;
  } else { headline = `${after}%`; sub = "raw G-Cite draft (no repair)"; }
  covStat = stat("","Citation coverage", headline, sub,
    "Of the note's citable claims, the share that carry a citation (structural coverage). "
    +"The P-Cite repair loop attaches missing cites after the draft, so this shows the raw "
    +"G-Cite coverage rising to the repaired coverage. Descriptive, never a pass/fail — the "
    +"citation gate is the binary check (ADR-0023).");
}
$("#dash").innerHTML = [
  stat(c.ok?"ok":"bad","Citation gate", c.ok?'<span class="pill ok">PASS</span>':'<span class="pill bad">FAIL</span>',
       `${nCited} cited · ${nUncited} uncited · ${nDangling} dangling`,
       "Does every claim in the note carry a [cite] that resolves to real retrieved evidence? "
       +"FAIL = a claim is uncited, or cites evidence that isn't in the ledger (dangling)."),
  covStat,
  stat("","Evidence calls", DATA.ledger.length, `${new Set(DATA.ledger.map(e=>e.source)).size} source(s) engaged`,
       "How many times the agent queried an evidence store (graph / relational / text) to ground "
       +"the note. More sources engaged = more cross-checking across the data."),
  DATA.utilization!=null ? stat("","Context utilization", Math.round(DATA.utilization*100)+"%",
       "retrieved evidence that grounded a claim",
       "Of the distinct evidence the agent retrieved, the share that grounded a cited claim. "
       +"Descriptive, never a pass/fail — exploratory and negative-confirmation retrieval "
       +"(checking alternatives, establishing an absence) legitimately lower it.") : "",
  gov!==null ? stat(govOk?"ok":"bad","Read-only contract", govOk?'<span class="pill ok">UPHELD</span>':'<span class="pill bad">VIOLATED</span>',
       `${(gov.write_attempts||[]).length} write attempt(s)`,
       "Did the agent only READ from the evidence stores? UPHELD = it never tried to modify the "
       +"data — the guarantee that an analysis can't tamper with its own sources.") : "",
  tc!==null ? stat("","ICD-203 tradecraft", (tc.standard_terms||[]).length,
       `${(tc.nonstandard_terms||[]).length} non-standard · confidence ${tc.has_confidence_statement?"stated":"—"}`,
       "Use of the Intelligence Community's standard estimative language (ICD-203: 'likely', "
       +"'probable', 'almost certain'…). Counts standard terms; flags vague hedges ('maybe') and "
       +"whether the note states its analytic confidence.") : "",
].join("");
document.querySelectorAll("#dash .stat").forEach(card=>{
  card.addEventListener("click",()=>card.classList.toggle("open"));
  card.addEventListener("keydown",e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();card.classList.toggle("open");}});
});

// ---- Provenance flow: entity -> source(s) -> evidence (tiered, always legible) ----
const SRC_COLORS={graph:"#69b6d6",relational:"#b58ce0",text:"#76d3a4",evidence:"#7c8190"};
const svg=$("#graph"); const NS="http://www.w3.org/2000/svg";
function el(t,a){const n=document.createElementNS(NS,t);for(const k in a)n.setAttribute(k,a[k]);return n;}
const sources=[...new Set(DATA.ledger.map(e=>e.source))];
const bySrc={}; sources.forEach(s=>bySrc[s]=[]); DATA.ledger.forEach(e=>bySrc[e.source].push(e));
// Three columns: entity | sources | evidence. Evidence is stacked vertically and
// grouped by source, so labels never collide regardless of how many calls there are.
const ROWH=26, TOP=30, W=600, H=Math.max(320, DATA.ledger.length*ROWH + TOP*2);
const xE=66, xS=250, xV=430;
svg.setAttribute("viewBox",`0 0 ${W} ${H}`);
const pos={}; let row=0;
sources.forEach(s=>{const ys=[];
  bySrc[s].forEach(e=>{const y=TOP+row*ROWH; pos[e.id]={x:xV,y}; ys.push(y); row++;});
  pos["src:"+s]={x:xS,y:ys.reduce((a,b)=>a+b,0)/ys.length};});
pos["entity"]={x:xE,y:H/2};
const eEls={};
function link(a,b,gid){const p1=pos[a],p2=pos[b],mx=(p1.x+p2.x)/2;
  const path=el("path",{class:"edge",d:`M${p1.x},${p1.y} C${mx},${p1.y} ${mx},${p2.y} ${p2.x},${p2.y}`});
  if(gid){path.dataset.gid=gid;(eEls[gid]=eEls[gid]||[]).push(path);} svg.appendChild(path);}
sources.forEach(s=>link("entity","src:"+s,null));
DATA.ledger.forEach(e=>link("src:"+e.source,e.id,e.id));
function node(id,x,y,r,color,label,onclick){
  const g=el("g",{class:"node",transform:`translate(${x},${y})`});
  g.appendChild(el("circle",{r:r,fill:color+"22",stroke:color,"stroke-width":1.6}));
  if(label){const t=el("text",{x:r+8,dy:"0.32em","text-anchor":"start"});t.textContent=label;g.appendChild(t);}
  g.dataset.node=id; if(onclick){g.style.cursor="pointer";g.addEventListener("click",onclick);}
  svg.appendChild(g); return g;}
const ent=node("entity",xE,H/2,18,"#e0a73c","",null);
ent.appendChild(Object.assign(el("text",{"text-anchor":"middle",dy:"0.34em",
  style:"fill:#1a1205;font-weight:700;font-size:10px"}),{textContent:(DATA.entity||"?").slice(0,3).toUpperCase()}));
const elbl=el("text",{x:xE,y:H/2+32,"text-anchor":"middle",style:"fill:var(--soft);font-size:10px"});
elbl.textContent=(DATA.entity||"").slice(0,20); svg.appendChild(elbl);
sources.forEach(s=>node("src:"+s,pos["src:"+s].x,pos["src:"+s].y,11,SRC_COLORS[s]||"#7c8190",
  s+" ("+bySrc[s].length+")",null));
DATA.ledger.forEach(e=>{const n=citeCounts[e.id]||0,r=Math.min(4+n*1.5,9);
  const g=node(e.id,pos[e.id].x,pos[e.id].y,r,SRC_COLORS[e.source]||"#7c8190",
    e.id+(n?" · "+n+"×":""),()=>selectEvidence(e.id,null));
  g.addEventListener("mouseenter",()=>{if(!$("#drawer").classList.contains("open"))provTrace(e.id,e.source);});
  g.addEventListener("mouseleave",()=>{if(!$("#drawer").classList.contains("open"))provClear();});});
const PROV_LEGEND=sources.map(s=>`<span><i style="background:${SRC_COLORS[s]}"></i>${s}</span>`).join("")
  + `<span><i style="background:#e0a73c"></i>entity</span><span style="color:var(--muted)">size = times cited · click any node</span>`;

// ---- Entity network: the real traversed subgraph (force-directed) ----
const NET_COLORS={Person:"#69b6d6",person:"#69b6d6",Unit:"#e0a73c",unit:"#e0a73c",
  Site:"#76d3a4",site:"#76d3a4",Org:"#b58ce0",org:"#b58ce0",team:"#b58ce0",Topic:"#e0746e"};
const netColor=l=>NET_COLORS[l]||"#9aa0ad";
let NET_LEGEND="", hasNet=false;
// Fruchterman-Reingold layout — ideal spacing scales with the canvas, so the
// network fills whatever size it's drawn at (panel or fullscreen). Re-callable.
function renderNet(W,H){
  const sg=DATA.subgraph;
  if(!sg||!sg.nodes||!sg.nodes.length) return false;
  const gsvg=$("#netgraph"); gsvg.innerHTML="";
  gsvg.setAttribute("viewBox",`0 0 ${W} ${H}`); gsvg._baseVb=[0,0,W,H];
  const n=sg.nodes.length;
  const nodes=sg.nodes.map((d,i)=>{const a=i/n*2*Math.PI, R=Math.min(W,H)*0.33;
    return {...d,x:W/2+Math.cos(a)*R,y:H/2+Math.sin(a)*R};});
  nodes.forEach(d=>{d.vx=0;d.vy=0;});
  const ix=Object.fromEntries(nodes.map((d,i)=>[d.id,i]));
  const links=sg.edges.filter(e=>ix[e.src]!=null&&ix[e.dst]!=null&&e.src!==e.dst);
  // Edge rest length (and matching repulsion) scale with the canvas, so the same
  // graph spreads to fill a bigger fullscreen while staying readable in the panel.
  const REST=Math.max(118,Math.min(W,H)*0.30), REP=REST*REST*0.95;
  for(let it=0;it<360;it++){
    for(let i=0;i<n;i++)for(let j=i+1;j<n;j++){
      let dx=nodes[i].x-nodes[j].x,dy=nodes[i].y-nodes[j].y,d2=dx*dx+dy*dy+.01,d=Math.sqrt(d2),f=REP/d2;
      nodes[i].vx+=f*dx/d;nodes[i].vy+=f*dy/d;nodes[j].vx-=f*dx/d;nodes[j].vy-=f*dy/d;}
    links.forEach(l=>{let a=nodes[ix[l.src]],b=nodes[ix[l.dst]],dx=b.x-a.x,dy=b.y-a.y,
      d=Math.sqrt(dx*dx+dy*dy)+.01,f=(d-REST)*0.02,fx=f*dx/d,fy=f*dy/d;
      a.vx+=fx;a.vy+=fy;b.vx-=fx;b.vy-=fy;});
    nodes.forEach(nd=>{nd.vx+=(W/2-nd.x)*0.004;nd.vy+=(H/2-nd.y)*0.004;
      nd.x+=nd.vx*0.8;nd.y+=nd.vy*0.8;nd.vx*=0.82;nd.vy*=0.82;
      nd.x=Math.max(44,Math.min(W-44,nd.x));nd.y=Math.max(36,Math.min(H-36,nd.y));});
  }
  const NS2="http://www.w3.org/2000/svg";
  const mk=(t,a)=>{const e=document.createElementNS(NS2,t);for(const kk in a)e.setAttribute(kk,a[kk]);return e;};
  const escL=s=>String(s).replace(/[<&>]/g,c=>({"<":"&lt;","&":"&amp;",">":"&gt;"}[c]));
  // emails -> local-part; long names truncated, so labels stop colliding
  const shortName=s=>{s=String(s||"");const at=s.indexOf("@");if(at>0)s=s.slice(0,at);
    return s.length>24?s.slice(0,23)+"…":s;};
  // adjacency + degree (degree drives node size and label prominence)
  const adj={},deg={}; nodes.forEach(d=>{adj[d.id]=new Set([d.id]);deg[d.id]=0;});
  links.forEach(l=>{adj[l.src].add(l.dst);adj[l.dst].add(l.src);deg[l.src]++;deg[l.dst]++;});
  const maxDeg=Math.max(1,...nodes.map(d=>deg[d.id]));
  // Homogeneous edges (one relationship type) carry no per-edge information, so the legend
  // states the type and we draw NO edge labels (kills the "EMAILED x N" noise). Mixed types
  // keep labels; on a large graph they're revealed only for an active node's incident edges.
  const edgeTypes=[...new Set(links.map(l=>l.type))],homogeneous=edgeTypes.length<=1;
  const labelAll=n<=14;  // small graph: all node labels legible at once; large: target + on hover

  links.forEach(l=>{const a=nodes[ix[l.src]],b=nodes[ix[l.dst]];
    gsvg.appendChild(mk("path",{class:"edge",d:`M${a.x},${a.y} L${b.x},${b.y}`,
      "data-pair":l.src+"|"+l.dst}));});
  if(!homogeneous){
    const elabels=links.map(l=>{const a=nodes[ix[l.src]],b=nodes[ix[l.dst]];
      return {x:(a.x+b.x)/2,y:(a.y+b.y)/2,t:l.type,w:l.type.length*5.2+8,pair:l.src+"|"+l.dst};});
    for(let it=0;it<90;it++){let moved=false;  // nudge overlapping labels apart
      for(let i=0;i<elabels.length;i++)for(let j=i+1;j<elabels.length;j++){
        const A=elabels[i],B=elabels[j],ox=(A.w+B.w)/2-Math.abs(A.x-B.x),oy=14-Math.abs(A.y-B.y);
        if(ox>0&&oy>0){const dir=A.y===B.y?(i%2?1:-1):(A.y<B.y?-1:1),p=(oy/2+0.6)*dir;A.y+=p;B.y-=p;moved=true;}}
      if(!moved)break;}
    elabels.forEach(L=>{const g=mk("g",{class:"elabelg"+(labelAll?" show":""),"data-pair":L.pair});
      g.appendChild(mk("rect",{x:L.x-L.w/2,y:L.y-7.5,width:L.w,height:14,rx:3,class:"elabel-bg"}));
      const t=mk("text",{class:"elabel",x:L.x,y:L.y,dy:"0.32em","text-anchor":"middle"});
      t.textContent=L.t; g.appendChild(t); gsvg.appendChild(g);});
  }
  // shared highlight — used by transient hover AND committed (pinned) click
  function applyFocus(id){const on=adj[id];
    gsvg.querySelectorAll(".node").forEach(o=>{const k=on.has(o.dataset.node);
      o.classList.toggle("dim",!k); o.classList.toggle("nbr",k&&o.dataset.node!==id);
      o.classList.toggle("foc",o.dataset.node===id);});
    gsvg.querySelectorAll(".edge").forEach(p=>{const[s,t2]=p.dataset.pair.split("|"),inc=s===id||t2===id;
      p.classList.toggle("hot",inc); p.classList.toggle("dim",!(on.has(s)&&on.has(t2)));});
    if(!homogeneous&&!labelAll) gsvg.querySelectorAll(".elabelg").forEach(g=>{
      const[s,t2]=g.dataset.pair.split("|"); g.classList.toggle("show",s===id||t2===id);});}
  function clearFocus(){gsvg.querySelectorAll(".dim,.nbr,.foc").forEach(o=>o.classList.remove("dim","nbr","foc"));
    gsvg.querySelectorAll(".edge.hot").forEach(o=>o.classList.remove("hot"));
    if(!homogeneous&&!labelAll) gsvg.querySelectorAll(".elabelg.show").forEach(g=>g.classList.remove("show"));}
  gsvg._clearFocus=clearFocus; gsvg._focus=applyFocus;  // reused by closeEntity + node search

  nodes.forEach(d=>{const g=mk("g",{class:"node"+((labelAll||d.target)?"":" lab-min"),
      "data-node":d.id,"data-name":String(d.name||"").toLowerCase(),transform:`translate(${d.x},${d.y})`});
    const r=d.target?15:6+Math.round(deg[d.id]/maxDeg*7);  // 6..13 by degree centrality
    if(d.target) g.appendChild(mk("circle",{r:r+5,fill:"none",stroke:"#e0a73c",
      "stroke-width":1.5,"stroke-dasharray":"3 3",opacity:.8}));
    g.appendChild(mk("circle",{r,fill:netColor(d.label)+"33",stroke:netColor(d.label),"stroke-width":1.8}));
    const lab=mk("text",{class:"nlabel",y:r+12,"text-anchor":"middle"}); lab.textContent=shortName(d.name); g.appendChild(lab);
    g.addEventListener("mouseenter",()=>{if(!gsvg.dataset.pin)applyFocus(d.id);});
    g.addEventListener("mouseleave",()=>{if(!gsvg.dataset.pin)clearFocus();});
    g.addEventListener("click",ev=>{ev.stopPropagation();gsvg.dataset.pin=d.id;applyFocus(d.id);selectEntity(d.id);});
    gsvg.appendChild(g);});
  gsvg.onclick=ev=>{if(ev.target===gsvg){delete gsvg.dataset.pin;clearFocus();closeEntity();}};
  const labels=[...new Set(nodes.map(d=>d.label))];
  const relTxt=homogeneous?(edgeTypes[0]||"linked"):edgeTypes.length+" relationship types";
  NET_LEGEND=labels.map(l=>`<span><i style="background:${netColor(l)}"></i>${escL(l)}</span>`).join("")
    +`<span class="leg-rel">&mdash; ${escL(relTxt)} &mdash;</span>`
    +`<span style="color:var(--muted)">${n} entities · ${links.length} links · hover to trace · click to pin</span>`;
  return true;
}
const SG_N=(DATA.subgraph&&DATA.subgraph.nodes)?DATA.subgraph.nodes.length:0;
function panelDims(){return [1080, 400];}  // full-width band; the network spreads across it
function netDims(fs){return fs?[Math.min(1500,innerWidth-90),Math.min(840,innerHeight-200)]:panelDims();}
hasNet=renderNet(...panelDims());

// ---- Graph view tabs ----
function showView(v){
  const net=v==="net"&&hasNet;
  $("#netgraph").style.display=net?"block":"none";
  $("#graph").style.display=net?"none":"block";
  $("#legend").innerHTML=net?NET_LEGEND:PROV_LEGEND;
  const sb=$("#net-search"); if(sb)sb.style.display=net?"":"none";  // search applies to the network only
  document.querySelectorAll(".gtab").forEach(b=>b.classList.toggle("on",b.dataset.view===(net?"net":"prov")));
}
document.querySelectorAll(".gtab").forEach(b=>b.addEventListener("click",()=>showView(b.dataset.view)));
if(!hasNet){const t=document.querySelector('.gtab[data-view=net]'); if(t)t.style.display="none";}
showView(hasNet?"net":"prov");

// ---- Fullscreen graph toggle ----
const gcard=$("#graph-card"), gscrim=$("#gscrim"), fsb=$("#fs-btn");
function setFs(on){gcard.classList.toggle("fs",on); gscrim.classList.toggle("open",on);
  fsb.innerHTML=on?"&#10005;":"&#9974;"; fsb.title=on?"Exit fullscreen (Esc)":"Fullscreen (Esc to exit)";
  if(hasNet) requestAnimationFrame(()=>renderNet(...netDims(on)));}  // re-layout to fill the new size
fsb.addEventListener("click",()=>setFs(!gcard.classList.contains("fs")));
gscrim.addEventListener("click",()=>setFs(false));
document.addEventListener("keydown",e=>{if(e.key==="Escape"&&gcard.classList.contains("fs"))setFs(false);});

// ---- Node search: locate / highlight nodes by name, fade the rest (Linkurious-style) ----
const netSearch=$("#net-search");
if(netSearch) netSearch.addEventListener("input",()=>{
  const ng=$("#netgraph"); if(!ng) return;
  const q=netSearch.value.trim().toLowerCase(), nodes=[...ng.querySelectorAll(".node")];
  if(!q){delete ng.dataset.pin; if(ng._clearFocus)ng._clearFocus();
    nodes.forEach(o=>o.classList.remove("match")); return;}
  ng.dataset.pin="search";  // suppress hover-trace while a query is active
  let hitId=null,nHit=0;
  nodes.forEach(o=>{const hit=(o.dataset.name||"").includes(q);
    o.classList.toggle("match",hit); o.classList.toggle("dim",!hit); o.classList.remove("nbr","foc");
    if(hit){nHit++;hitId=o.dataset.node;}});
  ng.querySelectorAll(".edge").forEach(p=>{p.classList.add("dim");p.classList.remove("hot");});
  if(nHit===1&&ng._focus) ng._focus(hitId);  // exactly one hit -> reveal its trace
});

// ---- Zoom + pan the network (wheel zoom toward cursor · drag to pan · dbl-click reset) ----
(function(){const ng=$("#netgraph"); if(!ng) return;
  const vb=()=>ng.getAttribute("viewBox").split(" ").map(Number), setVb=a=>ng.setAttribute("viewBox",a.join(" "));
  ng.addEventListener("wheel",e=>{e.preventDefault(); const[x,y,w,h]=vb(), base=ng._baseVb||[0,0,w,h];
    const r=ng.getBoundingClientRect(), mx=x+(e.clientX-r.left)/r.width*w, my=y+(e.clientY-r.top)/r.height*h;
    const nw=Math.min(base[2]*1.05,Math.max(base[2]*0.15,w*(e.deltaY<0?0.86:1.163))), nh=nw*h/w;
    setVb([mx-(mx-x)*nw/w, my-(my-y)*nh/h, nw, nh]);},{passive:false});
  let drag=null;
  ng.addEventListener("pointerdown",e=>{if(e.target.closest(".node"))return;
    drag={x:e.clientX,y:e.clientY,v:vb()}; ng.style.cursor="grabbing";});
  window.addEventListener("pointermove",e=>{if(!drag)return; const[x,y,w,h]=drag.v,r=ng.getBoundingClientRect();
    setVb([x-(e.clientX-drag.x)/r.width*w, y-(e.clientY-drag.y)/r.height*h, w, h]);});
  window.addEventListener("pointerup",()=>{if(drag){drag=null; ng.style.cursor="";}});
  ng.addEventListener("dblclick",e=>{if(!e.target.closest(".node")&&ng._baseVb)setVb(ng._baseVb);});
})();

// ---- Provenance trace: highlight entity -> source -> evidence (hover preview + click) ----
function provTrace(id,source){
  document.querySelectorAll("#graph .node").forEach(n=>n.classList.toggle("dim",
    n.dataset.node!==id && n.dataset.node!=="entity" && n.dataset.node!=="src:"+source));
  document.querySelectorAll("#graph .edge").forEach(p=>{const on=p.dataset.gid===id;
    p.classList.toggle("hot",on); p.classList.toggle("dim", p.dataset.gid && !on);});
}
function provClear(){
  document.querySelectorAll("#graph .node.dim,#graph .edge.dim").forEach(n=>n.classList.remove("dim"));
  document.querySelectorAll("#graph .edge.hot").forEach(n=>n.classList.remove("hot"));
}
// ---- Evidence drawer (details-on-demand) ----
function selectEvidence(id, chip){
  const e=byId[id]; if(!e) return;
  $("#d-gid").textContent=id;
  const sb=$("#d-src"); sb.textContent=e.source; sb.className="srcbadge bgs-"+e.source;
  $("#d-q").textContent=e.query||"—"; $("#d-ex").textContent=e.excerpt||"—";
  closeEntity();  // never stack the evidence + entity drawers
  $("#drawer").classList.add("open"); $("#scrim").classList.add("open");
  $("#drawer").setAttribute("aria-hidden","false");
  // cross-highlight: chips, note blocks, graph
  document.querySelectorAll("#note .cite").forEach(b=>{
    const on=b.dataset.cite===id; b.classList.toggle("sel",on);
    const blk=b.closest("p,li,h1,h2,h3"); if(blk) blk.classList.toggle("blk-hot",on);
  });
  provTrace(id, e.source);  // scoped to the provenance svg (was global — dimmed the network too)
}
function closeDrawer(){
  $("#drawer").classList.remove("open"); $("#scrim").classList.remove("open");
  $("#drawer").setAttribute("aria-hidden","true");
  document.querySelectorAll(".sel").forEach(n=>n.classList.remove("sel"));
  document.querySelectorAll(".blk-hot").forEach(n=>n.classList.remove("blk-hot"));
  document.querySelectorAll(".dim").forEach(n=>n.classList.remove("dim"));
  document.querySelectorAll(".edge.hot").forEach(n=>n.classList.remove("hot"));
}
$("#d-x").addEventListener("click",closeDrawer);
$("#scrim").addEventListener("click",()=>{closeDrawer();closeEntity();});
document.addEventListener("keydown",e=>{if(e.key==="Escape"){closeDrawer();closeEntity();}});

// ---- Trajectory ----
$("#traj").innerHTML = DATA.ledger.map(e=>
  `<div class="step" data-gid="${e.id}"><div class="sg">${e.id}</div>
   <div class="ss" data-src="${e.source}">${e.source}</div>
   <div class="sq">${(e.query||"").replace(/[<&]/g,m=>({"<":"&lt;","&":"&amp;"}[m]))}</div></div>`).join("");
document.querySelectorAll("#traj .step").forEach(s=>
  s.addEventListener("click",()=>selectEvidence(s.dataset.gid,null)));

// ---- Reconciliation panel ----
const REC=DATA.reconciliation||{corroborations:[],conflicts:[]};
const esc=t=>t.replace(/[<&]/g,m=>({"<":"&lt;","&":"&amp;"}[m]));
function recCol(cls,title,items){
  const body=items.length?items.map(s=>`<div class="rec-item">${esc(s)}</div>`).join("")
    :`<div class="rec-empty">None surfaced in this note.</div>`;
  return `<div class="recol ${cls}"><h3>${title} (${items.length})</h3>${body}</div>`;}
$("#recon").innerHTML=recCol("corr","✔ Corroborations · stores agree",REC.corroborations)
  +recCol("conf","⚑ Conflicts · stores disagree",REC.conflicts);

// ---- Entity detail drawer: click a network node -> its attributes + relationships ----
const SG=DATA.subgraph||{nodes:[],edges:[]};
const sgById=Object.fromEntries((SG.nodes||[]).map(n=>[n.id,n]));
function netFocus(id){  // replay a node's in-graph focus highlight from outside the graph
  const sel='#netgraph .node[data-node="'+(window.CSS&&CSS.escape?CSS.escape(id):id)+'"]';
  const g=document.querySelector(sel); if(g) g.dispatchEvent(new Event("click"));  // re-uses node-click (focus + drawer)
}
function selectEntity(id){
  const node=sgById[id]; if(!node) return;
  $("#e-name").textContent=node.name||id;
  const badge=$("#e-type"),col=netColor(node.label);
  badge.textContent=node.label||"Node"; badge.className="srcbadge";
  badge.style.background=col+"22"; badge.style.color=col;
  const props=node.props||{},keys=Object.keys(props);
  $("#e-attrs").innerHTML=keys.length
    ? keys.map(k=>`<div class="attr"><span class="ak">${esc(k)}</span><span class="av">${esc(String(props[k]))}</span></div>`).join("")
    : `<div class="drawer-empty">No additional attributes recorded for this entity.</div>`;
  const rels=[];
  (SG.edges||[]).forEach(e=>{
    if(e.src===id&&sgById[e.dst]) rels.push({dir:"→",type:e.type,o:sgById[e.dst]});
    else if(e.dst===id&&sgById[e.src]) rels.push({dir:"←",type:e.type,o:sgById[e.src]});});
  $("#e-rels").innerHTML=rels.length
    ? rels.map(r=>`<button class="rel" data-go="${esc(r.o.id)}"><span class="rd">${r.dir}</span>`
        +`<span class="rt">${esc(r.type)}</span><span class="rn">${esc(r.o.name)}</span>`
        +`<span class="rl">${esc(r.o.label)}</span></button>`).join("")
    : `<div class="drawer-empty">No relationships in the traversed neighbourhood.</div>`;
  $("#e-rels").querySelectorAll(".rel").forEach(b=>b.addEventListener("click",()=>netFocus(b.dataset.go)));
  // Non-modal: close the modal evidence drawer + its note highlights, but KEEP the
  // graph trace the node-click just drew. NO scrim — the graph stays lit AND clickable,
  // so clicking nodes still shows the connection trace (and you can pivot node to node).
  $("#drawer").classList.remove("open"); $("#drawer").setAttribute("aria-hidden","true");
  $("#scrim").classList.remove("open");
  document.querySelectorAll("#note .sel").forEach(n=>n.classList.remove("sel"));
  document.querySelectorAll("#note .blk-hot").forEach(n=>n.classList.remove("blk-hot"));
  $("#edrawer").classList.add("open");
  $("#edrawer").setAttribute("aria-hidden","false");
}
function closeEntity(){
  $("#edrawer").classList.remove("open"); $("#edrawer").setAttribute("aria-hidden","true");
  // deselecting unpins + clears the graph trace too
  const ng=$("#netgraph"); if(ng){delete ng.dataset.pin; if(ng._clearFocus)ng._clearFocus();}
  document.querySelectorAll(".node.dim,.node.nbr,.node.foc,.edge.dim").forEach(n=>n.classList.remove("dim","nbr","foc"));
  document.querySelectorAll(".edge.hot").forEach(n=>n.classList.remove("hot"));
}
$("#e-x").addEventListener("click",closeEntity);

// ---- Analytic evaluation panel (eval.json + rubric.json; present only when scored) ----
const EV=DATA.evaluation, RB=DATA.rubric;
if(EV||RB){
  $("#eval-card").style.display="";
  const fx=v=>v==null?"—":(typeof v==="number"?v.toFixed(2):esc(String(v)));
  const pct=v=>v==null?"—":Math.round(v*100)+"%";
  const m=(k,v)=>`<div class="evm"><div class="ek">${k}</div><div class="ev">${v}</div></div>`;
  let body="";
  if(EV){
    const cells=[
      m("Grounded", EV.grounded?'<span class="pill ok">YES</span>':'<span class="pill bad">NO</span>'),
      m("Recall", pct(EV.recall)), m("Trajectory", pct(EV.trajectory))];
    if(EV.supporting_fact_f1!=null) cells.push(m("Supporting-fact F1", fx(EV.supporting_fact_f1)));
    if(EV.context_utilization!=null) cells.push(m("Context utilization", pct(EV.context_utilization)));
    if(EV.citation_coverage!=null) cells.push(m("Citation coverage", pct(EV.citation_coverage)));
    cells.push(m("Queries", EV.queries_run!=null?EV.queries_run:"—"));
    cells.push(m("Pivot burden", fx(EV.pivot_burden)));
    if(EV.reconciliation){const R=EV.reconciliation;
      cells.push(m("Reconciliation", pct(R.reconciliation)
        +(R.total!=null?` <span style="font-size:11px;color:var(--muted)">${R.handled}/${R.total}</span>`:"")));}
    body+=`<div class="evsub">Planted-needle eval · fixture ${esc(EV.fixture||"—")}</div>`
      +`<div class="evgrid">${cells.join("")}</div>`;
  }
  if(RB){
    const dims=(RB.dimensions||[]).map(d=>`<div class="rdim"><div class="rh">`
      +`<span class="rk">${esc(d.key)}</span><span class="rs">${esc(String(d.score))}/5</span></div>`
      +`<div class="rbar"><i style="width:${d.score/5*100}%"></i></div>`
      +`<div class="rr">${esc(d.rationale||"")}</div></div>`).join("");
    body+=`<div class="evsub">ICD-203 analytic-standards rubric · LLM-judged</div>`
      +`<div class="rubricw"><div class="rov">Overall <b>${fx(RB.overall)}</b> / 5</div>${dims}</div>`;
  }
  $("#eval-body").innerHTML=body;
}

// ---- Light / dark theme toggle (persisted; initial theme set pre-paint in <head>) ----
const root=document.documentElement, THEME_KEY="ariadne-theme", tgl=$("#theme-toggle");
function paintToggle(){const light=root.dataset.theme==="light";
  tgl.textContent=light?"◐ Dark":"◑ Light"; tgl.setAttribute("aria-pressed",String(light));}
paintToggle();
tgl.addEventListener("click",()=>{
  const next=root.dataset.theme==="light"?"dark":"light";
  root.dataset.theme=next; try{localStorage.setItem(THEME_KEY,next);}catch(e){} paintToggle();
});
</script>
</body>
</html>
"""
