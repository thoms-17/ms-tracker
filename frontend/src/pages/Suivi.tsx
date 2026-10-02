import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, posterUrl } from "../api";
import type { SeriesSummary, UpcomingItem } from "../types";
import Confetti from "../components/Confetti";
import Modal from "../components/Modal";
import Spinner from "../components/Spinner";
import VusTab from "./VusTab";

type Tab = "encours" | "vus" | "prochainement";
const TABS: Tab[] = ["encours", "vus", "prochainement"];

export default function Suivi() {
  // L'onglet actif vit dans l'URL (?tab=…) pour rester synchro avec la barre du bas.
  const [params, setParams] = useSearchParams();
  const raw = params.get("tab");
  const tab: Tab = TABS.includes(raw as Tab) ? (raw as Tab) : "encours";
  const setTab = (t: Tab) => setParams(t === "encours" ? {} : { tab: t });
  const series = useQuery({ queryKey: ["series"], queryFn: api.series });
  const movies = useQuery({ queryKey: ["movies"], queryFn: api.movies });
  const watchTime = useQuery({ queryKey: ["watchTime"], queryFn: api.watchTime });

  // Confettis « série terminée » : montés ici (le parent survit à la carte, qui quitte
  // la liste « En cours » une fois complétée) et rendus dans un portail sur <body>.
  const [confetti, setConfetti] = useState(false);
  const celebrate = () => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    setConfetti(true);
    setTimeout(() => setConfetti(false), 4000);
  };

  if (series.isLoading || movies.isLoading) return <Spinner />;
  if (series.error) return <p className="muted">Erreur API — le back FastAPI est-il lancé (port 8000) ?</p>;

  const all = series.data ?? [];
  // Compte sans aucune donnée → on oriente vers la recherche pour démarrer son suivi.
  if (all.length === 0 && (movies.data?.length ?? 0) === 0) return <EmptySuivi />;
  // Une série à jour dont l'épisode suivant n'est pas sorti attend dans « Prochainement ».
  // Dès qu'il sort, elle revient ici, en tête (la plus récente sortie d'abord).
  // Un revisionnage en cours n'apparaît que s'il est récent : abandonné, la série
  // reste seulement dans « Vus ».
  const inProgress = all
    .filter((s) => (s.n_watched > 0 && s.completion < 1 && !s.waiting) || (s.rewatch && s.recent))
    .sort((a, b) =>
      Number(b.new_episode) - Number(a.new_episode) ||
      (a.new_episode && b.new_episode
        ? (b.next_episode?.air_date ?? "").localeCompare(a.next_episode?.air_date ?? "")
        : (b.last_activity ?? "").localeCompare(a.last_activity ?? "")));
  // Comme TV Time : ce qu'on regarde en ce moment d'abord, le reste replié en dessous.
  const recent = inProgress.filter((s) => s.recent);
  const stale = inProgress.filter((s) => !s.recent);
  const completed = all.filter((s) => s.completion >= 1);

  return (
    <>
      {confetti && <Confetti />}
      {watchTime.data && (
        <div className="stats">
          <div className="stat">
            <div className="label">Séries</div>
            <div className="value">{watchTime.data.series_label}</div>
          </div>
          <div className="stat">
            <div className="label">Films</div>
            <div className="value">{watchTime.data.movie_label}</div>
          </div>
          <div className="stat total">
            <div className="label">Temps total devant l'écran</div>
            <div className="value">{watchTime.data.total_label}</div>
          </div>
        </div>
      )}

      <div className="tabs">
        <button className={tab === "encours" ? "active" : ""} onClick={() => setTab("encours")}>
          En cours ({inProgress.length})
        </button>
        <button className={tab === "vus" ? "active" : ""} onClick={() => setTab("vus")}>
          Vus ({completed.length} séries + films)
        </button>
        <button className={tab === "prochainement" ? "active" : ""} onClick={() => setTab("prochainement")}>
          Prochainement
        </button>
      </div>

      {tab === "encours" && (
        <>
          <h3 className="section-title">Regardées récemment ({recent.length})</h3>
          {recent.length === 0 ? (
            <p className="muted">Aucune série regardée ces deux dernières semaines.</p>
          ) : (
            <div className="grid">
              {recent.map((s) => <SeriesCard key={s.uuid} s={s} showNext onComplete={celebrate} />)}
            </div>
          )}
          {stale.length > 0 && (
            <details className="section-fold">
              <summary className="section-title">Pas regardées depuis un moment ({stale.length})</summary>
              <div className="grid">
                {stale.map((s) => <SeriesCard key={s.uuid} s={s} showNext onComplete={celebrate} />)}
              </div>
            </details>
          )}
        </>
      )}

      {tab === "vus" && <VusTab />}

      {tab === "prochainement" && <Prochainement />}
    </>
  );
}

/** Accueil d'un compte encore vide : on renvoie vers la recherche. */
function EmptySuivi() {
  return (
    <div className="empty-state">
      <h2 className="empty-title">Bienvenue sur MS Tracker</h2>
      <p className="muted">
        Ton suivi est vide. Cherche une série ou un film pour commencer à suivre tes visionnages.
      </p>
    </div>
  );
}

function SeriesCard({ s, showNext, onComplete }: {
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
      qc.invalidateQueries({ queryKey: ["series"] });
      qc.invalidateQueries({ queryKey: ["history"] });
      // Ce visionnage était-il le dernier (de la série ou du passage) ? → confettis.
      if (total > 0 && vus + 1 >= total) onComplete?.();
    },
  });
  const [askDismiss, setAskDismiss] = useState(false);
  const dismiss = useMutation({
    mutationFn: () => api.dismissRewatch(s.uuid),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["series"] }),
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

/** "2026-07-25" → "sam. 25 juil. 2026" (format français, sans décalage de fuseau). */
function frDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  if (!y || !m || !d) return iso;
  return new Date(y, m - 1, d).toLocaleDateString("fr-FR", {
    weekday: "short", day: "numeric", month: "short", year: "numeric",
  });
}

function Prochainement() {
  const up = useQuery({ queryKey: ["upcoming"], queryFn: api.upcoming });
  const items = up.data ?? [];
  const groups: [string, (i: UpcomingItem) => boolean][] = [
    ["Cette semaine", (i) => i.days <= 7],
    ["Ce mois-ci", (i) => i.days > 7 && i.days <= 31],
    ["Plus tard", (i) => i.days > 31],
  ];
  return (
    <>
      {up.isLoading && <Spinner />}
      {!up.isLoading && items.length === 0 && (
        <p className="muted">Aucune sortie annoncée pour tes séries.</p>
      )}
      {groups.map(([label, pred]) => {
        const g = items.filter(pred);
        if (g.length === 0) return null;
        return (
          <div key={label}>
            <h3>{label}</h3>
            {g.map((i, k) => {
              const url = posterUrl(i.poster_path);
              return (
                <div className="upcoming-row" key={k}>
                  {url && <img src={url} alt="" />}
                  <div>
                    <strong>{i.series_title}</strong> · S{String(i.season).padStart(2, "0")}E
                    {String(i.number).padStart(2, "0")}
                    <div className="muted">{i.name}</div>
                  </div>
                  <div style={{ marginLeft: "auto", textAlign: "right" }}>
                    <div>{frDate(i.air_date)}</div>
                    <div className="muted">
                      {i.days === 0 ? "aujourd'hui" : i.days === 1 ? "demain" : `dans ${i.days} j`}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        );
      })}
    </>
  );
}
