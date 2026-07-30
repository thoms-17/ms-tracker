import { useQuery } from "@tanstack/react-query";
import { api } from "../api";

/** "2026-07-29T10:12:00.000Z" → "29/07/2026" */
const shortDate = (iso: string) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleDateString("fr-FR");
};

/**
 * Version de l'application, affichée dans le menu profil.
 *
 * Le front porte sa version **figée au build** (constantes injectées par Vite) ;
 * le back annonce la sienne **à l'exécution**. Les deux se déploient séparément
 * (rsync du dist d'un côté, git pull + redémarrage de l'autre) : afficher l'écart
 * rend immédiatement visible un back resté sur l'ancien code.
 */
export default function VersionInfo() {
  const back = useQuery({
    queryKey: ["version"],
    queryFn: api.version,
    staleTime: Infinity,
    retry: false,
  });

  // On compare les commits : c'est la seule donnée qui ne peut pas mentir.
  const mismatch = !!back.data && back.data.git_sha !== __GIT_SHA__;

  return (
    <div className="version-info">
      <span>
        v{__APP_VERSION__} · {__GIT_SHA__} · {shortDate(__BUILD_DATE__)}
      </span>
      {mismatch && (
        <span className="version-warn" title={`Serveur sur le commit ${back.data!.git_sha}`}>
          Serveur sur une autre version ({back.data!.git_sha})
        </span>
      )}
    </div>
  );
}
