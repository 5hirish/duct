import { Config } from "@remotion/cli/config";
import { enableTailwind } from "@remotion/tailwind-v4";

// Tailwind v4 is what the app uses, and the token sheet the film imports is
// written against it; enabling it here is what lets the film share classes
// with app/src instead of restating every colour.
Config.overrideBundlerConfig((current) => enableTailwind(current));
Config.setOverwriteOutput(true);
