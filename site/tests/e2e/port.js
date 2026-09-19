// The one place the test server's port is written. The static server, the
// Playwright config and the consent spec (which needs a real hostname, so it
// cannot use baseURL) all read it here; three copies of a number drift, and
// this one did when the port moved.
//
// 8091 sits beside the site dev server's 8090. The old 4317 is the OTLP gRPC
// port, so the suite could not start on a laptop running a trace collector.
module.exports = { PORT: Number(process.env.PORT || 8091) };
