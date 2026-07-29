/**
 * Indicateur de chargement partagé par toute l'application.
 *  · `full` : occupe la hauteur de l'écran (gate d'authentification au démarrage)
 *  · défaut : bloc centré dans le flux de la page (sections, listes, détails)
 */
export default function Spinner({ full = false, size = 34 }: {
  full?: boolean;
  size?: number;
}) {
  return (
    <div className={full ? "app-loading" : "loading-block"}>
      <span
        className="spinner"
        style={{ width: size, height: size }}
        role="status"
        aria-label="Chargement"
      />
    </div>
  );
}
