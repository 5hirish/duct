/**
 * An OpenAI-compatible endpoint as one credential string.
 *
 * The address, the key (possibly empty) and the models the reader chose, with
 * the context length the server reported for each, packed so the result can
 * go wherever a key goes: session storage, the desktop keychain, the
 * `X-Provider-Compatible` header, a remembered key. `backend/service/
 * compatible.py` reads the same shape; `__tests__/endpointCredential.test.js`
 * and the backend's `test_compatible_provider.py` hold one fixture between
 * them so the two cannot drift apart.
 */

export const CREDENTIAL_PREFIX = "oaic1.";

function toBase64Url(text) {
  const bytes = new TextEncoder().encode(text);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
}

function fromBase64Url(encoded) {
  const padded = encoded.replaceAll("-", "+").replaceAll("_", "/") + "=".repeat((4 - (encoded.length % 4)) % 4);
  const binary = atob(padded);
  return new TextDecoder().decode(Uint8Array.from(binary, (char) => char.charCodeAt(0)));
}

/** `{ baseUrl, apiKey, models: [{ id, contextLength }] }` → the credential. */
export function packEndpoint({ baseUrl, apiKey = "", models = [] }) {
  const body = { u: baseUrl, k: apiKey, m: models.map((model) => [model.id, model.contextLength || 0]) };
  return CREDENTIAL_PREFIX + toBase64Url(JSON.stringify(body));
}

/** The endpoint inside a credential, or null for anything that is not one. */
export function unpackEndpoint(value) {
  const text = (value || "").trim();
  if (!text.startsWith(CREDENTIAL_PREFIX)) return null;
  try {
    const body = JSON.parse(fromBase64Url(text.slice(CREDENTIAL_PREFIX.length)));
    const models = (body.m || []).map(([id, contextLength]) => ({ id: String(id), contextLength: Number(contextLength) || 0 }));
    if (!body.u || models.length === 0) return null;
    return { baseUrl: String(body.u), apiKey: String(body.k || ""), models };
  } catch {
    return null;
  }
}
