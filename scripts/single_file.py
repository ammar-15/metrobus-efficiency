"""Bundle the web map into one self-contained HTML file (data included).

    python scripts/single_file.py                    # -> output/metrobus-map.html
    python scripts/single_file.py --no-tiles         # skip the street map (for hosts that block outside images)
    python scripts/single_file.py --share-base https://ammar-15.github.io/metrobus-efficiency/

Leaflet's script loads from cdnjs; its stylesheet, the page's CSS/JS and the data are inlined.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
LEAFLET_JS = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"


def build(data: Path, out: Path, no_tiles: bool, share_base: str | None, fragment: bool) -> Path:
    html = (DOCS / "index.html").read_text()
    css = (DOCS / "vendor/leaflet/leaflet.css").read_text() + "\n" + (DOCS / "style.css").read_text()
    js = (DOCS / "app.js").read_text()
    plan = json.loads(data.read_text())

    head = re.search(r"<head>(.*)</head>", html, re.S).group(1)
    body = re.search(r"<body>(.*)</body>", html, re.S).group(1)
    keep = "\n".join(l for l in head.splitlines() if re.search(r"<title>|<meta name=\"description|fonts\.g", l))
    body = re.sub(r'\s*<script src="vendor/leaflet/leaflet.js"></script>\s*<script src="app.js"></script>', "", body)

    switches = {"PLAN": plan, "NO_TILES": no_tiles, "SHARE_BASE": share_base}
    boot = ";".join(f"window.{k}={json.dumps(v, separators=(',', ':'))}" for k, v in switches.items())
    scripts = f'<script src="{LEAFLET_JS}"></script>\n<script>{boot}</script>\n<script>{js}</script>\n'
    inner_head = f"{keep}\n<style>\n{css}\n</style>"
    if fragment:  # for hosts that wrap the page in their own <html>/<head>/<body>
        page = f"{inner_head}\n{body}{scripts}"
    else:
        meta = '<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
        page = f'<!doctype html>\n<html lang="en">\n<head>\n{meta}\n{inner_head}\n</head>\n<body>{body}{scripts}</body>\n</html>\n'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=str(DOCS / "data/plan.json"))
    ap.add_argument("--out", default=str(ROOT / "output/metrobus-map.html"))
    ap.add_argument("--no-tiles", action="store_true")
    ap.add_argument("--share-base")
    ap.add_argument("--fragment", action="store_true", help="omit <html>/<head>/<body> (for hosts that add them)")
    a = ap.parse_args()
    p = build(Path(a.data), Path(a.out), a.no_tiles, a.share_base, a.fragment)
    print(f"Wrote {p} ({p.stat().st_size / 1e6:.1f} MB)")
