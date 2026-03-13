// Scroll reveal
const obs = new IntersectionObserver(function(entries) {
entries.forEach(function(e) { if (e.isIntersecting) e.target.classList.add('in'); });
}, { threshold: 0.08, rootMargin: '0px 0px -40px 0px' });
document.querySelectorAll('.reveal').forEach(function(el) { obs.observe(el); });

// Nav shadow
window.addEventListener('scroll', function() {
document.getElementById('nav').style.boxShadow = window.scrollY > 10 ? '0 2px 20px rgba(0,0,0,.07)' : 'none';
});

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
})
.catch(function() {
btn.textContent = 'You are on the list!';
btn.style.background = '#1a9e5c';
btn.disabled = false;
input.disabled = true;
});
}
