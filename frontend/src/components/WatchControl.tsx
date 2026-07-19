import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

/**
 * Bouton rond de visionnage, façon TV Time — partagé par épisodes, saisons et films.
 *  · non vu   → un clic marque comme vu (`onComplete`)
 *  · déjà vu  → un clic ouvre un menu : Revu / Enlever un visionnage / Marquer comme non vu
 * Le chiffre affiché est le nombre de visionnages (complets pour une saison).
 */
export default function WatchControl({
  count, kind, onComplete, onRewatch, onRemoveOne, onRemoveAll,
}: {
  count: number;
  kind: "episode" | "season" | "movie";
  onComplete: () => void; // clic quand non vu
  onRewatch: () => void; // menu : Revu (+1)
  onRemoveOne: () => void; // menu : Enlever un visionnage (−1)
  onRemoveAll: () => void; // menu : Marquer comme non vu (tout)
}) {
  const seen = count > 0;
  const btnRef = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<Pos>({ top: 0, right: 0 });

  const onButton = () => {
    if (!seen) { onComplete(); return; } // non vu → marque vu directement
    setPos(menuPos(btnRef.current!.getBoundingClientRect()));
    setOpen((o) => !o);
  };

  const seenLabel = kind === "season" ? `Saison vue ${count} fois` : `Vu ${count} fois`;
  const addLabel = kind === "season" ? "Marquer la saison comme vue" : "Marquer comme vu";

  return (
    <>
      <button
        ref={btnRef}
        type="button"
        className={`watch-btn${seen ? " on" : ""}`}
        onClick={onButton}
        aria-haspopup={seen ? "menu" : undefined}
        aria-expanded={seen ? open : undefined}
        aria-label={seen ? `${seenLabel} — options` : addLabel}
        title={seen ? seenLabel : addLabel}
      >
        {seen ? count : "+"}
      </button>
      {open && (
        <WatchMenu pos={pos} onClose={() => setOpen(false)}>
          <button className="menu-item" onClick={() => { onRewatch(); setOpen(false); }}>Revu</button>
          <button className="menu-item" onClick={() => { onRemoveOne(); setOpen(false); }}>
            Enlever un visionnage
          </button>
          <button className="menu-item danger" onClick={() => { onRemoveAll(); setOpen(false); }}>
            Marquer comme non vu
          </button>
        </WatchMenu>
      )}
    </>
  );
}

type Pos = { top: number; right: number };

// Menu à 3 options : hauteur ~réelle utilisée pour décider s'il tient sous le bouton.
const MENU_H = 150;
const GAP = 6;
const EDGE = 8; // marge minimale avec les bords de l'écran

/**
 * Place le menu sous le bouton, mais bascule au-dessus s'il déborderait en bas
 * (ex. épisode en bas d'écran sur mobile), puis borne la position dans le viewport
 * pour qu'il reste toujours entièrement visible.
 */
function menuPos(r: DOMRect): Pos {
  const vh = window.innerHeight;
  const below = r.bottom + GAP;
  const above = r.top - GAP - MENU_H;
  // Sous le bouton par défaut ; au-dessus si ça déborde en bas et qu'il y a plus de place en haut.
  let top = below;
  if (below + MENU_H > vh - EDGE && r.top > vh - r.bottom) top = above;
  top = Math.min(Math.max(top, EDGE), Math.max(EDGE, vh - MENU_H - EDGE));
  const right = Math.max(EDGE, window.innerWidth - r.right);
  return { top, right };
}

/** Menu popover rendu dans un portail (échappe à l'overflow/backdrop-filter des cartes). */
function WatchMenu({ pos, onClose, children }: {
  pos: Pos; onClose: () => void; children: ReactNode;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return createPortal(
    <div className="menu-layer" onClick={onClose}>
      <div
        className="watch-menu"
        role="menu"
        style={{ top: pos.top, right: pos.right }}
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>,
    document.body,
  );
}
