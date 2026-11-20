import { useState } from "react";
import { backdropUrl, profileUrl } from "../api";
import type { CastMember } from "../types";

/**
 * Éléments de fiche TMDB partagés par les pages de films et de séries : image de fond,
 * informations de l'en-tête, bande-annonce, synopsis et casting.
 */

/** Image de fond floutée derrière l'en-tête (la page doit avoir la classe `media-page`). */
export function Backdrop({ path }: { path: string | null }) {
  const url = backdropUrl(path);
  return url ? <div className="media-backdrop" style={{ backgroundImage: `url(${url})` }} aria-hidden="true" /> : null;
}

/** Accroche, ligne d'informations, puis note TMDB et auteurs (« Réalisé par… »). */
export function Facts({ tagline, infos, score, votes, people }: {
  tagline?: string | null;
  infos: (string | null | undefined)[];
  score?: number | null;
  votes?: number;
  people?: string | null;
}) {
  const ligne = infos.filter(Boolean);
  return (
    <>
      {tagline && <p className="media-tagline">{tagline}</p>}
      {ligne.length > 0 && <p className="muted media-infos">{ligne.join(" · ")}</p>}
      {(score || people) && (
        <p className="muted media-infos">
          {score ? (
            <span className="media-score" title={votes ? `${votes.toLocaleString("fr-FR")} votes sur TMDB` : undefined}>
              ★ {score.toFixed(1).replace(".", ",")}
            </span>
          ) : null}
          {score && people ? " · " : null}
          {people}
        </p>
      )}
    </>
  );
}

export function TrailerLink({ youtubeKey }: { youtubeKey: string | null }) {
  if (!youtubeKey) return null;
  return (
    <a className="btn" href={`https://www.youtube.com/watch?v=${youtubeKey}`}
      target="_blank" rel="noreferrer">
      ▶ Bande-annonce
    </a>
  );
}

/**
 * `folded` : replié sur trois lignes, avec « Lire la suite » (pages de séries, où le
 * synopsis précède les saisons et ne doit pas les repousser trop bas).
 */
export function Synopsis({ text, folded = false }: { text: string | null; folded?: boolean }) {
  const [ouvert, setOuvert] = useState(!folded);
  if (!text) return null;
  const long = text.length > 220;
  return (
    <section className="media-section">
      <h3 className="section-title">Synopsis</h3>
      <p className={`media-overview${ouvert || !long ? "" : " folded"}`}>{text}</p>
      {long && folded && (
        <button type="button" className="back-link muted media-more" onClick={() => setOuvert((o) => !o)}>
          {ouvert ? "Réduire" : "Lire la suite"}
        </button>
      )}
    </section>
  );
}

/** Casting : photos rondes à faire défiler. */
export function CastRow({ cast }: { cast: CastMember[] }) {
  if (!cast.length) return null;
  return (
    <section className="media-section">
      <h3 className="section-title">Casting</h3>
      <div className="cast-row">
        {cast.map((c, i) => {
          const photo = profileUrl(c.profile_path);
          return (
            <div className="cast-card" key={`${c.name}-${i}`}>
              {photo
                ? <img className="cast-photo" src={photo} alt="" loading="lazy" />
                : <span className="cast-photo ph">{(c.name ?? "?").slice(0, 1)}</span>}
              <span className="cast-name">{c.name}</span>
              {c.character && <span className="cast-role">{c.character}</span>}
            </div>
          );
        })}
      </div>
    </section>
  );
}

/** "142" → "2 h 22" ; "47" → "47 min". */
export function duree(minutes: number): string {
  const h = Math.floor(minutes / 60), m = minutes % 60;
  return h ? `${h} h${m ? ` ${String(m).padStart(2, "0")}` : ""}` : `${m} min`;
}
