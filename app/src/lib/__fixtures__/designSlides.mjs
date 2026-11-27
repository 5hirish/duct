// A design slide (kind "design": the agent's own HTML and CSS) beside a
// template slide, for the /preview scene. The colours are slide content the
// agent wrote, not app styling.

// The slide engine's head, cut to what a design slide relies on: the real one
// arrives with the post's slides_html (agents/content/styles.py BASE_CSS).
export const DESIGN_SLIDE_HEAD =
  '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=Playfair+Display:ital,wght@0,400;0,700;1,400&family=Space+Grotesk:wght@400..700&family=Bricolage+Grotesque:wght@400..800&family=Syne:wght@500..800&family=Archivo+Black&family=Anton&family=Bebas+Neue&family=Fraunces:ital,wght@0,400..900;1,400..900&family=DM+Serif+Display:ital@0;1&family=Instrument+Serif:ital@0;1&family=Caveat:wght@500..700&family=JetBrains+Mono:wght@400..700&display=swap" rel="stylesheet">' +
  "<style>:root{--safe-right:200px;--safe-bottom:310px;--safe-left:72px;--safe-top:72px}" +
  "*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}" +
  ".slide{width:1080px;height:1920px;position:relative;overflow:hidden;zoom:var(--zoom)}</style>";

export const DESIGN_SLIDES = [
  // A cover drawn with what the freedom allows: an SVG gradient and grain
  // referenced by id (scoped to the slide at render), a display font, a
  // sticker and a hand-drawn swash. Stored form: already cleaned.
  {
    slide_id: "slide-04",
    kind: "design",
    html: "<svg class=\"art\" viewbox=\"0 0 1080 1920\" preserveaspectratio=\"xMidYMid slice\"><defs><radialgradient id=\"sun\" cx=\"0.78\" cy=\"0.22\" r=\"0.75\"><stop offset=\"0\" stop-color=\"#ff9b6a\" /><stop offset=\"0.45\" stop-color=\"#e0643a\" /><stop offset=\"1\" stop-color=\"#7a2a14\" /></radialgradient><filter id=\"grain\"><feturbulence type=\"fractalNoise\" basefrequency=\"0.9\" numoctaves=\"2\" stitchtiles=\"stitch\" /><fecolormatrix type=\"saturate\" values=\"0\" /><fecomponenttransfer><fefunca type=\"linear\" slope=\"0.18\" /></fecomponenttransfer></filter></defs><rect width=\"1080\" height=\"1920\" fill=\"url(#sun)\" /><circle cx=\"860\" cy=\"420\" r=\"300\" fill=\"#ffd2b3\" opacity=\"0.35\" /><rect width=\"1080\" height=\"1920\" filter=\"url(#grain)\" /></svg><div class=\"copy\"><p class=\"tag\">Stylist survey · 2026</p><p class=\"num\">73<span>%</span></p><h2>of cuts that “didn’t work” were the <em>brief</em>, not the stylist</h2><svg class=\"swash\" viewbox=\"0 0 600 60\"><path d=\"M6 40 C 160 6, 380 6, 594 34\" fill=\"none\" stroke=\"#fff3e8\" stroke-width=\"10\" stroke-linecap=\"round\" /></svg><p class=\"next\">Swipe for the 3-line brief</p></div>",
    css: ":scope{background:#7a2a14;color:#fff3e8}.art{position:absolute;inset:0;width:100%;height:100%}.copy{position:absolute;left:var(--safe-left);right:var(--safe-right);top:var(--safe-top);bottom:var(--safe-bottom);display:flex;flex-direction:column;justify-content:flex-end;gap:28px}.tag{align-self:flex-start;font:700 30px 'Space Grotesk',sans-serif;letter-spacing:4px;text-transform:uppercase;background:#fff3e8;color:#7a2a14;padding:14px 26px;border-radius:999px;transform:rotate(-3deg)}.num{font:400 520px/0.82 'Anton',sans-serif;letter-spacing:-12px;margin-left:-14px;color:#fff3e8;text-shadow:0 18px 60px rgba(60,16,4,.45)}.num span{font-size:260px;vertical-align:top;letter-spacing:0}h2{font:500 76px/1.08 'Fraunces',serif;max-width:16ch}h2 em{font-style:italic;font-weight:800;color:#ffd2b3}.swash{width:420px;height:44px;margin-top:-8px}.next{font:600 44px 'Space Grotesk',sans-serif;opacity:.9}",
  },
  { slide_id: "slide-05", kind: "text", headline: "Blunt bob or\nface-framing layers?", caption_style: "body-neutral" },
  {
    slide_id: "slide-06",
    kind: "design",
    html:
      '<div class="card"><p class="kicker">Your stylist brief</p><h2>Ask for these three things</h2><ol>' +
      "<li><b>Length</b><span>Just past the chin, longest at the front</span></li>" +
      "<li><b>Layers</b><span>Start at the cheekbone, not the crown</span></li>" +
      "<li><b>Finish</b><span>Point-cut ends so it moves</span></li></ol>" +
      '<p class="save">Save this for your next appointment</p></div>',
    css:
      ":scope{background:#f6ede4}" +
      ".card{position:absolute;inset:var(--safe-top) var(--safe-right) var(--safe-bottom) var(--safe-left);display:flex;flex-direction:column;justify-content:center;gap:56px;font-family:Inter,sans-serif;color:#2b1d16}" +
      ".kicker{font-size:34px;letter-spacing:3px;text-transform:uppercase;color:#b4532a;font-weight:700}" +
      'h2{font-family:"Playfair Display",serif;font-size:96px;line-height:1.05}' +
      "ol{list-style:none;display:flex;flex-direction:column;gap:40px;counter-reset:n}" +
      "li{counter-increment:n;display:grid;grid-template-columns:96px 1fr;column-gap:28px;align-items:baseline}" +
      "li::before{content:counter(n);grid-row:span 2;width:96px;height:96px;border-radius:50%;background:#b4532a;color:#fff;font:800 52px Inter;display:grid;place-items:center}" +
      "li b{font-size:56px}li span{font-size:44px;line-height:1.3;color:#5a463b}" +
      ".save{font-size:40px;font-weight:600;color:#b4532a;border-top:3px solid #e8d5c4;padding-top:32px}",
  },
];


// The cover as an earlier version: a navy ground and no sunset, for the
// viewport's version history.
export const EARLIER_COVER = {
  ...DESIGN_SLIDES[0],
  css: DESIGN_SLIDES[0].css.replace(":scope{background:#7a2a14", ":scope{background:#1f3a5f"),
  html: DESIGN_SLIDES[0].html.replace('<rect width="1080" height="1920" fill="url(#sun)" />', ""),
};
