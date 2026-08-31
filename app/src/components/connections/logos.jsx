"use client";

// Connector and provider marks, in one place.
//
// Local files, not hot-linked Wikimedia SVGs: the grid renders eleven of these
// on first paint, and a card whose logo is a broken image is a card that looks
// broken. The OpenAI knot is inline rather than a file because it draws in
// `currentColor` — an `<img>` has no CSS context to inherit the theme from, so
// it would stay black on the dark theme's dark tile.

function Img({ src, alt }) {
  return <img src={src} alt={alt} width="24" height="24" loading="lazy" decoding="async" />;
}

export const OpenAiMark = (
  <svg viewBox="0 0 24 24" role="img" aria-label="OpenAI" fill="none" stroke="currentColor" strokeWidth="1.5">
    <ellipse cx="12" cy="12" rx="3.9" ry="8.6" />
    <ellipse cx="12" cy="12" rx="3.9" ry="8.6" transform="rotate(60 12 12)" />
    <ellipse cx="12" cy="12" rx="3.9" ry="8.6" transform="rotate(120 12 12)" />
  </svg>
);

export const LOGOS = {
  google_ads: <Img src="/icons/google-ads.svg" alt="Google Ads" />,
  gsc: <Img src="/icons/google-search-console.png" alt="Google Search Console" />,
  ga4: <Img src="/icons/google-analytics.svg" alt="Google Analytics" />,
  gtm: <Img src="/icons/google-tag-manager.svg" alt="Google Tag Manager" />,
  meta_ads: <Img src="/icons/meta-ads.svg" alt="Meta Ads" />,
  stripe: <Img src="/icons/stripe.svg" alt="Stripe" />,
  apple_ads: <Img src="/icons/apple-search-ads.svg" alt="Apple Search Ads" />,
  revenuecat: <Img src="/icons/revenuecat.svg" alt="RevenueCat" />,
  openai_ads: OpenAiMark,
  hubspot: <Img src="/icons/hubspot.svg" alt="HubSpot" />,
  mixpanel: <Img src="/icons/mixpanel.svg" alt="Mixpanel" />,
  clarity: <Img src="/icons/clarity.svg" alt="Microsoft Clarity" />,
  growthbook: <Img src="/icons/growthbook.svg" alt="GrowthBook" />,

  // Model providers
  anthropic: <Img src="/icons/anthropic.svg" alt="Anthropic" />,
  openai: OpenAiMark,
  gemini: <Img src="/icons/gemini.svg" alt="Google Gemini" />,
};
