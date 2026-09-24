import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { MouseEvent, PointerEvent } from "react";
import { Link, Route, Routes, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "./api";
import { useCloseOnScroll } from "./hooks";
import { clearPersistedCache } from "./persist";
import AutoSync from "./components/AutoSync";
import SearchBar from "./components/SearchBar";
import Spinner from "./components/Spinner";
import Toast from "./components/Toast";
import VersionInfo from "./components/VersionInfo";
import Landing from "./pages/Landing";
import Register from "./pages/Register";
import VerifyEmail from "./pages/VerifyEmail";
import ResetPassword from "./pages/ResetPassword";
import Suivi from "./pages/Suivi";
import SeriesDetail from "./pages/SeriesDetail";
import SeriesPreview from "./pages/SeriesPreview";
import MoviePreview from "./pages/MoviePreview";

export default function App() {
  const qc = useQueryClient();
  const [searchOpen, setSearchOpen] = useState(false); // overlay de recherche (loupe mobile)
  const me = useQuery({
    queryKey: ["me"],
    queryFn: api.me,
    staleTime: Infinity,
    // Au réveil de la PWA (iOS), la 1re requête part souvent avant que le réseau
    // soit prêt. Un échec réseau ne veut pas dire « déconnecté » : on réessaie.
    // Seul un 401 est une vraie fin de session → inutile d'insister.
    retry: (failureCount, error) =>
      !(error instanceof ApiError && error.status === 401) && failureCount < 3,
    retryDelay: (n) => Math.min(1000 * 2 ** n, 5000),
  });

  // Session expirée en cours d'usage (401 sur une requête) → repasse au login.
  // On efface aussi la copie locale : plus de session valide, plus de raison de
  // garder l'historique sur l'appareil (un autre compte pourrait s'y connecter).
  useEffect(() => {
    const onUnauth = () => {
      qc.setQueryData(["me"], null);
      clearPersistedCache();
    };
    window.addEventListener("auth:unauthorized", onUnauth);
    return () => window.removeEventListener("auth:unauthorized", onUnauth);
  }, [qc]);

  if (me.isLoading) return <Spinner full />;
  // Échec réseau (≠ 401) : on ne déconnecte pas l'utilisateur pour autant.
  // Sans ça, un simple réveil hors ligne renverrait vers l'écran de connexion.
  if (me.error && !(me.error instanceof ApiError && me.error.status === 401)) {
    return <OfflineGate onRetry={() => me.refetch()} pending={me.isFetching} />;
  }
  if (!me.data) {
    // Non connecté : vitrine + pages publiques d'inscription / vérification d'email.
    return (
      <Routes>
        <Route path="/register/:token" element={<Register />} />
        <Route path="/verify/:token" element={<VerifyEmail />} />
        <Route path="/reset/:token" element={<ResetPassword />} />
        <Route path="*" element={<Landing />} />
      </Routes>
    );
  }

  return (
    <>
      <header>
        <Link to="/"><h1>MS Tracker</h1></Link>
        <SearchBar expanded={searchOpen} setExpanded={setSearchOpen} />
        <UserMenu username={me.data.username} />
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Suivi />} />
          <Route path="/series/:uuid" element={<SeriesDetail />} />
          <Route path="/tmdb/tv/:tmdbId" element={<SeriesPreview />} />
          <Route path="/tmdb/movie/:tmdbId" element={<MoviePreview />} />
        </Routes>
      </main>
      <BottomNav onSearch={() => setSearchOpen(true)} />
      <Toast />
      <AutoSync />
    </>
  );
}

/**
 * Serveur injoignable au démarrage (réseau coupé, PWA qui se réveille).
 * On reste sur un écran neutre : la session est probablement toujours valide,
 * ce serait une erreur de renvoyer l'utilisateur vers la page de connexion.
 */
function OfflineGate({ onRetry, pending }: { onRetry: () => void; pending: boolean }) {
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

/** Pastille du profil connecté + menu de déconnexion. */
function UserMenu({ username }: { username: string }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const logout = useMutation({
    mutationFn: api.logout,
    onSuccess: () => {
      qc.setQueryData(["me"], null); // repasse au login
      qc.clear(); // vide le cache mémoire (données de l'utilisateur précédent)
      clearPersistedCache(); // …et sa copie sur l'appareil, sinon elle survivrait
    },
  });

  // Popover ancré à l'avatar : un défilement le décrocherait de son bouton.
  useCloseOnScroll(() => setOpen(false), open);

  return (
    <div className="usermenu">
      <button
        className="usermenu-btn" onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu" aria-expanded={open} title={username}
      >
        <span className="avatar">{username.slice(0, 1).toUpperCase()}</span>
        <span className="usermenu-name">{username}</span>
      </button>
      {open && (
        <>
          <div className="menu-backdrop" onClick={() => setOpen(false)} />
          <div className="usermenu-pop" role="menu">
            <div className="usermenu-head">
              Connecté en tant que<br /><strong>{username}</strong>
            </div>
            <button
              className="menu-item danger" disabled={logout.isPending}
              onClick={() => logout.mutate()}
            >
              Se déconnecter
            </button>
            <VersionInfo />
          </div>
        </>
      )}
    </div>
  );
}

const NAV = [
  { key: "encours", label: "En cours", icon: PlayIcon },
  { key: "vus", label: "Vus", icon: CheckIcon },
  { key: "prochainement", label: "Prochainement", icon: CalendarIcon },
] as const;

/** Seuil (px) au-delà duquel un appui sur la barre devient un glissé. */
const DRAG_THRESHOLD = 6;

/**
 * Barre de navigation flottante (mobile) — liquid glass façon iOS 26, présente sur
 * toutes les pages. Une bulle de verre unique glisse d'un onglet à l'autre (ressort
 * CSS) ; on peut aussi faire glisser le doigt le long de la barre pour changer d'onglet.
 */
function BottomNav({ onSearch }: { onSearch: () => void }) {
  const [params] = useSearchParams();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const onHome = pathname === "/";
  const tab = params.get("tab") ?? "encours";
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
      if (commit && drag) navigate(`/?tab=${NAV[drag.idx].key}`);
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
        {NAV.map(({ key, label, icon: Icon }, i) => (
          <Link
            key={key}
            ref={(el) => (itemRefs.current[i] = el)}
            to={`/?tab=${key}`}
            className={`bn-item${shownIdx === i ? " active" : ""}`}
            aria-current={activeIdx === i ? "page" : undefined}
            draggable={false}
          >
            <Icon />
            <span>{label}</span>
          </Link>
        ))}
      </div>
      <button type="button" className="bn-search lg" onClick={onSearch} aria-label="Rechercher">
        <SearchIcon />
      </button>
    </nav>
  );
}

/* Icônes (SVG inline, currentColor) */
function PlayIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="2" y="4" width="20" height="14" rx="3" />
      <path d="M10 9l4 2.5-4 2.5z" fill="currentColor" stroke="none" />
      <path d="M8 21h8" />
    </svg>
  );
}
function CheckIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="9" />
      <path d="M8.5 12.5l2.5 2.5 4.5-5" />
    </svg>
  );
}
function CalendarIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="3" y="4.5" width="18" height="16" rx="3" />
      <path d="M3 9h18M8 3v3M16 3v3" />
    </svg>
  );
}
function SearchIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="11" cy="11" r="7" />
      <path d="M21 21l-4.3-4.3" />
    </svg>
  );
}
