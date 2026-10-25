/**
 * Where a connector comes from, shown on its card and in its dialog.
 *
 * Native connectors are Duct's own code: it reads (and, where there is an
 * executor, changes) the vendor's data through the vendor's API, feeds
 * briefs, alerts and the chat, and Duct maintains it. MCP connectors are a
 * vendor's own server that Duct's agent calls (backend `service/mcp/`): the
 * vendor decides what its tools do, and only the insights chat uses them.
 * One grid holds both, so the card has to say which one it is, and who
 * stands behind it.
 */

export const ConnectorKind = Object.freeze({
  NATIVE: "native",
  MCP: "mcp",
});

/** Who publishes every native connector. A brand name, never translated. */
export const DUCT_PUBLISHER = "Duct";

export const NATIVE_SOURCE = Object.freeze({ kind: ConnectorKind.NATIVE, publisher: DUCT_PUBLISHER });

/** An MCP connector, published by whoever runs the server. */
export function mcpSource(publisher) {
  return { kind: ConnectorKind.MCP, publisher: publisher || "" };
}
