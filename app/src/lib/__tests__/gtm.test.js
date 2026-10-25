import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { gtm } from "../analytics/gtm.js";

// The one rule this file holds: the tag container never loads inside the
// desktop shell, however the environment is configured. The shell's IPC trusts
// every script on this origin, so a container that can be pointed at any
// script from outside the repository must not be given the chance to run
// there. The host and container-id checks are pinned beside it so a change to
// one cannot quietly pass as the other.

const CONTAINER_ID = "GTM-TEST";

function fakeWindow({ hostname = "app.getduct.ai", shell = false } = {}) {
  const win = { location: { hostname, protocol: "https:" } };
  if (shell) win.__TAURI__ = { core: { invoke: vi.fn() } };
  return win;
}

/** A document that records any attempt to insert the loader tag. */
function fakeDocument() {
  return {
    createElement: vi.fn(() => ({})),
    getElementsByTagName: vi.fn(() => []),
  };
}

describe("gtm.isConfigured", () => {
  let savedId;

  beforeEach(() => {
    savedId = process.env.NEXT_PUBLIC_GTM_ID;
    process.env.NEXT_PUBLIC_GTM_ID = CONTAINER_ID;
    globalThis.document = fakeDocument();
  });

  afterEach(() => {
    if (savedId === undefined) delete process.env.NEXT_PUBLIC_GTM_ID;
    else process.env.NEXT_PUBLIC_GTM_ID = savedId;
    delete globalThis.window;
    delete globalThis.document;
  });

  it("is true in a browser on a measurable host with a container id", () => {
    globalThis.window = fakeWindow();
    expect(gtm.isConfigured()).toBe(true);
  });

  it("is false without a container id", () => {
    delete process.env.NEXT_PUBLIC_GTM_ID;
    globalThis.window = fakeWindow();
    expect(gtm.isConfigured()).toBe(false);
  });

  it("is false on a developer's host", () => {
    globalThis.window = fakeWindow({ hostname: "localhost" });
    expect(gtm.isConfigured()).toBe(false);
  });

  it("is false inside the desktop shell, with a container id and a measurable host", () => {
    globalThis.window = fakeWindow({ shell: true });
    expect(gtm.isConfigured()).toBe(false);
  });

  it("never inserts the loader inside the desktop shell", () => {
    globalThis.window = fakeWindow({ shell: true });
    gtm.start();
    gtm.start({ deferred: true });
    expect(globalThis.document.createElement).not.toHaveBeenCalled();
    expect(gtm.isRunning()).toBe(false);
    // The loader also announces itself on the dataLayer before the tag; its
    // absence is the second witness that nothing ran.
    expect(globalThis.window.dataLayer).toBeUndefined();
  });
});
