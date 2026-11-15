import { useEffect, useState } from "react";

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

/**
 * Hauteur (px) que le clavier virtuel occupe en bas de l'écran, 0 s'il est fermé.
 *
 * Sur iOS, le clavier ne réduit pas la page : un élément fixé en bas resterait caché
 * derrière lui. Le « visual viewport » donne la zone réellement visible ; l'écart avec
 * la hauteur de la fenêtre est la place prise par le clavier. (Sur Android, la page est
 * redimensionnée : l'écart reste nul et l'élément remonte tout seul.)
 */
export function useKeyboardInset(active = true): number {
  const [inset, setInset] = useState(0);
  useEffect(() => {
    const vv = window.visualViewport;
    if (!active || !vv) return;
    const update = () => {
      const gap = window.innerHeight - vv.height - vv.offsetTop;
      setInset(gap > 80 ? Math.round(gap) : 0); // en dessous : barre d'outils du navigateur, pas un clavier
    };
    update();
    vv.addEventListener("resize", update);
    vv.addEventListener("scroll", update);
    return () => {
      vv.removeEventListener("resize", update);
      vv.removeEventListener("scroll", update);
    };
  }, [active]);
  return inset;
}
