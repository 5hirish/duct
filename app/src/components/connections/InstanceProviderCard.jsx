"use client";

/**
 * A provider the server offers itself, with no key to paste: Ollama today.
 *
 * Shown only where the operator offered one (`configured` on its status row).
 * A hosted user reading "set OLLAMA_BASE_URL" is reading instructions for a
 * server they do not run, so on that deployment the tile is simply absent.
 *
 * Where it is offered, the tile says whether it can run an agent right now,
 * and the dialog says what to do when it cannot. It fails one of two ways —
 * a server that does not answer, or one holding no model that calls tools —
 * and "Check again" asks the server which, through the same verify route a
 * pasted key goes through.
 */

import { useState } from "react";
import { Trans, useLingui } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
import { verifyProvider } from "../../lib/onboardingApi";
import { SOURCE_DETAIL, SOURCE_LABELS, SOURCE_TONE } from "../../lib/modelTiers";
import ConnectorDialog from "./ConnectorDialog";
import ConnectorDot from "./ConnectorDot";
import ConnectorTile from "./ConnectorTile";

export default function InstanceProviderCard({ provider, logo, status }) {
  const { i18n, t } = useLingui();
  const [open, setOpen] = useState(false);
  const [checking, setChecking] = useState(false);
  const [check, setCheck] = useState(null);

  if (!status?.configured) return null;

  const ready = Boolean(status.reachable);
  const tone = SOURCE_TONE[ready ? "instance" : "none"];
  const label = ready ? i18n._(SOURCE_LABELS.instance) : t`Not answering`;
  const detail = ready
    ? i18n._(SOURCE_DETAIL.instance)
    : t`Ollama isn't answering, or holds no model that can call tools`;

  async function checkAgain() {
    setChecking(true);
    setCheck(null);
    try {
      setCheck(await verifyProvider(provider.statusId));
    } catch (err) {
      setCheck({ ok: false, detail: String(err?.message || err) });
    } finally {
      setChecking(false);
    }
  }

  return (
    <>
      <ConnectorTile
        logo={logo}
        title={provider.label}
        description={provider.description}
        tone={tone}
        status={label}
        onClick={() => setOpen(true)}
      />

      <ConnectorDialog
        open={open}
        onOpenChange={setOpen}
        logo={logo}
        title={provider.label}
        description={provider.description}
        status={
          <span className="conn-state">
            <span className="conn-state-glyph" title={detail}>
              <ConnectorDot tone={tone} label={label} />
            </span>
          </span>
        }
        footer={
          <Button type="button" size="sm" onClick={checkAgain} disabled={checking}>
            {checking ? <Trans>Checking…</Trans> : <Trans>Check again</Trans>}
          </Button>
        }
      >
        <div className="conn-dialog-section">
          {ready ? (
            <p className="conn-hint">
              <Trans>
                Pick one of its models for a tier on the Tiers tab. Only models that can call
                tools are listed, because every Duct agent works by calling them.
              </Trans>
            </p>
          ) : (
            <>
              <p className="conn-hint">
                <Trans>
                  This server is set up to run open models on Ollama, but Ollama isn&rsquo;t
                  answering or holds no model that can call tools.
                </Trans>
              </p>
              <ol className="conn-hint">
                <li>
                  <Trans>
                    Start Ollama on the machine it was set up on (
                    <a href={provider.downloadUrl} target="_blank" rel="noreferrer noopener">
                      download it
                    </a>
                    ).
                  </Trans>
                </li>
                <li>
                  <Trans>
                    Pull a model that calls tools, for example <code>ollama pull qwen3</code>.
                  </Trans>
                </li>
              </ol>
            </>
          )}
          {check && (
            <p className={`conn-hint${check.ok ? "" : " conn-hint--alert"}`} role={check.ok ? undefined : "alert"}>
              {check.ok ? t`Ready: ${check.model} answered.` : check.detail}
            </p>
          )}
        </div>
      </ConnectorDialog>
    </>
  );
}
