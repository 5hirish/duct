"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

/**
 * The command registry.
 *
 * Commands are contributed by whoever owns them and withdrawn when that
 * component unmounts, rather than collected in one file that has to import
 * half the app. A route that can do something registers it on mount; the
 * palette only ever renders what is currently possible, so it cannot offer an
 * action for a screen you are not on.
 *
 * A command:
 *   { id, label, group?, keywords?, icon?, shortcut?, run() }
 *
 * `id` must be stable — it is the dedupe key and the React key.
 */

const CommandContext = createContext(null);

export function CommandProvider({ children }) {
  // Keyed by the registering component's own bucket so unmount removes exactly
  // what that component added, never a later registration of the same id.
  const [buckets, setBuckets] = useState(() => new Map());
  const [open, setOpen] = useState(false);

  const register = useCallback((bucketId, commands) => {
    setBuckets((prev) => {
      const next = new Map(prev);
      next.set(bucketId, commands);
      return next;
    });
  }, []);

  const unregister = useCallback((bucketId) => {
    setBuckets((prev) => {
      if (!prev.has(bucketId)) return prev;
      const next = new Map(prev);
      next.delete(bucketId);
      return next;
    });
  }, []);

  const commands = useMemo(() => {
    const seen = new Set();
    const flat = [];
    for (const list of buckets.values()) {
      for (const command of list) {
        if (!command?.id || seen.has(command.id)) continue;
        seen.add(command.id);
        flat.push(command);
      }
    }
    return flat;
  }, [buckets]);

  const value = useMemo(
    () => ({ commands, register, unregister, open, setOpen }),
    [commands, register, unregister, open]
  );

  return <CommandContext.Provider value={value}>{children}</CommandContext.Provider>;
}

/** Palette state + the current command list. Safe outside the provider. */
export function useCommands() {
  return (
    useContext(CommandContext) || {
      commands: [],
      register: () => {},
      unregister: () => {},
      open: false,
      setOpen: () => {},
    }
  );
}

let bucketSeq = 0;

/**
 * Contribute commands for as long as this component is mounted.
 *
 * `commands` is re-read whenever `deps` change, exactly like useMemo — pass the
 * values the commands close over. Building the array inline is fine; it is not
 * used as the dependency, so a new array identity each render costs nothing.
 */
export function useRegisterCommands(commands, deps = []) {
  const { register, unregister } = useCommands();
  const bucketId = useRef(null);
  if (bucketId.current === null) bucketId.current = `bucket-${++bucketSeq}`;

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const memo = useMemo(() => commands, deps);

  useEffect(() => {
    const id = bucketId.current;
    register(id, memo);
    return () => unregister(id);
  }, [memo, register, unregister]);
}
