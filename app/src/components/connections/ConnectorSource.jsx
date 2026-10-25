"use client";

// "Native · by Duct" or "MCP · by OpenSEO": what kind of connector a card is,
// and who stands behind it. One line under the name, on the tile and in the
// dialog, so the two never describe the same connector differently.
//
// Toneless on purpose. The tile's foot dot is its only colour (DESIGN.md, the
// accent rule), and kind is a fact about the connector, not a state.

import { Trans, useLingui } from "@lingui/react/macro";
import { ConnectorKind } from "@/lib/connectorSource";

/** @param source  `{ kind, publisher }` from `lib/connectorSource.js`. */
export default function ConnectorSource({ source }) {
  const { t } = useLingui();
  if (!source) return null;
  const publisher = source.publisher;
  return (
    <p className="conn-source">
      <span className="conn-source-kind">{source.kind === ConnectorKind.MCP ? t`MCP` : t`Native`}</span>
      {publisher && (
        <span className="conn-source-by">
          <Trans>by {publisher}</Trans>
        </span>
      )}
    </p>
  );
}
