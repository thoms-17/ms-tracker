import { stillUrl } from "../api";

/** Miniature d'un épisode (16:9) ; cadre vide de même taille si TMDB n'en a pas. */
export default function EpisodeStill({ path }: { path: string | null }) {
  const url = stillUrl(path);
  return url
    ? <img className="ep-still" src={url} alt="" loading="lazy" />
    : <span className="ep-still" aria-hidden="true" />;
}
