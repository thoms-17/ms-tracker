/** Mise en forme partagée : codes d'épisode et dates en français. */

/** (2, 5) → "S02E05". */
export function episodeCode(season: number, number: number): string {
  return `S${String(season).padStart(2, "0")}E${String(number).padStart(2, "0")}`;
}

/** "2026-07-25" → "sam. 25 juil. 2026" (date seule, sans décalage de fuseau). */
export function frDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  if (!y || !m || !d) return iso;
  return new Date(y, m - 1, d).toLocaleDateString("fr-FR", {
    weekday: "short", day: "numeric", month: "short", year: "numeric",
  });
}

/** "2026-08-19T21:03:00" → "aujourd'hui", "hier", "il y a 3 j", "19 août" au-delà d'une semaine. */
export function relativeDay(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const jours = Math.floor((Date.now() - d.getTime()) / 86_400_000);
  if (jours <= 0) return "aujourd'hui";
  if (jours === 1) return "hier";
  if (jours < 7) return `il y a ${jours} j`;
  return d.toLocaleDateString("fr-FR", { day: "numeric", month: "short" });
}

/** "2026-08-19T21:03:00" → "août 26". */
export function monthYear(iso: string | null): string {
  return iso ? new Date(iso).toLocaleDateString("fr-FR", { month: "short", year: "2-digit" }) : "";
}

/** 2280 → "38 h" ; 45 → "45 min" (durées de visionnage, arrondies à l'heure). */
export function hours(minutes: number): string {
  if (minutes < 60) return `${Math.round(minutes)} min`;
  return `${Math.round(minutes / 60).toLocaleString("fr-FR")} h`;
}
