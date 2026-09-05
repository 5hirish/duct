"use client";

// Which property / container / account this project reads, for one connector.
//
// A Radix Select was the obvious choice and the wrong one: it has no search,
// and the lists here are unbounded — a consultant's Search Console holds every
// client site they have ever been given access to. So this is a Popover with a
// filter box, which is also why the options load lazily: listing them costs a
// live API call per connector, and a page that opened four dialogs' worth of
// them on mount would spend four round trips to render controls nobody touched.
//
// The vocabulary and the row contents both come from the server, not from a
// lookup table here. "Account" over a list of domain names reads as a bug, and
// a per-connector table in the frontend is one more place to forget when a
// connector is added — so an adapter that has a URL, a disambiguating line or a
// couple of short facts sends them as `entity_url` / `entity_detail` /
// `entity_meta`, and this renders whatever arrived.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Popover } from "radix-ui";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { listConnectorEntities } from "../../lib/connectorsApi";
import EntityAvatar from "./EntityAvatar";

/** Title-case for sentence starts; the nouns arrive lowercase from the catalog. */
function capitalize(word) {
  return word ? word[0].toUpperCase() + word.slice(1) : word;
}

/**
 * "a property" but "an account".
 *
 * The nouns are connector-supplied, so the article cannot be baked into the
 * string — and getting it wrong is the kind of small wrongness that makes a
 * product feel unfinished ("Choose a account").
 */
function withArticle(noun) {
  return `${/^[aeiou]/i.test(noun) ? "an" : "a"} ${noun}`;
}

/** Everything about a row a search should match, including the chips. */
function haystack(entity) {
  return [
    entity.account_name,
    entity.account_id,
    entity.entity_detail,
    entity.parent_account_name,
    entity.entity_url,
    ...(entity.entity_meta || []).map((fact) => fact?.value),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

/**
 * The line under the name.
 *
 * `entity_detail` is the connector's own answer; `parent_account_name` is the
 * older key that predates it and still arrives from GA4. Neither earns a line
 * by repeating the name above it.
 */
function subtitleOf(entity) {
  const detail = entity.entity_detail || entity.parent_account_name || "";
  return detail && detail !== entity.account_name ? detail : "";
}

export default function ProjectEntitySelect({
  projectName,
  credentialId,
  binding,
  onChange,
  busy = false,
  // How to fetch the list. Defaults to the real call; the only other caller is
  // the preview route, which passes a stub so the loading, empty, error and
  // populated states can all be looked at without a signed-in session and a
  // live Google grant behind them. One optional prop with a real default beats
  // the alternative — reconstructing this component's markup by hand somewhere
  // else, which is a copy that silently stops matching.
  loadEntities = listConnectorEntities,
  // Sent with the connector row, so the label is right on first paint. Without
  // it the field read "Account" over a list of Search Console properties until
  // someone opened the dropdown and the lazy listing corrected it.
  noun = "account",
  nounPlural = "accounts",
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [state, setState] = useState({ status: "idle", entities: [] });
  const [nouns, setNouns] = useState({ one: noun, many: nounPlural });
  const searchRef = useRef(null);

  const selectedId = binding?.entity_id || "";
  const selectedName = binding?.entity_name || "";

  const load = useCallback(async () => {
    if (!credentialId) return;
    setState((prev) => ({ ...prev, status: "loading" }));
    try {
      const data = await loadEntities(credentialId);
      setNouns({
        one: data.entity_noun || "account",
        many: data.entity_noun_plural || "accounts",
      });
      setState({
        status: data.supported === false ? "unsupported" : "ready",
        entities: Array.isArray(data.entities) ? data.entities : [],
      });
    } catch (err) {
      // Listing reaches the provider, so this fails for reasons that have
      // nothing to do with Duct — an expired grant, a revoked property, an
      // outage. Say which, and leave any existing choice untouched: a failed
      // lookup is not evidence the stored selection is wrong.
      setState({ status: "error", entities: [], error: err?.message || String(err) });
    }
  }, [credentialId, loadEntities]);

  // Load on first open only. Reopening keeps what we have; Refresh re-fetches.
  useEffect(() => {
    if (open && state.status === "idle") load();
    if (open) setTimeout(() => searchRef.current?.focus(), 0);
  }, [open, state.status, load]);

  // The binding stores an id and a name, not a URL, so the trigger shows a
  // monogram until the listing has been opened once. Matching it back to a
  // loaded row upgrades that to the real favicon without another round trip.
  const selected = useMemo(
    () => state.entities.find((entity) => entity.account_id === selectedId) || null,
    [state.entities, selectedId],
  );

  if (!projectName || !credentialId) return null;

  const needle = query.trim().toLowerCase();
  const matches = needle
    ? state.entities.filter((entity) => haystack(entity).includes(needle))
    : state.entities;

  function choose(entity) {
    setOpen(false);
    setQuery("");
    onChange?.({ entityId: entity?.account_id || "", entityName: entity?.account_name || "" });
  }

  return (
    <div className="conn-field">
      {/* Just the noun. The section heading above already says which project
          this is for, and repeating it put the same three words on two
          consecutive lines. */}
      <Label htmlFor={`entity-${projectName}`}>{capitalize(nouns.one)}</Label>

      <Popover.Root open={open} onOpenChange={setOpen}>
        <Popover.Trigger asChild>
          <button
            id={`entity-${projectName}`}
            type="button"
            className="conn-entity-trigger"
            disabled={busy}
            aria-label={`Choose ${withArticle(nouns.one)} for ${projectName}`}
          >
            <span className="conn-entity-trigger-main">
              {selectedName && (
                <EntityAvatar url={selected?.entity_url} name={selectedName} />
              )}
              <span className={selectedName ? "conn-entity-value" : "conn-entity-placeholder"}>
                {selectedName || `Choose ${withArticle(nouns.one)}`}
              </span>
            </span>
            <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
              <path
                d="M4 6l4 4 4-4"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.75"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </button>
        </Popover.Trigger>

        <Popover.Portal>
          <Popover.Content className="conn-entity-panel" align="start" sideOffset={6}>
            <div className="conn-entity-search">
              <Input
                ref={searchRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={`Search ${nouns.many}`}
                aria-label={`Search ${nouns.many}`}
              />
            </div>

            <div className="conn-entity-list" role="listbox">
              {state.status === "loading" && (
                <p className="conn-entity-note">Loading {nouns.many}…</p>
              )}
              {state.status === "error" && (
                <p className="conn-entity-note conn-entity-note-error">
                  Could not list {nouns.many}. {state.error}
                </p>
              )}
              {state.status === "unsupported" && (
                <p className="conn-entity-note">
                  This connector has no {nouns.many} to choose from.
                </p>
              )}
              {state.status === "ready" && matches.length === 0 && (
                <p className="conn-entity-note">
                  {state.entities.length === 0
                    ? `No ${nouns.many} reachable with this connection.`
                    : `No ${nouns.many} match “${query}”.`}
                </p>
              )}

              {state.status === "ready" &&
                matches.map((entity, index) => {
                  const active = entity.account_id === selectedId;
                  const subtitle = subtitleOf(entity);
                  const facts = (entity.entity_meta || []).filter((fact) => fact?.value);
                  return (
                    <button
                      // Two rows sharing an id is a connector bug, not a reason
                      // to crash the list — the index keeps them distinct.
                      key={`${entity.account_id || "row"}-${index}`}
                      type="button"
                      role="option"
                      aria-selected={active}
                      className={`conn-entity-option${active ? " is-active" : ""}`}
                      onClick={() => choose(entity)}
                    >
                      <EntityAvatar url={entity.entity_url} name={entity.account_name} />
                      <span className="conn-entity-option-main">
                        {entity.account_name || entity.account_id}
                      </span>
                      {subtitle && <span className="conn-entity-option-sub">{subtitle}</span>}
                      {facts.length > 0 && (
                        <span className="conn-entity-option-facts">
                          {facts.map((fact) => (
                            // The label is the tooltip, not a prefix: "USD"
                            // reads on its own, "Currency: USD" costs a line.
                            <span key={fact.label} className="conn-entity-fact" title={fact.label}>
                              {fact.value}
                            </span>
                          ))}
                        </span>
                      )}
                      {active && (
                        <svg
                          className="conn-entity-check"
                          viewBox="0 0 16 16"
                          width="14"
                          height="14"
                          aria-hidden="true"
                        >
                          <path
                            d="M3 8.5l3.5 3.5L13 5"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                        </svg>
                      )}
                    </button>
                  );
                })}
            </div>

            <div className="conn-entity-foot">
              {selectedId && (
                <button type="button" className="conn-entity-link" onClick={() => choose(null)}>
                  Clear
                </button>
              )}
              <button
                type="button"
                className="conn-entity-link"
                onClick={() => {
                  setState({ status: "idle", entities: [] });
                }}
              >
                Refresh
              </button>
            </div>
          </Popover.Content>
        </Popover.Portal>
      </Popover.Root>

      <p className="conn-hint">
        {selectedName
          ? `Reports and agent runs use this ${nouns.one}.`
          : `Optional — the agent will ask if you leave this unset.`}
      </p>
    </div>
  );
}
