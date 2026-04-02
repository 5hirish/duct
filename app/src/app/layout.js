import Link from "next/link";
import "./globals.css";

export const metadata = {
  title: "Duct App Shell",
  description: "Minimal no-auth app shell for rendering Duct reports.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <div className="app-shell">
          <header className="app-header">
            <div className="app-header-inner">
              <Link className="app-brand" href="/reports">
                duct app
              </Link>
              <span className="app-subtle">minimal report shell</span>
            </div>
          </header>
          <main className="app-main">{children}</main>
        </div>
      </body>
    </html>
  );
}

