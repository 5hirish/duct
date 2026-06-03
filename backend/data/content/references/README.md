# Global content reference library

Curated reference images bundled with the backend repo. Shipped via the
docker image; **NOT** stored in the Railway Volume / storage bucket.

This trades a small docker image size bump (~25 MB for ~50 images) for
zero runtime network cost on the hot path. The Gemini image-generation
agent picks references from here, passes them as `input_asset_ids`
alongside per-project character references, and Gemini renders new
images that imitate real high-performing TikTok aesthetic + framing.

Per-project user-uploaded references live on the Railway Volume under
`/app/uploads/projects/{project_id}/references/`; only globals live
here.

## Layout

Three axes, each axis has a fixed set of subtypes. One image = one
choice along one axis. Filename is `{slug}.{ext}` where `slug` is a
short, slugged identifier (e.g. `bathroom-vanity-iphone.jpeg`).

```
data/content/references/
├── layouts/
│   ├── collage/         4-grid educational format (2×2 with serif label)
│   ├── full-bleed/      single photo + text overlay (the duct default)
│   ├── before-after/    do/don't split — 2 separate images, ❌/✅ in HTML
│   ├── editorial/       styled shoot, ivory bg, product lineup
│   └── text-only/       dark bg, numbered list — used sparingly
│
├── camera/
│   ├── closeup/         face fills frame, intimate address — sadness peak
│   ├── selfie-talking/  phone-held arm's length, direct eye contact — default
│   └── lifestyle/       full body in environment, not a selfie
│
└── captions/
    ├── bold-sans/       thick white text, top or bottom anchored
    ├── pill-bubble/     white rounded box, black text — info-heavy
    ├── serif-italic/    italic label, center-positioned — collage label
    └── minimal-whisper/ almost no text — highest engagement pattern
```

## How the agent picks (planned — Pattern 7 follow-up)

1. `fetch_reference_library(axis?, subtype?)` reader @tool enumerates
   globals from disk + per-project rows from `content_assets`. Returns
   `{asset_id, axis, subtype, url, source}` so the orchestrator can
   pick by vibe match for this post's emotional trigger.
2. `generate_image` already accepts `input_asset_ids: list[UUID]`
   (max 3). Pattern for slides 2-5:
   ```
   input_asset_ids: [slide_01_asset_id, camera_ref_asset_id]
   ```
   — first locks character identity, second locks TikTok framing.

## URLs

Served at `/static/references/{axis}/{subtype}/{filename}` by FastAPI
StaticFiles in `server.py` when this directory exists. Resolution is
read-only; no admin upload route (globals are version-controlled via
git, not user-uploaded).

## Adding a new reference

```bash
# 1. Drop a high-performing TikTok screenshot into the matching subtype
cp ~/Desktop/IMG_5885.jpeg backend/data/content/references/camera/selfie-talking/

# 2. Commit
git add backend/data/content/references/camera/selfie-talking/IMG_5885.jpeg
git commit -m "content(refs): add selfie-talking IMG_5885 reference"

# 3. Ships on next deploy. No DB write needed; the enumeration helper
#    picks it up automatically.
```

## What NOT to put here

- Per-project / per-customer images — those go to the Railway Volume
  under `/app/uploads/projects/{project_id}/references/`.
- Generated outputs — those go to `/app/uploads/projects/{id}/generated/`.
- Anything > 2 MB. Resize down before committing; we're shipping these
  in the docker image.
- Anything with identifying personal information or brand logos —
  these references are reusable across all projects.
