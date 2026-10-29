/**
 * Whether this browser holds a member's session, known before first paint.
 *
 * The server renders the front door for everyone, because the session lives
 * in `localStorage` and the server cannot see it. A member who opens the app
 * at `/` (every desktop launch does) is redirected into it once the page
 * hydrates, and without this they would watch the front door flash first.
 * The script below runs before the body paints, marks `<html>` with
 * `data-session="member"`, and `styles/signin.css` keeps the front door
 * hidden while the redirect happens.
 *
 * A display hint, never a trust decision: it decodes the token without
 * verifying it, exactly as `isSignedInUser()` (`lib/guest.js`) does. It
 * mirrors that check and the per-shell keys in `lib/authFetch.js`, which a
 * test holds it to. No imports, so a server component can inline it.
 */

const ATTRIBUTE = "session";
const MEMBER = "member";

// Keep in step with AUTH_TOKEN_KEY and DESKTOP_AUTH_TOKEN_KEY in authFetch.js;
// the test fails if they drift.
const WEB_KEY = "duct_auth_token";
const DESKTOP_KEY = "duct_auth_token__desktop";

export const SESSION_HINT_SCRIPT = `(function(){try{var t=localStorage.getItem(window.__TAURI__?"${DESKTOP_KEY}":"${WEB_KEY}");if(!t)return;var p=JSON.parse(atob(t.split(".")[1].replace(/-/g,"+").replace(/_/g,"/")));if(p.exp*1000>Date.now()&&p.guest!==true)document.documentElement.dataset.${ATTRIBUTE}="${MEMBER}"}catch(e){}})()`;

/**
 * Drop the hint once the page knows better. The front door calls this when it
 * decides to show itself: a session the hint saw can still be gone by then
 * (signed out, or discarded as another backend's by `reconcileStoredSession`),
 * and the attribute outlives client navigations, so a stale one would hide the
 * front door from the person who just signed out.
 */
export function clearSessionHint() {
  if (typeof document === "undefined") return;
  delete document.documentElement.dataset[ATTRIBUTE];
}
