import "./index.css";
import { Composition } from "remotion";
import { loadFont as loadDmSans } from "@remotion/google-fonts/DMSans";
import { loadFont as loadMono } from "@remotion/google-fonts/JetBrainsMono";
import { DURATION, FPS, Film, HEIGHT, WIDTH } from "./Film.jsx";

// The same two faces the app loads through next/font; the film points the
// app's tokens at them (index.css) so a class from app/src reads the same.
loadDmSans("normal", { weights: ["400", "500", "600", "700"], subsets: ["latin"] });
loadMono("normal", { weights: ["500"], subsets: ["latin"] });

export const RemotionRoot = () => (
  <Composition id="Film" component={Film} durationInFrames={DURATION} fps={FPS} width={WIDTH} height={HEIGHT} defaultProps={{ sound: true }} />
);
