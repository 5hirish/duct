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

import ProjectAccountSelect from "./ProjectAccountSelect";
import ProjectEntitySelect from "./ProjectEntitySelect";

export default function ProjectBinding({
  projectName,
  rows = [],
  binding,
  onMappingChange,
  onEntityChange,
  busy = false,
}) {
  if (!projectName || rows.length === 0) return null;

  // The mapped credential when there is one, otherwise the account-level
  // default — the same row the backend resolves to, so the entities listed are
  // the entities that will actually be read.
  const credentialId = binding?.connector_credential_id || rows[0]?.id;
  const active = rows.find((row) => row.id === credentialId) || rows[0];

  return (
    <div className="conn-dialog-section">
      <h4 className="conn-dialog-heading">Use for {projectName}</h4>

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
