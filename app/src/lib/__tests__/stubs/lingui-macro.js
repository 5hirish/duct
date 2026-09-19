/**
 * The Lingui macros, for tests.
 *
 * `msg`, `t`, `plural` and friends are compile-time macros: the SWC plugin
 * rewrites them in `next build` and `next dev`, and vitest runs neither, so a
 * `lib/*.js` module that carries a `msg` label would throw the moment a test
 * imported it. These are the macros' runtime shape with no catalogue behind
 * them — the English comes back, which is what a logic test wants to see.
 * Wired in by `resolve.alias` in vitest.config.js.
 */

function interpolate(strings, values) {
  return strings.reduce((out, part, i) => out + part + (i < values.length ? String(values[i]) : ""), "");
}

/** msg`…` → a message descriptor; `i18n._(descriptor)` renders `message`. */
export function msg(strings, ...values) {
  if (typeof strings === "object" && !Array.isArray(strings)) return strings;
  const message = interpolate(strings, values);
  return { id: message, message };
}
export const defineMessage = msg;

/** t`…` → the English string, values in. Also accepts a descriptor. */
export function t(strings, ...values) {
  if (typeof strings === "object" && !Array.isArray(strings)) return strings.message ?? strings.id;
  return interpolate(strings, values);
}

/** plural(n, { one, other }) → the matching form with `#` replaced. */
export function plural(value, forms) {
  const form = value === 1 && forms.one != null ? forms.one : forms.other;
  return String(form).replace(/#/g, String(value));
}

export function select(value, forms) {
  return forms[value] ?? forms.other ?? "";
}

export function selectOrdinal(value, forms) {
  return select(value, forms);
}
