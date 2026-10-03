"""The architecture canvas must stay true to the code it draws.

``architecture-canvas.html`` names files and Flask routes. Those names go stale
the moment someone renames a file or moves an endpoint, and a wrong path on a
map is worse than no map: people follow it. These tests check the names, and
they run the generator in check mode so the size and route counts cannot drift.

The behaviour of the page itself is covered by
``tests/architecture_canvas_smoke.js`` (jsdom). That one is skipped here when
node or its jsdom dependency is absent, because most of the Python test suite
runs without a frontend install.
"""

import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CANVAS = ROOT / "architecture-canvas.html"
BUILDER = ROOT / "scripts" / "build_architecture_canvas.py"
SMOKE = ROOT / "tests" / "architecture_canvas_smoke.js"
JSDOM = ROOT / "chainforge" / "react-server" / "node_modules" / "jsdom"


def load_builder():
    """Import the generator as a module, so the tests use the same code."""
    spec = importlib.util.spec_from_file_location("canvas_builder", BUILDER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load_builder()


@pytest.fixture(scope="module")
def canvas_text() -> str:
    return CANVAS.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# The files and routes the map names
# --------------------------------------------------------------------------

def test_every_named_file_exists(canvas_text):
    missing = [
        path for path in builder.repo_paths(canvas_text)
        if not (ROOT / path).exists()
    ]
    assert not missing, f"the canvas names files that do not exist: {missing}"


def test_every_named_route_is_real(canvas_text):
    routes = builder.flask_routes()
    assert routes, "no Flask routes found; the regex needs fixing"

    bogus = [
        named for named in builder.routes_named_in_canvas(canvas_text)
        if not builder.route_is_real(named, routes)
    ]
    assert not bogus, f"the canvas names routes flask_app.py does not declare: {bogus}"


def test_flask_routes_are_found():
    routes = builder.flask_routes()
    # A couple of anchors, so a broken regex cannot pass by finding nothing
    # (asserted above) or by finding only a handful.
    for expected in ("/api/flows", "/app/executepy", "/upload"):
        assert expected in routes, f"{expected} missing from the routes read from flask_app.py"


# --------------------------------------------------------------------------
# The map itself
# --------------------------------------------------------------------------

def test_every_node_sits_inside_its_layer(canvas_text):
    """A node drawn outside its layer frame looks like a bug, so guard it."""
    layers = {
        gid: (int(x), int(y), int(w), int(h))
        for gid, x, y, w, h in re.findall(
            r'\{\s*id:"(\w+)",\s*x:(\d+),\s*y:(\d+),\s*w:(\d+),\s*h:(\d+)',
            canvas_text,
        )
    }
    assert layers, "no layers found; the layout regex needs fixing"

    outside = []
    for nid, gid, x, y, w, h in re.findall(
        r'N\("(\w+)","(\w+)",(\d+),(\d+),(\d+),(\d+)', canvas_text
    ):
        x, y, w, h = int(x), int(y), int(w), int(h)
        if gid not in layers:
            outside.append(f"{nid} names an unknown layer {gid!r}")
            continue
        lx, ly, lw, lh = layers[gid]
        if not (lx <= x and ly <= y and x + w <= lx + lw and y + h <= ly + lh):
            outside.append(
                f"{nid} at ({x},{y},{w},{h}) sticks out of layer {gid} "
                f"({lx},{ly},{lw},{lh})"
            )
    assert not outside, "nodes drawn outside their layer:\n" + "\n".join(outside)


def test_node_and_edge_counts_are_sane(canvas_text):
    counts = builder.node_and_edge_counts(canvas_text)
    assert counts["nodes"] >= 70, counts
    assert counts["edges"] >= 40, counts
    assert counts["flows"] >= 8, counts


def test_flow_traces_only_use_edges_that_exist(canvas_text):
    """Every step of a trace must be a real edge, or the trace lights up nothing."""
    m = re.search(r"const FLOWS = \[(.*?)\n\];", canvas_text, re.S)
    assert m, "FLOWS block not found"
    flows_src = m.group(1)

    chains = re.findall(r"\[((?:\"[\w]+\",?)+)\]", flows_src)
    assert chains, "no flow chains found"

    edges = set(re.findall(r'\{\s*s:"(\w+)",\s*t:"(\w+)"', canvas_text))
    nodes = set(re.findall(r'N\("(\w+)"', canvas_text))

    for chain in chains:
        ids = re.findall(r'"(\w+)"', chain)
        for node in ids:
            assert node in nodes, f"a flow names a node that does not exist: {node}"
        for a, b in zip(ids, ids[1:]):
            assert (a, b) in edges, f"a flow step has no edge: {a} -> {b}"


def test_no_two_edges_share_a_pair(canvas_text):
    pairs = re.findall(r'\{\s*s:"(\w+)",\s*t:"(\w+)"', canvas_text)
    duplicates = {p for p in pairs if pairs.count(p) > 1}
    assert not duplicates, f"these edges are drawn twice, so one is unreachable: {duplicates}"


def test_the_auto_block_is_valid_json(canvas_text):
    block = builder.current_block(canvas_text)
    assert block is not None, "the AUTO block is missing or broken"
    assert block["generated"], "the AUTO block carries no date"
    assert len(block["fileLines"]) >= 40
    assert len(block["routes"]) >= 20


def test_auto_block_sits_inside_the_script_element(canvas_text):
    """A browser keeps HTML comments as raw text inside this block, so the
    markers must stay outside the script element or the JSON cannot be read."""
    assert builder.scaffold_problems(canvas_text) == []
    start, end = builder.auto_span(canvas_text)
    between = canvas_text[start:end]
    assert "<script" not in between, "the script tag is inside the AUTO markers"

    payload = between[between.index("{"):between.rindex("}") + 1]
    assert json.loads(payload)["totals"]["files"] >= 40, "the AUTO block does not parse as JSON"


# --------------------------------------------------------------------------
# The generator
# --------------------------------------------------------------------------

def test_generator_check_passes():
    """The committed block must match the code as it stands."""
    result = subprocess.run(
        [sys.executable, str(BUILDER), "--check"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        "architecture-canvas.html is out of date; run "
        f"`python scripts/build_architecture_canvas.py`\n{result.stderr}"
    )


def test_generator_check_fails_when_a_line_count_is_wrong(tmp_path):
    """Guard the check itself: make it lie, and see if it notices."""
    fake = tmp_path / "architecture-canvas.html"
    fake.write_text(CANVAS.read_text(encoding="utf-8"), encoding="utf-8")

    payload = builder.current_block(fake.read_text(encoding="utf-8"))
    payload["fileLines"]["chainforge/flask_app.py"] += 1
    text = fake.read_text(encoding="utf-8")
    start, end = builder.auto_span(text)
    fake.write_text(text[:start] + builder.render(payload) + text[end:], encoding="utf-8")

    # Compare the same way --check does, with a fixed date so only the edit matters.
    assert builder.comparable(payload) != builder.comparable(builder.build()[0])


def test_route_base_folds_parameters():
    assert builder.route_base("/media/<uid>") == "/media/*"
    assert builder.route_base("/api/getConfig/<name>/") == "/api/getConfig/*"
    assert builder.route_is_real("/media", ["/media/<uid>"])
    assert builder.route_is_real("/media/<uid>", ["/media/<uid>"])
    assert builder.route_is_real("/api/getConfig", ["/api/getConfig/<name>"])
    assert not builder.route_is_real("/api/nope", ["/api/flows"])


def test_route_scan_ignores_file_paths(canvas_text):
    """``backend/mediaStore.ts`` must not read as a call to ``/media``."""
    assert "/mediaStore" not in builder.routes_named_in_canvas(canvas_text)


# --------------------------------------------------------------------------
# The page behaviour, if a frontend install is around
# --------------------------------------------------------------------------

@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
@pytest.mark.skipif(not JSDOM.exists(), reason="jsdom is not installed")
def test_page_behaviour_in_jsdom():
    result = subprocess.run(
        ["node", str(SMOKE)], cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, f"jsdom smoke test failed:\n{result.stdout}\n{result.stderr}"