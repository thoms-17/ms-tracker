/**
 * Serveur injoignable au démarrage (réseau coupé, PWA qui se réveille).
 * On reste sur un écran neutre : la session est probablement toujours valide,
 * ce serait une erreur de renvoyer l'utilisateur vers la page de connexion.
 */
export default function OfflineGate({ onRetry, pending }: { onRetry: () => void; pending: boolean }) {
  return (
    <div className="app-loading">
      <div className="empty-state">
        <h2 className="empty-title">Connexion indisponible</h2>
        <p className="muted">
          Impossible de joindre le serveur. Vérifie ta connexion — tu resteras connecté.
        </p>
        <button className="btn primary" onClick={onRetry} disabled={pending}>
          {pending ? "Nouvelle tentative…" : "Réessayer"}
        </button>
      </div>
    </div>
  );
}
