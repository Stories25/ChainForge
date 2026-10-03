"""Keep architecture-canvas.html in step with the source.

The canvas draws facts about the repository: which files exist, how big they
are, and which Flask routes the server really has. Those facts go stale on
their own, so this script reads them back out of the tree and writes them into
the ``AUTO`` block of the HTML.

    python scripts/build_architecture_canvas.py           # refresh the block
    python scripts/build_architecture_canvas.py --check   # fail if stale

``--check`` is the one to put in CI: it exits non-zero when the block no longer
matches the code, when a file named in the canvas does not exist, or when a
route named in the canvas is not a route the server has.

Only the AUTO block is rewritten. The prose, the layout and the data-flow
traces are hand-written on purpose, because they are judgement calls.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CANVAS = ROOT / "architecture-canvas.html"

START = "<!-- AUTO:START"
END = "<!-- AUTO:END -->"

# Path -> what it holds, used only to make the failure messages readable.
NOTES = {
    "chainforge/flask_app.py": "the Flask API",
    "chainforge/app.py": "the CLI entry point",
}


def canvas_text() -> str:
    return CANVAS.read_text(encoding="utf-8")


def auto_span(text: str) -> tuple[int, int]:
    """Byte-free span of the generated block, comments included."""
    start = text.find(START)
    end = text.find(END)
    if start == -1 or end == -1 or end < start:
        raise SystemExit(
            f"{CANVAS.name}: no AUTO block found. Expected a {START!r} ... {END!r} pair."
        )
    return start, end + len(END)


def current_block(text: str) -> dict | None:
    """The AUTO payload now in the file, or None when it is empty or broken."""
    start, end = auto_span(text)
    inner = text[start:end]
    m = re.search(r"\{.*\}", inner, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def repo_paths(text: str) -> list[str]:
    """Every repository path the canvas points at.

    Matches strings that start with ``chainforge/`` and contain no space, so
    the descriptive ones ("flask_app.py — /app/executepy") are left out.
    """
    found = re.findall(r'"(chainforge/[^"\s]+)"', text)
    return sorted({p.rstrip('/') if not p.endswith('/') else p for p in found})


def count_lines(path: Path) -> int:
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        return sum(1 for _ in fh)


def flask_routes() -> list[str]:
    """Every route the server declares, read from the decorators themselves."""
    app = ROOT / "chainforge" / "flask_app.py"
    if not app.exists():
        return []
    source = app.read_text(encoding="utf-8")
    routes = set()
    for m in re.finditer(r"@app\.(?:route|get|post)\(\s*[\"']([^\"']+)[\"']", source):
        routes.add(m.group(1))
    return sorted(routes)


def routes_named_in_canvas(text: str) -> list[str]:
    """Route-looking strings the canvas shows the reader.

    File paths are stripped first: ``backend/mediaStore.ts`` would otherwise
    look like a call to ``/media``.
    """
    text = re.sub(r'"chainforge/[^"]*"', " ", text)
    text = re.sub(r'[\w./-]+\.tsx?\b', " ", text)
    named = set()
    for m in re.finditer(r"/(?:api/|app/|media|upload|getRetrieveProgress)[A-Za-z0-9_:/<>]*", text):
        named.add(m.group(0))
    return sorted(named)


def route_base(route: str) -> str:
    """A route with its parameters folded away: ``/media/<uid>`` -> ``/media/*``."""
    route = re.sub(r"<[^>]*>", "*", route)
    route = re.sub(r":[A-Za-z_][\w]*", "*", route)
    return route.rstrip("/") or "/"


def route_is_real(named: str, routes: list[str]) -> bool:
    """Is `named` the same route as one the server declares?

    A route may be shown in full (``/api/flows``) or shortened to its stem
    (``/api/getConfig`` for ``/api/getConfig/<name>``), so accept a match at a
    slash boundary in either direction.
    """
    n = route_base(named)
    for r in routes:
        d = route_base(r)
        if n == d or d.startswith(n + "/") or n.startswith(d + "/"):
            return True
    return False


def node_and_edge_counts(text: str) -> dict:
    nodes = len(re.findall(r'^\s*N\("', text, re.M))
    edges = len(re.findall(r'^\s*\{ s:"', text, re.M))
    flows = len(re.findall(r'\{ id:"f\d+"', text))
    return {"nodes": nodes, "edges": edges, "flows": flows}


def build() -> tuple[dict, list[str]]:
    """The payload to write, plus a list of problems found on the way."""
    text = canvas_text()
    problems: list[str] = []

    paths = repo_paths(text)
    file_lines: dict[str, int] = {}
    for p in paths:
        f = ROOT / p
        if not f.exists():
            problems.append(f"canvas names {p}, which does not exist")
            continue
        if f.is_dir():
            continue
        file_lines[p] = count_lines(f)

    routes = flask_routes()
    for named in routes_named_in_canvas(text):
        if not route_is_real(named, routes):
            problems.append(f"canvas names route {named}, which flask_app.py does not declare")

    counts = node_and_edge_counts(text)
    payload = {
        "generated": date.today().isoformat(),
        "fileLines": dict(sorted(file_lines.items())),
        "routes": routes,
        "totals": {
            "files": len(file_lines),
            "routes": len(routes),
            **counts,
        },
    }
    return payload, problems


def render(payload: dict) -> str:
    body = json.dumps(payload, indent=2, sort_keys=False)
    # The JSON sits inside <script type="application/json">, where the only two
    # sequences that would end the block early are these.
    body = body.replace("<", "\\u003c").replace("&", "\\u0026")
    # Only the comment and the JSON live between the markers. The script tags
    # stay outside them, because a browser keeps an HTML comment as raw text
    # inside such a block and would hand the parser a string it cannot read.
    return (
        "<!-- AUTO:START — written by scripts/build_architecture_canvas.py. "
        "Do not edit by hand. -->\n"
        f"{body}\n"
        f"{END}"
    )


def scaffold_problems(text: str) -> list[str]:
    """The script tags that hold the block must still be there."""
    start, end = auto_span(text)
    problems = []
    open_tag = '<script id="auto-data" type="application/json">'
    before = text[max(0, start - 200):start]
    if open_tag not in before:
        problems.append(f"{CANVAS.name}: the {open_tag} opening tag is missing above AUTO:START")
    after = text[end:end + 200]
    if "</script>" not in after:
        problems.append(f"{CANVAS.name}: the closing </script> tag is missing below AUTO:END")
    return problems


def comparable(payload: dict) -> dict:
    """The payload minus the date, so --check does not fail every morning."""
    return {k: v for k, v in payload.items() if k != "generated"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="fail instead of writing, when the block is stale")
    args = ap.parse_args()

    text = canvas_text()
    payload, problems = build()
    problems += scaffold_problems(text)

    for p in problems:
        print(f"problem: {p}", file=sys.stderr)

    if args.check:
        have = current_block(text)
        if have is None:
            print(f"{CANVAS.name}: the AUTO block is empty or broken", file=sys.stderr)
            return 1
        if comparable(have) != comparable(payload):
            print(f"{CANVAS.name}: the AUTO block is out of date. "
                  f"Run: python scripts/build_architecture_canvas.py", file=sys.stderr)
            return 1
        if problems:
            print(f"{CANVAS.name}: {len(problems)} problem(s) found", file=sys.stderr)
            return 1
        print(f"{CANVAS.name}: up to date "
              f"({payload['totals']['files']} files, {payload['totals']['routes']} routes)")
        return 0

    start, end = auto_span(text)
    CANVAS.write_text(text[:start] + render(payload) + text[end:], encoding="utf-8")
    t = payload["totals"]
    print(f"wrote {CANVAS.name}: {t['files']} files, {t['routes']} routes, "
          f"{t['nodes']} parts, {t['edges']} edges, {t['flows']} flows")
    if problems:
        print(f"{len(problems)} problem(s) above still need fixing", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())