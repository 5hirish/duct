import "./globals.css";

import { DM_Sans, JetBrains_Mono } from "next/font/google";

import { ProductAnalytics } from "../components/ProductAnalytics";
import { ThemeProvider } from "../components/ThemeProvider";
import { TooltipProvider } from "@/components/ui/tooltip";

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

const gtmId = process.env.NEXT_PUBLIC_GTM_ID;
const shouldRenderNoScriptGtm = Boolean(gtmId) && process.env.NODE_ENV === "production";

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

export default function RootLayout({ children }) {
  return (
    <html
      lang="en"
      className={`${dmSans.variable} ${jetbrainsMono.variable}`}
      suppressHydrationWarning
    >
      <body className="min-h-dvh bg-background font-sans text-foreground antialiased">
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem storageKey="duct-theme">
          <TooltipProvider>
            <a href="#main-content" className="skip-link">
              Skip to main content
            </a>
            {shouldRenderNoScriptGtm ? (
              <noscript>
                <iframe
                  src={`https://www.googletagmanager.com/ns.html?id=${gtmId}`}
                  height="0"
                  width="0"
                  style={{ display: "none", visibility: "hidden" }}
                  title="Google Tag Manager"
                />
              </noscript>
            ) : null}
            <ProductAnalytics />
            {children}
          </TooltipProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
