import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, posterUrl } from "../api";
import type { TrendingItem } from "../types";
import Login from "./Login";

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
        <span className="landing-logo">📺 TV Time</span>
        <button className="btn primary" onClick={() => setShowLogin(true)}>Se connecter</button>
      </header>

      <main className="landing-main">
        <section className="landing-hero">
          <h1>Les séries et films du moment</h1>
          <p className="muted">
            Découvre les tendances de la semaine. Connecte-toi pour suivre ton propre visionnage.
          </p>
        </section>

        {trending.isLoading && <p className="muted">Chargement des tendances…</p>}
        {trending.error && (
          <p className="muted">Tendances indisponibles pour le moment.</p>
        )}
        {trending.data && (
          <>
            <TrendingRow title="🔥 Séries en vogue" items={trending.data.tv}
              onPick={() => setShowLogin(true)} />
            <TrendingRow title="🎬 Films en vogue" items={trending.data.movie}
              onPick={() => setShowLogin(true)} />
          </>
        )}
      </main>

      {showLogin && <Login onClose={() => setShowLogin(false)} />}
    </div>
  );
}

function TrendingRow({ title, items, onPick }: {
  title: string; items: TrendingItem[]; onPick: () => void;
}) {
  if (!items.length) return null;
  return (
    <section className="trending-section">
      <h2 className="trending-title">{title}</h2>
      <div className="trending-row">
        {items.map((it) => (
          <button
            key={`${it.media_type}-${it.tmdb_id}`}
            className="trending-card"
            onClick={onPick}
            title={`${it.title ?? ""}${it.year ? ` (${it.year})` : ""} — connecte-toi pour suivre`}
          >
            {it.poster_path ? (
              <img className="trending-poster" src={posterUrl(it.poster_path, true) ?? ""}
                alt={it.title ?? ""} loading="lazy" />
            ) : (
              <div className="trending-poster ph" />
            )}
            <span className="trending-name">{it.title}</span>
            {it.year && <span className="trending-year">{it.year}</span>}
          </button>
        ))}
      </div>
    </section>
  );
}
