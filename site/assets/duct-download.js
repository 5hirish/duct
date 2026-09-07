/* Resolves the current desktop release and upgrades download CTAs in place.
 *
 * Every download CTA on the site ships as a plain link (to /download, or to the
 * releases page). This file only ever *improves* one — naming the visitor's
 * platform and pointing at the installer itself. If the request fails, the
 * repo has no release yet, or JavaScript never runs, the link still works. No
 * CTA on the site can become a dead end, which matters more now that
 * downloading is the only call to action.
 *
 * Why the API and not the release asset
 * -------------------------------------
 * The release carries a `downloads.json` built for exactly this, and the
 * obvious URL is `releases/latest/download/downloads.json`. A browser cannot
 * read it: that redirects to release-assets.githubusercontent.com, which sends
 * no `Access-Control-Allow-Origin`, so the fetch dies in CORS. It looked fine
 * for as long as the repo had no release — the 404 and the CORS failure both
 * land in the same `catch`, so the page fell back and nothing said why.
 *
 * `api.github.com` sends `Access-Control-Allow-Origin: *`, so the release is
 * read from there and the installers are matched by filename. Unauthenticated
 * requests are limited to 60/hour per visitor IP, which is far above what one
 * page view costs. `downloads.json` is still published — it is the same data
 * for anything server-side that wants it without a rate limit.
 */
(function () {
  var API = 'https://api.github.com/repos/5hirish/duct/releases/latest';
  var RELEASES = 'https://github.com/5hirish/duct/releases';

  // Order is the tie-break when detection is ambiguous, and the order the
  // "all platforms" list renders in.
  var SLOTS = [
    { key: 'macos',          label: 'macOS',            hint: 'Universal · Apple silicon and Intel' },
    { key: 'windows',        label: 'Windows',          hint: 'Windows 10 and later' },
    { key: 'linux-appimage', label: 'Linux (AppImage)', hint: 'Runs on any distribution' },
    { key: 'linux-deb',      label: 'Linux (.deb)',     hint: 'Debian and Ubuntu' }
  ];

  // Same mapping as .github/scripts/build-downloads-manifest.mjs. Assets that
  // match nothing here (updater archives, .sig files, the manifests) are not
  // installers and are skipped.
  function slotFor(name) {
    if (/\.dmg$/i.test(name)) return 'macos';
    if (/-setup\.exe$/i.test(name)) return 'windows';
    if (/\.AppImage$/i.test(name)) return 'linux-appimage';
    if (/\.deb$/i.test(name)) return 'linux-deb';
    return null;
  }

  function detect() {
    // userAgentData is the only non-deprecated source, but Safari and Firefox
    // do not ship it — fall back to the UA string rather than guessing macOS,
    // which would hand a Windows user a .dmg.
    var p = (navigator.userAgentData && navigator.userAgentData.platform) || '';
    var ua = p + ' ' + (navigator.platform || '') + ' ' + (navigator.userAgent || '');
    if (/Win/i.test(ua)) return 'windows';
    if (/Mac|Darwin/i.test(ua)) return 'macos';
    if (/Linux|X11/i.test(ua)) return 'linux-appimage';
    return null;
  }

  function mb(bytes) {
    if (!bytes) return '';
    return ' · ' + Math.round(bytes / 1048576) + ' MB';
  }

  // One request per page regardless of how many CTAs are on it — the home page
  // has three.
  var pending = null;
  function load() {
    if (!pending) {
      pending = fetch(API, {
        cache: 'no-store',
        headers: { 'Accept': 'application/vnd.github+json' }
      }).then(function (r) {
        if (!r.ok) throw new Error(r.status);
        return r.json();
      }).then(function (rel) {
        var platforms = {};
        (rel.assets || []).forEach(function (a) {
          var key = slotFor(a.name);
          if (key && !platforms[key]) {
            platforms[key] = { filename: a.name, size: a.size, url: a.browser_download_url };
          }
        });
        return {
          // Tags are `desktop-v0.4.0`; the version is what people read.
          version: String(rel.tag_name || '').replace(/^desktop-v/, ''),
          release_url: rel.html_url,
          platforms: platforms
        };
      });
    }
    return pending;
  }

  /* Upgrade every `[data-duct-download]` anchor on the page. The element's
   * existing text and href are the fallback, so this never has to undo itself. */
  function wire() {
    var nodes = document.querySelectorAll('[data-duct-download]');
    if (!nodes.length) return;

    load().then(function (data) {
      var platforms = (data && data.platforms) || {};
      var mine = detect();
      var slot = SLOTS.filter(function (s) { return s.key === mine && platforms[s.key]; })[0];
      if (!slot) return; // unknown platform, or no build for it: leave /download

      var asset = platforms[slot.key];
      for (var i = 0; i < nodes.length; i++) {
        var el = nodes[i];
        el.href = asset.url;
        el.setAttribute('download', '');
        // `short` is for tight spots (the nav) where the platform name does not fit.
        el.textContent = el.hasAttribute('data-duct-download-short')
          ? 'Download ↓'
          : 'Download for ' + slot.label + ' ↓';
      }

      // Every CTA on a page resolves to the same build, so the notes beneath
      // them all say the same thing — no need to pair each one to an anchor.
      var notes = document.querySelectorAll('[data-duct-download-meta]');
      for (var j = 0; j < notes.length; j++) {
        notes[j].textContent =
          'Version ' + data.version + mb(asset.size) + ' · ' + slot.hint;
      }
    }).catch(function () {
      /* Left as shipped: a working link to /download. */
    });
  }

  window.DuctDownload = { load: load, detect: detect, mb: mb, SLOTS: SLOTS, RELEASES: RELEASES, API: API };

  // Partials inject CTAs after DOMContentLoaded, so wait for them when present.
  if (window.__DUCT_PARTIALS_READY) wire();
  else if (window.__DUCT_PARTIALS_LOADING || document.querySelector('[data-duct-partial]')) {
    document.addEventListener('duct-partials-ready', wire, { once: true });
  } else if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wire, { once: true });
  } else wire();
})();
