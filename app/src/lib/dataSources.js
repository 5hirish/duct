/**
 * "How many data sources can Duct actually reach?" — the rule, with no IO.
 *
 * Dependency-free so `scripts/check-data-sources.mjs` can load it in bare node,
 * the same arrangement as connectorCount.js and desk.js.
 *
 * This is the CLIENT half of `service/connector_access.py`. That module answers
 * the question properly — it walks the whole connector registry, so OAuth
 * connectors and pasted-API-key connectors are inventoried the same way, and it
 * applies the project's bindings. The browser's older answer (connectorCount.js)
 * could only ever see four Google session tokens plus a list of stored rows,
 * which is why it and the Connections page kept disagreeing.
 *
 * Keep the three statuses in step with the constants in that file.
 */

/** The project points this connector at a specific account. Ready to use. */
export const STATUS_BOUND = "bound";
/** Credentials are stored; this project has not chosen an account yet. */
export const STATUS_AVAILABLE = "available";
/** Nothing stored. This is the one that means "go and connect something". */
export const STATUS_NOT_CONNECTED = "not_connected";

/**
 * Connected = anything but `not_connected`.
 *
 * `available` counts deliberately. The backend treats a single stored account
 * with no binding as unambiguous and uses it, so calling that "not connected"
 * would ask someone to reconnect a source that already works. Choosing between
 * two accounts is a later, different question, and the agent asks it itself
 * (SelectAccount) rather than the desk pre-empting it.
 */
export function isConnected(source) {
  const status = source?.status;
  return status === STATUS_BOUND || status === STATUS_AVAILABLE;
}

export function connectedSources(sources = []) {
  return (Array.isArray(sources) ? sources : []).filter(isConnected);
}

export function connectedCount(sources = []) {
  return connectedSources(sources).length;
}
