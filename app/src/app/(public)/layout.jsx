export const metadata = {
  robots: { index: false, follow: false },
};

export default function PublicLayout({ children }) {
  return (
    <div className="h-dvh flex flex-col bg-background overflow-hidden">
      <header className="shrink-0 border-b border-border/70 bg-background/90 backdrop-blur-xl px-4 h-14 flex items-center gap-3">
        <a href="https://getduct.ai" className="flex items-center gap-2 text-sm font-semibold text-foreground hover:opacity-80 transition-opacity">
          <svg width="22" height="22" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
            <rect width="32" height="32" rx="8" fill="#ff5c00"/>
            <path d="M8 10h10a6 6 0 0 1 0 12H8V10z" fill="#fff"/>
          </svg>
          Duct
        </a>
        <span className="text-border/70" aria-hidden="true">·</span>
        <span className="text-sm text-muted-foreground">Free SEO Audit</span>
        <div className="flex-1" />
        <a
          href="https://getduct.ai"
          className="text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          Back to site
        </a>
      </header>
      <main id="main-content" className="flex-1 min-h-0 flex flex-col" tabIndex={-1}>
        {children}
      </main>
    </div>
  );
}
