import { withSentryConfig } from "@sentry/nextjs";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  experimental: {
    viewTransition: true,
  },
};

export default withSentryConfig(nextConfig, {
  org: "alleviate-lab",
  project: "app-duct",
  silent: !process.env.CI,
});

