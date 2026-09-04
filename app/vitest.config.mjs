import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// Unit tests for the plain-JS layer: the session reducer, the SSE reader, the
// history mapper. No DOM, no React — the hook and the components are checked
// by `next build` and by looking at them. Fixtures under src/**/__fixtures__
// are recorded streams; a test replays one and asserts the phase sequence.
export default defineConfig({
  test: {
    include: ["src/**/*.test.js"],
    environment: "node",
  },
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
});
