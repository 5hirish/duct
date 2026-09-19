"use client";

// Connector and provider marks, in one place.
//
// Local files, not hot-linked Wikimedia SVGs: the grid renders eleven of these
// on first paint, and a card whose logo is a broken image is a card that looks
// broken. The OpenAI knot is inline rather than a file because it draws in
// `currentColor` — an `<img>` has no CSS context to inherit the theme from, so
// it would stay black on the dark theme's dark tile.
//
// The alt text is a product name and goes through the catalogue anyway: some
// of these are localised by their owners ("Google 広告"), and the ones that are
// not cost a translator one glance to leave alone.

import { useLingui } from "@lingui/react/macro";
import { msg } from "@lingui/core/macro";

function Img({ src, alt }) {
  const { i18n } = useLingui();
  return <img src={src} alt={i18n._(alt)} width="24" height="24" loading="lazy" decoding="async" />;
}

export function OpenAiMark() {
  const { t } = useLingui();
  return (
    <svg viewBox="0 0 24 24" role="img" aria-label={t`OpenAI`} fill="none" stroke="currentColor" strokeWidth="1.5">
      <ellipse cx="12" cy="12" rx="3.9" ry="8.6" />
      <ellipse cx="12" cy="12" rx="3.9" ry="8.6" transform="rotate(60 12 12)" />
      <ellipse cx="12" cy="12" rx="3.9" ry="8.6" transform="rotate(120 12 12)" />
    </svg>
  );
}

// Drawn rather than shipped, for the same `currentColor` reason as the OpenAI
// knot — and because a routing glyph is an honest generic mark. OpenRouter's
// wordmark is their trademark; an approximation of it in our bundle would be
// worse than a shape that just says "one input, many models".
export function OpenRouterMark() {
  const { t } = useLingui();
  return (
    <svg viewBox="0 0 24 24" role="img" aria-label={t`OpenRouter`} fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <circle cx="4" cy="12" r="2" />
      <circle cx="20" cy="4.5" r="2" />
      <circle cx="20" cy="12" r="2" />
      <circle cx="20" cy="19.5" r="2" />
      <path d="M6 12h4c2 0 2-7.5 4-7.5h4" />
      <path d="M6 12h12" />
      <path d="M6 12h4c2 0 2 7.5 4 7.5h4" />
    </svg>
  );
}

// xAI's wordmark is a trademark too; a stylised X in `currentColor` says
// which provider without borrowing their letterforms.
export function XaiMark() {
  const { t } = useLingui();
  return (
    <svg viewBox="0 0 24 24" role="img" aria-label={t`xAI`} fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round">
      <path d="M5 5l14 14" />
      <path d="M19 5l-5.5 5.5" />
      <path d="M10.5 13.5L5 19" />
    </svg>
  );
}

export const LOGOS = {
  google_ads: <Img src="/icons/google-ads.svg" alt={msg`Google Ads`} />,
  gsc: <Img src="/icons/google-search-console.png" alt={msg`Google Search Console`} />,
  ga4: <Img src="/icons/google-analytics.svg" alt={msg`Google Analytics`} />,
  gtm: <Img src="/icons/google-tag-manager.svg" alt={msg`Google Tag Manager`} />,
  meta_ads: <Img src="/icons/meta-ads.svg" alt={msg`Meta Ads`} />,
  stripe: <Img src="/icons/stripe.svg" alt={msg`Stripe`} />,
  apple_ads: <Img src="/icons/apple-search-ads.svg" alt={msg`Apple Search Ads`} />,
  revenuecat: <Img src="/icons/revenuecat.svg" alt={msg`RevenueCat`} />,
  openai_ads: <OpenAiMark />,
  hubspot: <Img src="/icons/hubspot.svg" alt={msg`HubSpot`} />,
  mixpanel: <Img src="/icons/mixpanel.svg" alt={msg`Mixpanel`} />,
  clarity: <Img src="/icons/clarity.svg" alt={msg`Microsoft Clarity`} />,
  growthbook: <Img src="/icons/growthbook.svg" alt={msg`GrowthBook`} />,

  // Model providers
  anthropic: <Img src="/icons/anthropic.svg" alt={msg`Anthropic`} />,
  openai: <OpenAiMark />,
  gemini: <Img src="/icons/gemini.svg" alt={msg`Google Gemini`} />,
  openrouter: <OpenRouterMark />,
  xai: <XaiMark />,
};
