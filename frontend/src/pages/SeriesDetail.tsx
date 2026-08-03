import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, posterUrl } from "../api";
import Confetti from "../components/Confetti";
import Spinner from "../components/Spinner";
import { useCloseOnScroll } from "../hooks";
import WatchControl from "../components/WatchControl";
import WatchProviders from "../components/WatchProviders";
import type { EpisodeItem, SeasonGroup } from "../types";

export default function SeriesDetail() {
  const { uuid = "" } = useParams();
  const qc = useQueryClient();
  const detail = useQuery({ queryKey: ["series", uuid], queryFn: () => api.seriesDetail(uuid) });

  // Confettis quand la série vient d'être terminée (transition non-terminée → terminée).
  const [confetti, setConfetti] = useState(false);
  const wasComplete = useRef<boolean | null>(null);
  const d = detail.data;
  const isComplete = !!d && d.n_episodes > 0 && d.n_watched >= d.n_episodes;
  useEffect(() => {
    if (!d) return; // on n'arme le suivi qu'une fois les données chargées
    const was = wasComplete.current;
    wasComplete.current = isComplete;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (was === false && isComplete && !reduced) {
      setConfetti(true);
      const t = setTimeout(() => setConfetti(false), 4000);
      return () => clearTimeout(t);
    }
  }, [isComplete, d]);

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["series", uuid] });
    qc.invalidateQueries({ queryKey: ["series"] });
    qc.invalidateQueries({ queryKey: ["watchTime"] });
  };

  if (detail.isLoading) return <Spinner />;
  if (detail.error || !detail.data) return <p className="muted">Série introuvable.</p>;
  const s = detail.data;
  const url = posterUrl(s.poster_path, true);
  const nextSeason = s.seasons.find((se) => se.season_number !== 0 && se.watched < se.total)?.season_number;

  return (
    <>
      {confetti && <Confetti />}
      <Link to="/" className="muted">← Suivi</Link>
      <div className="detail-head">
        {url ? <img className="detail-poster" src={url} alt={s.title} /> : null}
        <div className="detail-meta">
          <h2>{s.title}</h2>
          <div className="bar" style={{ maxWidth: 320 }}>
            <span style={{ width: `${Math.min(s.completion * 100, 100)}%` }} />
          </div>
          <p className="muted">
            {s.n_watched}/{s.n_episodes} épisodes réguliers ({Math.round(s.completion * 100)} %)
          </p>
          {s.tmdb_id && <WatchProviders media="tv" tmdbId={s.tmdb_id} />}
        </div>
      </div>

      {s.seasons.map((se) => (
        <Season key={se.season_number} uuid={uuid} se={se} open={se.season_number === nextSeason} onChange={refresh} />
      ))}
    </>
  );
}

function Season({ uuid, se, open, onChange }: {
  uuid: string; se: SeasonGroup; open: boolean; onChange: () => void;
}) {
  const s = se.season_number;
  const markWatched = useMutation({ mutationFn: () => api.markSeason(uuid, s, true), onSuccess: onChange });
  const markUnwatched = useMutation({ mutationFn: () => api.markSeason(uuid, s, false), onSuccess: onChange });
  const rewatch = useMutation({ mutationFn: () => api.rewatchSeason(uuid, s), onSuccess: onChange });
  const removeOne = useMutation({ mutationFn: () => api.removeSeasonWatch(uuid, s), onSuccess: onChange });
  const done = se.watched === se.total;
  // Nombre de visionnages complets de la saison = min des compteurs de ses épisodes.
  const passes = se.episodes.length ? Math.min(...se.episodes.map((e) => e.watched_count)) : 0;
  return (
    <details className="season" open={open}>
      <summary>
        <span>{se.label} · {se.watched}/{se.total} vus{done ? " · complète" : ""}</span>
        <span className="season-actions" onClick={(e) => e.preventDefault()}>
          <WatchControl
            count={passes}
            kind="season"
            onComplete={() => markWatched.mutate()}
            onRewatch={() => rewatch.mutate()}
            onRemoveOne={() => removeOne.mutate()}
            onRemoveAll={() => markUnwatched.mutate()}
          />
        </span>
      </summary>
      {se.episodes.map((e) => {
        // Épisodes plus anciens de la saison encore non vus (façon TV Time : rattrapage).
        const prevUnwatched = se.episodes.filter(
          (x) => x.episode_number < e.episode_number && x.watched_count === 0,
        ).length;
        return <Episode key={e.episode_id} e={e} prevUnwatched={prevUnwatched} onChange={onChange} />;
      })}
    </details>
  );
}

function Episode({ e, prevUnwatched, onChange }: {
  e: EpisodeItem; prevUnwatched: number; onChange: () => void;
}) {
  const add = useMutation({ mutationFn: () => api.watchEpisode(e.episode_id), onSuccess: onChange });
  const catchUp = useMutation({ mutationFn: () => api.catchUpEpisode(e.episode_id), onSuccess: onChange });
  const removeOne = useMutation({ mutationFn: () => api.removeEpisodeWatch(e.episode_id), onSuccess: onChange });
  const removeAll = useMutation({ mutationFn: () => api.unwatchEpisode(e.episode_id), onSuccess: onChange });
  const [ask, setAsk] = useState(false); // propose de rattraper les précédents
  const num = `S${String(e.season_number).padStart(2, "0")}E${String(e.episode_number).padStart(2, "0")}`;

  const onComplete = () => {
    if (prevUnwatched > 0) setAsk(true); // des épisodes avant celui-ci ne sont pas vus
    else add.mutate();
  };

  return (
    <div className={`ep${e.watched_count > 0 ? " seen" : ""}`}>
      <span className="num">{num}</span>
      <span className="ep-name">{e.name}</span>
      <WatchControl
        count={e.watched_count}
        kind="episode"
        onComplete={onComplete}
        onRewatch={() => add.mutate()}
        onRemoveOne={() => removeOne.mutate()}
        onRemoveAll={() => removeAll.mutate()}
      />
      {ask && (
        <Modal onClose={() => setAsk(false)}>
          <h3 className="modal-title">Rattraper les épisodes précédents ?</h3>
          <p className="muted">
            {prevUnwatched} épisode{prevUnwatched > 1 ? "s" : ""} avant {num} {prevUnwatched > 1 ? "ne sont pas vus" : "n'est pas vu"}.
            Veux-tu {prevUnwatched > 1 ? "les" : "l'"} marquer comme vu{prevUnwatched > 1 ? "s" : ""} aussi ?
          </p>
          <div className="modal-actions">
            <button className="btn" onClick={() => { add.mutate(); setAsk(false); }}>
              Seulement {num}
            </button>
            <button className="btn primary" onClick={() => { catchUp.mutate(); setAsk(false); }}>
              Marquer les {prevUnwatched + 1} épisodes
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}

/** Boîte de dialogue centrée, rendue dans un portail sur <body>. */
function Modal({ onClose, children }: { onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    const onKey = (ev: KeyboardEvent) => ev.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  useCloseOnScroll(onClose);

  return createPortal(
    <div className="modal-layer" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" onClick={(ev) => ev.stopPropagation()}>
        {children}
      </div>
    </div>,
    document.body,
  );
}

