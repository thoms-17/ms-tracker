import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { api, posterUrl } from "../api";
import type { SearchItem } from "../types";

/**
 * Recherche partagée header/mobile.
 *  · desktop : champ inline dans le header
 *  · mobile  : champ masqué ; l'overlay est ouvert via la loupe de la barre du bas
 *              (état `expanded` piloté par le parent).
 */
export default function SearchBar({ expanded, setExpanded }: {
  expanded: boolean;
  setExpanded: (v: boolean) => void;
}) {
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const [open, setOpen] = useState(false); // liste de résultats déroulée
  const boxRef = useRef<HTMLDivElement>(null);
  const overlayRef = useRef<HTMLDivElement>(null);
  const nav = useNavigate();

  useEffect(() => {
    const t = setTimeout(() => setDebounced(q.trim()), 250);
    return () => clearTimeout(t);
  }, [q]);

  // Ferme la liste (et le panneau mobile) sur clic extérieur ou touche Échap.
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      // L'overlay mobile est porté hors de boxRef : ne pas fermer si le clic est dedans.
      if (boxRef.current?.contains(t) || overlayRef.current?.contains(t)) return;
      setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
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

  const close = () => {
    setOpen(false);
    setExpanded(false);
  };

  const pick = (r: SearchItem) => {
    setQ("");
    close();
    if (r.media_type === "tv") nav(r.tracked_uuid ? `/series/${r.tracked_uuid}` : `/tmdb/tv/${r.tmdb_id}`);
    else nav(`/tmdb/movie/${r.tmdb_id}`);
  };

  const field = (autoFocus: boolean) => (
    <SearchField
      q={q} setQ={setQ} open={open} setOpen={setOpen}
      debounced={debounced} results={results} pick={pick} autoFocus={autoFocus}
    />
  );

  return (
    <div className="searchbox" ref={boxRef}>
      {/* Desktop : champ inline dans le header (masqué en mobile via CSS) */}
      <div className="search-panel">{field(false)}</div>

      {/* Mobile : panneau plein écran au-dessus de tout, via portail sur <body> */}
      {expanded && createPortal(
        <div className="search-overlay" ref={overlayRef}>
          <div className="search-scrim" onClick={close} />
          <div className="search-panel expanded">{field(true)}</div>
        </div>,
        document.body,
      )}
    </div>
  );
}

/** Champ de saisie + liste de résultats. Partagé par la vue desktop et l'overlay mobile. */
function SearchField({ q, setQ, open, setOpen, debounced, results, pick, autoFocus }: {
  q: string;
  setQ: (v: string) => void;
  open: boolean;
  setOpen: (v: boolean) => void;
  debounced: string;
  results: UseQueryResult<SearchItem[]>;
  pick: (r: SearchItem) => void;
  autoFocus: boolean;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  // L'overlay mobile monte ce champ à l'ouverture : on lui donne le focus.
  useEffect(() => { if (autoFocus) inputRef.current?.focus(); }, [autoFocus]);

  return (
    <>
      <input
        ref={inputRef}
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
    </>
  );
}
