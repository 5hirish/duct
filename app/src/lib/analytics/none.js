"use client";

/**
 * No analytics.
 *
 * A complete implementation of the contract, not a stub with holes: a build
 * that selects this is a supported configuration. It is what a self-host build
 * gets by default, because someone running Duct for themselves did not sign up
 * to run our measurement.
 */
export const none = {
  id: "none",
  isConfigured: () => false,
  setDefaults: () => {},
  setConsent: () => {},
  forgetStoredData: () => {},
  start: () => {},
  isRunning: () => false,
  track: () => {},
};
