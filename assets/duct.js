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
