/**
 * What leaves the browser, minus what must not: query strings (OAuth
 * `auth_code`s, invite tokens) and the two route shapes whose last segment is
 * a credential. Shared by the browser reporter and the server one, and kept
 * free of imports so both, and the tests, can load it.
 */

/** Paths whose last segment is a credential: an invitation, a shared audit. */
const SECRET_PATHS = [/^(\/invite\/)[^/]+/, /^(\/open\/audit\/)[^/]+/];

const URL_PROPERTIES = [
  "$current_url",
  "$referrer",
  "$initial_current_url",
  "$initial_referrer",
  "$session_entry_url",
  "$session_entry_referrer",
];
const PATH_PROPERTIES = [
  "$pathname",
  "$initial_pathname",
  "$session_entry_pathname",
  "$prev_pageview_pathname",
];

/** A credential in a path becomes its placeholder; a query string goes. */
export function scrubPath(path) {
  if (typeof path !== "string") return path;
  return SECRET_PATHS.reduce((p, re) => p.replace(re, "$1[token]"), path.split(/[?#]/)[0]);
}

export function scrubUrl(value) {
  if (typeof value !== "string" || !value) return value;
  try {
    const url = new URL(value);
    return `${url.origin}${scrubPath(url.pathname)}`;
  } catch {
    return scrubPath(value);
  }
}

function scrubProps(props) {
  if (!props) return;
  for (const key of URL_PROPERTIES) if (key in props) props[key] = scrubUrl(props[key]);
  for (const key of PATH_PROPERTIES) if (key in props) props[key] = scrubPath(props[key]);
}

/**
 * Query strings carry OAuth `auth_code`s and invite tokens, and two route
 * shapes carry credentials in the path. PostHog has already lifted `utm_*`
 * and click ids into their own properties by the time this runs, so
 * attribution survives the cut.
 */
export function beforeSend(event) {
  if (!event) return event;
  scrubProps(event.properties);
  scrubProps(event.$set);
  scrubProps(event.$set_once);
  return event;
}
