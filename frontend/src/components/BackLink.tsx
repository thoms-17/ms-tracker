import { useNavigate } from "react-router-dom";

/**
 * « ← Retour » des pages de détail : revient à l'écran d'où l'on vient (onglet,
 * sous-onglet de « Vus » compris), comme le bouton retour du navigateur. Ouverte
 * directement (lien partagé, rechargement), la page n'a pas de précédent dans l'app :
 * on retourne alors à l'accueil.
 */
export default function BackLink() {
  const nav = useNavigate();
  // React Router numérote les entrées d'historique de l'app : 0 = la première.
  const hasPrevious = ((window.history.state as { idx?: number } | null)?.idx ?? 0) > 0;
  return (
    <button type="button" className="back-link muted" onClick={() => (hasPrevious ? nav(-1) : nav("/"))}>
      ← Retour
    </button>
  );
}
