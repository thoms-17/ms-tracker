import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

// Le proxy renvoie /api vers le back FastAPI en dev → même origine, pas de CORS.
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      // Icônes/manifest servis depuis public/ ; SW généré au build.
      includeAssets: ["favicon.ico", "apple-touch-icon.png"],
      manifest: {
        name: "TV Time",
        short_name: "TV Time",
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
    host: true, // écoute sur le réseau local → accessible depuis ton téléphone
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
