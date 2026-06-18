"use client";

import { useState } from "react";
import { Check } from "lucide-react";
import { PlatformGlyph, platformMeta } from "./platformGlyphs";

// Resolve a real profile picture from the handle (best-effort, falls back to a
// monogram on error). PostBridge itself doesn't return avatars.
export function avatarUrl(platform, username) {
  if (!username) return "";
  return `https://unavatar.io/${platform}/${encodeURIComponent(username)}?fallback=false`;
}

// Per-size class sets — keeps the avatar legible from the dropdown trigger (sm)
// up to the Accounts tab cards (md).
const SIZES = {
  xs: { box: "size-6",  badge: "size-3.5", glyph: "size-2",   check: "size-3",   initial: "text-[10px]" },
  sm: { box: "size-8",  badge: "size-4",   glyph: "size-2.5", check: "size-3.5", initial: "text-xs" },
  md: { box: "size-11", badge: "size-5",   glyph: "size-3",   check: "size-4",   initial: "text-sm" },
};

/**
 * Round profile avatar for a social account, badged with the platform's brand
 * glyph. Falls back to a monogram when the handle has no resolvable picture.
 *
 * @param account { platform, username }
 * @param linked  show the small "linked" check (Accounts tab)
 * @param size    "xs" | "sm" | "md"
 */
export function AccountAvatar({ account, linked = false, size = "md" }) {
  const s = SIZES[size] || SIZES.md;
  const meta = platformMeta(account.platform);
  const [imgFailed, setImgFailed] = useState(false);
  const src = imgFailed ? "" : avatarUrl(account.platform, account.username);
  const initial = (account.username || "?").charAt(0).toUpperCase();

  return (
    <div className="relative shrink-0">
      <div className={`flex ${s.box} items-center justify-center overflow-hidden rounded-full border border-border/60 bg-muted`}>
        {src ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={src}
            alt=""
            className="size-full object-cover"
            referrerPolicy="no-referrer"
            onError={() => setImgFailed(true)}
          />
        ) : (
          <span className={`${s.initial} font-semibold text-muted-foreground`}>{initial}</span>
        )}
      </div>
      {/* Platform badge — brand-colored chip with a white glyph (legible on both themes) */}
      <span
        className={`absolute -bottom-0.5 -right-0.5 flex ${s.badge} items-center justify-center rounded-full border-2 border-card text-white`}
        title={meta.label}
        style={{ backgroundColor: meta.color }}
      >
        <PlatformGlyph platform={account.platform} className={s.glyph} />
      </span>
      {linked && (
        <span className={`absolute -left-0.5 -top-0.5 flex ${s.check} items-center justify-center rounded-full bg-primary text-primary-foreground`}>
          <Check className="size-2.5" />
        </span>
      )}
    </div>
  );
}
