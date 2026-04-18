import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <main className="mx-auto flex min-h-[70vh] w-full max-w-2xl flex-col items-center justify-center px-6 py-12 text-center">
      <p className="mb-2 text-xs font-semibold tracking-[0.14em] text-muted-foreground uppercase">
        404
      </p>
      <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
        Page not found
      </h1>
      <p className="mt-3 max-w-md text-sm text-muted-foreground sm:text-base">
        The page you are looking for does not exist or has moved.
      </p>

      <div className="mt-7 flex w-full flex-col items-center justify-center gap-3 sm:flex-row">
        <Button asChild size="lg">
          <Link href="/reports">Go to Home</Link>
        </Button>
        <Button asChild variant="outline" size="lg">
          <Link href="/">Go to Sign In</Link>
        </Button>
      </div>
    </main>
  );
}
