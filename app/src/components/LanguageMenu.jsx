"use client";

/**
 * The interface language, wherever someone is when they want to change it.
 *
 * One component for three places — the profile page, the sign-in screen and
 * `/start` — because the rule is the same in all of them and would drift if
 * written three times: write the cookie the server layout reads, save the
 * profile when there is one to save to, then `router.refresh()` so the frame
 * re-renders in the new language with no reload and nothing typed lost.
 *
 * Labels are the languages' own names, untranslated on purpose. Someone who
 * landed in the wrong language has to be able to find their own in the list.
 */
import { useRouter } from "next/navigation";
import { useLingui } from "@lingui/react/macro";
import { Languages } from "lucide-react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { writeLocaleCookie } from "@/i18n/cookie";
import { LOCALES, normalizeLocale } from "@/i18n/locales";
import { hasAuthToken } from "@/lib/authFetch";
import { saveProfile } from "@/lib/userProfile";
import { cn } from "@/lib/utils";

/**
 * @param {object} props
 * @param {string} [props.value] The active locale; defaults to the catalogue's.
 * @param {boolean} [props.compact] Icon-only trigger for a header.
 * @param {string} [props.id] For a <label htmlFor>.
 * @param {string} [props.className]
 * @param {(locale: string) => void} [props.onChange] Fires after the switch.
 */
export default function LanguageMenu({ value, compact = false, id, className, onChange }) {
  const router = useRouter();
  const { i18n, t } = useLingui();
  const current = normalizeLocale(value) || normalizeLocale(i18n.locale) || "en";

  function change(next) {
    if (next === current) return;
    writeLocaleCookie(next);
    if (hasAuthToken()) saveProfile({ interface_language: next });
    onChange?.(next);
    router.refresh();
  }

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
