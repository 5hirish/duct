"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { BASE } from "../../../lib/api";
import { Button } from "@/components/ui/button";

export default function ConnectionsPage() {
  const [ga4Connected, setGa4Connected] = useState(false);
  const [gscConnected, setGscConnected] = useState(false);

  useEffect(() => {
    const hash = window.location.hash;
    if (hash.startsWith("#")) {
      const params = new URLSearchParams(hash.slice(1));
      const ga4Token = params.get("ga4_refresh_token");
      const gscToken = params.get("gsc_refresh_token");
      if (ga4Token) sessionStorage.setItem("ga4_refresh_token", decodeURIComponent(ga4Token));
      if (gscToken) sessionStorage.setItem("gsc_refresh_token", decodeURIComponent(gscToken));
      window.history.replaceState(null, "", window.location.pathname);
    }

    setGa4Connected(!!sessionStorage.getItem("ga4_refresh_token"));
    setGscConnected(!!sessionStorage.getItem("gsc_refresh_token"));
  }, []);

  function signOutGa4() {
    sessionStorage.removeItem("ga4_refresh_token");
    setGa4Connected(false);
  }

  function signOutGsc() {
    sessionStorage.removeItem("gsc_refresh_token");
    setGscConnected(false);
  }

  return (
    <section>
      <div className="page-toolbar-back">
        <Button
          variant="ghost"
          size="icon"
          className="connection-back-btn shrink-0 rounded-full"
          asChild
        >
          <Link href="/reports" aria-label="Back to Reports" title="Back to Reports">
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
        Manage data source connections for reports. Choose your Google Ads account when you{" "}
        <Link href="/generate" className="app-link">
          generate a report
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
          <div className="connection-status-row">
            <span className="status-pill yellow">Coming Soon</span>
            <Button type="button" variant="secondary" size="sm" disabled>
              Coming Soon
            </Button>
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
