import type { RankingRow } from "../models/ranking";

/** Muestra los puestos calculados por el servidor sin cambiar su desempate. */
export function topRankingRows(rows: RankingRow[]): RankingRow[] {
  return [...rows].sort((a, b) => a.position - b.position).slice(0, 10);
}
