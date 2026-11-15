/** Onglets de l'accueil. L'onglet actif vit dans l'URL (?tab=…), partagée par
 * les onglets du haut (desktop) et la barre de navigation du bas (mobile). */
export type Tab = "encours" | "vus" | "prochainement" | "stats";

/** `short` : libellé de la barre du bas, quand le libellé complet n'y tient pas. */
export const TABS: { key: Tab; label: string; short?: string }[] = [
  { key: "encours", label: "En cours" },
  { key: "vus", label: "Vus" },
  { key: "prochainement", label: "Prochainement", short: "À venir" },
  { key: "stats", label: "Stats" },
];

export const DEFAULT_TAB: Tab = "encours";

/** Valeur de ?tab= → onglet connu (l'onglet par défaut sinon). */
export function tabFromParam(raw: string | null): Tab {
  return TABS.some((t) => t.key === raw) ? (raw as Tab) : DEFAULT_TAB;
}

/** Lien vers un onglet (l'onglet par défaut n'a pas de paramètre). */
export function tabHref(tab: Tab): string {
  return tab === DEFAULT_TAB ? "/" : `/?tab=${tab}`;
}
