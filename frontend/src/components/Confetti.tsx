import { useMemo, type CSSProperties } from "react";
import { createPortal } from "react-dom";

const COLORS = ["#3987e5", "#38d39f", "#ffd23f", "#ff6b6b", "#c77dff", "#ff9f43"];

/**
 * Pluie de confettis (CSS pur, sans dépendance), rendue dans un portail sur <body>.
 * Purement décorative (`pointer-events: none`). Le parent la monte/démonte via un état
 * temporisé ; l'animation dure ~4 s. Respecte `prefers-reduced-motion` (masquée en CSS).
 */
export default function Confetti() {
  const pieces = useMemo(
    () => Array.from({ length: 110 }, (_, i) => ({
      left: Math.random() * 100,
      delay: Math.random() * 0.7,
      duration: 2.8 + Math.random() * 1.8,
      color: COLORS[i % COLORS.length],
      size: 6 + Math.random() * 6,
      drift: (Math.random() - 0.5) * 160,
      rot: 180 + Math.random() * 540,
    })),
    [],
  );
  return createPortal(
    <div className="confetti" aria-hidden="true">
      {pieces.map((p, i) => (
        <span
          key={i}
          className="confetti-piece"
          style={{
            left: `${p.left}%`,
            width: `${p.size}px`,
            height: `${p.size * 0.6}px`,
            background: p.color,
            animationDelay: `${p.delay}s`,
            animationDuration: `${p.duration}s`,
            ["--drift" as string]: `${p.drift}px`,
            ["--rot" as string]: `${p.rot}deg`,
          } as CSSProperties}
        />
      ))}
    </div>,
    document.body,
  );
}
