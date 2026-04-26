export default function manifest() {
  return {
    name: "Duct App",
    short_name: "Duct",
    description:
      "Duct synthesizes data across product, marketing, and sales tools into weekly intelligence briefs.",
    start_url: "/insights",
    scope: "/",
    display: "standalone",
    background_color: "#ffffff",
    theme_color: "#0d0f1a",
    orientation: "portrait",
    icons: [
      {
        src: "/icon.svg",
        sizes: "any",
        type: "image/svg+xml",
        purpose: "any maskable",
      },
      {
        src: "/apple-icon.svg",
        sizes: "180x180",
        type: "image/svg+xml",
        purpose: "any",
      },
    ],
  };
}
