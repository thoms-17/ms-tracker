import { useQuery } from "@tanstack/react-query";
import { api } from "../api";

/**
 * Version de l'application, affichée en pied du menu profil.
 *
 * Seul le numéro lisible est montré. Le commit reste comparé en arrière-plan :
 * front (figé au build) et back (lu au démarrage) se déploient séparément, et un
 * écart signale une mise à jour à moitié appliquée — typiquement un uvicorn non
 * redémarré. Dans ce cas seulement, un avertissement apparaît.
 */
export default function VersionInfo() {
  const back = useQuery({
    queryKey: ["version"],
    queryFn: api.version,
    staleTime: Infinity,
    retry: false,
  });

  const mismatch = !!back.data && back.data.git_sha !== __GIT_SHA__;

  return (
    <div className="version-info">
      <span>v{__APP_VERSION__}</span>
      {mismatch && (
        <span
          className="version-warn"
          title={`Front ${__GIT_SHA__} · serveur ${back.data!.git_sha}`}
        >
          Serveur sur une autre version
        </span>
      )}
    </div>
  );
}
