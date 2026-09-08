"use client";

import { useCallback, useEffect, useState } from "react";

import { CookieConsent } from "./CookieConsent";
import { analytics } from "../lib/analytics";
import {
  CONSENT_DENIED,
  CONSENT_GRANTED,
  CONSENT_SETTINGS_EVENT,
  consentRequired,
  readConsentChoice,
  storeConsentChoice,
} from "../lib/consent";
import { getTelemetrySettings } from "../lib/telemetry";
import { isDesktopShell } from "../lib/shell";

/**
 * Decides whether Duct measures, and asks when it has to.
 *
 * The provider behind `lib/analytics` decides how, and is the only thing here
 * that names a vendor — swap it, or select `none`, and this file is unchanged.
 */
export function ProductAnalytics() {
  const [asking, setAsking] = useState(false);

  const accept = useCallback(() => {
    storeConsentChoice(CONSENT_GRANTED);
    analytics.setConsent(true);
    setAsking(false);
    analytics.start();
  }, []);

  const decline = useCallback(() => {
    const wasRunning = analytics.isRunning();
    storeConsentChoice(CONSENT_DENIED);
    analytics.setConsent(false);
    analytics.forgetStoredData();
    setAsking(false);
    // A provider already loaded cannot be unloaded. If it was running under an
    // earlier "accept", a reload is the only honest way to make the withdrawal
    // real rather than cosmetic.
    if (wasRunning) window.location.reload();
  }, []);

  useEffect(() => {
    if (isDesktopShell()) return undefined;
    const reopen = () => setAsking(true);
    window.addEventListener(CONSENT_SETTINGS_EVENT, reopen);
    return () => window.removeEventListener(CONSENT_SETTINGS_EVENT, reopen);
  }, []);

  useEffect(() => {
    if (!analytics.isConfigured()) return undefined;

    // The desktop shell never asks. It measures with storage permanently off,
    // so nothing is written to the machine — nothing stored means nothing to
    // consent to, and a bar in front of a window someone just opened is the
    // worst version of this question. The opt-out is the Preferences switch,
    // which also governs crash reports and is on in the builds we distribute.
    if (isDesktopShell()) {
      let cancelled = false;
      getTelemetrySettings().then((settings) => {
        if (cancelled || !settings.enabled) return;
        analytics.setDefaults({ cookieless: true });
        // So the desktop is distinguishable from a browser tab, which it never
        // was: same URL, same container.
        analytics.track("duct_shell_ready", { duct_shell: "desktop" });
        analytics.start({ deferred: true });
      });
      return () => {
        cancelled = true;
      };
    }

    analytics.setDefaults();

    const choice = readConsentChoice();
    if (choice === CONSENT_GRANTED) {
      analytics.setConsent(true);
      analytics.start({ deferred: true });
      return undefined;
    }
    if (choice === CONSENT_DENIED) return undefined;

    let cancelled = false;
    consentRequired().then((required) => {
      if (cancelled) return;
      if (required) {
        setAsking(true);
        return;
      }
      // Outside the EEA, UK and Switzerland the default is measurement, with
      // the settings link as the way out. Deliberately not stored: a choice
      // nobody made should not follow them to a country that would have asked.
      analytics.setConsent(true);
      analytics.start({ deferred: true });
    });

    return () => {
      cancelled = true;
    };
  }, []);

  if (!asking) return null;
  return <CookieConsent onAccept={accept} onDecline={decline} />;
}
