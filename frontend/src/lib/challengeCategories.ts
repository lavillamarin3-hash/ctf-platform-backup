/** Categorías existentes y personalizadas, sin estado local oculto ni tabla adicional. */
export function normalizeChallengeCategory(value: string): string {
  return value.trim().replace(/\s+/g, " ").toUpperCase();
}

export function isValidChallengeCategory(value: string): boolean {
  if (/[\r\n\t]/.test(value)) return false;
  const normalized = normalizeChallengeCategory(value);
  return normalized.length >= 2 && normalized.length <= 48 &&
    /^[A-ZÁÉÍÓÚÜÑ0-9][A-ZÁÉÍÓÚÜÑ0-9 /_-]*$/.test(normalized);
}

export function challengeCategoryOptions(defaults: string[], existing: string[], selected: string): string[] {
  return [...new Set([...defaults, ...existing, selected].map(normalizeChallengeCategory).filter(Boolean))]
    .sort((a, b) => a.localeCompare(b, "es"));
}
