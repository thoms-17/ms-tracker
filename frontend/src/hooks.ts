import { useEffect } from "react";

/**
 * Ferme un menu / une boîte de dialogue dès que la page défile.
 *
 * Indispensable pour les popovers ancrés à un élément (menu profil, menu de
 * visionnage) : leur position est calculée une fois à l'ouverture, un défilement
 * les décrocherait visuellement de leur bouton.
 *
 * `capture: true` intercepte aussi les défilements de conteneurs internes, que
 * l'écoute classique sur window ne verrait pas (l'événement scroll ne remonte pas).
 * `passive: true` : on n'annule jamais le défilement, on l'observe seulement.
 */
export function useCloseOnScroll(onClose: () => void, active = true) {
  useEffect(() => {
    if (!active) return;
    const handler = () => onClose();
    window.addEventListener("scroll", handler, { passive: true, capture: true });
    return () => window.removeEventListener("scroll", handler, { capture: true });
  }, [onClose, active]);
}
