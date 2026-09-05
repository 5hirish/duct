"use client";

// Which of your saved accounts this project uses for one connector.
//
// This used to be a whole "Project mappings" tab, which asked you to pick a
// project you had already picked in the header. The mapping is a property of
// the connector, so it lives inside that connector's dialog now, scoped to the
// active project. Agents, executions, and reports resolve through the mapping
// first; "Account default" falls back to the account-level connector.

import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

// Radix SelectItem values must be non-empty — sentinel for "no mapping".
export const DEFAULT_VALUE = "__default__";

function accountLabel(row) {
  return row.account_name || row.account_id || "Unnamed account";
}

export default function ProjectAccountSelect({
  projectName,
  rows = [],
  binding,
  onChange,
  busy = false,
}) {
  if (!projectName || rows.length === 0) return null;

  // A binding can point at a teammate's credential row — one we can't offer in
  // the options list. Say so rather than silently showing "Account default".
  const foreign = binding && !rows.some((row) => row.id === binding.connector_credential_id);

  return (
    // No section wrapper: `ProjectBinding` owns the "Use for <project>" block
    // this sits in, and a section inside a section drew a second rule and a
    // second heading for one decision.
    <div className="conn-field">
      <Label htmlFor={`mapping-${projectName}`}>Account</Label>
      <Select
        value={binding && !foreign ? binding.connector_credential_id : DEFAULT_VALUE}
        onValueChange={onChange}
        disabled={busy}
      >
        <SelectTrigger id={`mapping-${projectName}`}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={DEFAULT_VALUE}>Account default</SelectItem>
          {rows.map((row) => (
            <SelectItem key={row.id} value={row.id}>
              {accountLabel(row)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <p className="conn-hint">
        {foreign
          ? `Currently mapped to ${
              binding.account_name || binding.account_id || "a teammate's account"
            } — a teammate's connector.`
          : "Reports and agent runs for this project use this account. Other projects keep their own."}
      </p>
    </div>
  );
}
