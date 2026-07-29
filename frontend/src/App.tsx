import { useEffect, useState } from "react";
import { Link, Route, Routes, useLocation, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import SearchBar from "./components/SearchBar";
import Spinner from "./components/Spinner";
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
    retry: false,
    staleTime: Infinity,
  });

  // Session expirée en cours d'usage (401 sur une requête) → repasse au login.
  useEffect(() => {
    const onUnauth = () => qc.setQueryData(["me"], null);
    window.addEventListener("auth:unauthorized", onUnauth);
    return () => window.removeEventListener("auth:unauthorized", onUnauth);
  }, [qc]);

  if (me.isLoading) return <Spinner full />;
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
    </>
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
      qc.clear(); // vide le cache (données de l'utilisateur précédent)
    },
  });

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

/** Barre de navigation flottante (mobile) — liquid glass, présente sur toutes les pages. */
function BottomNav({ onSearch }: { onSearch: () => void }) {
  const [params] = useSearchParams();
  const { pathname } = useLocation();
  const onHome = pathname === "/";
  const tab = params.get("tab") ?? "encours";
  return (
    <nav className="bottom-nav" aria-label="Navigation">
      {NAV.map(({ key, label, icon: Icon }) => (
        <Link
          key={key}
          to={`/?tab=${key}`}
          className={`bn-item${onHome && tab === key ? " active" : ""}`}
          aria-current={onHome && tab === key ? "page" : undefined}
        >
          <Icon />
          <span>{label}</span>
        </Link>
      ))}
      <button type="button" className="bn-item" onClick={onSearch}>
        <SearchIcon />
        <span>Rechercher</span>
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
