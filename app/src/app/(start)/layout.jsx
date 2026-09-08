import Link from "next/link";

// The threshold. No AuthGuard — `/start` is where someone arrives before they
// have an account — and none of the app shell, which needs a project to mean
// anything. Its own route group rather than `(public)` because that layout
// is the lead magnet's, with the lead magnet's header.
export const metadata = {
  robots: { index: false, follow: false },
};

export default function StartLayout({ children }) {
  return (
    <div className="flex min-h-dvh flex-col bg-background">
      <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border/70 bg-background/90 px-4 backdrop-blur-xl">
        <Link
          href="/start"
          className="flex items-center gap-2 text-sm font-semibold text-foreground transition-opacity hover:opacity-80"
        >
          <svg width="22" height="22" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
            <rect width="32" height="32" rx="8" fill="#ff5c00" />
            <path d="M8 10h10a6 6 0 0 1 0 12H8V10z" fill="#fff" />
          </svg>
          Duct
        </Link>
        <div className="flex-1" />
        <Link href="/" className="text-sm text-muted-foreground transition-colors hover:text-foreground">
          Sign in
        </Link>
      </header>
      <main id="main-content" className="flex flex-1 flex-col" tabIndex={-1}>
        {children}
      </main>
    </div>
  );
}
