"use client";

import Link from "next/link";

import { Button } from "@/components/ui/button";

export function ReportsGenerateCta() {
  return (
    <Button variant="outline" size="default" asChild>
      <Link href="/generate">Generate</Link>
    </Button>
  );
}
