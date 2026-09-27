"""Every page under docs/ is in the zensical.toml nav.

Zensical publishes every Markdown file under docs/ and cannot exclude one, so a page the nav
leaves out still deploys, unreachable from the site. Working notes belong under plans/.
"""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def nav_pages(entries: object) -> set[str]:
    if isinstance(entries, list):
        return set().union(*(nav_pages(e) for e in entries)) if entries else set()
    if isinstance(entries, dict):
        return set().union(*(nav_pages(v) for v in entries.values())) if entries else set()
    if isinstance(entries, str) and not re.match(r"https?://", entries):
        return {entries}
    return set()


def test_every_docs_page_is_in_the_nav() -> None:
    nav = tomllib.loads((ROOT / "zensical.toml").read_text())["project"]["nav"]
    docs = ROOT / "docs"
    sources = {p.relative_to(docs).as_posix() for p in docs.rglob("*.md")}
    listed = nav_pages(nav)
    assert sources - listed == set(), "published but not in the nav; list it or move it to plans/"
    assert listed - sources == set(), "in the nav but missing from docs/"
