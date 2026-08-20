import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, posterUrl } from "../api";
import type { SeriesSummary, SyncResult, UpcomingItem } from "../types";
import Confetti from "../components/Confetti";
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
  const inProgress = all.filter((s) => s.n_watched > 0 && s.completion < 1)
    .sort((a, b) => (b.last_watched ?? "").localeCompare(a.last_watched ?? ""));
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
        <div className="grid">
          {inProgress.map((s) => <SeriesCard key={s.uuid} s={s} showNext onComplete={celebrate} />)}
        </div>
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
  const next = useMutation({
    mutationFn: () => api.markNext(s.uuid),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["series"] });
      qc.invalidateQueries({ queryKey: ["history"] });
      // Ce visionnage était-il le dernier ? → série terminée : confettis.
      if (s.n_episodes > 0 && s.n_watched + 1 >= s.n_episodes) onComplete?.();
    },
  });
  return (
    <div className="card">
      <Link to={`/series/${s.uuid}`}>
        {url ? <img className="poster" src={url} alt={s.title} /> : <div className="poster" />}
      </Link>
      <div className="bar"><span style={{ width: `${Math.min(s.completion * 100, 100)}%` }} /></div>
      <span className="sub">{s.n_watched}/{s.n_episodes}</span>
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

function SyncControls() {
  const qc = useQueryClient();
  const [justFinished, setJustFinished] = useState<SyncResult | null>(null);

  const status = useQuery({
    queryKey: ["syncStatus"],
    queryFn: api.syncStatus,
    refetchInterval: (q) => (q.state.data?.running ? 800 : false),
  });
  const start = useMutation({
    mutationFn: api.startSync,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["syncStatus"] }),
  });

  const running = status.data?.running ?? false;
  const wasRunning = useRef(false);
  useEffect(() => {
    if (wasRunning.current && !running) {
      // La synchro vient de finir → rafraîchit les données dérivées.
      ["upcoming", "series", "movies", "watchTime", "history"].forEach((k) =>
        qc.invalidateQueries({ queryKey: [k] }),
      );
      setJustFinished(status.data?.result ?? null);
    }
    wasRunning.current = running;
  }, [running, qc, status.data?.result]);

  const last = status.data?.last_sync;
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <button className="btn primary" disabled={running || start.isPending} onClick={() => start.mutate()}>
          {running ? "Vérification en cours…" : "Vérifier les nouveautés"}
        </button>
        <span className="muted">
          {last ? `Dernière vérification : ${new Date(last).toLocaleString("fr-FR")}` : "Jamais synchronisé"}
        </span>
      </div>
      {running && (
        <div className="bar" style={{ marginTop: 10, maxWidth: 360 }}>
          <span style={{ width: `${Math.round((status.data?.progress ?? 0) * 100)}%` }} />
        </div>
      )}
      {justFinished && !running && (
        <p className="muted" style={{ marginTop: 8 }}>
          {justFinished.checked} séries vérifiées
          {justFinished.episodes_added > 0
            ? ` · ${justFinished.episodes_added} nouvel(s) épisode(s) ajouté(s)`
            : " · déjà à jour"}
        </p>
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
      <SyncControls />
      {up.isLoading && <Spinner />}
      {!up.isLoading && items.length === 0 && (
        <p className="muted">Aucune sortie annoncée. Lance une vérification pour rafraîchir.</p>
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
