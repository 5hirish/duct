# Motion

Remotion compositions for the landing page: the 30-second launch film, and
later the short loops the feature tiles play. Everything here is React that
renders one frame per call; nothing here runs in the browser on the site.

```
design/
  storyboard/     the nine Claude Design boards the film is cut from
  motion/         the Remotion package (this file)
  motion/src/Film.jsx    the beats, the camera, the clock, the ground
  motion/src/scenes/     one component per beat
  motion/src/ui/         the app's surfaces redrawn for the stage
  motion/src/story.js    every number, bound to the story fixture
  motion/src/lib/        motion vocabulary and resolved tokens
  motion/public/         gitignored; sync-assets copies the marks and covers in
  motion/out/            gitignored renders
```

## Running it

```bash
npm install                 # own node_modules, separate from app/
npm run studio              # Remotion Studio on http://localhost:3000
npm run render:film         # out/demo.mp4, out/demo.webm, out/demo-poster.webp
npm run publish:media       # copy them into site/assets/media, within budget
```

The first render downloads Remotion's headless Chrome shell into
`node_modules/.remotion`. The poster is a PNG still turned into WebP by
`ffmpeg` (Remotion stills are PNG or JPEG only), so `ffmpeg` must be on the
path; Homebrew's build has libwebp. Headless Chrome cannot launch inside the agent
sandbox; render from a normal shell.

## Rules of the stage

- **Numbers come from the fixture.** `src/story.js` imports
  `app/src/lib/__fixtures__/solo-story.mjs`, the same story the README
  screenshots and `/preview` scenes use, so the three cannot drift.
- **Tokens come from the app.** `src/index.css` imports the app's
  `tokens.css`; `src/lib/tokens.js` lists the resolved values for the places
  that need a number (SVG, gradients). Change a colour in the app and the
  film follows on the next render.
- **The ground is the README frame.** Same gradient and lift as
  `scripts/shots/shoot.mjs`, so the video sits beside the screenshots as one
  family. A grain layer stops H.264 banding it.
- **Every move is a function of the frame.** No CSS transitions, no
  `animate-*` classes; springs and `interpolate` only, per the
  `remotion-best-practices` skill.
- **The storyboard is the spec.** `../storyboard/canvas.json` carries the timing
  and the motion notes per beat; when the film and the boards disagree, fix
  whichever is wrong and keep them agreeing.

## Sound

`src/Sound.jsx` holds one music bed and a UI sound per beat, with times on the
film's own clock; re-time a beat in `Film.jsx` and move its cue with it. The
film prop `sound` (default on) drops the whole layer for a silent render. The
landing page plays the file muted regardless (browsers block autoplay with
sound); the sound is for the social and YouTube cuts.

- `audio/sfx/*.wav` are the remotion.media set (usable without attribution,
  peaks normalised to −3 dB).
- `audio/music/music.mp3` is the first 31 s of **"Deliberate Thought" by Kevin
  MacLeod (incompetech.com)**, licensed under Creative Commons: By Attribution
  4.0, https://creativecommons.org/licenses/by/4.0/. Any page or post that
  publishes a render with sound carries that credit.

## Licence

Remotion is free for individuals and companies of up to three people. Check
that still holds before a render that ships.
