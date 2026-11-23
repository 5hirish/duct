"use client";

// "Use for <project>" — the whole per-project mapping block, for any connector.
//
// This existed only inside `OAuthConnectorCard`, which meant the entity picker
// was a Google feature by accident: a Meta ad account, a Mixpanel project and a
// Stripe account are all things a project gets pointed at, and none of them
// could be. The block is two decisions and they are not the same decision:
//
//   which credential — only a real question when several are stored, so the
//     control appears only then.
//   which entity inside it — the property, container, ad account. Always a
//     question when the connector can list them, and optional by design: an
//     unset one means the agent asks, not that the connector is broken.
//
// Composed rather than inherited: both cards render <ProjectBinding> with the
// props they already hold, and a new connector gets the block for free.

import { useMemo } from "react";
import { Trans } from "@lingui/react/macro";
import ProjectAccountSelect, { DEFAULT_VALUE } from "./ProjectAccountSelect";
import ProjectEntitySelect from "./ProjectEntitySelect";

// The stored rows as the picker's entity list, with no network: each row is
// one entity (`entity_per_row`), so its listing is the rows themselves. The
// searchable picker stays, because a GitHub grant only grows.
function entityRows(rows) {
  const byId = new Map(rows.map((row) => [row.account_id, row]));
  const first = rows[0] || {};
  const listing = {
    supported: true,
    entity_noun: first.entity_noun,
    entity_noun_plural: first.entity_noun_plural,
    entities: rows.map((row) => ({
      account_id: row.account_id,
      account_name: row.account_name || row.account_id,
    })),
  };
  return { byId, load: async () => listing };
}

export default function ProjectBinding({
  projectName,
  rows = [],
  binding,
  onMappingChange,
  onEntityChange,
  busy = false,
}) {
  // One picker over the rows when each row already is a repository: see
  // `entityRows` below. Memoised so the picker keeps its loaded list.
  const perRow = rows[0]?.entity_per_row === true;
  const rowEntities = useMemo(() => entityRows(rows), [rows]);

  if (!projectName || rows.length === 0) return null;

  // The mapped credential when there is one, otherwise the account-level
  // default — the same row the backend resolves to, so the entities listed are
  // the entities that will actually be read.
  const credentialId = binding?.connector_credential_id || rows[0]?.id;
  const active = rows.find((row) => row.id === credentialId) || rows[0];

  if (perRow) {
    // A read goes to the bound row (the backend never reads the binding's
    // entity for these), so the picker shows the bound row and choosing an
    // entry binds that row. The old pair asked the same question twice: an
    // "Account" list of repositories, and under it a "Repository" list whose
    // choice no read used.
    const bound = rows.find((row) => row.id === binding?.connector_credential_id);
    const shown = bound ? { entity_id: bound.account_id, entity_name: bound.account_name || bound.account_id } : binding;
    return (
      <div className="conn-dialog-section">
        <h4 className="conn-dialog-heading">
          <Trans>Use for {projectName}</Trans>
        </h4>
        <ProjectEntitySelect
          projectName={projectName}
          noun={active?.entity_noun || "account"}
          nounPlural={active?.entity_noun_plural || "accounts"}
          credentialId={credentialId}
          binding={shown}
          loadEntities={rowEntities.load}
          onChange={(choice) => {
            // Clear means "not chosen": unbind, and the agent asks.
            if (!choice.entityId) return onMappingChange?.(DEFAULT_VALUE);
            const row = rowEntities.byId.get(choice.entityId);
            if (row) onEntityChange?.(row.id, choice);
          }}
          busy={busy}
        />
      </div>
    );
  }

  return (
    <div className="conn-dialog-section">
      <h4 className="conn-dialog-heading">
        <Trans>Use for {projectName}</Trans>
      </h4>

      {/* Only when there is genuinely a choice. One account made this a select
          with a single option and a sentinel above it, which reads as a
          decision the user has to make and is not one. */}
      {rows.length > 1 && (
        <ProjectAccountSelect
          projectName={projectName}
          rows={rows}
          binding={binding}
          onChange={onMappingChange}
          busy={busy}
        />
      )}

      <ProjectEntitySelect
        projectName={projectName}
        noun={active?.entity_noun || "account"}
        nounPlural={active?.entity_noun_plural || "accounts"}
        credentialId={credentialId}
        binding={binding}
        onChange={(choice) => onEntityChange?.(credentialId, choice)}
        busy={busy}
      />
    </div>
  );
}
