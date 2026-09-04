// A fixture-replaying stand-in for the backend's agent routes.
//
// For working on the agent workspaces without a backend, a model or a
// database: each session streams one of the recorded fixtures under
// src/lib/__fixtures__ and pauses exactly where the real backend would — on a
// question until it is answered, at a turn boundary until the user sends
// something. Reattaching to a session continues where it left off, so a
// reload exercises the hook's reattach path; the session-state and
// thread-state routes answer the way the real ones do.
//
//   npm run mock:agents                                     # :8012
//   NEXT_PUBLIC_API_BASE=http://localhost:8012 npm run dev  # the app, pointed at it
//
// Sign in is client-side (a JWT in localStorage), so any well-formed token
// with a future `exp` gets past the guard — scripts/smoke-agent-workspaces.mjs
// shows the three lines that do it. Never run this on the port the real
// backend uses; the app cannot tell them apart, which is the point.
import http from "node:http";
import { readFileSync } from "node:fs";
import { randomUUID } from "node:crypto";
import { fileURLToPath } from "node:url";

const FIX = fileURLToPath(new URL("../src/lib/__fixtures__", import.meta.url));
const fixtures = {
  insights: JSON.parse(readFileSync(`${FIX}/insights-pause.json`, "utf8")),
  tiktok_studio: JSON.parse(readFileSync(`${FIX}/content-plan.json`, "utf8")),
  audit_seo: JSON.parse(readFileSync(`${FIX}/audit-run.json`, "utf8")),
};
const FRAME_MS = Number(process.env.FRAME_MS || 220);

const sessions = new Map();   // id -> { type, frames, cursor, waiting, wake, conversationId, res, log }
const log = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a);

function cors(res) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Headers", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET,POST,PATCH,DELETE,OPTIONS");
}
function json(res, status, body) {
  cors(res);
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify(body));
}
function readBody(req) {
  return new Promise((resolve) => {
    let s = "";
    req.on("data", (c) => (s += c));
    req.on("end", () => { try { resolve(s ? JSON.parse(s) : {}); } catch { resolve({}); } });
  });
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function pauseFrameOf(frames) {
  return frames.find((f) => f.event === "questions_required" && !f.replay);
}

async function stream(session, res) {
  cors(res);
  res.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-cache", Connection: "keep-alive" });
  res.flushHeaders();  // uvicorn sends the response start before the first chunk; so must this
  session.res = res;
  const send = (obj) => {
    if (session.res !== res) return false;
    res.write(`data: ${JSON.stringify({ ...obj, agent_type: session.type, session_id: session.id })}\n\n`);
    return true;
  };
  const ping = setInterval(() => { if (session.res === res) res.write(": ping\n\n"); }, 5000);
  res.on("close", () => { clearInterval(ping); if (session.res === res) session.res = null; log("stream closed", session.id.slice(0, 8), "cursor", session.cursor); });

  while (session.cursor < session.frames.length) {
    if (session.res !== res) return;
    const frame = session.frames[session.cursor];
    if (frame.__answer__ !== undefined || frame.__send__ !== undefined) {
      session.waiting = frame.__answer__ !== undefined ? "answer" : "chat";
      // The real backend queues a message that arrives before the turn
      // boundary; so does this.
      if (session.queued > 0) {
        session.queued -= 1;
        if (session.waiting === "chat" && session.queuedIds?.length) {
          send({ event: "user_input_consumed", client_message_id: session.queuedIds.shift() });
        }
      } else {
        log("waiting for", session.waiting, session.id.slice(0, 8));
        await new Promise((r) => (session.wake = r));
      }
      session.waiting = null;
      session.cursor += 1;
      continue;
    }
    if (!send(frame)) return;
    session.cursor += 1;
    await sleep(FRAME_MS);
  }
  log("fixture done", session.id.slice(0, 8), "(stream stays open, idle)");
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  const path = url.pathname;
  if (req.method === "OPTIONS") { cors(res); res.writeHead(204); return res.end(); }
  if (!path.includes("/stream")) log("→", req.method, path);

  let m;
  if ((m = path.match(/^\/api\/agents\/([^/]+)\/sessions$/)) && req.method === "POST") {
    const type = m[1];
    const body = await readBody(req);
    const id = randomUUID();
    const frames = fixtures[type] || fixtures.insights;
    const conversationId = body.conversation_id || `conv-${id.slice(0, 8)}`;
    const session = { id, type, frames, cursor: 0, waiting: null, wake: null, conversationId, res: null };
    if (body.resume) {
      // The real backend re-emits the pause the thread is parked on, flagged
      // as a replay, and runs nothing until it is answered.
      const pause = pauseFrameOf(frames);
      const at = frames.findIndex((f) => f.__answer__ !== undefined);
      session.frames = [
        { event: "pipeline_started", status: "running", autonomy: "ask", autonomy_configured: "ask" },
        ...(pause && at >= 0 ? [{ ...pause, replay: true }] : []),
        ...frames.slice(at >= 0 ? at : frames.length),
      ];
    }
    sessions.set(id, session);
    log("create", type, id.slice(0, 8), body.resume ? "(resume)" : "", "prompt=", JSON.stringify(body.prompt || body.url || body.mode || ""));
    return json(res, 200, { session_id: id, stream_url: `/api/agents/${type}/sessions/${id}/stream`, agent_type: type, conversation_id: conversationId });
  }
  if ((m = path.match(/^\/api\/agents\/([^/]+)\/sessions\/([^/]+)\/stream$/)) && req.method === "GET") {
    const session = sessions.get(m[2]);
    if (!session) return json(res, 404, { detail: "Session not found." });
    log("stream open", m[2].slice(0, 8), "from cursor", session.cursor);
    return stream(session, res);
  }
  if ((m = path.match(/^\/api\/agents\/([^/]+)\/sessions\/([^/]+)\/messages$/)) && req.method === "POST") {
    const session = sessions.get(m[2]);
    if (!session) return json(res, 404, { detail: "Session not found." });
    const body = await readBody(req);
    log("message", body.type, m[2].slice(0, 8), JSON.stringify(body.answers || body.content || "").slice(0, 60), body.interrupt_id ? `interrupt_id=${body.interrupt_id}` : "");
    // A chat while the run is busy (mid-frames, or parked on a card) is
    // queued, as the real backend does; it is consumed at the next __send__
    // wait point, which then also releases the row's "queued" mark.
    if (body.type === "chat" && (session.waiting !== "chat")) {
      session.queued = (session.queued || 0) + 1;
      if (body.client_message_id) (session.queuedIds ||= []).push(body.client_message_id);
      return json(res, 200, { status: "queued", type: body.type, delivery: session.waiting === "answer" ? "steer" : "queue" });
    }
    if (session.waiting && session.wake) session.wake();
    else session.queued = (session.queued || 0) + 1;
    return json(res, 200, { status: "queued", type: body.type, delivery: "turn" });
  }
  if ((m = path.match(/^\/api\/agents\/([^/]+)\/sessions\/([^/]+)$/)) && req.method === "GET") {
    const session = sessions.get(m[2]);
    if (!session) return json(res, 404, { detail: "Session not found." });
    // What the run is parked on, so a reattaching client can put the card back.
    const pending = session.waiting === "answer" ? [session.frames.slice(0, session.cursor).reverse().find((f) => f.event === "questions_required")].filter(Boolean) : [];
    return json(res, 200, { session_id: m[2], agent_type: m[1], report_versions: [], has_pending_question: pending.length > 0, pending });
  }
  if ((m = path.match(/^\/api\/agents\/([^/]+)\/sessions\/([^/]+)$/)) && req.method === "DELETE") {
    const session = sessions.get(m[2]);
    log("close", m[2].slice(0, 8));
    if (session?.res) session.res.end();
    sessions.delete(m[2]);
    return json(res, 200, { status: "ok" });
  }
  if ((m = path.match(/^\/api\/agents\/([^/]+)\/conversations\/([^/]+)\/state$/))) {
    const pause = pauseFrameOf(fixtures[m[1]] || []);
    return json(res, 200, m[1] === "insights" && pause
      ? { status: "paused", pauses: [pause], todos: [{ content: "Pull Ads campaigns", status: "completed" }] }
      : { status: "unsupported", pauses: [], todos: [] });
  }
  if ((m = path.match(/^\/api\/agents\/([^/]+)\/conversations\/([^/]+)$/)) && req.method === "GET") {
    return json(res, 200, {
      conversation: { id: m[2], agent_type: m[1], title: "why did CPA jump?" },
      events: [
        { seq: 1, kind: "user", data: { content: "why did CPA jump?" } },
        { seq: 2, kind: "assistant", data: { text: "Before I dig in, one thing:" } },
        { seq: 3, kind: "question", data: { questions: [{ question: "Which goal matters most?" }] } },
      ],
    });
  }
  if (path.startsWith("/api/agents/") && req.method === "GET") return json(res, 200, []);
  if (req.method === "GET") return json(res, 200, []);
  return json(res, 200, {});
});

const PORT = Number(process.argv[2] || 8012);
server.listen(PORT, () => log(`mock backend on :${PORT} (fixtures: ${Object.keys(fixtures).join(", ")})`));
