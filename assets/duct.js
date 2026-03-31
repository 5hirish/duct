// ─── Google Tag Manager (deferred) ───────────────────────────────────────────
(function(w, d, s, l, i) {
  var loaded = false;
  if (!i) return;

  function loadGtm() {
    if (loaded) return;
    loaded = true;
    w[l] = w[l] || [];
    w[l].push({ 'gtm.start': new Date().getTime(), event: 'gtm.js' });
    var f = d.getElementsByTagName(s)[0];
    var j = d.createElement(s);
    var dl = l !== 'dataLayer' ? '&l=' + l : '';
    j.async = true;
    j.src = 'https://www.googletagmanager.com/gtm.js?id=' + i + dl;
    f.parentNode.insertBefore(j, f);
  }

  // Load GTM after first interaction or when browser is idle.
  function bindInteractionTriggers() {
    ['pointerdown', 'keydown', 'scroll', 'touchstart'].forEach(function(evt) {
      w.addEventListener(evt, loadGtm, { once: true, passive: true });
    });
  }

  bindInteractionTriggers();

  if ('requestIdleCallback' in w) {
    w.requestIdleCallback(loadGtm, { timeout: 3000 });
  } else {
    w.setTimeout(loadGtm, 3000);
  }
})(window, document, 'script', 'dataLayer', (window.DUCT_CONFIG || {}).gtm || '');
// ─────────────────────────────────────────────────────────────────────────────

// Scroll reveal
const obs = new IntersectionObserver(function(entries) {
entries.forEach(function(e) { if (e.isIntersecting) e.target.classList.add('in'); });
}, { threshold: 0.08, rootMargin: '0px 0px -40px 0px' });
document.querySelectorAll('.reveal').forEach(function(el) { obs.observe(el); });

// Nav shadow (passive + rAF throttled)
(function() {
var nav = document.getElementById('nav');
if (!nav) return;

var ticking = false;
function updateNavShadow() {
  nav.style.boxShadow = window.scrollY > 10 ? '0 2px 20px rgba(0,0,0,.07)' : 'none';
  ticking = false;
}

window.addEventListener('scroll', function() {
  if (ticking) return;
  ticking = true;
  window.requestAnimationFrame(updateNavShadow);
}, { passive: true });
})();

// Mobile nav drawer
(function() {
var nav = document.getElementById('nav');
if (!nav) return;

var linksHost = nav.querySelector('.nav-links');
if (!linksHost) return;

var toggle = document.createElement('button');
toggle.type = 'button';
toggle.className = 'nav-toggle';
toggle.setAttribute('aria-expanded', 'false');
toggle.setAttribute('aria-controls', 'nav-mobile-drawer');
toggle.setAttribute('aria-label', 'Open navigation menu');

var toggleIcon = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
toggleIcon.setAttribute('viewBox', '0 0 24 24');
toggleIcon.setAttribute('fill', 'none');
toggleIcon.setAttribute('stroke', 'currentColor');
toggleIcon.setAttribute('stroke-width', '2.2');
toggleIcon.setAttribute('stroke-linecap', 'round');
['M4 7h16', 'M4 12h16', 'M4 17h16'].forEach(function(d) {
  var path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  path.setAttribute('d', d);
  toggleIcon.appendChild(path);
});
toggle.appendChild(toggleIcon);

var backdrop = document.createElement('div');
backdrop.className = 'nav-mobile-backdrop';
backdrop.hidden = true;

var drawer = document.createElement('aside');
drawer.id = 'nav-mobile-drawer';
drawer.className = 'nav-mobile-drawer';
drawer.hidden = true;
drawer.setAttribute('aria-hidden', 'true');

var closeBtn = document.createElement('button');
closeBtn.type = 'button';
closeBtn.className = 'nav-mobile-close';
closeBtn.setAttribute('aria-label', 'Close navigation menu');
closeBtn.textContent = '×';

var header = document.createElement('div');
header.className = 'nav-mobile-header';
var title = document.createElement('span');
title.className = 'nav-mobile-title';
title.textContent = 'Menu';
header.appendChild(title);
header.appendChild(closeBtn);

var linkList = document.createElement('div');
linkList.className = 'nav-mobile-links';
var hasDropdownItems = false;

function appendLink(href, label, className) {
  if (!href || !label) return;
  var anchor = document.createElement('a');
  anchor.href = href;
  anchor.className = className || 'nav-mobile-link';
  anchor.textContent = label;
  linkList.appendChild(anchor);
}

function appendGroupLabel(label) {
  var item = document.createElement('div');
  item.className = 'nav-mobile-link-group-label';
  item.textContent = label;
  linkList.appendChild(item);
}

var seen = {};

var dropdownLinks = linksHost.querySelectorAll('.dropdown-menu a[href]');
if (dropdownLinks.length) {
  hasDropdownItems = true;
  appendGroupLabel('Solutions');
}

dropdownLinks.forEach(function(anchor) {
  var href = anchor.getAttribute('href');
  var labelNode = anchor.querySelector('.dm-text strong');
  var label = labelNode ? labelNode.textContent.trim() : anchor.textContent.trim();
  var key = href + '|' + label;
  if (seen[key]) return;
  seen[key] = true;
  appendLink(href, label, 'nav-mobile-link');
});

linksHost.querySelectorAll('a[href]').forEach(function(anchor) {
  if (anchor.closest('.dropdown-menu')) return;
  if (hasDropdownItems && anchor.parentElement && anchor.parentElement.classList.contains('nav-dropdown')) return;
  var href = anchor.getAttribute('href');
  var label = anchor.textContent.trim();
  if (!label) return;
  var key = href + '|' + label;
  if (seen[key]) return;
  seen[key] = true;
  var className = anchor.classList.contains('btn')
    ? 'nav-mobile-link btn btn-orange nav-mobile-link--cta'
    : 'nav-mobile-link';
  appendLink(href, label, className);
});

if (!linksHost.querySelector('.btn') && document.getElementById('cta')) {
  appendLink('#cta', 'Get early access →', 'nav-mobile-link btn btn-orange nav-mobile-link--cta');
}

if (!linkList.children.length) return;

drawer.appendChild(header);
drawer.appendChild(linkList);
nav.appendChild(toggle);
document.body.appendChild(backdrop);
document.body.appendChild(drawer);

var focusables = 'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])';
var lastFocused = null;

function setOpen(isOpen) {
  toggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
  drawer.setAttribute('aria-hidden', isOpen ? 'false' : 'true');
  toggle.setAttribute('aria-label', isOpen ? 'Close navigation menu' : 'Open navigation menu');
  backdrop.hidden = !isOpen;
  drawer.hidden = !isOpen;
  document.body.style.overflow = isOpen ? 'hidden' : '';

  if (isOpen) {
    lastFocused = document.activeElement;
    requestAnimationFrame(function() {
      backdrop.classList.add('is-open');
      drawer.classList.add('is-open');
      closeBtn.focus();
    });
    return;
  }

  backdrop.classList.remove('is-open');
  drawer.classList.remove('is-open');
  if (lastFocused && lastFocused.focus) lastFocused.focus();
}

function closeDrawer() {
  setOpen(false);
  window.setTimeout(function() {
    if (!drawer.classList.contains('is-open')) {
      backdrop.hidden = true;
      drawer.hidden = true;
    }
  }, 220);
}

toggle.addEventListener('click', function() {
  if (drawer.classList.contains('is-open')) closeDrawer();
  else setOpen(true);
});

closeBtn.addEventListener('click', closeDrawer);
backdrop.addEventListener('click', closeDrawer);
linkList.querySelectorAll('a[href]').forEach(function(anchor) {
  anchor.addEventListener('click', closeDrawer);
});

window.addEventListener('keydown', function(e) {
  if (!drawer.classList.contains('is-open')) return;
  if (e.key === 'Escape') {
    closeDrawer();
    return;
  }
  if (e.key !== 'Tab') return;
  var items = drawer.querySelectorAll(focusables);
  if (!items.length) return;
  var first = items[0];
  var last = items[items.length - 1];
  if (e.shiftKey && document.activeElement === first) {
    e.preventDefault();
    last.focus();
  } else if (!e.shiftKey && document.activeElement === last) {
    e.preventDefault();
    first.focus();
  }
});

window.addEventListener('resize', function() {
  if (window.innerWidth > 860 && drawer.classList.contains('is-open')) closeDrawer();
});
})();

// UTM params — persist to sessionStorage and attach to dataLayer on pageload
(function() {
var params = new URLSearchParams(window.location.search);
var utmKeys = ['utm_source','utm_medium','utm_campaign','utm_term','utm_content'];
var utms = {};
utmKeys.forEach(function(k) {
  var v = params.get(k) || sessionStorage.getItem(k);
  if (v) { utms[k] = v; sessionStorage.setItem(k, v); }
});
if (Object.keys(utms).length) {
  window.dataLayer = window.dataLayer || [];
  window.dataLayer.push(Object.assign({ event: 'utm_data' }, utms));
}
})();

// Shared submit function — reads form URL and entry ID from data- attributes on the button
function submitForm(inputId, btn) {
var input = document.getElementById(inputId);
var email = input.value.trim();
if (!email || email.indexOf('@') === -1) {
input.style.borderColor = 'var(--orange)';
input.focus();
setTimeout(function() { input.style.borderColor = ''; }, 2000);
return;
}
btn.textContent = 'Submitting...';
btn.disabled = true;

var formURL = btn.dataset.formUrl;
var entryId = btn.dataset.entryId;
var body = new FormData();
body.append(entryId, email);

fetch(formURL, { method: 'POST', mode: 'no-cors', body: body })
.then(function() {
btn.textContent = 'You are on the list!';
btn.style.background = '#1a9e5c';
btn.style.boxShadow = '0 8px 24px rgba(26,158,92,.25)';
btn.disabled = false;
input.disabled = true;
window.dataLayer = window.dataLayer || [];
window.dataLayer.push({ event: 'form_submit', page: window.location.pathname + window.location.search + (window.location.hash || '') });
})
.catch(function() {
btn.textContent = 'You are on the list!';
btn.style.background = '#1a9e5c';
btn.disabled = false;
input.disabled = true;
window.dataLayer = window.dataLayer || [];
window.dataLayer.push({ event: 'form_submit', page: window.location.pathname + window.location.search + (window.location.hash || '') });
});
}
