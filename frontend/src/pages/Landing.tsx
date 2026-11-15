import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import Spinner from "../components/Spinner";
import TitleRow from "../components/TitleRow";
import type { TrendingItem } from "../types";
import Login from "./Login";

const rangee = (items: TrendingItem[]) => items.map((t) => ({ ...t, key: `${t.media_type}-${t.tmdb_id}` }));
const invite = (t: TrendingItem) =>
  `${t.title ?? ""}${t.year ? ` (${t.year})` : ""} — connecte-toi pour suivre`;

/** Vitrine publique (non connecté) : séries & films en vogue + accès à la connexion. */
export default function Landing() {
  const [showLogin, setShowLogin] = useState(false);
  const trending = useQuery({
    queryKey: ["trending"],
    queryFn: api.trending,
    staleTime: 60 * 60 * 1000, // 1 h (aligné sur le cache back)
  });

  return (
    <div className="landing">
      <header className="landing-header">
        <span className="landing-logo">MS Tracker</span>
        <button className="btn primary" onClick={() => setShowLogin(true)}>Se connecter</button>
      </header>

      <main className="landing-main">
        <section className="landing-hero">
          <h1>Les séries et films du moment</h1>
          <p className="muted">
            Découvre les tendances de la semaine. Connecte-toi pour suivre ton propre visionnage.
          </p>
        </section>

        {trending.isLoading && <Spinner />}
        {trending.error && (
          <p className="muted">Tendances indisponibles pour le moment.</p>
        )}
        {trending.data && (
          <>
            <TitleRow title="Séries en vogue" items={rangee(trending.data.tv)}
              onPick={() => setShowLogin(true)} hint={invite} />
            <TitleRow title="Films en vogue" items={rangee(trending.data.movie)}
              onPick={() => setShowLogin(true)} hint={invite} />
          </>
        )}
      </main>

      {showLogin && <Login onClose={() => setShowLogin(false)} />}
    </div>
  );
}
