// ─── Duct Site Config ────────────────────────────────────────────────────────
// GTM: google.com/tagmanager → Admin → Container ID
// api_url / app_url: auto-switched to localhost in local dev
// ─────────────────────────────────────────────────────────────────────────────

var _isLocal = location.hostname === 'localhost' || location.hostname === '127.0.0.1';

var DUCT_CONFIG = {
  gtm: 'GTM-PKL589SW',
  api_url: _isLocal ? 'http://localhost:8002' : 'https://api.getduct.ai',
  app_url: _isLocal ? 'http://localhost:3003' : 'https://app.getduct.ai',
  turnstile_site_key: '0x4AAAAAAC1Fpx1L4KeNnMpK'
};
