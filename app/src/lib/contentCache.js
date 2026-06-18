/**
 * Tiny in-memory TTL cache for Content reads, with in-flight de-duplication.
 *
 * Why: the Content tabs unmount on switch and refetch on every remount. These
 * reads (posts, brand, analytics, formats) rarely change between tab switches,
 * so we serve them from memory within a short TTL and de-dupe concurrent calls.
 *
 * Correctness: every write goes through contentApi, which invalidates the
 * relevant key prefix. We err toward freshness — invalidation is broad (by
 * prefix) and TTLs are short, so the worst case is an extra refetch, never
 * stale data after an edit. The cache is module-scoped (per browser tab) and
 * cleared on full reload.
 */

const store = new Map();    // key -> { value, expires }
const inflight = new Map(); // key -> Promise

/** Return cached value if fresh; otherwise run `fetcher`, cache success, return it. */
export async function cached(key, ttlMs, fetcher) {
  const hit = store.get(key);
  if (hit && hit.expires > Date.now()) return hit.value;

  const pending = inflight.get(key);
  if (pending) return pending;

  const p = (async () => {
    try {
      const value = await fetcher();
      store.set(key, { value, expires: Date.now() + ttlMs });
      return value;
    } finally {
      inflight.delete(key);
    }
  })();
  inflight.set(key, p);
  return p;
}

/** Read the last cached value for `key` even if its TTL has lapsed, else null.
 * For stale-while-revalidate: paint the stale value instantly, then refetch. */
export function peek(key) {
  const hit = store.get(key);
  return hit ? hit.value : null;
}

/** Write a value directly (no fetcher). Pairs with peek() for snapshot-style
 * state like the Discover tab's last run. Default: no expiry (read via peek,
 * which ignores TTL); the value lives until invalidated or a full page reload. */
export function put(key, value, ttlMs = Infinity) {
  store.set(key, { value, expires: Date.now() + ttlMs });
}

/** Drop every cached entry (and in-flight promise) whose key starts with `prefix`. */
export function invalidate(prefix) {
  for (const k of store.keys())    if (k.startsWith(prefix)) store.delete(k);
  for (const k of inflight.keys()) if (k.startsWith(prefix)) inflight.delete(k);
}

/** Clear everything — e.g. on project switch or sign-out. */
export function invalidateAll() {
  store.clear();
  inflight.clear();
}
