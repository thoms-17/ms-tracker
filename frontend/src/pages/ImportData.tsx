import { useState, type ChangeEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../api";

/** Module d'import d'un export TV Time — affiché sur l'accueil quand le compte est vide. */
export default function ImportData() {
  const qc = useQueryClient();
  const [series, setSeries] = useState<File | null>(null);
  const [movies, setMovies] = useState<File | null>(null);

  const importMut = useMutation({
    mutationFn: () => api.importTvtime({ series: series ?? undefined, movies: movies ?? undefined }),
    onSuccess: () => {
      ["series", "movies", "watchTime", "upcoming"].forEach((k) =>
        qc.invalidateQueries({ queryKey: [k] }),
      );
    },
  });

  const pick = (set: (f: File | null) => void) => (e: ChangeEvent<HTMLInputElement>) =>
    set(e.target.files?.[0] ?? null);

  const errorMsg = importMut.error instanceof ApiError ? importMut.error.message
    : importMut.error ? "Import impossible. Réessaie." : null;

  return (
    <div className="import-card">
      <h2 className="import-title">Bienvenue sur MS Tracker</h2>
      <p className="import-sub">
        Ton suivi est vide. Importe ton export TV Time pour retrouver tout ton historique
        (séries, films, visionnages).
      </p>

      <details className="import-help">
        <summary>Où récupérer mes fichiers TV Time&nbsp;?</summary>
        <p className="muted">
          Dans l'appli TV Time : demande l'export de tes données. Tu reçois deux fichiers JSON,
          <code>tvtime-series-….json</code> et <code>tvtime-movies-….json</code>. Sélectionne-les ci-dessous
          (tu peux n'en fournir qu'un seul).
        </p>
      </details>

      <label className="import-field">
        <span>Séries <em>(tvtime-series-….json)</em></span>
        <input type="file" accept=".json,application/json" onChange={pick(setSeries)} />
      </label>
      <label className="import-field">
        <span>Films <em>(tvtime-movies-….json)</em></span>
        <input type="file" accept=".json,application/json" onChange={pick(setMovies)} />
      </label>

      {errorMsg && <p className="login-error">{errorMsg}</p>}
      {importMut.isSuccess && (
        <p className="import-ok">
          Import terminé : {importMut.data.series} séries, {importMut.data.movies} films,
          {" "}{importMut.data.watches} visionnages.
        </p>
      )}

      <button
        className="btn primary import-submit"
        disabled={importMut.isPending || (!series && !movies)}
        onClick={() => importMut.mutate()}
      >
        {importMut.isPending ? "Import en cours…" : "Importer mes données"}
      </button>
    </div>
  );
}
