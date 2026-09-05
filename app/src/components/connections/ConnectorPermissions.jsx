"use client";

// What this connection is allowed to do, and what it was actually granted.
//
// The list was a flat run of rows carrying the same fact three times: a label
// ending "— read", a pill reading "Read", and a sentence beginning "Read-only".
// It also scaled badly — Tag Manager asks for four scopes, and four rows of
// tick + name + two pills + two lines of prose is a wall.
//
// So the access level becomes the structure instead of a repeated pill. Two
// groups, "Can read" and "Can change", is the division a person actually cares
// about — the second one is the whole reason to read this section at all — and
// it stays two groups however many scopes a connector adds. Grant state is then
// the only per-row variable left, and only the exceptions are marked: a tick
// beside every row in a fully granted connection is decoration, and the header
// already said "all granted".
//
// Split out of `OAuthConnectorCard` because nothing about it is Google-specific
// — any connector that reports scope rows renders the same block.

import { Eye, PencilLine } from "lucide-react";
import { Badge } from "@/components/ui/badge";

// Mirrors `service/connector_scopes.py`. Only the values are needed here; the
// labels and justifications are joined server-side so this file holds no
// catalog of its own and cannot drift from what the backend requests.
const ACCESS_WRITE = "write";
export const SCOPE_PARTIAL = "partial";
export const SCOPE_UNKNOWN = "unknown";

const GROUPS = [
  {
    key: "read",
    label: "Can read",
    icon: Eye,
    match: (row) => row.access !== ACCESS_WRITE,
  },
  {
    key: "write",
    // Named for the consequence. "Write access" is the mechanism; what someone
    // deciding wants to know is whether Duct can alter their account.
    label: "Can change",
    icon: PencilLine,
    match: (row) => row.access === ACCESS_WRITE,
  },
];

/** "Granted" · "All 4 granted" · "3 of 4 granted" — a count needs a total. */
function summarize(scopes) {
  const granted = scopes.filter((row) => row.granted).length;
  if (granted < scopes.length) return `${granted} of ${scopes.length} granted`;
  return scopes.length === 1 ? "Granted" : `All ${scopes.length} granted`;
}

export default function ConnectorPermissions({ scopes = [], scopeStatus = "" }) {
  if (scopes.length === 0) return null;

  const unknown = scopeStatus === SCOPE_UNKNOWN;
  const partial = scopeStatus === SCOPE_PARTIAL;

  return (
    <section className="conn-dialog-section">
      <div className="conn-perm-head">
        <h4 className="conn-dialog-heading">Permissions</h4>
        {unknown ? (
          <Badge variant="outline">Not recorded</Badge>
        ) : (
          <span className="conn-perm-summary">{summarize(scopes)}</span>
        )}
      </div>

      {unknown ? (
        <p className="conn-hint">
          This connection was made before Duct recorded which permissions Google
          granted. Reconnect to find out — nothing is assumed either way.
        </p>
      ) : (
        GROUPS.map((group) => {
          const rows = scopes.filter(group.match);
          if (rows.length === 0) return null;
          const Icon = group.icon;
          return (
            <div key={group.key} className="conn-perm-group">
              <p className="conn-perm-group-label">{group.label}</p>
              <ul className="conn-perm-list">
                {rows.map((row) => (
                  <li
                    key={row.scope}
                    className={`conn-perm${row.granted ? "" : " is-declined"}`}
                  >
                    <span className="conn-perm-glyph">
                      <Icon size={15} aria-hidden="true" />
                    </span>
                    <div className="conn-perm-text">
                      <span className="conn-perm-label">{row.label}</span>
                      {/* Never colour alone: a declined row is muted *and*
                          says so (WCAG 1.4.1). Required ones take the warning
                          tone, optional ones stay grey — declining an optional
                          scope is a working configuration, not a fault. */}
                      {!row.granted && (
                        <span
                          className={`conn-perm-state${row.required ? " is-required" : ""}`}
                        >
                          {row.required ? "Not granted" : "Declined"}
                        </span>
                      )}
                      {row.why && <p className="conn-hint">{row.why}</p>}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          );
        })
      )}

      {partial && (
        <p className="conn-hint">
          Everything above still works. To grant the rest, choose Reconnect and
          tick them on Google&rsquo;s consent screen.
        </p>
      )}
    </section>
  );
}
