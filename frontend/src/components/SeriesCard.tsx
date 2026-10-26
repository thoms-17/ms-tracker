import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, posterUrl } from "../api";
import { refreshAfterWatch } from "../refresh";
import type { SeriesSummary } from "../types";
import Modal from "./Modal";

/**
 * Carte d'une série dans « En cours » : affiche, progression, badges (nouvel
 * épisode, revisionnage) et bouton « Voir » vers l'épisode suivant.
 */
export default function SeriesCard({ s, showNext, onComplete }: {
  s: SeriesSummary; showNext?: boolean; onComplete?: () => void;
}) {
  const qc = useQueryClient();
  const url = posterUrl(s.poster_path);
  // Dans « En cours », un revisionnage affiche la progression de CE passage.
  const rw = showNext ? s.rewatch : null;
  const [vus, total] = rw ? [rw.watched, rw.total] : [s.n_watched, s.n_episodes];
  const next = useMutation({
    // revisionnage : +1 visionnage sur le prochain épisode du passage (déjà vu, donc
    // pas « le prochain non vu » que choisit markNext)
    mutationFn: () => (rw && s.next_episode ? api.watchEpisode(s.next_episode.episode_id) : api.markNext(s.uuid)),
    onSuccess: () => {
      refreshAfterWatch(qc);
      // Ce visionnage était-il le dernier (de la série ou du passage) ? → confettis.
      if (total > 0 && vus + 1 >= total) onComplete?.();
    },
  });
  const [askDismiss, setAskDismiss] = useState(false);
  const dismiss = useMutation({
    mutationFn: () => api.dismissRewatch(s.uuid),
    onSuccess: () => refreshAfterWatch(qc),
  });
  return (
    <div className="card">
      <div className="poster-wrap">
        <Link to={`/series/${s.uuid}`}>
          {url ? <img className="poster" src={url} alt={s.title} /> : <div className="poster" />}
          {showNext && s.new_episode && <span className="new-badge">Nouvel épisode</span>}
          {rw && <span className="new-badge rewatch-badge">Revisionnage · {rw.pass_number}e</span>}
        </Link>
        {rw && (
          <button type="button" className="dismiss-btn" aria-label="Retirer d'En cours"
            title="Retirer d'En cours" onClick={() => setAskDismiss(true)}>
            ×
          </button>
        )}
      </div>
      {askDismiss && rw && (
        <Modal onClose={() => setAskDismiss(false)}>
          <h3 className="modal-title">Retirer {s.title} d'« En cours » ?</h3>
          <p className="muted">
            La série disparaît d'ici jusqu'à ce que tu revoies un épisode.
            Tes visionnages restent enregistrés et la série reste dans « Vus ».
          </p>
          <div className="modal-actions">
            <button className="btn" onClick={() => setAskDismiss(false)}>Annuler</button>
            <button className="btn primary" disabled={dismiss.isPending}
              onClick={() => { dismiss.mutate(); setAskDismiss(false); }}>
              Retirer
            </button>
          </div>
        </Modal>
      )}
      <div className="bar"><span style={{ width: `${total > 0 ? Math.min((vus / total) * 100, 100) : 0}%` }} /></div>
      <span className="sub">{vus}/{total}</span>
      <Link to={`/series/${s.uuid}`} className="title">{s.title}</Link>
      {showNext && s.next_episode && (
        <button className="btn" disabled={next.isPending} onClick={() => next.mutate()}>
          Voir S{String(s.next_episode.season).padStart(2, "0")}E
          {String(s.next_episode.number).padStart(2, "0")}
        </button>
      )}
    </div>
  );
}
