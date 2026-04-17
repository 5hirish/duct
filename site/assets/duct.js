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

function initDuct() {
  if (window.__ductInitDone) return;
  window.__ductInitDone = true;

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

// Mark active nav/footer links for partial-based pages
(function() {
var currentPath = window.location.pathname;
if (!currentPath) return;
if (currentPath.length > 1 && currentPath.slice(-1) === '/') {
  currentPath = currentPath.slice(0, -1);
}

function normalizePath(href) {
  if (!href) return '';
  if (href.indexOf('#') === 0) return '';
  var url;
  try {
    url = new URL(href, window.location.origin);
  } catch (e) {
    return '';
  }
  if (url.origin !== window.location.origin) return '';
  var path = url.pathname || '';
  if (path.length > 1 && path.slice(-1) === '/') path = path.slice(0, -1);
  return path || '/';
}

document.querySelectorAll('#nav a[href], .footer-expanded a[href]').forEach(function(anchor) {
  var path = normalizePath(anchor.getAttribute('href'));
  if (!path) return;
  if (path === currentPath) anchor.setAttribute('aria-current', 'page');
});

var navEl = document.getElementById('nav');
if (navEl) {
  navEl.querySelectorAll('.nav-dropdown').forEach(function(drop) {
    var menu = drop.querySelector('.dropdown-menu-inner');
    if (!menu) return;
    var links = menu.querySelectorAll('a.dm-item[href]');
    var isSolutionsMenu = false;
    var isToolsMenu = false;
    for (var j = 0; j < links.length; j++) {
      var mp = normalizePath(links[j].getAttribute('href'));
      if (mp.indexOf('/for-') === 0) isSolutionsMenu = true;
      if (mp.indexOf('/tools/') === 0) isToolsMenu = true;
    }
    var trigger = drop.querySelector(':scope > a.nav-link');
    if (!trigger) return;
    if (isSolutionsMenu && currentPath.indexOf('/for-') === 0) {
      trigger.classList.add('nav-link--active-section');
    }
    if (isToolsMenu && currentPath.indexOf('/tools/') === 0) {
      trigger.classList.add('nav-link--active-section');
    }
  });
}
})();

// Render related tools link chips from one config map
(function() {
var tools = [
  { slug: 'saas-metrics-calculator', title: 'SaaS Metrics Benchmark Calculator', href: '/tools/saas-metrics-calculator' },
  { slug: 'weekly-brief-template', title: 'Weekly Marketing Brief Generator', href: '/tools/weekly-brief-template' },
  { slug: 'cac-ltv-calculator', title: 'CAC / LTV Calculator', href: '/tools/cac-ltv-calculator' },
  { slug: 'mrr-growth-calculator', title: 'MRR Growth Rate Calculator', href: '/tools/mrr-growth-calculator' },
  { slug: 'engagement-rate-calculator', title: 'Engagement Rate Calculator', href: '/tools/engagement-rate-calculator' },
  { slug: 'ctr-calculator', title: 'CTR Calculator', href: '/tools/ctr-calculator' },
  { slug: 'cpm-calculator', title: 'CPM Calculator', href: '/tools/cpm-calculator' },
  { slug: 'cpc-calculator', title: 'CPC Calculator', href: '/tools/cpc-calculator' },
  { slug: 'cpa-calculator', title: 'CPA Calculator', href: '/tools/cpa-calculator' },
  { slug: 'marketing-roi-calculator', title: 'Marketing ROI Calculator', href: '/tools/marketing-roi-calculator' }
];

var relatedByTool = {
  'saas-metrics-calculator': ['cac-ltv-calculator', 'mrr-growth-calculator', 'engagement-rate-calculator', 'ctr-calculator', 'cpm-calculator', 'cpc-calculator', 'cpa-calculator', 'marketing-roi-calculator', 'weekly-brief-template'],
  'weekly-brief-template': ['saas-metrics-calculator', 'cac-ltv-calculator', 'engagement-rate-calculator', 'ctr-calculator', 'cpm-calculator', 'cpc-calculator', 'cpa-calculator', 'marketing-roi-calculator', 'mrr-growth-calculator'],
  'cac-ltv-calculator': ['saas-metrics-calculator', 'mrr-growth-calculator', 'engagement-rate-calculator', 'ctr-calculator', 'cpm-calculator', 'cpc-calculator', 'cpa-calculator', 'marketing-roi-calculator', 'weekly-brief-template'],
  'mrr-growth-calculator': ['saas-metrics-calculator', 'cac-ltv-calculator', 'engagement-rate-calculator', 'ctr-calculator', 'cpm-calculator', 'cpc-calculator', 'cpa-calculator', 'marketing-roi-calculator', 'weekly-brief-template'],
  'engagement-rate-calculator': ['ctr-calculator', 'cpm-calculator', 'cpc-calculator', 'cpa-calculator', 'marketing-roi-calculator', 'saas-metrics-calculator', 'weekly-brief-template', 'mrr-growth-calculator', 'cac-ltv-calculator'],
  'ctr-calculator': ['cpc-calculator', 'cpm-calculator', 'cpa-calculator', 'marketing-roi-calculator', 'engagement-rate-calculator', 'saas-metrics-calculator', 'weekly-brief-template', 'mrr-growth-calculator', 'cac-ltv-calculator'],
  'cpm-calculator': ['cpc-calculator', 'cpa-calculator', 'marketing-roi-calculator', 'ctr-calculator', 'engagement-rate-calculator', 'saas-metrics-calculator', 'weekly-brief-template', 'mrr-growth-calculator', 'cac-ltv-calculator'],
  'cpc-calculator': ['cpa-calculator', 'marketing-roi-calculator', 'ctr-calculator', 'cpm-calculator', 'engagement-rate-calculator', 'saas-metrics-calculator', 'weekly-brief-template', 'mrr-growth-calculator', 'cac-ltv-calculator'],
  'cpa-calculator': ['marketing-roi-calculator', 'cpc-calculator', 'ctr-calculator', 'cpm-calculator', 'engagement-rate-calculator', 'saas-metrics-calculator', 'weekly-brief-template', 'mrr-growth-calculator', 'cac-ltv-calculator'],
  'marketing-roi-calculator': ['cpa-calculator', 'cpc-calculator', 'ctr-calculator', 'cpm-calculator', 'engagement-rate-calculator', 'saas-metrics-calculator', 'weekly-brief-template', 'mrr-growth-calculator', 'cac-ltv-calculator']
};

function findToolBySlug(slug) {
  for (var i = 0; i < tools.length; i++) {
    if (tools[i].slug === slug) return tools[i];
  }
  return null;
}

function getDefaultCandidates(currentSlug) {
  var list = [];
  for (var i = 0; i < tools.length; i++) {
    if (tools[i].slug !== currentSlug) list.push(tools[i]);
  }
  return list;
}

document.querySelectorAll('[data-related-tools]').forEach(function(container) {
  var current = container.getAttribute('data-current-tool') || '';
  var strategy = (container.getAttribute('data-related-strategy') || 'relevant').toLowerCase();
  var customSlugs = (container.getAttribute('data-related-slugs') || '').split(',').map(function(s) {
    return s.trim();
  }).filter(Boolean);
  var limit = parseInt(container.getAttribute('data-related-limit') || '', 10);
  var candidates = [];

  if (strategy === 'custom' && customSlugs.length) {
    customSlugs.forEach(function(slug) {
      if (slug === current) return;
      var tool = findToolBySlug(slug);
      if (tool) candidates.push(tool);
    });
  } else if (strategy === 'all') {
    candidates = getDefaultCandidates(current);
  } else {
    var relatedSlugs = relatedByTool[current] || [];
    relatedSlugs.forEach(function(slug) {
      var tool = findToolBySlug(slug);
      if (tool && tool.slug !== current) candidates.push(tool);
    });
    if (!candidates.length) candidates = getDefaultCandidates(current);
  }

  if (isNaN(limit) || limit <= 0) limit = candidates.length;

  var count = 0;
  for (var i = 0; i < candidates.length; i++) {
    var tool = candidates[i];
    if (count >= limit) break;
    var link = document.createElement('a');
    link.href = tool.href;
    link.className = 'insight-link';
    link.textContent = tool.title + ' →';
    container.appendChild(link);
    count++;
  }
});
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

linksHost.querySelectorAll('.nav-dropdown').forEach(function(drop) {
  var dropdownLinks = drop.querySelectorAll('.dropdown-menu a[href]');
  if (!dropdownLinks.length) return;
  hasDropdownItems = true;
  var firstHref = dropdownLinks[0].getAttribute('href') || '';
  var groupLabel = firstHref.indexOf('/tools/') === 0 ? 'Free Tools' : 'Solutions';
  appendGroupLabel(groupLabel);
  dropdownLinks.forEach(function(anchor) {
    var href = anchor.getAttribute('href');
    var labelNode = anchor.querySelector('.dm-text strong');
    var label = labelNode ? labelNode.textContent.trim() : anchor.textContent.trim();
    var key = href + '|' + label;
    if (seen[key]) return;
    seen[key] = true;
    var mCls = 'nav-mobile-link';
    if (anchor.getAttribute('aria-current') === 'page') mCls += ' nav-mobile-link--current';
    appendLink(href, label, mCls);
  });
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
  if (!anchor.classList.contains('btn') && anchor.getAttribute('aria-current') === 'page') {
    className += ' nav-mobile-link--current';
  }
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

window.submitForm = submitForm;
}

if (window.__DUCT_PARTIALS_READY) {
  initDuct();
} else if (window.__DUCT_PARTIALS_LOADING || document.querySelector('[data-duct-partial]')) {
  document.addEventListener('duct-partials-ready', initDuct, { once: true });
} else {
  initDuct();
}
