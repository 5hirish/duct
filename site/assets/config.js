// ─── Duct Site Config ────────────────────────────────────────────────────────
// PostHog: project settings → Project token (public by design: it can only
//   send events, never read them). It loads only behind the consent gate in
//   duct.js, and never on localhost.
// posthog_api_host: the app's reverse proxy to PostHog US, so a blocker that
//   drops *.posthog.com does not drop the event with it.
// api_url / app_url: auto-switched to localhost in local dev
// ─────────────────────────────────────────────────────────────────────────────

var _isLocal = location.hostname === 'localhost' || location.hostname === '127.0.0.1';

var DUCT_CONFIG = {
  posthog_token: 'phc_zeaCYQ3SbcNouD6T2LsVVnjNR4JLrS23CjgZxcu47MtU',
  posthog_api_host: 'https://app.getduct.ai/ingest',
  posthog_ui_host: 'https://us.posthog.com',
  api_url: _isLocal ? 'http://localhost:8002' : 'https://api.getduct.ai',
  app_url: _isLocal ? 'http://localhost:3003' : 'https://app.getduct.ai',
  turnstile_site_key: '0x4AAAAAAC1Fpx1L4KeNnMpK'
};
