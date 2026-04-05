import "./globals.css";

export const metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_APP_URL ?? "https://getduct.ai"),
  title: {
    default: "Duct App",
    template: "%s | Duct App",
  },
  description:
    "Duct synthesizes data across your product, marketing, and sales tools into weekly intelligence briefs and real-time alerts. Stop tab-switching. Start deciding.",
  applicationName: "Duct App",
  manifest: "/manifest.webmanifest",
  icons: {
    icon: "/icon.svg",
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
  themeColor: "#0d0f1a",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

