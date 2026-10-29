/**
 * How much of production Sentry traces, in one place for all three runtimes
 * (browser, server, edge), which used to repeat the expression and could drift.
 *
 * A tenth, not a half. Every traced browser session is also profiled
 * (`profileLifecycle: "trace"` in `instrumentation-client.ts`), so this is the
 * profiling rate too, and both cost the person on the page: the sampling
 * profiler runs on their main thread and the spans leave over their
 * connection. When a regression needs more data, raise this for the week it
 * is being chased rather than charging every session for it all the time.
 * Development keeps everything, because there the trace is the point.
 */
export const TRACES_SAMPLE_RATE = process.env.NODE_ENV === "development" ? 1.0 : 0.1;
