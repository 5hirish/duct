"use client";

// Your memory — what Duct knows about how *you* work, as opposed to what it
// knows about an account. Role, the depth and tone you want, the methods you
// insist on, the tools you ignore, the corrections you have made.
//
// It crosses projects and is private to you, which is exactly why the pause,
// reset and export controls matter more here than anywhere else.

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import MemoryTimeline from "@/components/memory/MemoryTimeline";
import { hasAuthToken } from "@/lib/authFetch";
import {
  USER_MEMORY_KINDS,
  createUserMemory,
  deleteUserMemory,
  exportUserMemory,
  listUserMemory,
  resetUserMemory,
  setUserMemoryPaused,
  updateUserMemory,
} from "@/lib/memoryApi";

export default function UserMemoryPage() {
  const [signedIn, setSignedIn] = useState(true);

  useEffect(() => {
    setSignedIn(hasAuthToken());
  }, []);

  const api = useMemo(
    () => ({
      list: (opts) => listUserMemory(opts),
      create: (entry) => createUserMemory(entry),
      patch: (patch) => updateUserMemory(patch),
      remove: ({ memoryId }) => deleteUserMemory({ memoryId }),
      setPaused: ({ paused }) => setUserMemoryPaused({ paused }),
      reset: () => resetUserMemory(),
      exportAll: () => exportUserMemory(),
    }),
    []
  );

  return (
    <section>
      <div className="page-toolbar">
        <h1 className="page-toolbar-title text-2xl font-semibold tracking-tight">
          Your memory
        </h1>
        <Button asChild variant="ghost" size="sm" className="ml-auto">
          <Link href="/projects">
            <ArrowLeft className="size-4" /> Projects
          </Link>
        </Button>
      </div>

      <p className="app-subtle" style={{ marginTop: 0, marginBottom: 14 }}>
        How you like to be worked with — the depth and tone you want, the methods you
        insist on, the tools you trust. This follows you across every project and is
        private to you. Your preferences land here automatically; add anything else you
        want every agent to know.
      </p>

      <MemoryTimeline
        api={api}
        signedIn={signedIn}
        kinds={USER_MEMORY_KINDS}
        defaultKind="method"
        addLabel="Add something about how you work"
        titlePlaceholder="e.g. Always compare to the same period last year"
        exportFilename="duct-your-memory.json"
        resetPrompt="Delete everything Duct has learned about how you work? This cannot be undone — export first if you want a copy."
        emptyHint="Nothing yet. Set your preferences from the sidebar, or add a rule here — 'give me the number first, then the why' is a good start."
      />
    </section>
  );
}
