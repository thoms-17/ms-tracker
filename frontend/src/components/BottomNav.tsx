import { useLayoutEffect, useRef, useState } from "react";
import type { MouseEvent, PointerEvent } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { TABS, tabFromParam, tabHref, type Tab } from "../tabs";
import { CalendarIcon, ChartIcon, CheckIcon, PlayIcon, SearchIcon } from "./icons";

const ICONS: Record<Tab, () => JSX.Element> = {
  encours: PlayIcon,
  vus: CheckIcon,
  prochainement: CalendarIcon,
  stats: ChartIcon,
  decouvrir: SearchIcon,
};
const NAV = TABS.filter((t) => t.bottomNav !== false).map((t) => ({ ...t, icon: ICONS[t.key] }));

/** Seuil (px) au-delà duquel un appui sur la barre devient un glissé. */
const DRAG_THRESHOLD = 6;

/**
 * Barre de navigation flottante (mobile) — liquid glass façon iOS 26, présente sur
 * toutes les pages. Une bulle de verre unique glisse d'un onglet à l'autre (ressort
 * CSS) ; on peut aussi faire glisser le doigt le long de la barre pour changer d'onglet.
 * La loupe, détachée de la capsule, mène à l'onglet « Découvrir ».
 */
export default function BottomNav() {
  const [params] = useSearchParams();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const onHome = pathname === "/";
  const tab = tabFromParam(params.get("tab"));
  const activeIdx = onHome ? NAV.findIndex((n) => n.key === tab) : -1;

  const barRef = useRef<HTMLDivElement>(null);
  const itemRefs = useRef<(HTMLAnchorElement | null)[]>([]);
  // Position/largeur de chaque onglet dans la barre, pour placer la bulle
  const [rects, setRects] = useState<{ x: number; w: number }[]>([]);
  const [pressed, setPressed] = useState(false);
  const [drag, setDrag] = useState<{ x: number; idx: number } | null>(null);
  const gesture = useRef<{ startX: number; id: number; moved: boolean } | null>(null);
  const suppressClick = useRef(false);

  useLayoutEffect(() => {
    const bar = barRef.current;
    if (!bar) return;
    // La barre est masquée sur desktop (tailles nulles) : l'observer remesure
    // dès qu'elle apparaît, et après le chargement des polices.
    const measure = () =>
      setRects(itemRefs.current.map((el) => ({ x: el?.offsetLeft ?? 0, w: el?.offsetWidth ?? 0 })));
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(bar);
    return () => ro.disconnect();
  }, []);

  const nearest = (x: number) => {
    let best = 0;
    rects.forEach((r, i) => {
      if (Math.abs(r.x + r.w / 2 - x) < Math.abs(rects[best].x + rects[best].w / 2 - x)) best = i;
    });
    return best;
  };

  const onPointerDown = (e: PointerEvent<HTMLDivElement>) => {
    if (e.pointerType === "mouse" && e.button !== 0) return;
    gesture.current = { startX: e.clientX, id: e.pointerId, moved: false };
    suppressClick.current = false;
    setPressed(true);
  };
  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    const g = gesture.current;
    const bar = barRef.current;
    if (!g || !bar || rects.length === 0) return;
    if (!g.moved) {
      if (Math.abs(e.clientX - g.startX) < DRAG_THRESHOLD) return;
      g.moved = true;
      bar.setPointerCapture(g.id);
    }
    const first = rects[0], last = rects[rects.length - 1];
    const x = Math.min(
      Math.max(e.clientX - bar.getBoundingClientRect().left, first.x + first.w / 2),
      last.x + last.w / 2,
    );
    setDrag({ x, idx: nearest(x) });
  };
  const endGesture = (commit: boolean) => {
    const g = gesture.current;
    if (g?.moved) {
      suppressClick.current = true; // le glissé ne doit pas aussi « cliquer » un onglet
      if (commit && drag) navigate(tabHref(NAV[drag.idx].key));
    }
    gesture.current = null;
    setDrag(null);
    setPressed(false);
  };
  const onClickCapture = (e: MouseEvent) => {
    // detail === 0 : activation clavier, jamais issue d'un glissé
    if (suppressClick.current && e.detail !== 0) {
      e.preventDefault();
      e.stopPropagation();
    }
    suppressClick.current = false;
  };

  const shownIdx = drag?.idx ?? activeIdx;
  const target = rects[shownIdx];
  const bubble = target
    ? { x: drag ? drag.x - target.w / 2 : target.x, w: target.w }
    : null;

  return (
    <nav className="bottom-nav" aria-label="Navigation">
      <div
        ref={barRef}
        className={`bn-bar lg${pressed ? " pressed" : ""}${drag ? " dragging" : ""}`}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={() => endGesture(true)}
        onPointerCancel={() => endGesture(false)}
        onClickCapture={onClickCapture}
      >
        <span
          className={`bn-bubble${bubble && rects.length ? " visible" : ""}`}
          style={bubble ? { transform: `translateX(${bubble.x}px)`, width: bubble.w } : undefined}
          aria-hidden="true"
        >
          {/* remonté à chaque changement d'onglet → rejoue l'étirement */}
          <span key={shownIdx} className="bn-bubble-body lg" />
        </span>
        {NAV.map(({ key, label, short, icon: Icon }, i) => (
          <Link
            key={key}
            ref={(el) => (itemRefs.current[i] = el)}
            to={tabHref(key)}
            className={`bn-item${shownIdx === i ? " active" : ""}`}
            aria-current={activeIdx === i ? "page" : undefined}
            draggable={false}
          >
            <Icon />
            <span>{short ?? label}</span>
          </Link>
        ))}
      </div>
      {/* La loupe est un onglet à part entière : « Découvrir », avec la recherche */}
      <Link
        to={tabHref("decouvrir")}
        className={`bn-search lg${onHome && tab === "decouvrir" ? " active" : ""}`}
        aria-label="Découvrir et rechercher"
        aria-current={onHome && tab === "decouvrir" ? "page" : undefined}
        draggable={false}
      >
        <SearchIcon />
      </Link>
    </nav>
  );
}
