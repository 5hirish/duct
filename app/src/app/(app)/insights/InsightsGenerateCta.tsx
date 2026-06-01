"use client";

import Link from "next/link";

import { Button } from "@/components/ui/button";

export function InsightsGenerateCta() {
  return (
    <Button variant="outline" size="default" asChild>
      <Link href="/insights/generate">Generate Insight</Link>
    </Button>
  );
}
