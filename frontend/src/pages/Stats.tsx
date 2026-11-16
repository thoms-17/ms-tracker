import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, posterUrl } from "../api";
import Spinner from "../components/Spinner";
import { hours } from "../format";
import type { SeriesSummary, StatsPeriod, StatsTitle } from "../types";

const JOURS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"];
/** Sans visionnage depuis ce nombre de jours, une série commencée est « laissée en plan ». */
const STALE_DAYS = 90;

const nombre = (n: number) => n.toLocaleString("fr-FR");
const visionnages = (p: StatsPeriod) => {
  const n = p.episodes + p.movies;
  return `${nombre(n)} visionnage${n > 1 ? "s" : ""}`;
};

/** "2026-03" → { court: "mars", long: "mars 2026" }. */
function mois(iso: string) {
  const [y, m] = iso.split("-").map(Number);
  const d = new Date(y, m - 1, 1);
  return {
    court: d.toLocaleDateString("fr-FR", { month: "short" }).replace(".", ""),
    long: d.toLocaleDateString("fr-FR", { month: "long", year: "numeric" }),
  };
}

/** Onglet « Stats » : rythme, genres et titres les plus regardés. */
export default function Stats() {
  const stats = useQuery({ queryKey: ["stats"], queryFn: api.stats });
  const series = useQuery({ queryKey: ["series"], queryFn: api.series });
  const watchTime = useQuery({ queryKey: ["watchTime"], queryFn: api.watchTime });

  if (stats.isLoading) return <Spinner />;
  if (!stats.data) return <p className="muted">Statistiques indisponibles pour le moment.</p>;
  const s = stats.data;
  if (s.views === 0) {
    return <p className="muted">Tes statistiques apparaîtront dès ton premier visionnage.</p>;
  }

  const annee = s.months.reduce((t, m) => t + m.minutes, 0);
  const maxGenre = Math.max(...s.genres.map((g) => g.minutes), 1);
  const maxAnnee = Math.max(...s.years.map((y) => y.minutes), 1);
  const delaissees = laisseesEnPlan(series.data ?? []);

  return (
    <div className="statspage">
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
      <div className="stats">
        <div className="stat">
          <div className="label">Visionnages enregistrés</div>
          <div className="value">{nombre(s.views)}</div>
        </div>
        <div className="stat">
          <div className="label">Titres vus</div>
          <div className="value">{nombre(s.titles_watched)}</div>
        </div>
        <div className="stat">
          <div className="label">En moyenne, ces 12 derniers mois</div>
          <div className="value">{hours(annee / 52)} par semaine</div>
        </div>
      </div>

      <section className="stat-section">
        <h3 className="section-title">Ton rythme, ces 12 derniers mois</h3>
        <Columns
          items={s.months.map((m) => ({
            key: m.month, label: mois(m.month).court, value: m.minutes,
            detail: `${mois(m.month).long} : ${hours(m.minutes)} · ${visionnages(m)}`,
          }))}
        />
      </section>

      <section className="stat-section">
        <h3 className="section-title">Tes jours de visionnage</h3>
        <Columns
          items={s.weekdays.map((d) => ({
            key: String(d.day), label: JOURS[d.day], value: d.minutes,
            detail: `${JOURS[d.day]} : ${hours(d.minutes)} · ${visionnages(d)}`,
          }))}
        />
      </section>

      {s.years.length > 1 && (
        <section className="stat-section">
          <h3 className="section-title">Par année</h3>
          <ul className="bars">
            {s.years.map((y) => (
              <Bar key={y.year} label={String(y.year)} share={y.minutes / maxAnnee}
                value={hours(y.minutes)} hint={visionnages(y)} />
            ))}
          </ul>
        </section>
      )}

      {s.genres.length > 0 && (
        <section className="stat-section">
          <h3 className="section-title">Tes genres</h3>
          <ul className="bars">
            {s.genres.map((g) => (
              <Bar key={g.name} label={g.name} share={g.minutes / maxGenre}
                value={hours(g.minutes)} hint={`${g.titles} titre${g.titles > 1 ? "s" : ""}`} />
            ))}
          </ul>
          <p className="stat-note muted">
            Un titre compte dans chacun de ses genres.
            {s.titles_with_genres < s.titles_watched &&
              ` Genres connus pour ${s.titles_with_genres} titres sur ${s.titles_watched} ; les autres arrivent à la prochaine synchro.`}
          </p>
        </section>
      )}
      {s.genres.length === 0 && (
        <p className="stat-note muted">Tes genres apparaîtront après la prochaine synchro quotidienne.</p>
      )}

      {s.top_series.length > 0 && (
        <section className="stat-section">
          <h3 className="section-title">Les séries qui t'ont pris le plus de temps</h3>
          <Ranking items={s.top_series} value={(t) => hours(t.minutes)} share={(t) => t.minutes}
            link={(t) => `/series/${t.uuid}`} />
        </section>
      )}

      {s.top_movies.length > 0 && (
        <section className="stat-section">
          <h3 className="section-title">Tes films les plus revus</h3>
          <Ranking items={s.top_movies} value={(t) => `vu ×${t.views}`} share={(t) => t.views}
            link={(t) => (t.tmdb_id ? `/tmdb/movie/${t.tmdb_id}` : null)} />
        </section>
      )}

      {delaissees.length > 0 && (
        <section className="stat-section">
          <h3 className="section-title">Laissées en plan ({delaissees.length})</h3>
          <p className="stat-note muted stat-lead">
            Commencées, sans visionnage depuis plus de trois mois — les plus avancées d'abord.
          </p>
          <div className="rank">
            {delaissees.slice(0, 6).map((x) => {
              const url = posterUrl(x.poster_path);
              return (
                <Link to={`/series/${x.uuid}`} className="rank-row" key={x.uuid}>
                  {url ? <img className="rank-poster" src={url} alt="" /> : <span className="rank-poster" />}
                  <span className="rank-main">
                    <span className="rank-title">{x.title}</span>
                    <span className="bar"><span style={{ width: `${x.completion * 100}%` }} /></span>
                  </span>
                  <span className="rank-value">{x.n_watched}/{x.n_episodes}</span>
                </Link>
              );
            })}
          </div>
        </section>
      )}

      {s.undated_views > 0 && (
        <p className="stat-note muted">
          {nombre(s.undated_views)} visionnages ont été enregistrés en lot (import TV Time, saison
          cochée d'un coup) et n'ont pas de date réelle : ils comptent dans les totaux et les
          classements, pas dans le rythme, les jours ni les années.
        </p>
      )}
    </div>
  );
}

/**
 * Séries commencées, non terminées, dont l'épisode suivant est sorti, sans activité
 * récente. La date de dernière activité n'est pas affichée : pour les séries importées
 * de TV Time, c'est celle de l'import, pas d'un vrai visionnage.
 */
function laisseesEnPlan(all: SeriesSummary[]): SeriesSummary[] {
  const limite = Date.now() - STALE_DAYS * 86_400_000;
  return all
    .filter((x) => x.n_watched > 0 && x.completion < 1 && !x.waiting &&
      x.last_activity !== null && new Date(x.last_activity).getTime() < limite)
    .sort((a, b) => b.completion - a.completion); // les plus proches de la fin d'abord
}

/** Ligne d'un classement à barres : libellé, barre proportionnelle, valeur en clair. */
function Bar({ label, share, value, hint }: { label: string; share: number; value: string; hint: string }) {
  return (
    <li className="bars-row" title={`${label} : ${value} · ${hint}`}>
      <span className="bars-label">{label}</span>
      <span className="bars-track"><span className="bars-fill" style={{ width: `${Math.max(share * 100, 1)}%` }} /></span>
      <span className="bars-value">{value}</span>
    </li>
  );
}

type Column = { key: string; label: string; value: number; detail: string };

/**
 * Histogramme à une seule série. Survoler ou toucher une colonne affiche son détail
 * sous le graphique (le survol seul ne suffirait pas sur un écran tactile) ; par
 * défaut, c'est la colonne la plus haute qui est détaillée.
 */
function Columns({ items }: { items: Column[] }) {
  const max = Math.max(...items.map((i) => i.value), 1);
  const plusHaute = items.reduce((best, it, i) => (it.value > items[best].value ? i : best), 0);
  const [choisie, setChoisie] = useState<number | null>(null);
  const active = choisie ?? plusHaute;
  return (
    <div className="cols-chart">
      <div className="cols" onMouseLeave={() => setChoisie(null)}>
        {items.map((it, i) => (
          <button type="button" key={it.key} className={`col${i === active ? " active" : ""}`}
            aria-label={it.detail} onMouseEnter={() => setChoisie(i)} onFocus={() => setChoisie(i)}
            onClick={() => setChoisie(i)}>
            <span className="col-track">
              <span className="col-fill" style={{ height: `${(it.value / max) * 100}%` }} />
            </span>
            <span className="col-label">{it.label}</span>
          </button>
        ))}
      </div>
      <p className="cols-detail" aria-live="polite">{items[active].detail}</p>
    </div>
  );
}

/** Classement de titres : affiche, titre, barre proportionnelle au premier, valeur. */
function Ranking({ items, value, share, link }: {
  items: StatsTitle[];
  value: (t: StatsTitle) => string;
  share: (t: StatsTitle) => number;
  link: (t: StatsTitle) => string | null;
}) {
  const max = Math.max(...items.map(share), 1);
  return (
    <div className="rank">
      {items.map((t) => {
        const url = posterUrl(t.poster_path);
        const to = link(t);
        const row = (
          <>
            {url ? <img className="rank-poster" src={url} alt="" /> : <span className="rank-poster" />}
            <span className="rank-main">
              <span className="rank-title">{t.title}</span>
              <span className="bars-track"><span className="bars-fill" style={{ width: `${(share(t) / max) * 100}%` }} /></span>
            </span>
            <span className="rank-value">{value(t)}</span>
          </>
        );
        return to
          ? <Link to={to} className="rank-row" key={t.uuid}>{row}</Link>
          : <div className="rank-row" key={t.uuid}>{row}</div>;
      })}
    </div>
  );
}
