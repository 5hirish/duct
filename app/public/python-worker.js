/* RunPython's interpreter: Pyodide in a Web Worker, cut off from the network.
 *
 * The insights agent computes its figures here, over rows it fetched, with code
 * it wrote (backend/agents/insights/python_run.py). That code is shaped by text
 * other people wrote — page titles, search queries, referrers — so it is
 * treated as hostile: it may read the rows it was handed and nothing else, and
 * it has no way to send them anywhere.
 *
 * Two locks, because either alone has a gap:
 *
 * 1. This file's own Content-Security-Policy (next.config.mjs, public/_headers)
 *    lets it load scripts and connect only to one pinned Pyodide release on
 *    jsDelivr. A dedicated worker obeys its own response's policy, not the
 *    page's, and the browser enforces it below anything Python can reach.
 * 2. After boot, fetch is narrowed to GET on that same prefix and every other
 *    way out (XHR, WebSocket, EventSource, importScripts, nested workers) is
 *    removed. Belt and braces for a host that drops the header.
 *
 * The allowlist is ours and fixed. Pyodide fetches packages from it on first
 * import (scipy, duckdb); any host that accepts a write would be an exfiltration
 * channel, which is why nobody can add one from settings.
 *
 * A classic worker rather than a module worker: importScripts is how Pyodide's
 * loader is meant to arrive in a worker, and WKWebView (the desktop window) has
 * supported classic workers far longer than module ones.
 */

"use strict";

const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/";
const PRELOAD = ["numpy", "pandas"];
// Twice the backend's cap, which clips again; the model reads at most that.
const MAX_CHARS = 40000;

importScripts(PYODIDE + "pyodide.js");

const PRELUDE = `
import io, json, sys, time, traceback
import numpy as np
import pandas as pd

def _duct_run(code, tables_json):
    tables = json.loads(tables_json)
    data = {n: pd.DataFrame(t["rows"], columns=t["columns"]) for n, t in tables.items()}
    ns = {"pd": pd, "np": np, "data": data, "__name__": "__analysis__"}
    out = io.StringIO()
    saved = sys.stdout, sys.stderr
    sys.stdout = sys.stderr = out
    ok, err = True, ""
    started = time.perf_counter()
    try:
        exec(compile(code, "<analysis>", "exec"), ns)
    except BaseException:
        ok = False
        err = traceback.format_exc(limit=-4)
    finally:
        sys.stdout, sys.stderr = saved
    took = int((time.perf_counter() - started) * 1000)
    shown = ""
    res = ns.get("result")
    if res is not None:
        try:
            shown = res.head(200).to_csv() if isinstance(res, (pd.DataFrame, pd.Series)) else repr(res)
        except Exception:
            shown = repr(res)
    return json.dumps({"ok": ok, "stdout": out.getvalue(), "result": shown, "error": err, "duration_ms": took})
`;

function allowed(input, init) {
  // Pyodide's package loader passes a URL object, not a string; a Request
  // carries its own url. Resolve all three the way fetch itself would.
  const raw = input instanceof Request ? input.url : String(input);
  let url;
  try {
    url = new URL(raw, self.location.href).href;
  } catch {
    return false;
  }
  const method = ((init && init.method) || (input instanceof Request && input.method) || "GET").toUpperCase();
  return method === "GET" && url.startsWith(PYODIDE);
}

function lockDown() {
  const realFetch = self.fetch.bind(self);
  self.fetch = (input, init) =>
    allowed(input, init)
      ? realFetch(input, init)
      : Promise.reject(new TypeError("network access is disabled for analysis code"));
  for (const name of ["XMLHttpRequest", "WebSocket", "EventSource", "Worker", "SharedWorker", "importScripts"]) {
    try {
      Object.defineProperty(self, name, { value: undefined, writable: false, configurable: false });
    } catch {
      self[name] = undefined;
    }
  }
}

let booting = null;
function boot() {
  if (!booting) {
    booting = (async () => {
      const py = await loadPyodide({ indexURL: PYODIDE });
      await py.loadPackage(PRELOAD);
      lockDown();
      py.runPython(PRELUDE);
      return py;
    })();
  }
  return booting;
}

const clip = (s) => (typeof s === "string" && s.length > MAX_CHARS ? s.slice(0, MAX_CHARS) : s || "");

self.onmessage = async ({ data: msg }) => {
  if (!msg || msg.type !== "run") return;
  try {
    const py = await boot();
    self.postMessage({ type: "started", id: msg.id });
    // Anything the script imports beyond the preload (scipy, duckdb) comes
    // from the same pinned release, through the narrowed fetch.
    await py.loadPackagesFromImports(msg.code);
    const run = py.globals.get("_duct_run");
    const out = JSON.parse(run(msg.code, JSON.stringify(msg.tables || {})));
    run.destroy();
    self.postMessage({
      type: "done",
      id: msg.id,
      ok: Boolean(out.ok),
      stdout: clip(out.stdout),
      result: clip(out.result),
      error: clip(out.error),
      duration_ms: out.duration_ms,
    });
  } catch (err) {
    self.postMessage({ type: "done", id: msg.id, ok: false, error: clip(String((err && err.message) || err)) });
  }
};

// Start loading as soon as the page creates the worker, not on the first run.
boot().then(
  () => self.postMessage({ type: "ready" }),
  (err) => self.postMessage({ type: "boot_failed", error: String((err && err.message) || err) }),
);
