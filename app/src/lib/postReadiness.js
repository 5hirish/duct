// Where a slideshow stands: which slides still need a picture, whether the
// agent is waiting on the person's word about one, and whether the post is
// ready to publish. Read off the slides alone, so it holds after a reload.
//
// Before this, the slide strip offered "Looks good" on every slide at every
// moment, and pressing it with nothing left to make sent the agent looking
// for a next slide; and a post with every picture done showed no sign it was
// ready, nor a way to publish from where it was made (2026-11-27).

// A picture is owed where a prompt asks for one and there is none, or the
// picture there was made from an older prompt.
function owes(target) {
  const prompt = (target?.image_prompt || "").trim();
  if (!prompt) return false;
  if (!target.image_url) return true;
  return prompt !== (target.image_prompt_used || "").trim();
}

function targets(slide) {
  if (!slide || slide.kind === "text" || slide.kind === "design") return [];
  return Array.isArray(slide.items) && slide.items.length ? slide.items : [slide];
}

export function needsPicture(slide) {
  return targets(slide).some(owes);
}

export function hasPicture(slide) {
  const own = targets(slide);
  return own.length > 0 && own.every((t) => Boolean(t?.image_url));
}

/** Indices of the slides still owed a picture, in order. */
export function pendingSlides(slides = []) {
  return slides.reduce((out, s, i) => (needsPicture(s) ? [...out, i] : out), []);
}

/** Every slide has what it needs; nothing stands between the post and Publish. */
export function readyToPublish(slides = []) {
  return slides.length > 0 && pendingSlides(slides).length === 0;
}

/**
 * The slide the agent is waiting to hear about, as the index of the next
 * slide it would make, or -1. The image loop makes one picture, then stops
 * for the person's word: that is the slide just made, when the agent is idle
 * and the next slide owed a picture comes after it with nothing to make in
 * between.
 */
export function nextAfterApproval(slides = [], index = 0, idle = false) {
  if (!idle || !hasPicture(slides[index]) || needsPicture(slides[index])) return -1;
  const next = pendingSlides(slides).find((i) => i > index);
  if (next === undefined) return -1;
  for (let i = index + 1; i < next; i += 1) if (targets(slides[i]).length) return -1;
  return next;
}
