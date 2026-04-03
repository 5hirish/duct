import Link from "next/link";
import AppNav from "../components/AppNav";
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

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <div className="app-shell">
          <header className="app-header">
            <div className="app-header-inner">
              <div className="app-header-left">
                <Link className="logo" href="/reports">
                  duct <span className="logo-mark" aria-hidden="true" />
                </Link>
                <span className="app-subtle">app</span>
              </div>

              <AppNav />
            </div>
          </header>
          <main className="app-main">{children}</main>
        </div>
      </body>
    </html>
  );
}

