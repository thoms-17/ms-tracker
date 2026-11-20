import { posterUrl } from "../api";

export interface RowItem {
  key: string;
  title: string | null;
  year: string | null;
  poster_path: string | null;
}

/**
 * Rangée d'affiches à faire défiler — tendances de la vitrine, suggestions « Pour toi ».
 * `onDismiss` ajoute sur chaque affiche un bouton × (« pas intéressé »).
 */
export default function TitleRow<T extends RowItem>({ title, items, onPick, onDismiss, hint }: {
  title: string;
  items: T[];
  onPick: (item: T) => void;
  onDismiss?: (item: T) => void;
  /** Infobulle de chaque affiche. */
  hint?: (item: T) => string;
}) {
  if (!items.length) return null;
  return (
    <section className="trending-section">
      <h2 className="trending-title">{title}</h2>
      <div className="trending-row">
        {items.map((it) => (
          <div className="trending-card" key={it.key}>
            <button type="button" className="trending-pick" onClick={() => onPick(it)}
              title={hint?.(it) ?? `${it.title ?? ""}${it.year ? ` (${it.year})` : ""}`}>
              {it.poster_path ? (
                <img className="trending-poster" src={posterUrl(it.poster_path, true) ?? ""}
                  alt={it.title ?? ""} loading="lazy" />
              ) : (
                <div className="trending-poster ph" />
              )}
              <span className="trending-name">{it.title}</span>
              {it.year && <span className="trending-year">{it.year}</span>}
            </button>
            {onDismiss && (
              <button type="button" className="dismiss-btn" aria-label={`Pas intéressé par ${it.title ?? "ce titre"}`}
                title="Pas intéressé" onClick={() => onDismiss(it)}>
                ×
              </button>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
