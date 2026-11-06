import { describe, expect, it } from "vitest";
import { packEndpoint, unpackEndpoint } from "../endpointCredential.js";

// The same fixture as backend tests/test_compatible_provider.py: the browser
// packs what the server unpacks, so the two must agree byte for byte.
const FIXTURE = "oaic1.eyJ1IjoiaHR0cHM6Ly9hcGkudG9nZXRoZXIueHl6L3YxIiwiayI6InNrLXRnIiwibSI6W1siUXdlbi9Rd2VuMy0zMkIiLDQwOTYwXSxbInNtYWxsLWNoYXQiLDBdXX0";
const ENDPOINT = {
  baseUrl: "https://api.together.xyz/v1",
  apiKey: "sk-tg",
  models: [
    { id: "Qwen/Qwen3-32B", contextLength: 40960 },
    { id: "small-chat", contextLength: 0 },
  ],
};

describe("endpoint credential", () => {
  it("packs exactly as the backend does", () => {
    expect(packEndpoint(ENDPOINT)).toBe(FIXTURE);
  });

  it("round-trips", () => {
    expect(unpackEndpoint(FIXTURE)).toEqual(ENDPOINT);
  });

  it.each(["", "sk-tg", "oaic1.not-json", "oaic1.e30"])("reads %j as no endpoint", (value) => {
    expect(unpackEndpoint(value)).toBeNull();
  });
});
