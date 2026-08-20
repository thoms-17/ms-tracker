import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, posterUrl } from "../api";
import Confetti from "../components/Confetti";
import Spinner from "../components/Spinner";
import { useCloseOnScroll } from "../hooks";
import { signalerEchec } from "../toast";
import WatchControl from "../components/WatchControl";
import WatchProviders from "../components/WatchProviders";
import type { EpisodeItem, SeasonGroup, SeriesDetail as Detail } from "../types";

/** Retard de visionnage avant un épisode : épisodes concernés, et saisons traversées. */
type Retard = { total: number; saisons: number; ids: number[] };

/**
 * Applique localement un changement de compteur sur un ou plusieurs épisodes,
 * et met à jour les agrégats affichés (compteur de saison, progression série).
 *
 * Les agrégats sont ajustés **par delta** plutôt que recalculés : le serveur
 * exclut les épisodes « spéciaux » du décompte, un marqueur absent du modèle
 * front. Un recalcul complet produirait donc un écart visible avant que la
 * réponse du serveur ne le corrige.
 */
function majEpisodes(d: Detail, ids: Set<number>, calc: (n: number) => number): Detail {
  let deltaSerie = 0;
  const seasons = d.seasons.map((se) => {
    if (!se.episodes.some((e) => ids.has(e.episode_id))) return se;
    let deltaSaison = 0;
    const episodes = se.episodes.map((e) => {
      if (!ids.has(e.episode_id)) return e;
      const avant = e.watched_count;
      const apres = Math.max(0, calc(avant));
      if (avant === 0 && apres > 0) {
        deltaSaison += 1;
        if (se.season_number !== 0) deltaSerie += 1;
      } else if (avant > 0 && apres === 0) {
        deltaSaison -= 1;
        if (se.season_number !== 0) deltaSerie -= 1;
      }
      return { ...e, watched_count: apres };
    });
    return { ...se, episodes, watched: se.watched + deltaSaison };
  });
  const n_watched = d.n_watched + deltaSerie;
  return {
    ...d,
    seasons,
    n_watched,
    completion: d.n_episodes > 0 ? n_watched / d.n_episodes : d.completion,
  };
}

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
    qc.invalidateQueries({ queryKey: ["history"] });
  };

  if (detail.isLoading) return <Spinner />;
  if (detail.error || !detail.data) return <p className="muted">Série introuvable.</p>;
  const s = detail.data;
  const url = posterUrl(s.poster_path, true);
  const nextSeason = s.seasons.find((se) => se.season_number !== 0 && se.watched < se.total)?.season_number;

  // Tous les épisodes réguliers de la série, dans l'ordre de diffusion. Le
  // rattrapage traverse les saisons : il faut donc raisonner sur l'ensemble,
  // pas sur la seule saison affichée.
  const reguliers = s.seasons
    .filter((se) => se.season_number !== 0)
    .flatMap((se) => se.episodes);

  /** Épisodes réguliers non vus situés avant celui-ci (saisons précédentes incluses). */
  const avantNonVus = (e: EpisodeItem): Retard => {
    if (e.season_number === 0) return { total: 0, saisons: 0, ids: [] }; // un spécial ne rattrape rien
    const avant = reguliers.filter(
      (x) =>
        x.watched_count === 0 &&
        (x.season_number < e.season_number ||
          (x.season_number === e.season_number && x.episode_number < e.episode_number)),
    );
    return {
      total: avant.length,
      saisons: new Set(
        avant.filter((x) => x.season_number < e.season_number).map((x) => x.season_number),
      ).size,
      ids: avant.map((x) => x.episode_id),
    };
  };

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
        <Season
          key={se.season_number}
          uuid={uuid}
          se={se}
          open={se.season_number === nextSeason}
          avantNonVus={avantNonVus}
          onChange={refresh}
        />
      ))}
    </>
  );
}

function Season({ uuid, se, open, avantNonVus, onChange }: {
  uuid: string;
  se: SeasonGroup;
  open: boolean;
  avantNonVus: (e: EpisodeItem) => Retard;
  onChange: () => void;
}) {
  const s = se.season_number;
  // Ces actions ne sont pas optimistes (elles touchent toute la saison) : en cas
  // d'échec rien ne bouge à l'écran, d'où le message pour ne pas rester muet.
  const echec = { onError: (err: unknown) => signalerEchec(err, "Échec — saison non mise à jour") };
  const markWatched = useMutation({ mutationFn: () => api.markSeason(uuid, s, true), onSuccess: onChange, ...echec });
  const markUnwatched = useMutation({ mutationFn: () => api.markSeason(uuid, s, false), onSuccess: onChange, ...echec });
  const rewatch = useMutation({ mutationFn: () => api.rewatchSeason(uuid, s), onSuccess: onChange, ...echec });
  const removeOne = useMutation({ mutationFn: () => api.removeSeasonWatch(uuid, s), onSuccess: onChange, ...echec });
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
      {se.episodes.map((e) => (
        <Episode key={e.episode_id} uuid={uuid} e={e} retard={avantNonVus(e)} onChange={onChange} />
      ))}
    </details>
  );
}

function Episode({ uuid, e, retard, onChange }: {
  uuid: string; e: EpisodeItem; retard: Retard; onChange: () => void;
}) {
  const qc = useQueryClient();
  const cle = ["series", uuid];

  /**
   * Mise à jour optimiste : le compteur bouge dès le clic, sans attendre le
   * serveur. Sans ça, l'affichage attend deux allers-retours (l'écriture, puis
   * la relecture) — plusieurs secondes sur un réseau mobile ou un serveur qui
   * sort de veille. En cas d'échec, on restaure l'état précédent.
   */
  const optimiste = (ids: number[], calc: (n: number) => number) => ({
    onMutate: async () => {
      await qc.cancelQueries({ queryKey: cle }); // évite qu'une réponse en vol écrase notre écriture
      const precedent = qc.getQueryData<Detail>(cle);
      if (precedent) qc.setQueryData(cle, majEpisodes(precedent, new Set(ids), calc));
      return { precedent };
    },
    onError: (err: unknown, _v: void, ctx?: { precedent?: Detail }) => {
      if (ctx?.precedent) qc.setQueryData(cle, ctx.precedent);
      // Le compteur redescend : sans message, l'annulation passerait inaperçue.
      signalerEchec(err, "Échec — visionnage non enregistré");
    },
    onSettled: onChange, // réconcilie avec le serveur, succès comme échec
  });

  const id = e.episode_id;
  const add = useMutation({
    mutationFn: () => api.watchEpisode(id),
    ...optimiste([id], (n) => n + 1),
  });
  const catchUp = useMutation({
    mutationFn: () => api.catchUpEpisode(id),
    // les précédents non vus passent à 1, l'épisode ciblé est incrémenté
    ...optimiste([...retard.ids, id], (n) => n + 1),
  });
  const removeOne = useMutation({
    mutationFn: () => api.removeEpisodeWatch(id),
    ...optimiste([id], (n) => n - 1),
  });
  const removeAll = useMutation({
    mutationFn: () => api.unwatchEpisode(id),
    ...optimiste([id], () => 0),
  });
  const [ask, setAsk] = useState(false); // propose de rattraper les précédents
  const num = `S${String(e.season_number).padStart(2, "0")}E${String(e.episode_number).padStart(2, "0")}`;

  const onComplete = () => {
    if (retard.total > 0) setAsk(true); // des épisodes avant celui-ci ne sont pas vus
    else add.mutate();
  };
  const pluriel = retard.total > 1;

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
            {retard.total} épisode{pluriel ? "s" : ""} avant {num} {pluriel ? "ne sont pas vus" : "n'est pas vu"}
            {retard.saisons > 0 && (
              <>, dont {retard.saisons > 1 ? `ceux de ${retard.saisons} saisons précédentes` : "ceux de la saison précédente"}</>
            )}.
            {" "}Veux-tu {pluriel ? "les" : "l'"} marquer comme vu{pluriel ? "s" : ""} aussi ?
          </p>
          <div className="modal-actions">
            <button className="btn" onClick={() => { add.mutate(); setAsk(false); }}>
              Seulement {num}
            </button>
            <button className="btn primary" onClick={() => { catchUp.mutate(); setAsk(false); }}>
              Marquer les {retard.total + 1} épisodes
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

