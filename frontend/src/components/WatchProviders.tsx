import { useQuery } from "@tanstack/react-query";
import { api, logoUrl } from "../api";
import type { Provider } from "../types";

function dedupe(list: Provider[]): Provider[] {
  const seen = new Set<string>();
  return list.filter((p) => (seen.has(p.name) ? false : seen.add(p.name)));
}

function Logos({ items }: { items: Provider[] }) {
  return (
    <div className="prov-logos">
      {items.map((p) => {
        const url = logoUrl(p.logo_path);
        return url ? (
          <img key={p.name} src={url} alt={p.name} title={p.name} className="prov-logo" />
        ) : (
          <span key={p.name} className="prov-name">{p.name}</span>
        );
      })}
    </div>
  );
}

export default function WatchProviders({ media, tmdbId }: { media: "tv" | "movie"; tmdbId: number }) {
  const q = useQuery({
    queryKey: ["providers", media, tmdbId],
    queryFn: () => api.providers(media, tmdbId),
    staleTime: 60 * 60 * 1000, // 1 h
  });
  const p = q.data;
  if (!p) return null;

  const stream = dedupe([...p.flatrate, ...p.free, ...p.ads]);
  const rentBuy = dedupe([...p.rent, ...p.buy]);
  if (stream.length === 0 && rentBuy.length === 0) {
    return <p className="muted" style={{ fontSize: 13 }}>Aucune plateforme trouvée en France.</p>;
  }

  return (
    <div className="providers">
      <div className="prov-head">Où le regarder <span className="muted">· France</span></div>
      {stream.length > 0 && <Logos items={stream} />}
      {rentBuy.length > 0 && (
        <details className="prov-rentbuy">
          <summary className="muted">Location / Achat ({rentBuy.length})</summary>
          <Logos items={rentBuy} />
        </details>
      )}
      {p.link && (
        <a className="muted prov-jw" href={p.link} target="_blank" rel="noreferrer">
          Source : JustWatch
        </a>
      )}
    </div>
  );
}
