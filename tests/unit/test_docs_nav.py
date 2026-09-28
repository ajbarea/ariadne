"""Every page under docs/ is in the zensical.toml nav.

Zensical publishes every Markdown file under docs/ and cannot exclude one, so
a page the nav leaves out still deploys, unreachable from the site. Working
notes belong outside docs/.

Shared by every sister docs site; the canonical copy is in techne
(plugins/techne/skills/docs-site/templates/shared/).
"""

import tomllib
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = next(p for p in HERE.parents if (p / "zensical.toml").is_file())
UNLISTED = "published but not in the nav; list it or move it out of docs/"
MISSING = "in the nav but missing from docs/"


def nav_pages(entries: object) -> set[str]:
    if isinstance(entries, list):
        return {page for entry in entries for page in nav_pages(entry)}
    if isinstance(entries, dict):
        return {page for v in entries.values() for page in nav_pages(v)}
    # External links, and static pages the build generates, are not sources.
    if isinstance(entries, str) and entries.endswith(".md"):
        return {entries}
    return set()


def test_every_docs_page_is_in_the_nav() -> None:
    config = tomllib.loads((ROOT / "zensical.toml").read_text())
    listed = nav_pages(config["project"]["nav"])
    docs = ROOT / "docs"
    sources = {p.relative_to(docs).as_posix() for p in docs.rglob("*.md")}
    assert sources - listed == set(), UNLISTED
    assert listed - sources == set(), MISSING
