import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, posterUrl } from "../api";
import { episodeCode, relativeDay } from "../format";
import Spinner from "./Spinner";

/**
 * Derniers visionnages enregistrés — sert à vérifier d'un coup d'œil qu'un
 * épisode ou un film a bien été coché.
 */
export default function Historique() {
  const q = useQuery({ queryKey: ["history"], queryFn: () => api.history(20) });

  if (q.isLoading) return <Spinner />;
  if (q.error) return <p className="muted">Historique indisponible.</p>;
  const items = q.data ?? [];
  if (!items.length) return <p className="muted">Aucun visionnage enregistré pour le moment.</p>;

  return (
    <div className="histo">
      {items.map((h, i) => {
        const url = posterUrl(h.poster_path);
        const cible = h.kind === "episode" && h.uuid ? `/series/${h.uuid}` : null;
        const num = h.season !== null && h.number !== null ? episodeCode(h.season, h.number) : null;
        const ligne = (
          <>
            {url ? (
              <img className="histo-poster" src={url} alt="" loading="lazy" />
            ) : (
              <span className="histo-poster ph" />
            )}
            <span className="histo-texte">
              <span className="histo-titre">{h.title}</span>
              {num ? (
                <span className="muted">
                  {num}
                  {h.episode_name ? ` · ${h.episode_name}` : ""}
                </span>
              ) : (
                <span className="muted">Film</span>
              )}
            </span>
            <span className="histo-date muted">{relativeDay(h.watched_at)}</span>
          </>
        );
        // Les séries mènent à leur fiche ; les films n'ont pas de page dédiée.
        return cible ? (
          <Link className="histo-ligne" key={i} to={cible}>{ligne}</Link>
        ) : (
          <div className="histo-ligne" key={i}>{ligne}</div>
        );
      })}
    </div>
  );
}
