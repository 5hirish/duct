"use client";

// Connector and provider marks, in one place.
//
// Local files, not hot-linked: the grid renders eleven of these on first paint,
// and a card whose logo is a broken image is a card that looks broken.
//
// Every mark is the owner's own, never a redrawing: Google's product icons
// from its gstatic CDN, Microsoft's Clarity logo from its own static host,
// GrowthBook's logomark from its repository, and the rest from Simple Icons,
// which traces each brand from its owner's assets. A hand-drawn stand-in for a
// brand is a trademark problem, however close it looks. The OpenAI and
// OpenRouter marks are inline rather than files because they draw in
// `currentColor` — an `<img>` has no CSS context to inherit the theme from, so
// a black mark would stay black on the dark theme's dark tile.
//
// The alt text is a product name and goes through the catalogue anyway: some
// of these are localised by their owners ("Google 広告"), and the ones that are
// not cost a translator one glance to leave alone.

import { useLingui } from "@lingui/react/macro";
import { msg } from "@lingui/core/macro";

/**
 * What each mark is called. One map, because the name is needed twice — as the
 * logo's alt text and as the word beside it wherever a connector is named in
 * prose (the transcript's activity rows do both).
 */
export const CONNECTOR_NAMES = {
  google_ads: msg`Google Ads`,
  gsc: msg`Google Search Console`,
  ga4: msg`Google Analytics`,
  gtm: msg`Google Tag Manager`,
  meta_ads: msg`Meta Ads`,
  stripe: msg`Stripe`,
  apple_ads: msg`Apple Search Ads`,
  revenuecat: msg`RevenueCat`,
  openai_ads: msg`OpenAI Ads`,
  hubspot: msg`HubSpot`,
  mixpanel: msg`Mixpanel`,
  clarity: msg`Microsoft Clarity`,
  growthbook: msg`GrowthBook`,
  anthropic: msg`Anthropic`,
  openai: msg`OpenAI`,
  gemini: msg`Google Gemini`,
  openrouter: msg`OpenRouter`,
  xai: msg`xAI`,
};

function Img({ src, alt }) {
  const { i18n } = useLingui();
  return <img src={src} alt={i18n._(alt)} width="24" height="24" loading="lazy" decoding="async" />;
}

export function OpenAiMark() {
  const { t } = useLingui();
  return (
    <svg viewBox="0 0 24 24" role="img" aria-label={t`OpenAI`} fill="currentColor">
      <path d="M22.2819 9.8211a5.9847 5.9847 0 0 0-.5157-4.9108 6.0462 6.0462 0 0 0-6.5098-2.9A6.0651 6.0651 0 0 0 4.9807 4.1818a5.9847 5.9847 0 0 0-3.9977 2.9 6.0462 6.0462 0 0 0 .7427 7.0966 5.98 5.98 0 0 0 .511 4.9107 6.051 6.051 0 0 0 6.5146 2.9001A5.9847 5.9847 0 0 0 13.2599 24a6.0557 6.0557 0 0 0 5.7718-4.2058 5.9894 5.9894 0 0 0 3.9977-2.9001 6.0557 6.0557 0 0 0-.7475-7.0729zm-9.022 12.6081a4.4755 4.4755 0 0 1-2.8764-1.0408l.1419-.0804 4.7783-2.7582a.7948.7948 0 0 0 .3927-.6813v-6.7369l2.02 1.1686a.071.071 0 0 1 .038.052v5.5826a4.504 4.504 0 0 1-4.4945 4.4944zm-9.6607-4.1254a4.4708 4.4708 0 0 1-.5346-3.0137l.142.0852 4.783 2.7582a.7712.7712 0 0 0 .7806 0l5.8428-3.3685v2.3324a.0804.0804 0 0 1-.0332.0615L9.74 19.9502a4.4992 4.4992 0 0 1-6.1408-1.6464zM2.3408 7.8956a4.485 4.485 0 0 1 2.3655-1.9728V11.6a.7664.7664 0 0 0 .3879.6765l5.8144 3.3543-2.0201 1.1685a.0757.0757 0 0 1-.071 0l-4.8303-2.7865A4.504 4.504 0 0 1 2.3408 7.872zm16.5963 3.8558L13.1038 8.364 15.1192 7.2a.0757.0757 0 0 1 .071 0l4.8303 2.7913a4.4944 4.4944 0 0 1-.6765 8.1042v-5.6772a.79.79 0 0 0-.407-.667zm2.0107-3.0231l-.142-.0852-4.7735-2.7818a.7759.7759 0 0 0-.7854 0L9.409 9.2297V6.8974a.0662.0662 0 0 1 .0284-.0615l4.8303-2.7866a4.4992 4.4992 0 0 1 6.6802 4.66zM8.3065 12.863l-2.02-1.1638a.0804.0804 0 0 1-.038-.0567V6.0742a4.4992 4.4992 0 0 1 7.3757-3.4537l-.142.0805L8.704 5.459a.7948.7948 0 0 0-.3927.6813zm1.0976-2.3654l2.602-1.4998 2.6069 1.4998v2.9994l-2.5974 1.4997-2.6067-1.4997Z" />
    </svg>
  );
}

export function OpenRouterMark() {
  const { t } = useLingui();
  return (
    <svg viewBox="0 0 24 24" role="img" aria-label={t`OpenRouter`} fill="currentColor">
      <path d="M16.778 1.844v1.919q-.569-.026-1.138-.032-.708-.008-1.415.037c-1.93.126-4.023.728-6.149 2.237-2.911 2.066-2.731 1.95-4.14 2.75-.396.223-1.342.574-2.185.798-.841.225-1.753.333-1.751.333v4.229s.768.108 1.61.333c.842.224 1.789.575 2.185.799 1.41.798 1.228.683 4.14 2.75 2.126 1.509 4.22 2.11 6.148 2.236.88.058 1.716.041 2.555.005v1.918l7.222-4.168-7.222-4.17v2.176c-.86.038-1.611.065-2.278.021-1.364-.09-2.417-.357-3.979-1.465-2.244-1.593-2.866-2.027-3.68-2.508.889-.518 1.449-.906 3.822-2.59 1.56-1.109 2.614-1.377 3.978-1.466.667-.044 1.418-.017 2.278.02v2.176L24 6.014Z" />
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
  google_ads: <Img src="/icons/google-ads.svg" alt={CONNECTOR_NAMES.google_ads} />,
  gsc: <Img src="/icons/google-search-console.svg" alt={CONNECTOR_NAMES.gsc} />,
  ga4: <Img src="/icons/google-analytics.svg" alt={CONNECTOR_NAMES.ga4} />,
  gtm: <Img src="/icons/google-tag-manager.svg" alt={CONNECTOR_NAMES.gtm} />,
  meta_ads: <Img src="/icons/meta-ads.svg" alt={CONNECTOR_NAMES.meta_ads} />,
  stripe: <Img src="/icons/stripe.svg" alt={CONNECTOR_NAMES.stripe} />,
  apple_ads: <Img src="/icons/apple-search-ads.svg" alt={CONNECTOR_NAMES.apple_ads} />,
  revenuecat: <Img src="/icons/revenuecat.svg" alt={CONNECTOR_NAMES.revenuecat} />,
  openai_ads: <OpenAiMark />,
  hubspot: <Img src="/icons/hubspot.svg" alt={CONNECTOR_NAMES.hubspot} />,
  mixpanel: <Img src="/icons/mixpanel.svg" alt={CONNECTOR_NAMES.mixpanel} />,
  clarity: <Img src="/icons/clarity.svg" alt={CONNECTOR_NAMES.clarity} />,
  growthbook: <Img src="/icons/growthbook.svg" alt={CONNECTOR_NAMES.growthbook} />,

  // Model providers
  anthropic: <Img src="/icons/anthropic.svg" alt={CONNECTOR_NAMES.anthropic} />,
  openai: <OpenAiMark />,
  gemini: <Img src="/icons/gemini.svg" alt={CONNECTOR_NAMES.gemini} />,
  openrouter: <OpenRouterMark />,
  xai: <XaiMark />,
};
