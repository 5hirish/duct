/* Resolves the current desktop release and upgrades download CTAs in place.
 *
 * Two different jobs, and only one of them needs the network.
 *
 * The installer URLs are constants. `releases/latest/download/<name>` is
 * redirected by GitHub to whichever release is newest, so as long as the name
 * does not carry a version there is nothing to look up — the release workflow
 * publishes each installer a second time under the fixed names below
 * (.github/workflows/desktop-release.yml). A CTA is therefore upgraded to the
 * visitor's platform synchronously, before paint, with no request at all.
 *
 * The version and size are not constants, and only the download page shows
 * them. That is the one thing worth a request, and it is pure decoration: if
 * it fails, every link on the page still points at the right installer.
 *
 * It has to be api.github.com and not the release asset itself. The obvious
 * `releases/latest/download/downloads.json` redirects to
 * release-assets.githubusercontent.com, which sends no
 * Access-Control-Allow-Origin, so a browser cannot read it. That was invisible
 * for as long as the repo had no release: a 404 and a CORS failure land in the
 * same `catch`. api.github.com sends `Access-Control-Allow-Origin: *`, and its
 * unauthenticated limit is 60/hour per visitor IP — far above a page view.
 */
(function () {
  var API = 'https://api.github.com/repos/5hirish/duct/releases/latest';
  var RELEASES = 'https://github.com/5hirish/duct/releases';
  var LATEST = 'https://github.com/5hirish/duct/releases/latest/download/';

  // Fixed names published by the release workflow. Renaming one here without
  // renaming it there produces a 404 that nothing in CI notices.
  var SLOTS = [
    { key: 'macos',          label: 'macOS',            hint: 'Universal · Apple silicon and Intel',
      file: 'Duct-macOS-universal.dmg',   ext: '.dmg' },
    { key: 'windows',        label: 'Windows',          hint: 'Windows 10 and later',
      file: 'Duct-Windows-x64-setup.exe', ext: '.exe installer' },
    { key: 'linux-appimage', label: 'Linux (AppImage)', hint: 'Runs on any distribution',
      file: 'Duct-Linux-x86_64.AppImage', ext: '.AppImage' },
    { key: 'linux-deb',      label: 'Linux (.deb)',     hint: 'Debian and Ubuntu',
      file: 'Duct-Linux-amd64.deb',       ext: '.deb' }
  ];

  function urlFor(key) {
    for (var i = 0; i < SLOTS.length; i++) {
      if (SLOTS[i].key === key) return LATEST + SLOTS[i].file;
    }
    return null;
  }

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

  /* Upgrade every `[data-duct-download]` anchor to the visitor's installer.
   * Synchronous: the URL is a constant, so there is nothing to wait for and no
   * failure mode. The element's existing text and href stay as the fallback
   * for a platform we do not build for. */
  function wire() {
    var nodes = document.querySelectorAll('[data-duct-download]');
    if (!nodes.length) return;

    var mine = detect();
    var url = mine && urlFor(mine);
    if (!url) return; // unknown platform: leave the link to /download

    var label = SLOTS.filter(function (s) { return s.key === mine; })[0].label;
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      el.href = url;
      el.setAttribute('download', '');
      // `short` is for tight spots (the nav) where the platform name does not fit.
      el.textContent = el.hasAttribute('data-duct-download-short')
        ? 'Download ↓'
        : 'Download for ' + label + ' ↓';
    }
  }

  /* The download click, which is the top of the desktop funnel and was the one
   * conversion on this site nobody was counting.
   *
   * Delegated, because `wire()` rewrites these anchors and the /download page
   * lists every installer directly — one listener covers both, and anchors that
   * appear later. Matching on the release prefix as well as the attribute means
   * a per-platform link on /download counts even though it never needed
   * upgrading.
   *
   * Queued on dataLayer whether or not GTM has loaded; if the visitor declined
   * cookies it never loads and the array is simply never drained. */
  function osForHref(href) {
    var slot = SLOTS.filter(function (s) { return href && href.indexOf(s.file) !== -1; })[0];
    return (slot && slot.key) || detect() || '';
  }

  document.addEventListener('click', function (ev) {
    var el = ev.target && ev.target.closest && ev.target.closest('a[data-duct-download], a[href*="' + LATEST + '"]');
    if (!el) return;
    window.dataLayer = window.dataLayer || [];
    window.dataLayer.push({ event: 'download_started', os: osForHref(el.getAttribute('href') || '') });
  }, true);

  window.DuctDownload = { load: load, detect: detect, mb: mb, urlFor: urlFor,
                          SLOTS: SLOTS, RELEASES: RELEASES, LATEST: LATEST, API: API };

  // Partials inject CTAs after DOMContentLoaded, so wait for them when present.
  if (window.__DUCT_PARTIALS_READY) wire();
  else if (window.__DUCT_PARTIALS_LOADING || document.querySelector('[data-duct-partial]')) {
    document.addEventListener('duct-partials-ready', wire, { once: true });
  } else if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wire, { once: true });
  } else wire();
})();
