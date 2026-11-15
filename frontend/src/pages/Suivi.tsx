import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import Confetti from "../components/Confetti";
import SeriesCard from "../components/SeriesCard";
import Spinner from "../components/Spinner";
import { enCours } from "../enCours";
import { DEFAULT_TAB, tabFromParam, type Tab } from "../tabs";
import Discover from "./Discover";
import Prochainement from "./Prochainement";
import Stats from "./Stats";
import VusTab from "./VusTab";

export default function Suivi() {
  // L'onglet actif vit dans l'URL (?tab=…) pour rester synchro avec la barre du bas.
  const [params, setParams] = useSearchParams();
  const tab = tabFromParam(params.get("tab"));
  const setTab = (t: Tab) => setParams(t === DEFAULT_TAB ? {} : { tab: t });
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
  // Comme TV Time : ce qu'on regarde en ce moment d'abord, le reste replié en dessous.
  const { recent, stale } = enCours(all);
  const completed = all.filter((s) => s.completion >= 1);

  return (
    <>
      {confetti && <Confetti />}
      {watchTime.data && tab !== "decouvrir" && (
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
          En cours ({recent.length + stale.length})
        </button>
        <button className={tab === "vus" ? "active" : ""} onClick={() => setTab("vus")}>
          Vus ({completed.length} séries + films)
        </button>
        <button className={tab === "prochainement" ? "active" : ""} onClick={() => setTab("prochainement")}>
          Prochainement
        </button>
        <button className={tab === "stats" ? "active" : ""} onClick={() => setTab("stats")}>
          Stats
        </button>
        <button className={tab === "decouvrir" ? "active" : ""} onClick={() => setTab("decouvrir")}>
          Découvrir
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

      {tab === "stats" && <Stats />}

      {tab === "decouvrir" && <Discover />}
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
