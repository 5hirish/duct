import { Audio } from "@remotion/media";
import { Sequence, interpolate, staticFile } from "remotion";

// The film's sound: one music bed and a UI sound on each beat the motion
// already makes. Times are seconds on the film's own clock (Film.jsx BEATS),
// so a re-timed beat moves its sound with it when these are updated together.
// Sound effects are the remotion.media set (usable without attribution, peak
// normalised to -3 dB); the music bed is credited in the README.

const GAIN = 0.55; // every effect sits under the music, never on top of it

export const CUES = [
  // 0 · the question lands
  { at: 0.25, sfx: "whip", gain: 0.35 },
  // 1 · five tabs fan out, one whoosh each, on the same stagger as the springs
  ...[0, 1, 2, 3, 4].map((i) => ({ at: 3.05 + i * 0.2, sfx: "whoosh", gain: 0.5 })),
  // 2 · tabs collapse into the sidebar, then land
  { at: 6.62, sfx: "whip", gain: 0.6 },
  { at: 7.5, sfx: "switch", gain: 0.5 },
  // 3 · the latency pill, the chips, the two findings
  { at: 10.8, sfx: "switch", gain: 0.35 },
  { at: 11.3, sfx: "page-turn", gain: 0.35 },
  { at: 12.05, sfx: "whip", gain: 0.4 },
  { at: 12.25, sfx: "whip", gain: 0.3 },
  // 4 · the change card opens, the click on Apply, the applied chime
  { at: 13.8, sfx: "page-turn", gain: 0.5 },
  { at: 16.43, sfx: "mouse-click", gain: 0.8 },
  { at: 16.65, sfx: "ding", gain: 0.45 },
  // 5 · the memory stamps down
  { at: 19.25, sfx: "shutter-modern", gain: 0.55 },
  // 6 · the reply, the attachment, the reaction
  { at: 21.7, sfx: "whip", gain: 0.4 },
  { at: 22.5, sfx: "page-turn", gain: 0.4 },
  { at: 23.4, sfx: "switch", gain: 0.45 },
  // 7 · two cards flip up
  { at: 25.27, sfx: "whoosh", gain: 0.5 },
  { at: 25.37, sfx: "whoosh", gain: 0.5 },
  // 8 · the cut to navy, and the one thing to remember
  { at: 27.0, sfx: "whip", gain: 0.5 },
  { at: 27.85, sfx: "ding", gain: 0.5 },
];

export const MUSIC = { file: "music.mp3", gain: 0.22, fadeIn: 1.2, fadeOut: 2.0 };

export const Sound = ({ fps, durationInFrames }) => (
  <>
    <Audio
      src={staticFile(MUSIC.file)}
      volume={(f) =>
        MUSIC.gain *
        interpolate(f, [0, MUSIC.fadeIn * fps, durationInFrames - MUSIC.fadeOut * fps, durationInFrames - 1], [0, 1, 1, 0], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        })
      }
    />
    {CUES.map((cue, i) => (
      <Sequence key={`${cue.sfx}-${i}`} from={Math.round(cue.at * fps)} name={`sfx ${cue.sfx}`}>
        <Audio src={staticFile(`sfx/${cue.sfx}.wav`)} volume={GAIN * cue.gain} />
      </Sequence>
    ))}
  </>
);
