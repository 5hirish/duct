/* Loads shared HTML fragments from /partials/*.html into placeholders, then notifies duct.js.
 * Usage: <div data-duct-partial="/partials/nav-blog.html"></div>
 * Fires `duct-partials-ready` and sets window.__DUCT_PARTIALS_READY when done (including on error).
 * Include before <script src=".../duct.js" defer> (order may not be adjacent).
 */
(function () {
  var parser = new DOMParser();
  var version = window.DUCT_PARTIALS_VERSION || '2026-04-17';
  var nodes = Array.prototype.slice.call(document.querySelectorAll('[data-duct-partial]'));

  function notifyReady() {
    window.__DUCT_PARTIALS_READY = true;
    try {
      document.dispatchEvent(new CustomEvent('duct-partials-ready'));
    } catch (e) {
      /* IE11 / very old engines */
    }
  }

  if (!nodes.length) {
    notifyReady();
    return;
  }

  window.__DUCT_PARTIALS_LOADING = true;

  Promise.all(
    nodes.map(function (el) {
      var url = el.getAttribute('data-duct-partial');
      if (!url) return Promise.resolve();
      var requestUrl = url + (url.indexOf('?') === -1 ? '?' : '&') + 'v=' + encodeURIComponent(version);
      return fetch(requestUrl, { credentials: 'same-origin' })
        .then(function (res) {
          if (!res.ok) return null;
          return res.text();
        })
        .then(function (html) {
          if (html == null) return;
          html = html.replace(/^\s+|\s+$/g, '');
          if (!html) return;
          var doc = parser.parseFromString(html, 'text/html');
          var first = doc.body.firstElementChild;
          if (!first || !el.parentNode) return;
          el.parentNode.replaceChild(document.importNode(first, true), el);
        })
        .catch(function () {
          /* offline or file:// — leave placeholder */
        });
    })
  )
    .then(function () {
      notifyReady();
    })
    .catch(function () {
      notifyReady();
    });
})();
