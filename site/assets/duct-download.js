/* Resolves the current desktop release and upgrades download CTAs in place.
 *
 * Every download CTA on the site ships as a plain link to /download. This file
 * only ever *improves* one — naming the visitor's platform and pointing at the
 * installer itself. If the manifest 404s (no release published yet), the fetch
 * fails, or JavaScript never runs, the link still works and /download states
 * the situation. No CTA on the site can become a dead end, which matters more
 * now that downloading is the only call to action.
 *
 * The manifest URL is fixed: GitHub resolves `latest` to the newest release and
 * the release carries downloads.json, so shipping a new desktop version never
 * requires touching the site. See .github/scripts/build-downloads-manifest.mjs.
 */
(function () {
  var MANIFEST = 'https://github.com/5hirish/duct/releases/latest/download/downloads.json';
  var RELEASES = 'https://github.com/5hirish/duct/releases';

  // Order is the tie-break when detection is ambiguous, and the order the
  // "all platforms" list renders in.
  var SLOTS = [
    { key: 'macos',          label: 'macOS',            hint: 'Universal · Apple silicon and Intel' },
    { key: 'windows',        label: 'Windows',          hint: 'Windows 10 and later' },
    { key: 'linux-appimage', label: 'Linux (AppImage)', hint: 'Runs on any distribution' },
    { key: 'linux-deb',      label: 'Linux (.deb)',     hint: 'Debian and Ubuntu' }
  ];

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
      pending = fetch(MANIFEST, { cache: 'no-store' }).then(function (r) {
        if (!r.ok) throw new Error(r.status);
        return r.json();
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

  window.DuctDownload = { load: load, detect: detect, mb: mb, SLOTS: SLOTS, RELEASES: RELEASES };

  // Partials inject CTAs after DOMContentLoaded, so wait for them when present.
  if (window.__DUCT_PARTIALS_READY) wire();
  else if (window.__DUCT_PARTIALS_LOADING || document.querySelector('[data-duct-partial]')) {
    document.addEventListener('duct-partials-ready', wire, { once: true });
  } else if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wire, { once: true });
  } else wire();
})();
