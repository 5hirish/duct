"use client";

/**
 * Profile — who Duct is answering, and how they want to be written to.
 *
 * This replaces a dialog that asked five questions across five stacked grids of
 * option cards, most of which reached one agent. What it keeps is the part that
 * changes an answer: a role, one voice, and the person's own instructions. What
 * it drops is the deliverable format (a per-artifact choice, never an identity)
 * and the four-way outcome enum, which was flattening a sentence into a radio
 * group. An existing outcome is carried into the notes rather than deleted, in
 * `lib/userProfile.js`.
 *
 * Two decisions worth keeping:
 *
 *  * **One preset, not a style grid and a depth grid.** Almost nobody wants
 *    executive framing with exhaustive evidence, and the person who does says
 *    so in the notes, which outrank the preset. `service/profile.py` still
 *    derives the old style/depth pair, so no prompt had to change.
 *  * **The sample is the point.** "Practitioner" means nothing until you see it
 *    next to "Executive". The samples are canned — nine short strings — because
 *    a live rewrite would be a model call per click, on a settings page.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { FolderKanban } from "lucide-react";
import { Plural, Trans, useLingui } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  LANGUAGES,
  NOTES_MAX_CHARS,
  PROFILE_DEFAULTS,
  ROLE_OPTIONS,
  WRITING_PRESETS,
  detectTimezone,
  fetchProfile,
  listTimezones,
  loadProfile,
  migrateLegacyPreferences,
  saveProfile,
  zoneLabel,
  zoneOffsetLabel,
  zoneRegion,
} from "@/lib/userProfile";
import { hasAuthToken } from "@/lib/authFetch";
import VoiceSample from "@/components/profile/VoiceSample";
import LanguageMenu from "@/components/LanguageMenu";

/** Long enough that a typist is not interrupted, short enough to feel saved. */
const SAVE_DEBOUNCE_MS = 600;

/** Radix cannot hold "" as a select value; this is "not saying". */
const NO_ROLE = "none";

/** Same constraint for the timezone: "" is stored, "utc" is what Radix holds. */
const UTC_VALUE = "utc";

/**
 * The zone list, grouped by region and built once per mount.
 *
 * ~420 entries, which sounds unusable and is not: Radix Select does type-ahead
 * on the item text, and the items are named "Madrid" rather than
 * "Europe/Madrid", so typing three letters gets there. That is why the region
 * is a group heading instead of part of every label.
 *
 * ``pinned`` is dropped from its region group. Two items may not share a
 * value: Radix builds the trigger's text by concatenating *every* item whose
 * value matches the selection, so a zone listed both under "This device" and
 * under "Europe" renders the trigger as "Madrid · EuropeMadrid".
 */
function groupedZones(pinned = "") {
  const groups = new Map();
  for (const zone of listTimezones()) {
    if (zone === pinned) continue;
    const region = zoneRegion(zone);
    if (!groups.has(region)) groups.set(region, []);
    groups.get(region).push(zone);
  }
  return [...groups.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([region, zones]) => [region, zones.sort((a, b) => zoneLabel(a).localeCompare(zoneLabel(b)))]);
}

export default function ProfilePage() {
  const { t, i18n } = useLingui();
  const [profile, setProfile] = useState(() => loadProfile());
  const [saved, setSaved] = useState("");
  const [offline, setOffline] = useState(false);
  // Read after mount, never during render: `hasAuthToken` reads localStorage,
  // which the server frame cannot see, and a mismatched first frame is kept.
  const [signedIn, setSignedIn] = useState(true);
  const timer = useRef(null);
  const savedTimer = useRef(null);

  // The server is the truth; localStorage only painted the first frame. The
  // legacy dialog's values are folded in here, once, before that first read
  // lands, so an upgrading user never sees their old voice blink away.
  useEffect(() => {
    setSignedIn(hasAuthToken());
    const carried = migrateLegacyPreferences();
    let alive = true;
    fetchProfile().then((row) => {
      if (!alive) return;
      const next = { ...row, ...(carried || {}) };
      setProfile(next);
      if (carried) saveProfile(carried);
    });
    return () => {
      alive = false;
    };
  }, []);

  useEffect(
    () => () => {
      clearTimeout(timer.current);
      clearTimeout(savedTimer.current);
    },
    [],
  );

  const flash = useCallback((result) => {
    setOffline(result === null && hasAuthToken());  // null with a token means the write failed
    setSaved(result === null ? "" : t`Saved`);
    clearTimeout(savedTimer.current);
    savedTimer.current = setTimeout(() => setSaved(""), 1600);
  }, [t]);

  /** Optimistic: the control moves now, the row catches up. */
  const update = useCallback(
    (patch, { debounce = false } = {}) => {
      setProfile((prev) => ({ ...prev, ...patch }));
      clearTimeout(timer.current);
      if (!debounce) {
        saveProfile(patch).then(flash);
        return;
      }
      timer.current = setTimeout(() => saveProfile(patch).then(flash), SAVE_DEBOUNCE_MS);
    },
    [flash],
  );

  const notesLeft = NOTES_MAX_CHARS - (profile.notes || "").length;
  // Both are environment facts, not props: read once per mount rather than on
  // every keystroke in the notes box, which re-renders this whole form.
  const [deviceZone] = useState(detectTimezone);
  const [zoneGroups] = useState(() => groupedZones(deviceZone));
  const chosenZone = profile.timezone || "";
  const offset = zoneOffsetLabel(chosenZone || "UTC");
  const offsetSuffix = offset ? ` · ${offset}` : "";

  return (
    <section>
      <div className="page-toolbar-back">
        <h1 className="page-toolbar-title text-2xl font-semibold tracking-tight"><Trans>Profile</Trans></h1>
        <span aria-live="polite" className={`mt-saved${saved ? " mt-saved--on" : ""}`}>
          {saved}
        </span>
        <Button asChild variant="ghost" size="sm" className="ml-auto">
          {/* A shortcut, not a back link: the arrow read as "you came from
              projects", which is rarely where a settings page was opened
              from. The folder says what it is. */}
          <Link href="/projects">
            <FolderKanban className="size-4" /> <Trans>Your projects</Trans>
          </Link>
        </Button>
      </div>

      <p className="app-subtle" style={{ marginTop: 0, marginBottom: 20 }}>
        <Trans>Every agent reads this, on every project. Only you can see it.</Trans>
      </p>

      {!signedIn && (
        <p className="app-subtle" style={{ marginBottom: 16, fontSize: 13 }}>
          <Trans>
            Saved on this device until you sign in. A signed-in profile follows you, and the
            scheduled brief can read it.
          </Trans>
        </p>
      )}
      {offline && (
        <p role="alert" className="text-destructive" style={{ marginBottom: 16, fontSize: 13 }}>
          <Trans>Not saved to your account. It is kept on this device; try again in a moment.</Trans>
        </p>
      )}

      {/* One column, one right edge. Every block inside sits at the column
          width rather than carrying its own `ch` measure, which resolves
          against each element's own font-size and so lined nothing up: the
          character counter under the notes box stopped a fifth of the way
          short of it, because 68ch at 11px is not 68ch at 14px. */}
      <div className="pf-body">
        <div className="pf-rows">
          <div className="pf-row">
            <label className="pf-label" htmlFor="pf-name">
              <Trans>What should Duct call you?</Trans>
            </label>
            <input
              id="pf-name"
              className="pf-input"
              value={profile.display_name}
              maxLength={80}
              placeholder={t`Shirish`}
              onChange={(e) => update({ display_name: e.target.value }, { debounce: true })}
            />
          </div>

          <div className="pf-row">
            <label className="pf-label" htmlFor="pf-role">
              <Trans>What do you do?</Trans>
            </label>
            {/* Radix treats "" as no selection, so the empty option travels as a
                sentinel and is mapped back on the way in and out. */}
            <Select
              value={profile.role || NO_ROLE}
              onValueChange={(role) => update({ role: role === NO_ROLE ? "" : role })}
            >
              <SelectTrigger id="pf-role" className="pf-control">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ROLE_OPTIONS.map((option) => (
                  <SelectItem key={option.value || NO_ROLE} value={option.value || NO_ROLE}>
                    {i18n._(option.label)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="pf-row">
            <label className="pf-label" htmlFor="pf-interface-language">
              <Trans>Show Duct in</Trans>
            </label>
            {/* Saves itself (cookie + profile + refresh); the page only keeps
                its local copy current so the next save does not put the old
                value back. */}
            <LanguageMenu
              id="pf-interface-language"
              className="pf-control"
              value={profile.interface_language}
              onChange={(value) => setProfile((prev) => ({ ...prev, interface_language: value }))}
            />
          </div>

          <div className="pf-row">
            <label className="pf-label" htmlFor="pf-language">
              <Trans>Write to me in</Trans>
            </label>
            <Select
              value={profile.communication_language || "auto"}
              onValueChange={(value) =>
                update({ communication_language: value === "auto" ? "" : value })
              }
            >
              <SelectTrigger id="pf-language" className="pf-control">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {LANGUAGES.map((option) => (
                  <SelectItem key={option.value || "auto"} value={option.value || "auto"}>
                    {i18n._(option.label)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="pf-row">
            <label className="pf-label" htmlFor="pf-timezone">
              <Trans>My timezone</Trans>
            </label>
            <Select
              value={chosenZone || UTC_VALUE}
              onValueChange={(value) =>
                update({ timezone: value === UTC_VALUE ? "" : value })
              }
            >
              <SelectTrigger id="pf-timezone" className="pf-control">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {/* The device's own zone first, because it is the right answer
                    for almost everyone and scrolling to it otherwise means
                    passing four hundred that are not. Not pre-selected: a
                    detected value saved without being chosen reads back as a
                    preference, and this one decides which seven days "last
                    week" means. */}
                {deviceZone && (
                  <SelectGroup>
                    <SelectLabel><Trans>This device</Trans></SelectLabel>
                    {/* Just the city, like every other item: the trigger
                        renders the selected item's own text, so a pinned entry
                        spelled differently makes the closed control read
                        differently depending on where you picked from. */}
                    <SelectItem value={deviceZone}>{zoneLabel(deviceZone)}</SelectItem>
                  </SelectGroup>
                )}
                <SelectGroup>
                  <SelectLabel><Trans>Default</Trans></SelectLabel>
                  <SelectItem value={UTC_VALUE}>UTC</SelectItem>
                </SelectGroup>
                {zoneGroups.map(([region, zones]) => (
                  <SelectGroup key={region}>
                    <SelectLabel>{region}</SelectLabel>
                    {zones.map((zone) => (
                      <SelectItem key={zone} value={zone}>
                        {zoneLabel(zone)}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                ))}
              </SelectContent>
            </Select>
            <p className="pf-hint">
              {chosenZone
                ? <Trans>Duct reads "last week" and "yesterday" in {chosenZone}{offsetSuffix}.</Trans>
                : <Trans>Dates resolve in UTC{offsetSuffix}. Pick your zone so "last week" means your week.</Trans>}
            </p>
          </div>
        </div>

        <h2 className="pf-heading"><Trans>How Duct writes</Trans></h2>
        <div className="pf-presets" role="radiogroup" aria-label={t`How Duct writes`}>
          {WRITING_PRESETS.map((preset) => {
            const selected = preset.value === profile.writing_preset;
            return (
              <button
                key={preset.value}
                type="button"
                role="radio"
                aria-checked={selected}
                onClick={() => update({ writing_preset: preset.value })}
                className={`pf-preset${selected ? " pf-preset--on" : ""}`}
              >
                <span className="pf-preset-name">{i18n._(preset.label)}</span>
                <span className="pf-preset-desc">{i18n._(preset.description)}</span>
              </button>
            );
          })}
        </div>

        {/* The reason the presets are legible at all. Same finding, three voices. */}
        <VoiceSample preset={profile.writing_preset} language={profile.communication_language} />

        <h2 className="pf-heading"><Trans>Anything else Duct should know</Trans></h2>
        <p className="app-subtle" style={{ marginTop: 0, marginBottom: 8, fontSize: 13 }}>
          <Trans>
            House rules, the metric you actually care about, how you want to be argued with. This
            wins when it disagrees with the setting above.
          </Trans>
        </p>
        <textarea
          className="pf-notes"
          value={profile.notes}
          maxLength={NOTES_MAX_CHARS}
          rows={4}
          aria-label={t`Anything else Duct should know`}
          placeholder={t`Give me the number first, then the why. Never recommend a change I cannot roll back.`}
          onChange={(e) => update({ notes: e.target.value }, { debounce: true })}
        />
        <p className="pf-count"><Plural value={notesLeft} one="# character left" other="# characters left" /></p>

        <div className="pf-actions">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => {
              setProfile({ ...PROFILE_DEFAULTS });
              saveProfile({ ...PROFILE_DEFAULTS }).then(flash);
            }}
          >
            <Trans>Reset to defaults</Trans>
          </Button>
        </div>
      </div>
    </section>
  );
}
