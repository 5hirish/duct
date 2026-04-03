import Link from "next/link";
import "./globals.css";

export const metadata = {
  title: "Duct App Shell",
  description: "Minimal no-auth app shell for rendering Duct reports.",
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
                <span className="app-subtle">report viewer</span>
              </div>

              <div className="nav-links">
                <Link className="nav-link" href="/reports">
                  Reports
                </Link>
                <Link className="btn btn-ghost" href="/run">
                  Run
                </Link>
              </div>
            </div>
          </header>
          <main className="app-main">{children}</main>
        </div>
      </body>
    </html>
  );
}

