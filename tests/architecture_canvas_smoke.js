/**
 * Behaviour test for architecture-canvas.html, run with jsdom.
 *
 *     node tests/architecture_canvas_smoke.js
 *
 * jsdom has no layout engine, so this cannot prove that hit testing feels
 * right in a browser. What it does check is that the page boots without
 * errors, that the data is wired up, and that every control actually changes
 * what it should. The Python side (tests/test_architecture_canvas.py) checks
 * the facts the canvas claims about the repository.
 */

const fs = require("fs");
const path = require("path");

const REPO = path.resolve(__dirname, "..");
const { JSDOM, VirtualConsole } = require(
  path.join(REPO, "chainforge/react-server/node_modules/jsdom")
);

const CANVAS = path.join(REPO, "architecture-canvas.html");
const html = fs.readFileSync(CANVAS, "utf-8");

let failures = 0;
function ok(msg) { console.log("  ok:", msg); }
function fail(msg) { console.error("  FAIL:", msg); failures++; }
function check(cond, msg) { cond ? ok(msg) : fail(msg); }

function boot(hash) {
  const errors = [];
  const vc = new VirtualConsole();
  vc.on("jsdomError", (e) => errors.push(e.message));
  vc.on("error", (...a) => errors.push(a.join(" ")));

  const dom = new JSDOM(html, {
    url: "file:///" + CANVAS.replace(/\\/g, "/") + (hash || ""),
    runScripts: "dangerously",
    pretendToBeVisual: true,
    virtualConsole: vc,
  });
  const w = dom.window;
  w.innerWidth = 1536;
  w.innerHeight = 800;
  return { window: w, document: w.document, errors };
}

function mouse(el, type, x, y) {
  el.dispatchEvent(new el.ownerDocument.defaultView.MouseEvent(type, {
    clientX: x, clientY: y, bubbles: true, cancelable: true,
  }));
}
function pointer(el, type, x, y) {
  el.dispatchEvent(new el.ownerDocument.defaultView.MouseEvent(type, {
    clientX: x, clientY: y, bubbles: true, cancelable: true,
  }));
}
/** A tap the way a browser sends it: down, up, then click. */
function tap(el, x, y) {
  pointer(el, "pointerdown", x, y);
  pointer(el, "pointerup", x, y);
  mouse(el, "click", x, y);
}
/** A drag: down, move past the slop, up, then the click that follows it. */
function drag(el, fromX, fromY, toX, toY) {
  pointer(el, "pointerdown", fromX, fromY);
  pointer(el, "pointermove", toX, toY);
  pointer(el, "pointerup", toX, toY);
  mouse(el, "click", toX, toY);
}

// ---------------------------------------------------------------- boot ----
console.log("boot");
let { window, document, errors } = boot();
check(errors.length === 0, "no script errors at boot" + (errors.length ? ": " + errors[0] : ""));

const svg = document.querySelector("svg.world-svg");
const world = svg && svg.querySelector("g");
check(!!svg && !!world, "canvas mounted");

const nodes = document.querySelectorAll(".node");
const edges = document.querySelectorAll(".edge");
const groups = document.querySelectorAll(".group");
check(nodes.length >= 70, `nodes drawn: ${nodes.length}`);
check(edges.length >= 40, `edges drawn: ${edges.length}`);
check(groups.length === 5, `layer frames drawn: ${groups.length}`);
check(/translate\(/.test(world.getAttribute("transform") || ""), "world is transformed");

// ------------------------------------------------------------ generated ----
console.log("generated data block");
// A browser keeps HTML comments as raw text inside a
// <script type="application/json"> block, so strip them before parsing, the
// same way the page does.
const auto = JSON.parse(
  document.getElementById("auto-data").textContent.replace(/<!--[\s\S]*?-->/g, "")
);
check(auto && auto.generated, `generated stamp present: ${auto && auto.generated}`);
check(Object.keys((auto && auto.fileLines) || {}).length > 40,
      `file sizes recorded: ${Object.keys((auto && auto.fileLines) || {}).length}`);
check((auto && auto.routes || []).length > 20, `routes recorded: ${(auto && auto.routes || []).length}`);
check((document.getElementById("stamp").textContent || "").includes("built from the source"),
      "title bar shows the stamp");

// ----------------------------------------------------------------- zoom ----
console.log("zoom and pan");
const zoomBtn = document.getElementById("zin");
const before = world.getAttribute("transform");
zoomBtn.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
check(before !== world.getAttribute("transform"), "zoom button changes the view");
check(/%/.test(document.getElementById("zoompct").textContent), "zoom readout updates");
document.getElementById("zfit").dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
ok("fit button handled");

const stage = document.getElementById("stage");
const t0 = world.getAttribute("transform");
drag(stage, 600, 400, 700, 460);
check(t0 !== world.getAttribute("transform"), "drag pans the view");

// a drag must not count as a click on whatever it started over
promptGuard: {
  const target = [...document.querySelectorAll(".node")][0];
  const litBefore = document.querySelectorAll(".node.lit").length;
  drag(target, 0, 0, 30, 30);
  check(document.querySelectorAll(".node.lit").length === litBefore,
        "a drag does not select a node");
}

// ------------------------------------------------------------- selection ----
console.log("selection");
const promptNode = [...document.querySelectorAll(".node")].find(n => n.dataset.id === "p_prompt");
tap(promptNode, 0, 0);
const panel = document.getElementById("panel");
check(panel.classList.contains("open"), "clicking a node opens the panel");
check(panel.textContent.includes("PromptNode"), "panel shows the node title");
check(panel.textContent.includes("PromptNode.tsx"), "panel shows the file path");
check(/lines/.test(panel.textContent), "panel shows line counts from the generated block");
check(window.location.hash === "#node=p_prompt", `address bar carries the node: ${window.location.hash}`);

// clicking empty space clears it
tap(document.querySelector(".edge") || stage, 10, 10);
check(!document.getElementById("panel").classList.contains("open"),
      "clicking empty space clears the selection");

// ---------------------------------------------------------------- flows ----
console.log("flow traces");
const chip = document.querySelector('#flowchips .chip[data-flow="f1"]');
chip.dispatchEvent(new window.MouseEvent("click", { bubbles: true, cancelable: true }));
const litEdges = document.querySelectorAll(".edge.lit").length;
const pulses = document.querySelectorAll(".pulse").length;
check(litEdges >= 5, `flow lights up edges: ${litEdges}`);
check(document.querySelectorAll(".node.lit").length >= 6, "flow lights up nodes");
check(pulses >= 5, `flow animates pulses: ${pulses}`);
check(window.location.hash === "#flow=f1", `address bar carries the flow: ${window.location.hash}`);
chip.dispatchEvent(new window.MouseEvent("click", { bubbles: true, cancelable: true }));
check(document.querySelectorAll(".edge.lit").length === 0, "clicking the chip again clears the trace");

// ---------------------------------------------------------- deploy modes ----
console.log("deployment modes");
const webBtn = document.querySelector('#modeswitch .mbtn[data-mode="web"]');
webBtn.dispatchEvent(new window.MouseEvent("click", { bubbles: true, cancelable: true }));
check(document.querySelectorAll(".node.hide-mode").length > 20,
      `web mode dims the server: ${document.querySelectorAll(".node.hide-mode").length} parts`);
check(document.querySelectorAll(".group.hide-mode").length === 2,
      "web mode dims the two server layers");

const localBtn = document.querySelector('#modeswitch .mbtn[data-mode="local"]');
localBtn.dispatchEvent(new window.MouseEvent("click", { bubbles: true, cancelable: true }));
check(document.querySelectorAll(".node.hide-mode").length === 0,
      "local mode hides nothing");
check((document.getElementById("modenote").textContent || "").includes("Flask"),
      "local mode explains itself");

document.querySelector('#modeswitch .mbtn[data-mode="both"]')
        .dispatchEvent(new window.MouseEvent("click", { bubbles: true, cancelable: true }));

// -------------------------------------------------------------- collapse ----
console.log("layer collapse");
const total = document.querySelectorAll(".node").length;
const header = document.querySelector(".group rect[fill='transparent']");
tap(header, 100, 80);
check(document.querySelectorAll(".node").length < total, "header folds the layer");
tap(header, 100, 80);
check(document.querySelectorAll(".node").length === total, "header unfolds the layer");

// a drag that starts on a header must not fold the layer.
// The page rebuilds the layer frames on every fold, so look the header up
// again rather than reusing the element from before.
const total2 = document.querySelectorAll(".node").length;
const header2 = document.querySelector(".group rect[fill='transparent']");
drag(header2, 100, 80, 160, 110);
check(document.querySelectorAll(".node").length === total2, "dragging a header does not fold the layer");

// --------------------------------------------------------------- search ----
console.log("search");
const search = document.getElementById("search");
search.value = "pyodide";
search.dispatchEvent(new window.Event("input", { bubbles: true }));
check(document.querySelectorAll(".node.match").length >= 1, "search finds pyodide");
check(/found/.test(document.getElementById("searchcount").textContent), "search counts the hits");

// ------------------------------------------------------------ deep links ----
console.log("deep links");
({ window, document } = boot("#node=d_query"));
const panel2 = window.document.getElementById("panel");
check(panel2.classList.contains("open"), "a #node= link opens straight on that node");
check(panel2.textContent.includes("query.ts"), "the link lands on the right node");

({ window, document } = boot("#flow=f6"));
check(window.document.querySelectorAll(".edge.lit").length >= 5,
      "a #flow= link starts the trace on load");

console.log(failures ? `\n${failures} FAILURE(S)` : "\nall checks passed");
process.exit(failures ? 1 : 0);