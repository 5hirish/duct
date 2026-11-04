"use client";

// Your memory — what Duct knows about how *you* work, as opposed to what it
// knows about an account. Role, the depth and tone you want, the methods you
// insist on, the tools you ignore, the corrections you have made.
//
// It crosses projects and is private to you, which is exactly why the pause
// and reset controls matter more here than anywhere else.

import { useEffect, useMemo, useState } from "react";
import { Trans, useLingui } from "@lingui/react/macro";
import MemoryTimeline from "@/components/memory/MemoryTimeline";
import { hasAuthToken } from "@/lib/authFetch";
import {
  USER_MEMORY_KINDS,
  createUserMemory,
  deleteUserMemory,
  listUserMemory,
  resetUserMemory,
  setUserMemoryPaused,
  updateUserMemory,
} from "@/lib/memoryApi";
import { Page, PageHeader } from "@/components/ui/page";

export default function UserMemoryPage() {
  const { t } = useLingui();
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
    }),
    []
  );

  return (
    <Page width="reading">
      <PageHeader
        title={<Trans>Your memory</Trans>}
        status={<Trans>How you like to be worked with. Every agent reads it; only you can see it.</Trans>}
      />

      <MemoryTimeline
        api={api}
        signedIn={signedIn}
        kinds={USER_MEMORY_KINDS}
        defaultKind="method"
        addLabel={t`Add something about how you work`}
        titlePlaceholder={t`e.g. Always compare to the same period last year`}
        resetPrompt={t`Delete everything Duct has learned about how you work? This cannot be undone.`}
        emptyHint={t`Nothing yet. Set your preferences from the sidebar, or add a rule here — 'give me the number first, then the why' is a good start.`}
      />
    </Page>
  );
}
