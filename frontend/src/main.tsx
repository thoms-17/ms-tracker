import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient } from "@tanstack/react-query";
import { createSyncStoragePersister } from "@tanstack/query-sync-storage-persister";
import { PersistQueryClientProvider } from "@tanstack/react-query-persist-client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { persister, CACHE_MAX_AGE } from "./persist";
import "./index.css";

/**
 * Le cache est persisté dans le navigateur : à l'ouverture, l'app affiche
 * immédiatement les données de la dernière session, puis les rafraîchit en
 * arrière-plan. Sans ça, l'écran reste vide le temps que le serveur réponde —
 * jusqu'à plusieurs secondes quand l'hébergement mutualisé sort de veille.
 */
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      // Doit couvrir `maxAge`, sinon les données restaurées seraient aussitôt
      // évacuées du cache mémoire au lieu d'être affichées.
      gcTime: CACHE_MAX_AGE,
    },
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <PersistQueryClientProvider
      client={queryClient}
      persistOptions={{
        persister,
        maxAge: CACHE_MAX_AGE,
        // Un changement de version invalide le cache : le format des réponses
        // peut avoir évolué entre deux déploiements.
        buster: __APP_VERSION__,
      }}
    >
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </PersistQueryClientProvider>
  </React.StrictMode>,
);
