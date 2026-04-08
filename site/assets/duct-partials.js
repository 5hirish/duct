/* Loads shared HTML fragments from /partials/*.html into placeholders before duct.js runs.
 * Usage: <div data-duct-partial="/partials/nav-blog.html"></div>
 * Include as a blocking script immediately before <script src=".../duct.js" defer>.
 */
(function () {
  var nodes = document.querySelectorAll('[data-duct-partial]');
  var parser = new DOMParser();
  for (var i = 0; i < nodes.length; i++) {
    var el = nodes[i];
    var url = el.getAttribute('data-duct-partial');
    if (!url) continue;
    try {
      var xhr = new XMLHttpRequest();
      xhr.open('GET', url, false);
      xhr.send(null);
      if (xhr.status < 200 || xhr.status >= 300) continue;
      var html = xhr.responseText.replace(/^\s+|\s+$/g, '');
      if (!html) continue;
      var doc = parser.parseFromString(html, 'text/html');
      var first = doc.body.firstElementChild;
      if (!first) continue;
      el.parentNode.replaceChild(document.importNode(first, true), el);
    } catch (e) {
      /* offline or file:// — leave placeholder */
    }
  }
})();
