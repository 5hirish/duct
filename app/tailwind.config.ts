import type { Config } from "tailwindcss";

/** Present for tooling (e.g. shadcn preflight). Theme tokens live in `src/app/globals.css` (Tailwind v4). */
const config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
} satisfies Config;

export default config;
