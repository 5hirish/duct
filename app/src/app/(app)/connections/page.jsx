"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { BASE } from "../../../lib/api";
import {
  clearAdsDeveloperToken,
  getAdsDeveloperToken,
  getAdsLoginCustomerId,
  setAdsDeveloperToken,
  setAdsLoginCustomerId,
} from "../../../lib/adsCredentials";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function ConnectionsPage() {
  const [ga4Connected, setGa4Connected] = useState(false);
  const [gscConnected, setGscConnected] = useState(false);
  const [gadsOauthConnected, setGadsOauthConnected] = useState(false);
  const [gadsDevTokenSaved, setGadsDevTokenSaved] = useState(false);
  const [devTokenInput, setDevTokenInput] = useState("");
  const [mccInput, setMccInput] = useState("");

  useEffect(() => {
    const hash = window.location.hash;
    if (hash.startsWith("#")) {
      const params = new URLSearchParams(hash.slice(1));
      const gadsToken = params.get("refresh_token");
      const ga4Token = params.get("ga4_refresh_token");
      const gscToken = params.get("gsc_refresh_token");
      if (gadsToken) sessionStorage.setItem("gads_refresh_token", decodeURIComponent(gadsToken));
      if (ga4Token) sessionStorage.setItem("ga4_refresh_token", decodeURIComponent(ga4Token));
      if (gscToken) sessionStorage.setItem("gsc_refresh_token", decodeURIComponent(gscToken));
      window.history.replaceState(null, "", window.location.pathname);
    }

    setGadsOauthConnected(!!sessionStorage.getItem("gads_refresh_token"));
    setMccInput(getAdsLoginCustomerId());
    setGa4Connected(!!sessionStorage.getItem("ga4_refresh_token"));
    setGscConnected(!!sessionStorage.getItem("gsc_refresh_token"));
    getAdsDeveloperToken().then((token) => setGadsDevTokenSaved(!!token));
  }, []);

  async function saveGadsApiAccess(event) {
    event.preventDefault();
    const token = devTokenInput.trim();
    const mcc = mccInput.replace(/-/g, "").trim();
    if (token) {
      await setAdsDeveloperToken(token);
      setGadsDevTokenSaved(true);
      setDevTokenInput("");
    }
    setAdsLoginCustomerId(mcc);
    setMccInput(mcc);
  }

  async function signOutGads() {
    sessionStorage.removeItem("gads_refresh_token");
    sessionStorage.removeItem("gads_customer_id");
    await clearAdsDeveloperToken();
    setAdsLoginCustomerId("");
    setGadsOauthConnected(false);
    setGadsDevTokenSaved(false);
    setDevTokenInput("");
    setMccInput("");
  }

  function signOutGa4() {
    sessionStorage.removeItem("ga4_refresh_token");
    setGa4Connected(false);
  }

  function signOutGsc() {
    sessionStorage.removeItem("gsc_refresh_token");
    setGscConnected(false);
  }

  const gadsConnected = gadsOauthConnected && gadsDevTokenSaved;

  return (
    <section>
      <div className="page-toolbar-back">
        <Button
          variant="ghost"
          size="icon"
          className="connection-back-btn shrink-0 rounded-full"
          asChild
        >
          <Link href="/insights/organic-growth" aria-label="Back to Insights" title="Back to Insights">
            <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
              <path
                d="M15 18 9 12l6-6"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </Link>
        </Button>
        <h1 className="page-toolbar-title text-2xl font-semibold tracking-tight">Connections</h1>
      </div>
      <p className="app-subtle" style={{ marginTop: 0, marginBottom: 18 }}>
        Manage data source connections for insights. Choose your Google Ads account when you{" "}
        <Link href="/insights/organic-growth/generate" className="app-link">
          generate an insight
        </Link>
        .
      </p>

      <div className="connection-grid">
        <article className="connection-card">
          <div className="connection-card-head">
            <div className="connection-logo" aria-hidden="true">
              <img
                src="https://upload.wikimedia.org/wikipedia/commons/c/c7/Google_Ads_logo.svg"
                alt="Google Ads logo"
                width="28"
                height="28"
              />
            </div>
            <div>
              <h2 className="connection-title">Google Ads</h2>
              <p className="connection-description">
                Campaign performance metrics including spend, clicks, impressions, conversions, and ROAS.
              </p>
            </div>
          </div>

          <form onSubmit={saveGadsApiAccess} style={{ display: "grid", gap: 10, marginTop: 12 }}>
            <p className="app-subtle" style={{ margin: 0, fontSize: 13 }}>
              Duct&rsquo;s Google Ads API access is pending Google approval — bring your own{" "}
              <a
                className="app-link"
                href="https://developers.google.com/google-ads/api/docs/get-started/dev-token"
                target="_blank"
                rel="noreferrer"
              >
                developer token
              </a>{" "}
              from your manager account. It stays on this device and is only sent with your requests.
            </p>
            <div style={{ display: "grid", gap: 4 }}>
              <Label htmlFor="gads-dev-token">Developer token</Label>
              <Input
                id="gads-dev-token"
                type="password"
                autoComplete="off"
                placeholder={gadsDevTokenSaved ? "Saved — paste to replace" : "Paste your developer token"}
                value={devTokenInput}
                onChange={(e) => setDevTokenInput(e.target.value)}
              />
            </div>
            <div style={{ display: "grid", gap: 4 }}>
              <Label htmlFor="gads-mcc">Manager account ID (MCC, optional)</Label>
              <Input
                id="gads-mcc"
                inputMode="numeric"
                placeholder="e.g. 1234567890"
                value={mccInput}
                onChange={(e) => setMccInput(e.target.value)}
              />
            </div>
            <div>
              <Button type="submit" size="sm" variant="secondary" disabled={!devTokenInput.trim() && !gadsDevTokenSaved}>
                Save API access
              </Button>
            </div>
          </form>

          <div className="connection-status-row">
            <span className={`status-pill ${gadsConnected ? "green" : gadsOauthConnected || gadsDevTokenSaved ? "yellow" : "grey"}`}>
              {gadsConnected
                ? "Connected"
                : gadsOauthConnected
                  ? "Add developer token"
                  : gadsDevTokenSaved
                    ? "Sign in with Google"
                    : "Not connected"}
            </span>
            {gadsOauthConnected ? (
              <Button type="button" variant="outline" size="sm" onClick={signOutGads}>
                Disconnect
              </Button>
            ) : (
              <Button size="sm" asChild>
                <a href={`${BASE}/auth/connectors/google_ads/oauth/authorize`}>Connect</a>
              </Button>
            )}
          </div>
        </article>

        <article className="connection-card">
          <div className="connection-card-head">
            <div className="connection-logo" aria-hidden="true">
              <img
                src="/icons/google-search-console.png"
                alt="Google Search Console logo"
                width="28"
                height="28"
              />
            </div>
            <div>
              <h2 className="connection-title">Google Search Console</h2>
              <p className="connection-description">
                Organic search queries, clicks, impressions, and average position data for SEO reporting.
              </p>
            </div>
          </div>
          <div className="connection-status-row">
            <span className={`status-pill ${gscConnected ? "green" : "grey"}`}>
              {gscConnected ? "Connected" : "Not connected"}
            </span>
            {gscConnected ? (
              <Button type="button" variant="outline" size="sm" onClick={signOutGsc}>
                Disconnect
              </Button>
            ) : (
              <Button size="sm" asChild>
                <a href={`${BASE}/auth/connectors/gsc/oauth/authorize`}>Connect</a>
              </Button>
            )}
          </div>
        </article>

        <article className="connection-card">
          <div className="connection-card-head">
            <div className="connection-logo" aria-hidden="true">
              <img
                src="https://upload.wikimedia.org/wikipedia/commons/7/77/GAnalytics.svg"
                alt="Google Analytics logo"
                width="28"
                height="28"
              />
            </div>
            <div>
              <h2 className="connection-title">Google Analytics</h2>
              <p className="connection-description">
                Website traffic, sessions, engagement, and conversion trend data for performance reporting.
              </p>
            </div>
          </div>
          <div className="connection-status-row">
            <span className={`status-pill ${ga4Connected ? "green" : "grey"}`}>
              {ga4Connected ? "Connected" : "Not connected"}
            </span>
            {ga4Connected ? (
              <Button type="button" variant="outline" size="sm" onClick={signOutGa4}>
                Disconnect
              </Button>
            ) : (
              <Button size="sm" asChild>
                <a href={`${BASE}/auth/connectors/ga4/oauth/authorize`}>Connect</a>
              </Button>
            )}
          </div>
        </article>

        <article className="connection-card">
          <div className="connection-card-head">
            <div className="connection-logo" aria-hidden="true">
              <img
                src="/icons/meta-ads.svg"
                alt="Meta Ads logo"
                width="28"
                height="28"
              />
            </div>
            <div>
              <h2 className="connection-title">Meta Ads</h2>
              <p className="connection-description">
                Facebook and Instagram campaign performance including spend, reach, conversions, and CPA.
              </p>
            </div>
          </div>
          <div className="connection-status-row">
            <span className="status-pill yellow">Coming soon</span>
            <Button type="button" variant="secondary" size="sm" disabled>
              Coming soon
            </Button>
          </div>
        </article>

        <article className="connection-card">
          <div className="connection-card-head">
            <div className="connection-logo" aria-hidden="true">
              <img
                src="https://upload.wikimedia.org/wikipedia/commons/b/ba/Stripe_Logo%2C_revised_2016.svg"
                alt="Stripe logo"
                width="28"
                height="28"
              />
            </div>
            <div>
              <h2 className="connection-title">Stripe</h2>
              <p className="connection-description">
                Revenue, subscriptions, churn, and payment outcomes to connect marketing performance to business impact.
              </p>
            </div>
          </div>
          <div className="connection-status-row">
            <span className="status-pill yellow">Coming soon</span>
            <Button type="button" variant="secondary" size="sm" disabled>
              Coming soon
            </Button>
          </div>
        </article>

        <article className="connection-card">
          <div className="connection-card-head">
            <div className="connection-logo" aria-hidden="true">
              <img
                src="/icons/hubspot.svg"
                alt="HubSpot logo"
                width="28"
                height="28"
              />
            </div>
            <div>
              <h2 className="connection-title">HubSpot</h2>
              <p className="connection-description">
                CRM lifecycle and pipeline outcomes to tie paid and organic traffic to downstream revenue.
              </p>
            </div>
          </div>
          <div className="connection-status-row">
            <span className="status-pill yellow">Coming soon</span>
            <Button type="button" variant="secondary" size="sm" disabled>
              Coming soon
            </Button>
          </div>
        </article>
      </div>

    </section>
  );
}
