"use client";

import { useEffect } from "react";

import { bootGtmDeferred } from "../lib/analytics-client";

export function ProductAnalytics() {
  useEffect(() => {
    bootGtmDeferred(process.env.NEXT_PUBLIC_GTM_ID);
  }, []);

  return null;
}
