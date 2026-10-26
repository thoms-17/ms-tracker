import { useEffect, useState } from "react";
import { Link, Route, Routes } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "./api";
import { clearPersistedCache } from "./persist";
import AutoSync from "./components/AutoSync";
import BottomNav from "./components/BottomNav";
import OfflineGate from "./components/OfflineGate";
import SearchBar from "./components/SearchBar";
import Spinner from "./components/Spinner";
import Toast from "./components/Toast";
import UserMenu from "./components/UserMenu";
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
