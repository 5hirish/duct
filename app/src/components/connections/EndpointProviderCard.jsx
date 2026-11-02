"use client";

/**
 * Any server that speaks OpenAI's API, brought by the reader: vLLM on their own
 * GPU, LM Studio on a self-hosted Duct's machine, or a host of open-weight
 * models (Together, Fireworks, Groq, DeepInfra).
 *
 * A key card would not do. What the reader knows is an address, maybe a key,
 * and which model they want, and what can go wrong is specific to each: an
 * address Duct's servers cannot reach, a server that answers in some other
 * format, a key it refuses, a model that chats but never calls a tool. So
 * connecting is three visible steps, each answered by the server before the
 * next: where it runs (with the common hosts one click away), which of its
 * models Duct may use (read from the server, never typed), and a real tool
 * call on the first of them, because every Duct agent works by calling tools.
 * A failure names its fix in the step it happened in.
 *
 * What is saved is one credential string (`lib/endpointCredential.js`) going
 * where any key goes: this browser session or the desktop keychain, or
 * remembered on Duct, the same choice and the same storage glyph as every
 * provider card. The status row describes the connection (address, models,
 * whether a key is set) and never the key, so a remembered endpoint can be
 * shown without the browser holding it.
 */

import { useEffect, useMemo, useState } from "react";
import { Eye, EyeOff, Check } from "lucide-react";
import { Trans, useLingui } from "@lingui/react/macro";
import { msg } from "@lingui/core/macro";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { useConfirm } from "@/components/ui/confirm-dialog";
import { STORAGE_KEYCHAIN, STORAGE_NONE, STORAGE_SESSION, serverStorage } from "../../lib/credentialStorage";
import { packEndpoint, unpackEndpoint } from "../../lib/endpointCredential";
import { isLocalBackendActive } from "../../lib/localBackend";
import { verifyProvider } from "../../lib/onboardingApi";
import { clearProviderKey, readProviderKey, setProviderKey } from "../../lib/providerKeys";
import { forgetProviderKey, probeEndpoint, rememberProviderKey } from "../../lib/providerKeysRemote";
import { isDesktopShell } from "../../lib/shell";
import { SOURCE_DETAIL, SOURCE_TONE } from "../../lib/modelTiers";
import ConnectorDialog from "./ConnectorDialog";
import ConnectorDot from "./ConnectorDot";
import ConnectorTile from "./ConnectorTile";
import StorageBadge from "./StorageBadge";

const TILE_TONE = { ok: "on", info: "info", warn: "off" };

// Enough for a Heavy, Standard and Light pick with room to compare, and few
// enough that the tier pickers stay a choice rather than a host's catalogue.
const MAX_MODELS = 8;
// A local server lists one or two models; a host lists hundreds.
const FILTER_FROM = 8;

// The addresses a hosted Duct cannot reach, recognised as they are typed so
// the reader hears why before a round trip, not after.
const PRIVATE_ADDRESS = /^(https?:\/\/)?(localhost|127\.|0\.0\.0\.0|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|\[?::1\]?|[^/:]+\.local\b)/i;

/**
 * What to do about each way connecting can fail. The server's own detail is
 * shown under it, smaller: this says what to do, that says what happened.
 */
const PROBLEMS = {
  refused: msg`Duct can’t call that address.`,
  unreachable: msg`Nothing answered at that address. Check the server is running and the address is right.`,
  invalid_key: msg`The server turned the key down. Check it, or whether this server needs one at all.`,
  not_compatible: msg`Something answered, but not in OpenAI’s format. The address usually ends in /v1.`,
  no_models: msg`The server lists no chat models yet. Load or deploy one, then try again.`,
  no_tools: msg`This model answered, but didn’t call the tool it was handed. Duct’s agents work by calling tools, so pick one that supports them. On vLLM, start the server with tool calling turned on.`,
  model_access: msg`The server doesn’t serve that model to this key.`,
  rate_limited: msg`The server is limiting requests right now. Try again in a minute.`,
  no_billing: msg`The account behind this key has no credit.`,
  missing_key: msg`No endpoint is connected yet.`,
  unknown: msg`That didn’t work.`,
};

// A component rather than a helper taking `t`: the macro only rewrites a `t`
// it can see being taken from `useLingui`.
function ContextLength({ length }) {
  const { t } = useLingui();
  if (!length) return t`context not reported, Duct assumes 32K`;
  const size = `${Math.round(length / 1024)}K`;
  return t`${size} context`;
}

/**
 * @param status  This provider's row from `/api/providers/status`: `source`,
 *   `stored`, `private_ok`, and `endpoint` (address and models, never the key).
 * @param onChange  Called after a connect or disconnect, so the page reloads
 *   the status and the tier pickers' catalogue.
 * @param onOpenTiers  Takes the reader to the Tiers tab after connecting.
 * @param readKey, probe, check  The real store and routes by default; `/preview`
 *   passes stubs, since no server answers there.
 */
export default function EndpointProviderCard({
  provider,
  logo,
  status,
  loading = false,
  onChange,
  onOpenTiers,
  readKey = readProviderKey,
  probe = probeEndpoint,
  check = verifyProvider,
}) {
  const { t, i18n } = useLingui();
  const { confirm, dialog: confirmDialog } = useConfirm();
  const desktop = isDesktopShell();

  const [open, setOpen] = useState(false);
  // The credential this browser or keychain holds, if any; a remembered one
  // lives only on the server and is described by `status.endpoint`.
  const [local, setLocal] = useState("");
  const [localLoaded, setLocalLoaded] = useState(false);
  const [editing, setEditing] = useState(false);
  const [address, setAddress] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [revealed, setRevealed] = useState(false);
  const [found, setFound] = useState(null);
  const [chosen, setChosen] = useState([]);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState("");
  const [problem, setProblem] = useState(null);
  const [checked, setChecked] = useState(null);
  const [remember, setRemember] = useState(true);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    let alive = true;
    readKey(provider.id)
      .then(({ key }) => alive && setLocal(key || ""))
      .finally(() => alive && setLocalLoaded(true));
    return () => {
      alive = false;
    };
  }, [provider.id, readKey]);

  const endpoint = status?.endpoint || null;
  const source = status?.source || "none";
  const live = Boolean(endpoint) && source !== "none";
  const remembered = Boolean(status?.stored);
  const privateOk = Boolean(status?.private_ok);
  const settling = loading || !localLoaded;
  const showForm = editing || !live;
  const presets = provider.presets.filter((preset) => privateOk || !preset.local);
  const preset = provider.presets.find((p) => p.url === address.trim());

  const storage = desktop
    ? local
      ? STORAGE_KEYCHAIN
      : STORAGE_NONE
    : remembered
      ? serverStorage({ localSidecar: isLocalBackendActive() })
      : local
        ? STORAGE_SESSION
        : STORAGE_NONE;

  const host = endpoint?.host || "";
  const tile = settling
    ? { tone: "loading", label: t`Checking…`, detail: t`Looking up your endpoint.` }
    : live
      ? {
          // Which server, rather than "Your key": the storage glyph beside it
          // already says whose and where, and the address is what tells two
          // setups apart.
          tone: TILE_TONE[SOURCE_TONE[source]] || "on",
          label: t`Connected · ${host}`,
          detail: i18n._(SOURCE_DETAIL[source] || SOURCE_DETAIL.none),
        }
      : { tone: "off", label: t`Not connected`, detail: t`No endpoint connected` };

  const addressIsPrivate = PRIVATE_ADDRESS.test(address.trim());
  // Named, so the catalogue shows a translator `{modelCount}` rather than `{0}`.
  const modelCount = found?.models.length ?? 0;
  const foundAt = found ? new URL(found.baseUrl).host : "";
  const presetName = preset?.label ?? "";
  const readyModel = checked?.model ?? "";
  const readySeconds = checked?.latency_ms ? (checked.latency_ms / 1000).toFixed(1) : "";
  const visible = useMemo(() => {
    const models = found?.models || [];
    const needle = query.trim().toLowerCase();
    return needle ? models.filter((m) => m.id.toLowerCase().includes(needle)) : models;
  }, [found, query]);

  function resetDiscovery() {
    setFound(null);
    setProblem(null);
    setQuery("");
  }

  function startEditing() {
    const mine = unpackEndpoint(local);
    setAddress(endpoint?.base_url || mine?.baseUrl || "");
    setApiKey(mine?.apiKey || "");
    setChosen((endpoint?.models || []).map((m) => m.id));
    setRemember(remembered || !local);
    resetDiscovery();
    setChecked(null);
    setConnected(false);
    setEditing(true);
  }

  function onOpenChange(next) {
    setOpen(next);
    if (!next) {
      setEditing(false);
      setConnected(false);
      setChecked(null);
      resetDiscovery();
    }
  }

  async function findModels(event) {
    event?.preventDefault();
    if (!address.trim() || (addressIsPrivate && !privateOk) || busy) return;
    setBusy("find");
    resetDiscovery();
    try {
      const answer = await probe({ baseUrl: address.trim(), apiKey: apiKey.trim() });
      if (!answer.ok) {
        setProblem({ code: answer.code, detail: answer.detail });
        return;
      }
      const models = answer.models.map((m) => ({ id: m.id, contextLength: m.context_length }));
      setAddress(answer.base_url);
      setFound({ baseUrl: answer.base_url, models });
      // Keep what was chosen before where the server still lists it; a server
      // with a single model has nothing to choose.
      setChosen((before) => {
        const kept = before.filter((id) => models.some((m) => m.id === id));
        return kept.length ? kept : models.length === 1 ? [models[0].id] : [];
      });
    } catch (err) {
      setProblem({ code: "unknown", detail: String(err?.message || err) });
    } finally {
      setBusy("");
    }
  }

  function toggle(id) {
    setProblem(null);
    setChosen((current) =>
      current.includes(id) ? current.filter((x) => x !== id) : current.length < MAX_MODELS ? [...current, id] : current
    );
  }

  async function save(credential) {
    if (desktop || !remember) {
      await setProviderKey(provider.id, credential);
      if (remembered) await forgetProviderKey(provider.statusId);
    } else {
      // One home for the secret, as on every key card: a remembered endpoint is
      // not also kept in the session.
      await rememberProviderKey(provider.statusId, credential);
      await clearProviderKey(provider.id);
    }
    setLocal(desktop || !remember ? credential : "");
  }

  async function connect({ anyway = false } = {}) {
    if (!found || chosen.length === 0 || busy) return;
    setBusy("connect");
    setProblem(null);
    try {
      if (!anyway) {
        const answer = await probe({ baseUrl: found.baseUrl, apiKey: apiKey.trim(), model: chosen[0] });
        const failed = !answer.ok ? answer : answer.check && !answer.check.ok ? answer.check : null;
        if (failed) {
          setProblem({ code: failed.code, detail: failed.detail, model: chosen[0], canSaveAnyway: failed.code === "no_tools" });
          return;
        }
      }
      const byId = new Map(found.models.map((m) => [m.id, m]));
      await save(
        packEndpoint({ baseUrl: found.baseUrl, apiKey: apiKey.trim(), models: chosen.map((id) => byId.get(id)) })
      );
      setEditing(false);
      setConnected(true);
      resetDiscovery();
      onChange?.();
    } catch (err) {
      setProblem({ code: "unknown", detail: String(err?.message || err) });
    } finally {
      setBusy("");
    }
  }

  async function checkAgain() {
    setBusy("check");
    setChecked(null);
    try {
      setChecked(await check(provider.statusId));
    } catch (err) {
      setChecked({ ok: false, code: "unknown", detail: String(err?.message || err) });
    } finally {
      setBusy("");
    }
  }

  async function disconnect() {
    const ok = await confirm({
      title: t`Disconnect ${host}?`,
      description: t`Duct forgets this endpoint and its key. Tiers set to one of its models fall back to another provider you’ve connected.`,
      action: t`Disconnect`,
      cancel: t`Keep it`,
      destructive: true,
    });
    if (!ok) return;
    setBusy("remove");
    try {
      await clearProviderKey(provider.id);
      if (remembered) await forgetProviderKey(provider.statusId);
      setLocal("");
      setChecked(null);
      setConnected(false);
      onChange?.();
    } catch (err) {
      setProblem({ code: "unknown", detail: String(err?.message || err) });
    } finally {
      setBusy("");
    }
  }

  // A refusal's own sentence already says what to fix ("Use an https://
  // address…"), so it stands alone; every other code leads with what to do and
  // puts the server's detail under it.
  const problemNote = problem && (
    <div className="conn-endpoint-problem" role="alert">
      <p className="conn-hint conn-hint--alert">
        {problem.model ? <b className="conn-endpoint-model-name">{problem.model}: </b> : null}
        {problem.code === "refused" && problem.detail
          ? problem.detail
          : i18n._(PROBLEMS[problem.code] || PROBLEMS.unknown)}
      </p>
      {problem.detail && !["rate_limited", "refused"].includes(problem.code) ? (
        <p className="conn-hint">{problem.detail}</p>
      ) : null}
    </div>
  );

  return (
    <>
      <ConnectorTile
        logo={logo}
        title={provider.label}
        description={provider.description}
        tone={tile.tone}
        status={tile.label}
        storage={settling ? undefined : storage}
        onClick={() => setOpen(true)}
      />

      <ConnectorDialog
        open={open}
        onOpenChange={onOpenChange}
        logo={logo}
        title={provider.label}
        description={provider.description}
        status={
          <span className="conn-state">
            <span className="conn-state-glyph" title={tile.detail}>
              <ConnectorDot tone={tile.tone} label={tile.label} />
            </span>
            <StorageBadge storage={settling ? undefined : storage} />
          </span>
        }
        footer={
          showForm ? (
            <>
              {live && (
                <Button type="button" variant="ghost" size="sm" onClick={() => setEditing(false)} disabled={Boolean(busy)}>
                  <Trans>Cancel</Trans>
                </Button>
              )}
              <Button
                type="button"
                size="sm"
                onClick={() => connect()}
                disabled={!found || chosen.length === 0 || Boolean(busy)}
              >
                {busy === "connect" ? (
                  <>
                    <Spinner />
                    <Trans>Testing…</Trans>
                  </>
                ) : (
                  <Trans>Test and connect</Trans>
                )}
              </Button>
            </>
          ) : (
            <>
              <Button type="button" variant="destructive" size="sm" onClick={disconnect} disabled={Boolean(busy)}>
                <Trans>Disconnect</Trans>
              </Button>
              <Button type="button" variant="secondary" size="sm" onClick={startEditing} disabled={Boolean(busy)}>
                <Trans>Change</Trans>
              </Button>
              <Button type="button" size="sm" onClick={checkAgain} disabled={Boolean(busy)}>
                {busy === "check" ? <Trans>Checking…</Trans> : <Trans>Check again</Trans>}
              </Button>
            </>
          )
        }
      >
        {showForm ? (
          <>
            {/* 1. Where it runs. */}
            <form className="conn-dialog-section" onSubmit={findModels}>
              <div className="conn-field">
                <Label htmlFor="endpoint-address">
                  <Trans>Server address</Trans>
                </Label>
                {/* Once the server has answered, the step is done: the presets and
                    the hints give way so the models and the button fit on screen.
                    The fields stay, and editing one starts the search again. */}
                {!found && (
                  <div className="conn-endpoint-presets" role="group" aria-label={t`Common servers`}>
                    {presets.map((p) => (
                      <button
                        key={p.id}
                        type="button"
                        className="conn-endpoint-preset"
                        aria-pressed={address.trim() === p.url}
                        onClick={() => {
                          setAddress(p.url);
                          resetDiscovery();
                        }}
                      >
                        {p.label}
                      </button>
                    ))}
                  </div>
                )}
                <Input
                  id="endpoint-address"
                  value={address}
                  placeholder={provider.placeholder}
                  onChange={(event) => {
                    setAddress(event.target.value);
                    resetDiscovery();
                  }}
                  inputMode="url"
                  autoComplete="off"
                  autoCapitalize="off"
                  autoCorrect="off"
                  spellCheck={false}
                />
                {!found && (
                  <div className="conn-field-notes">
                    {address.trim() && addressIsPrivate && !privateOk ? (
                      <p className="conn-hint conn-hint--alert">
                        <Trans>
                          Duct’s servers can’t reach this address. A model on your own computer or
                          network needs a public https address, or Duct running on your side.
                        </Trans>
                      </p>
                    ) : (
                      <p className="conn-hint">
                        {privateOk ? (
                          <Trans>
                            The address that serves OpenAI’s API, usually ending in /v1. One on your
                            own network works here.
                          </Trans>
                        ) : (
                          <Trans>The public https address that serves OpenAI’s API, usually ending in /v1.</Trans>
                        )}
                      </p>
                    )}
                  </div>
                )}
              </div>

              <div className="conn-field">
                <Label htmlFor="endpoint-key">
                  <Trans>API key</Trans> <span className="conn-optional">{t`optional`}</span>
                </Label>
                <div className="conn-key-input">
                  <Input
                    id="endpoint-key"
                    type={revealed ? "text" : "password"}
                    value={apiKey}
                    placeholder={endpoint?.has_key && !apiKey ? t`Saved key not shown: paste it to change` : ""}
                    onChange={(event) => {
                      setApiKey(event.target.value);
                      resetDiscovery();
                    }}
                    autoComplete="off"
                    autoCapitalize="off"
                    autoCorrect="off"
                    spellCheck={false}
                  />
                  <button
                    type="button"
                    className="conn-reveal"
                    onClick={() => setRevealed((shown) => !shown)}
                    disabled={!apiKey}
                    aria-label={revealed ? t`Hide key` : t`Show key`}
                    aria-pressed={revealed}
                    aria-controls="endpoint-key"
                  >
                    {revealed ? <EyeOff size={15} aria-hidden="true" /> : <Eye size={15} aria-hidden="true" />}
                  </button>
                </div>
                {!found && (
                  <div className="conn-field-notes">
                    <p className="conn-hint">
                      <Trans>Leave it empty if your server doesn’t ask for one.</Trans>
                      {preset?.keyUrl ? (
                        <>
                          {" "}
                          <a className="app-link" href={preset.keyUrl} target="_blank" rel="noreferrer">
                            <Trans>Get a key from {presetName} →</Trans>
                          </a>
                        </>
                      ) : null}
                    </p>
                  </div>
                )}
              </div>

              {!found && (
                <Button
                  type="submit"
                  variant="secondary"
                  size="sm"
                  className="justify-self-start"
                  // Nothing to ask: the field already says why this address
                  // cannot be reached from here.
                  disabled={!address.trim() || (addressIsPrivate && !privateOk) || Boolean(busy)}
                >
                  {busy === "find" ? (
                    <>
                      <Spinner />
                      <Trans>Looking…</Trans>
                    </>
                  ) : (
                    <Trans>Find models</Trans>
                  )}
                </Button>
              )}
              {!found && problemNote}
            </form>

            {/* 2. Which of its models. */}
            {found && (
              <div className="conn-dialog-section">
                <h3 className="conn-dialog-heading">
                  {modelCount === 1 ? (
                    <Trans>One model at {foundAt}</Trans>
                  ) : (
                    <Trans>
                      {modelCount} models at {foundAt}
                    </Trans>
                  )}
                </h3>
                {found.models.length > 1 && (
                  <p className="conn-hint">
                    <Trans>
                      Pick the ones Duct may use, up to {MAX_MODELS}. They join the tier pickers, and the
                      first is used when a tier doesn’t name one.
                    </Trans>
                  </p>
                )}
                {found.models.length >= FILTER_FROM && (
                  <Input
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder={t`Filter models`}
                    aria-label={t`Filter models`}
                  />
                )}
                <ul className="conn-endpoint-models" aria-label={t`Models`}>
                  {visible.map((model) => {
                    const position = chosen.indexOf(model.id);
                    const full = position === -1 && chosen.length >= MAX_MODELS;
                    return (
                      <li key={model.id}>
                        <label className={`conn-endpoint-model${full ? " is-disabled" : ""}`}>
                          <Checkbox
                            checked={position !== -1}
                            disabled={full || Boolean(busy)}
                            onCheckedChange={() => toggle(model.id)}
                          />
                          <span className="conn-endpoint-model-text">
                            <span className="conn-endpoint-model-name">{model.id}</span>
                            <span className="conn-endpoint-model-sub">
                              <ContextLength length={model.contextLength} />
                            </span>
                          </span>
                          {position === 0 && chosen.length > 1 ? (
                            <span className="conn-endpoint-default">{t`default`}</span>
                          ) : null}
                        </label>
                      </li>
                    );
                  })}
                  {visible.length === 0 && (
                    <li className="conn-hint">
                      <Trans>No model matches “{query}”.</Trans>
                    </li>
                  )}
                </ul>
                {problemNote}
                {problem?.canSaveAnyway && (
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    className="justify-self-start"
                    onClick={() => connect({ anyway: true })}
                    disabled={Boolean(busy)}
                  >
                    <Trans>Connect anyway</Trans>
                  </Button>
                )}
                {!desktop && (
                  <label className="conn-check">
                    <Checkbox checked={remember} onCheckedChange={(next) => setRemember(next === true)} disabled={Boolean(busy)} />
                    <span>
                      <Trans>Remember this endpoint on Duct, so scheduled runs can use it</Trans>
                    </span>
                  </label>
                )}
              </div>
            )}
          </>
        ) : (
          <div className="conn-dialog-section">
            {connected && (
              <div className="conn-endpoint-success" role="status">
                <Check size={16} aria-hidden="true" />
                <p className="conn-hint">
                  <Trans>
                    Connected. Its models are in the tier pickers now, ready to run any Duct agent.
                  </Trans>
                </p>
              </div>
            )}
            <h3 className="conn-dialog-heading">
              <Trans>Connected to {host}</Trans>
            </h3>
            <ul className="conn-endpoint-models conn-endpoint-models--static" aria-label={t`Models`}>
              {(endpoint?.models || []).map((model, index) => (
                <li key={model.id} className="conn-endpoint-model">
                  <span className="conn-endpoint-model-text">
                    <span className="conn-endpoint-model-name">{model.id}</span>
                    <span className="conn-endpoint-model-sub">
                      <ContextLength length={model.context_length} />
                    </span>
                  </span>
                  {index === 0 && endpoint.models.length > 1 ? (
                    <span className="conn-endpoint-default">{t`default`}</span>
                  ) : null}
                </li>
              ))}
            </ul>
            <p className="conn-hint">
              {endpoint?.has_key ? <Trans>Sends a key with every request.</Trans> : <Trans>Sends no key.</Trans>}
            </p>
            <StorageBadge storage={storage} detail />
            {checked &&
              (checked.ok ? (
                <p className="conn-hint" role="status">
                  <Trans>
                    Ready: {readyModel} called a tool in {readySeconds} s.
                  </Trans>
                </p>
              ) : (
                <div className="conn-endpoint-problem" role="alert">
                  <p className="conn-hint conn-hint--alert">
                    {checked.model ? <b className="conn-endpoint-model-name">{checked.model}: </b> : null}
                    {i18n._(PROBLEMS[checked.code] || PROBLEMS.unknown)}
                  </p>
                  {checked.detail ? <p className="conn-hint">{checked.detail}</p> : null}
                </div>
              ))}
            {onOpenTiers && (
              <Button
                type="button"
                variant="secondary"
                size="sm"
                className="justify-self-start"
                onClick={() => {
                  onOpenChange(false);
                  onOpenTiers();
                }}
              >
                <Trans>Choose them for tiers</Trans>
              </Button>
            )}
            {problemNote}
          </div>
        )}
      </ConnectorDialog>
      {confirmDialog}
    </>
  );
}
