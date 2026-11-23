import { describe, expect, it } from "vitest";
import { accountKey, accountsToAutoLink } from "../channelLinks";

const li = { id: "li1", publisher: "zernio", platform: "linkedin", username: "Shirish Kadam" };
const tt = { id: "tt1", publisher: "zernio", platform: "tiktok", username: "glow" };
const xAtOther = { id: "x1", publisher: "post_bridge", platform: "twitter", username: "duct" };

describe("accountsToAutoLink", () => {
  it("links the one account a switched-on channel can mean", () => {
    const out = accountsToAutoLink({
      profiles: { linkedin: { enabled: true }, twitter: { enabled: true }, tiktok: { enabled: false } },
      accounts: [li, tt, xAtOther],
      primary: "zernio",
      linked: new Set(),
    });
    // LinkedIn: on, one account at Zernio. X: its account is at the other
    // scheduler, so nothing. TikTok: off.
    expect(out).toEqual([li]);
  });

  it("leaves a channel that already has a link, or a real choice, alone", () => {
    const li2 = { ...li, id: "li2", username: "Duct page" };
    expect(accountsToAutoLink({
      profiles: { linkedin: { enabled: true } },
      accounts: [li, li2],
      primary: "zernio",
      linked: new Set(),
    })).toEqual([]);
    expect(accountsToAutoLink({
      profiles: { linkedin: { enabled: true } },
      accounts: [li],
      primary: "zernio",
      linked: new Set([accountKey(li)]),
    })).toEqual([]);
  });

  it("does nothing before a primary scheduler is picked", () => {
    expect(accountsToAutoLink({ profiles: { linkedin: { enabled: true } }, accounts: [li], primary: "", linked: new Set() })).toEqual([]);
  });
});
