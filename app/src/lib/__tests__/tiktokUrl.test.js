import { describe, expect, it } from "vitest";
import { TikTokUrlError, parseTikTokPostUrl } from "../tiktokUrl.js";

// The same cases as backend tests/test_content_clone.py: the server is the
// authority, and this mirror must agree with it on what a post link is.
const ID = "7300000000000000001";
const CANONICAL = `https://www.tiktok.com/@kestrel/video/${ID}`;

describe("parseTikTokPostUrl", () => {
  it.each([
    CANONICAL,
    `https://www.tiktok.com/@kestrel/photo/${ID}?is_from_webapp=1&sender_device=pc#comments`,
    `tiktok.com/@kestrel/video/${ID}`,
    `https://m.tiktok.com/@kestrel/video/${ID}/`,
    `  http://www.tiktok.com/@kestrel/video/${ID}\n`,
  ])("reduces %j to the canonical link", (pasted) => {
    expect(parseTikTokPostUrl(pasted)).toEqual({ url: CANONICAL, handle: "kestrel", postId: ID });
  });

  it.each([
    ["", TikTokUrlError.EMPTY],
    [`https://example.com/@kestrel/video/${ID}`, TikTokUrlError.NOT_TIKTOK],
    [`https://tiktok.com.evil.net/@kestrel/video/${ID}`, TikTokUrlError.NOT_TIKTOK],
    [`https://www.tiktok.com@169.254.169.254/@kestrel/video/${ID}`, TikTokUrlError.NOT_TIKTOK],
    [`https://user:pass@www.tiktok.com/@kestrel/video/${ID}`, TikTokUrlError.NOT_TIKTOK],
    [`https://www.tiktok.com:8443/@kestrel/video/${ID}`, TikTokUrlError.NOT_TIKTOK],
    ["javascript:alert(1)", TikTokUrlError.NOT_A_LINK],
    ["https://vm.tiktok.com/ZMabc123/", TikTokUrlError.SHARE_LINK],
    ["https://www.tiktok.com/t/ZTabc123/", TikTokUrlError.SHARE_LINK],
    ["https://www.tiktok.com/@kestrel", TikTokUrlError.NOT_A_POST],
    [`https://www.tiktok.com/@kestrel/live/${ID}`, TikTokUrlError.NOT_A_POST],
    [`https://www.tiktok.com/@kestrel/video/${ID}/../../admin`, TikTokUrlError.NOT_A_POST],
  ])("refuses %j", (pasted, error) => {
    expect(parseTikTokPostUrl(pasted)).toEqual({ error });
  });
});
