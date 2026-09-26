/**
 * Is this pasted text a link to one TikTok post?
 *
 * A mirror of `parse_tiktok_post_url` in backend service/clone_reference.py,
 * which is the authority: the server rebuilds the URL from the handle and the
 * id and refuses anything else with a 422. This copy exists so the clone
 * dialog can say what is wrong while the person is still looking at the
 * field, instead of after a session has started and failed. It decides
 * nothing the server does not decide again.
 *
 * Returns `{ url, handle, postId }` with the canonical URL, or `{ error }`
 * with a `TikTokUrlError` code the caller turns into words.
 */

export const TikTokUrlError = Object.freeze({
  EMPTY:      "empty",
  NOT_A_LINK: "not_a_link",
  NOT_TIKTOK: "not_tiktok",
  SHARE_LINK: "share_link",
  NOT_A_POST: "not_a_post",
});

const TIKTOK_HOSTS = new Set(["tiktok.com", "www.tiktok.com", "m.tiktok.com"]);
// Share links carry no post id; the server would have to follow a redirect.
const SHORT_LINK_HOSTS = new Set(["vm.tiktok.com", "vt.tiktok.com"]);
const HANDLE_RE = /^@[A-Za-z0-9._]{1,64}$/;
const POST_ID_RE = /^\d{8,25}$/;
const POST_KINDS = new Set(["video", "photo"]);
const MAX_URL_CHARS = 2048;

export function parseTikTokPostUrl(raw) {
  let text = String(raw ?? "").trim();
  if (!text || text.length > MAX_URL_CHARS) return { error: TikTokUrlError.EMPTY };
  if (!text.includes("://")) text = `https://${text}`;

  let url;
  try {
    url = new URL(text);
  } catch {
    return { error: TikTokUrlError.NOT_A_LINK };
  }
  // URL drops a default port, so any port left here is one we refuse.
  if (!["https:", "http:"].includes(url.protocol) || url.username || url.password || url.port) {
    return { error: TikTokUrlError.NOT_TIKTOK };
  }
  const host = url.hostname.replace(/\.$/, "").toLowerCase();
  const segments = url.pathname.split("/").filter(Boolean);
  if (SHORT_LINK_HOSTS.has(host) || (TIKTOK_HOSTS.has(host) && segments[0] === "t")) {
    return { error: TikTokUrlError.SHARE_LINK };
  }
  if (!TIKTOK_HOSTS.has(host)) return { error: TikTokUrlError.NOT_TIKTOK };

  const [atHandle, kind, postId] = segments;
  if (segments.length !== 3 || !HANDLE_RE.test(atHandle) || !POST_KINDS.has(kind) || !POST_ID_RE.test(postId)) {
    return { error: TikTokUrlError.NOT_A_POST };
  }
  // /video/ for photo posts too, as the server writes it.
  return { url: `https://www.tiktok.com/${atHandle}/video/${postId}`, handle: atHandle.slice(1), postId };
}
