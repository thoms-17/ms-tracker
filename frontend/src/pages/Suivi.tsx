import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, posterUrl } from "../api";
import type { SeriesSummary, SyncResult, UpcomingItem } from "../types";
import ImportData from "./ImportData";
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

  if (series.isLoading || movies.isLoading) return <p className="muted">Chargement…</p>;
  if (series.error) return <p className="muted">Erreur API — le back FastAPI est-il lancé (port 8000) ?</p>;

  const all = series.data ?? [];
  // Compte sans aucune donnée → on met en avant le module d'import.
  if (all.length === 0 && (movies.data?.length ?? 0) === 0) return <ImportData />;
  const inProgress = all.filter((s) => s.n_watched > 0 && s.completion < 1)
    .sort((a, b) => (b.last_watched ?? "").localeCompare(a.last_watched ?? ""));
  const completed = all.filter((s) => s.completion >= 1);

  return (
    <>
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
          {inProgress.map((s) => <SeriesCard key={s.uuid} s={s} showNext />)}
        </div>
      )}

      {tab === "vus" && <VusTab />}

      {tab === "prochainement" && <Prochainement />}
    </>
  );
}

function SeriesCard({ s, showNext }: { s: SeriesSummary; showNext?: boolean }) {
  const qc = useQueryClient();
  const url = posterUrl(s.poster_path);
  const next = useMutation({
    mutationFn: () => api.markNext(s.uuid),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["series"] }),
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
      ["upcoming", "series", "movies", "watchTime"].forEach((k) =>
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
      {up.isLoading && <p className="muted">Chargement…</p>}
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
                    <div>{i.air_date}</div>
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
