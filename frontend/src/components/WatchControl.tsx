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
  const [pos, setPos] = useState<{ top: number; right: number }>({ top: 0, right: 0 });

  const onButton = () => {
    if (!seen) { onComplete(); return; } // non vu → marque vu directement
    const r = btnRef.current!.getBoundingClientRect();
    setPos({ top: r.bottom + 6, right: Math.max(8, window.innerWidth - r.right) });
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

/** Menu popover rendu dans un portail (échappe à l'overflow/backdrop-filter des cartes). */
function WatchMenu({ pos, onClose, children }: {
  pos: { top: number; right: number }; onClose: () => void; children: ReactNode;
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
