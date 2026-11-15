import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, posterUrl } from "../api";
import { useKeyboardInset } from "../hooks";
import type { SearchItem } from "../types";

/**
 * Champ de recherche TMDB et sa liste de résultats.
 *  · par défaut : dans le header (ordinateur ; masqué sur mobile) ;
 *  · `dock` : ancré en bas de l'écran, juste au-dessus de la barre de navigation
 *    (mobile, onglet « Découvrir ») — à portée de pouce, résultats déroulés vers le haut.
 */
export default function SearchBar({ dock = false }: { dock?: boolean }) {
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const [open, setOpen] = useState(false); // liste de résultats déroulée
  const boxRef = useRef<HTMLDivElement>(null);
  const nav = useNavigate();
  // Clavier virtuel ouvert : le champ ancré remonte juste au-dessus de lui.
  const keyboard = useKeyboardInset(dock);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(q.trim()), 250);
    return () => clearTimeout(t);
  }, [q]);

  // Ferme la liste sur clic extérieur ou touche Échap.
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (!boxRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, []);

  const results = useQuery({
    queryKey: ["search", debounced],
    queryFn: () => api.search(debounced),
    enabled: debounced.length >= 2,
  });

  const pick = (r: SearchItem) => {
    setQ("");
    setOpen(false);
    if (r.media_type === "tv") nav(r.tracked_uuid ? `/series/${r.tracked_uuid}` : `/tmdb/tv/${r.tmdb_id}`);
    else nav(`/tmdb/movie/${r.tmdb_id}`);
  };

  const box = (
    <div
      className={dock ? `search-dock${keyboard > 0 ? " keyboard" : ""}` : "searchbox"}
      style={dock && keyboard > 0 ? { bottom: keyboard + 8 } : undefined}
      ref={boxRef}
    >
      <div className="search-panel">
        <input
          enterKeyHint="search"
          placeholder="Rechercher une série ou un film…"
          value={q}
          onChange={(e) => { setQ(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
        />
        {open && debounced.length >= 2 && (
          <div className="results">
            {results.isLoading && <div className="res muted">…</div>}
            {results.data?.length === 0 && <div className="res muted">Aucun résultat</div>}
            {results.data?.map((r) => {
              const url = posterUrl(r.poster_path);
              return (
                <div className="res" key={`${r.media_type}-${r.tmdb_id}`} onClick={() => pick(r)}>
                  {url ? <img src={url} alt="" /> : <span className="thumb ph" />}
                  <span className="res-title">{r.title} <span className="muted">({r.year ?? "?"})</span></span>
                  {r.tracked_uuid && <span className="tag">déjà suivie</span>}
                  {r.watched_count ? <span className="tag">déjà vu ×{r.watched_count}</span> : null}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
  // Ancré : porté sur <body>, pour qu'aucun parent ne fausse son positionnement fixe.
  return dock ? createPortal(box, document.body) : box;
}
