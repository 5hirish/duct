"use client";

/**
 * The interface language, wherever someone is when they want to change it.
 *
 * One rule for four places — the profile page, the sign-in screen, `/start`
 * and the account menu in the sidebar — because it would drift if written
 * four times: write the cookie the server layout reads, save the profile when
 * there is one to save to, then `router.refresh()` so the frame re-renders in
 * the new language with no reload and nothing typed lost. `useSwitchLocale`
 * is that rule; the two components here are its two shapes, a select for a
 * page and a sub-menu for a dropdown.
 *
 * Labels are the languages' own names, untranslated on purpose. Someone who
 * landed in the wrong language has to be able to find their own in the list.
 */
import { useRouter } from "next/navigation";
import { Trans, useLingui } from "@lingui/react/macro";
import { Languages } from "lucide-react";
import {
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
} from "@/components/ui/dropdown-menu";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { writeLocaleCookie } from "@/i18n/cookie";
import { LOCALES, normalizeLocale } from "@/i18n/locales";
import { hasAuthToken } from "@/lib/authFetch";
import { saveProfile } from "@/lib/userProfile";
import { cn } from "@/lib/utils";

/**
 * @param {string} [value] The active locale; defaults to the catalogue's.
 * @param {(locale: string) => void} [onChange] Fires after the switch.
 * @returns {{ current: string, change: (locale: string) => void }}
 */
export function useSwitchLocale(value, onChange) {
  const router = useRouter();
  const { i18n } = useLingui();
  const current = normalizeLocale(value) || normalizeLocale(i18n.locale) || "en";

  function change(next) {
    if (next === current) return;
    writeLocaleCookie(next);
    if (hasAuthToken()) saveProfile({ interface_language: next });
    onChange?.(next);
    router.refresh();
  }

  return { current, change };
}

/**
 * @param {object} props
 * @param {string} [props.value] The active locale; defaults to the catalogue's.
 * @param {boolean} [props.compact] Icon-only trigger for a header.
 * @param {string} [props.id] For a <label htmlFor>.
 * @param {string} [props.className]
 * @param {(locale: string) => void} [props.onChange] Fires after the switch.
 */
export default function LanguageMenu({ value, compact = false, id, className, onChange }) {
  const { t } = useLingui();
  const { current, change } = useSwitchLocale(value, onChange);

  return (
    <Select value={current} onValueChange={change}>
      <SelectTrigger
        id={id}
        aria-label={t`Interface language`}
        className={cn(compact ? "h-8 w-auto gap-1.5 border-0 bg-transparent px-2 shadow-none" : "", className)}
      >
        <Languages className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        {compact ? null : <SelectValue />}
      </SelectTrigger>
      <SelectContent align="end">
        {LOCALES.map((locale) => (
          <SelectItem key={locale.value} value={locale.value}>
            {locale.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

/**
 * The same switch as a row in a dropdown, for the sidebar's account menu: the
 * trigger shows the current language's own name, the sub-menu lists the rest.
 * A person who cannot read the interface still finds their language here,
 * because the names are endonyms and the icon needs no reading at all.
 */
export function LanguageMenuItem({ value, onChange }) {
  const { current, change } = useSwitchLocale(value, onChange);
  const label = LOCALES.find((l) => l.value === current)?.label ?? current;

  return (
    <DropdownMenuSub>
      <DropdownMenuSubTrigger className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-2">
          <Languages className="size-4 text-muted-foreground" aria-hidden="true" />
          <span><Trans>Language</Trans></span>
        </span>
        <span className="ml-auto truncate text-xs text-muted-foreground">{label}</span>
      </DropdownMenuSubTrigger>
      <DropdownMenuSubContent>
        <DropdownMenuRadioGroup value={current} onValueChange={change}>
          {LOCALES.map((locale) => (
            <DropdownMenuRadioItem key={locale.value} value={locale.value} lang={locale.value}>
              {locale.label}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuSubContent>
    </DropdownMenuSub>
  );
}
