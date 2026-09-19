import "./globals.css";

import { DM_Sans, JetBrains_Mono } from "next/font/google";

import { ProductAnalytics } from "../components/ProductAnalytics";
import { ThemeProvider } from "../components/ThemeProvider";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Trans } from "@lingui/react/macro";

import { LinguiClientProvider } from "../i18n/LinguiClientProvider";
import { activateRequestI18n } from "../i18n/server";

const dmSans = DM_Sans({
  subsets: ["latin"],
  variable: "--font-dm-sans",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
  display: "swap",
});


/** CI must not use placeholder hosts (e.g. `<subdomain>`); `new URL()` throws and breaks `next build`. */
function metadataBaseUrl() {
  const raw = process.env.NEXT_PUBLIC_APP_URL?.trim();
  if (!raw) return "https://getduct.ai";
  try {
    return new URL(raw).toString();
  } catch {
    return "https://getduct.ai";
  }
}

export const metadata = {
  metadataBase: new URL(metadataBaseUrl()),
  title: {
    default: "Duct App",
    template: "%s | Duct App",
  },
  description:
    "Duct synthesizes data across your product, marketing, and sales tools into weekly intelligence briefs and real-time alerts. Stop tab-switching. Start deciding.",
  applicationName: "Duct App",
  manifest: "/manifest.webmanifest",
  icons: {
    icon: "/icons/icon.svg",
    apple: "/apple-icon.svg",
  },
  appleWebApp: {
    capable: true,
    title: "Duct App",
    statusBarStyle: "default",
  },
  openGraph: {
    title: "Duct App",
    description:
      "Duct synthesizes data across your product, marketing, and sales tools into weekly intelligence briefs and real-time alerts. Stop tab-switching. Start deciding.",
    url: "/",
    siteName: "Duct App",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Duct App",
    description:
      "Stop tab-switching. Duct synthesizes your entire tool stack into weekly briefs and real-time alerts.",
  },
  robots: {
    index: false,
    follow: false,
  },
};

export const viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#0d0f1a" },
  ],
};

export default async function RootLayout({ children }) {
  // Reading the cookie makes every route dynamic. That is already true of an
  // app that renders behind a bearer token, and it is the only way the first
  // frame arrives in the right language instead of flashing English.
  const i18n = await activateRequestI18n();
  return (
    <html
      lang={i18n.locale}
      className={`${dmSans.variable} ${jetbrainsMono.variable}`}
      suppressHydrationWarning
    >
      <body className="min-h-dvh bg-background font-sans text-foreground antialiased">
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem storageKey="duct-theme">
          <TooltipProvider>
            <a href="#main-content" className="skip-link">
              <Trans>Skip to main content</Trans>
            </a>
            {/* No GTM <noscript> iframe. It was the one thing that loaded a tag
                without asking, and it bought nothing: GA4 needs JavaScript, so
                with JS off the frame measures a visitor it cannot report on.
                The seam in lib/analytics is the only path in now. */}
            <ProductAnalytics />
            <LinguiClientProvider initialLocale={i18n.locale} initialMessages={i18n.messages}>
              {children}
            </LinguiClientProvider>
          </TooltipProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
