import { useQuery } from "@tanstack/react-query";
import { api, posterUrl } from "../api";
import Spinner from "../components/Spinner";
import type { UpcomingItem } from "../types";

/** "2026-07-25" → "sam. 25 juil. 2026" (format français, sans décalage de fuseau). */
function frDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  if (!y || !m || !d) return iso;
  return new Date(y, m - 1, d).toLocaleDateString("fr-FR", {
    weekday: "short", day: "numeric", month: "short", year: "numeric",
  });
}

/** Onglet « Prochainement » : sorties annoncées des séries suivies, par échéance. */
export default function Prochainement() {
  const up = useQuery({ queryKey: ["upcoming"], queryFn: api.upcoming });
  const items = up.data ?? [];
  const groups: [string, (i: UpcomingItem) => boolean][] = [
    ["Cette semaine", (i) => i.days <= 7],
    ["Ce mois-ci", (i) => i.days > 7 && i.days <= 31],
    ["Plus tard", (i) => i.days > 31],
  ];
  return (
    <>
      {up.isLoading && <Spinner />}
      {!up.isLoading && items.length === 0 && (
        <p className="muted">Aucune sortie annoncée pour tes séries.</p>
      )}
      {groups.map(([label, pred]) => {
        const g = items.filter(pred);
        if (g.length === 0) return null;
        return (
          <div key={label}>
            <h3>{label}</h3>
            {g.map((i, k) => {
              const url = posterUrl(i.poster_path);
              return (
                <div className="upcoming-row" key={k}>
                  {url && <img src={url} alt="" />}
                  <div>
                    <strong>{i.series_title}</strong> · S{String(i.season).padStart(2, "0")}E
                    {String(i.number).padStart(2, "0")}
                    <div className="muted">{i.name}</div>
                  </div>
                  <div style={{ marginLeft: "auto", textAlign: "right" }}>
                    <div>{frDate(i.air_date)}</div>
                    <div className="muted">
                      {i.days === 0 ? "aujourd'hui" : i.days === 1 ? "demain" : `dans ${i.days} j`}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        );
      })}
    </>
  );
}
