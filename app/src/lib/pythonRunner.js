/**
 * Runs the insights agent's analysis code in this app, and nowhere else.
 *
 * The backend sends `python_run_requested` with a script and the rows it may
 * read; this hands them to one long-lived worker (`public/python-worker.js`,
 * Pyodide with pandas) and returns what came out. One worker per tab, kept
 * warm: loading the interpreter is the slow part (seconds, first time only),
 * a run is usually milliseconds.
 *
 * The person's time limit is for their code, not for the download, so the
 * clock starts when the worker says the run has started. A run over the limit
 * kills the worker outright — Python cannot be interrupted from outside, and
 * a tab stuck in an infinite loop is worse than paying the load again.
 *
 * Runs are queued, one at a time: the agent issues them one per tool call, and
 * two scripts sharing an interpreter mid-run would share its stdout.
 */

const WORKER_URL = "/python-worker.js";
// The first run downloads the interpreter and pandas. The backend waits its
// own grace on top of the person's limit (LOAD_GRACE_SECONDS, 60 s), so give
// up a little before it does and report why, rather than let it time out
// knowing nothing.
const LOAD_TIMEOUT_MS = 55_000;

let worker = null;
let queue = Promise.resolve();
let nextId = 0;

function spawn() {
  if (!worker) worker = new Worker(WORKER_URL);
  return worker;
}

function kill() {
  if (worker) worker.terminate();
  worker = null;
}

function runOnce({ code, tables, timeoutSeconds }) {
  return new Promise((resolve) => {
    const w = spawn();
    const id = ++nextId;
    let timer = null;
    const finish = (result, { fatal = false } = {}) => {
      clearTimeout(timer);
      w.removeEventListener("message", onMessage);
      w.removeEventListener("error", onError);
      if (fatal) kill();
      resolve(result);
    };
    const onMessage = ({ data }) => {
      if (data?.type === "boot_failed") {
        finish({ ok: false, error: `Python did not load: ${data.error}` }, { fatal: true });
      } else if (data?.id !== id) {
        return;
      } else if (data.type === "started") {
        clearTimeout(timer);
        timer = setTimeout(
          () => finish({ ok: false, error: `Stopped after ${timeoutSeconds} s, the time limit in Settings.` }, { fatal: true }),
          timeoutSeconds * 1000,
        );
      } else if (data.type === "done") {
        const { type, id: _id, ...result } = data;
        finish(result);
      }
    };
    const onError = (event) => {
      finish({ ok: false, error: event?.message || "The Python worker crashed." }, { fatal: true });
    };
    w.addEventListener("message", onMessage);
    w.addEventListener("error", onError);
    timer = setTimeout(
      () => finish({ ok: false, error: "Python took too long to load. Check the connection and try again." }, { fatal: true }),
      LOAD_TIMEOUT_MS,
    );
    w.postMessage({ type: "run", id, code, tables });
  });
}

/**
 * Run one script. Never rejects: every outcome is a result the backend can
 * hand to the model, `{ ok, stdout?, result?, error?, duration_ms? }`.
 */
export function runPython({ code, tables = {}, timeoutSeconds = 60 }) {
  if (typeof Worker === "undefined") {
    return Promise.resolve({ ok: false, error: "This browser cannot run analysis code." });
  }
  const run = queue.then(() => runOnce({ code, tables, timeoutSeconds }));
  queue = run.catch(() => {});
  return run;
}
