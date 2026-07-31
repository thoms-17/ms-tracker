import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useCloseOnScroll } from "../hooks";

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
  const [anchor, setAnchor] = useState<DOMRect | null>(null); // null = menu fermé

  const onButton = () => {
    if (!seen) { onComplete(); return; } // non vu → marque vu directement
    setAnchor((a) => (a ? null : btnRef.current!.getBoundingClientRect()));
  };
  const open = anchor !== null;
  const close = () => setAnchor(null);

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
      {anchor && (
        <WatchMenu anchor={anchor} onClose={close}>
          <button className="menu-item" onClick={() => { onRewatch(); close(); }}>Revu</button>
          <button className="menu-item" onClick={() => { onRemoveOne(); close(); }}>
            Enlever un visionnage
          </button>
          <button className="menu-item danger" onClick={() => { onRemoveAll(); close(); }}>
            Marquer comme non vu
          </button>
        </WatchMenu>
      )}
    </>
  );
}

type Pos = { top: number; right: number };

const GAP = 6;
const EDGE = 8; // marge minimale avec les bords de l'écran

/**
 * Place le menu par rapport au bouton, à partir de ses dimensions **mesurées**.
 * Sous le bouton par défaut ; au-dessus s'il déborderait en bas et qu'il y a plus
 * de place en haut (épisode en bas d'écran sur mobile) ; puis bornage dans le
 * viewport sur les deux axes, pour qu'il reste toujours entièrement visible.
 */
function place(anchor: DOMRect, menuW: number, menuH: number): Pos {
  const vw = window.innerWidth;
  const vh = window.innerHeight;

  const below = anchor.bottom + GAP;
  let top = below;
  if (below + menuH > vh - EDGE && anchor.top > vh - anchor.bottom) {
    top = anchor.top - GAP - menuH; // bascule au-dessus
  }
  top = Math.min(Math.max(top, EDGE), Math.max(EDGE, vh - menuH - EDGE));

  // Ancré à droite du bouton, sans jamais sortir à gauche ni à droite.
  let right = vw - anchor.right;
  right = Math.min(Math.max(right, EDGE), Math.max(EDGE, vw - menuW - EDGE));
  return { top, right };
}

/** Menu popover rendu dans un portail (échappe à l'overflow/backdrop-filter des cartes). */
function WatchMenu({ anchor, onClose, children }: {
  anchor: DOMRect; onClose: () => void; children: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  // Position provisoire hors écran : on mesure d'abord, on place ensuite — sans
  // quoi la hauteur devrait être devinée, et toute évolution du menu la fausserait.
  const [pos, setPos] = useState<Pos | null>(null);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const apply = () => {
      const b = el.getBoundingClientRect();
      setPos(place(anchor, b.width, b.height));
    };
    apply();
    // Rotation de l'écran ou apparition du clavier → on replace.
    window.addEventListener("resize", apply);
    window.addEventListener("orientationchange", apply);
    return () => {
      window.removeEventListener("resize", apply);
      window.removeEventListener("orientationchange", apply);
    };
  }, [anchor]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  useCloseOnScroll(onClose);

  return createPortal(
    <div className="menu-layer" onClick={onClose}>
      <div
        ref={ref}
        className="watch-menu"
        role="menu"
        style={pos
          ? { top: pos.top, right: pos.right }
          : { top: 0, right: 0, visibility: "hidden" }}
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>,
    document.body,
  );
}
