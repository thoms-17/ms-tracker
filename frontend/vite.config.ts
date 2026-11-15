import { execSync } from "node:child_process";
import { resolve } from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

// --- Identité de la version, figée au moment du build -------------------------
// Le numéro lisible est le dernier tag git `vX.Y.Z` (même source que le back : publier
// une version, c'est poser un tag) ; le SHA et la date disent la vérité sur ce qui
// est réellement déployé.
const root = resolve(__dirname, "..");
const git = (args: string): string | null => {
  try {
    return execSync(`git ${args}`, { cwd: root, stdio: ["ignore", "pipe", "ignore"] }).toString().trim() || null;
  } catch {
    return null; // build hors dépôt git, ou aucun tag (clone superficiel de la CI)
  }
};
const version = git('describe --tags --abbrev=0 --match "v[0-9]*"')?.replace(/^v/, "") ?? "dev";
const gitSha = git("rev-parse --short HEAD") ?? "inconnu";

// Le proxy renvoie /api vers le back FastAPI en dev → même origine, pas de CORS.
export default defineConfig({
  define: {
    __APP_VERSION__: JSON.stringify(version),
    __GIT_SHA__: JSON.stringify(gitSha),
    __BUILD_DATE__: JSON.stringify(new Date().toISOString()),
  },
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      // Icônes/manifest servis depuis public/ ; SW généré au build.
      includeAssets: ["favicon.ico", "apple-touch-icon.png"],
      manifest: {
        name: "MS Tracker",
        short_name: "MS Tracker",
        description: "Suivi de visionnage séries & films",
        lang: "fr",
        start_url: "/",
        display: "standalone",
        background_color: "#0d0d0d",
        theme_color: "#0d0d0d",
        icons: [
          { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
          {
            src: "/maskable-512.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "maskable",
          },
        ],
      },
      // En dev, permet de tester l'installation via `vite` sans build.
      devOptions: { enabled: true },
    }),
  ],
  server: {
    // pas de `host` : Vite n'écoute que sur localhost, invisible du réseau local
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
