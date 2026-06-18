"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  getDiscoverResults,
  getDiscoverRunStatus,
  startDiscoverRun,
} from "../lib/contentApi";

/**
 * Discovery run state machine: idle → running → polling → fetching → done.
 *
 * Mirrors nomadapps/marketing/app/src/hooks/useScraperRun.ts but talks
 * to duct's backend (`/api/content/discover/*`) instead of the Vite
 * middleware.
 *
 * Returns:
 *   - phase, results, error, elapsed (seconds)
 *   - runId, datasetId (set once the run starts)
 *   - startRun({ projectId, actorId, inputPayload })
 *   - reset()
 */
export function useScraperRun() {
  const [phase,     setPhase]     = useState("idle");
  const [results,   setResults]   = useState([]);
  const [error,     setError]     = useState("");
  const [elapsed,   setElapsed]   = useState(0);
  const [runId,     setRunId]     = useState("");
  const [datasetId, setDatasetId] = useState("");

  const timerRef   = useRef(null);
  const pollRef    = useRef(null);
  const startedAt  = useRef(0);
  const cancelled  = useRef(false);

  const clearTimers = useCallback(() => {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
    if (pollRef.current)  { clearInterval(pollRef.current);  pollRef.current  = null; }
  }, []);

  const reset = useCallback(() => {
    cancelled.current = true;
    clearTimers();
    setPhase("idle");
    setResults([]);
    setError("");
    setElapsed(0);
    setRunId("");
    setDatasetId("");
  }, [clearTimers]);

  useEffect(() => () => {
    // Stop polling on unmount.
    cancelled.current = true;
    clearTimers();
  }, [clearTimers]);

  // Restore a previous run's results without re-scraping (stale snapshot replay).
  const hydrate = useCallback(({ results: r, runId: rid = "", datasetId: did = "" }) => {
    setResults(Array.isArray(r) ? r : []);
    setRunId(rid);
    setDatasetId(did);
    setError("");
    setPhase("done");
  }, []);

  // keepResults: on a refresh of the *same* query, leave the current results on
  // screen (with an "updating" treatment) instead of flashing a skeleton.
  const startRun = useCallback(async ({ projectId, actorId, inputPayload, keepResults = false }) => {
    cancelled.current = false;
    clearTimers();
    setPhase("running");
    if (!keepResults) setResults([]);
    setError("");
    setElapsed(0);
    setRunId("");
    setDatasetId("");

    startedAt.current = Date.now();
    timerRef.current = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startedAt.current) / 1000));
    }, 1000);

    try {
      const run = await startDiscoverRun({ projectId, actorId, inputPayload });
      if (cancelled.current) return;
      console.debug("[discover] run=%s dataset=%s status=%s", run.run_id, run.dataset_id, run.status);
      setRunId(run.run_id);
      setDatasetId(run.dataset_id);
      setPhase("polling");

      // Poll status every 3s until SUCCEEDED / FAILED / aborted.
      await new Promise((resolve, reject) => {
        pollRef.current = setInterval(async () => {
          if (cancelled.current) {
            clearInterval(pollRef.current); pollRef.current = null;
            reject(new Error("cancelled"));
            return;
          }
          try {
            const status = await getDiscoverRunStatus(run.run_id);
            if (status.status === "SUCCEEDED") {
              clearInterval(pollRef.current); pollRef.current = null;
              resolve();
            } else if (
              status.status === "FAILED" ||
              status.status === "ABORTED" ||
              status.status === "TIMED-OUT"
            ) {
              clearInterval(pollRef.current); pollRef.current = null;
              reject(new Error(`Run ${status.status.toLowerCase()}`));
            }
            // READY / RUNNING / ABORTING / TIMING-OUT — keep polling.
          } catch (e) {
            clearInterval(pollRef.current); pollRef.current = null;
            reject(e);
          }
        }, 3000);
      });

      if (cancelled.current) return;
      setPhase("fetching");
      const out = await getDiscoverResults(run.dataset_id, 500);
      if (cancelled.current) return;
      setResults(out.items || []);
      setPhase("done");
    } catch (e) {
      if (cancelled.current) return;
      setError(e?.message || String(e));
      setPhase("error");
    } finally {
      if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
    }
  }, [clearTimers]);

  return { phase, results, error, elapsed, runId, datasetId, startRun, reset, hydrate };
}
