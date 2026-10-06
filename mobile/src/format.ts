/** 4.19 -> { euros: "4", cents: "19" } */
export function priceParts(value: number) {
  const fixed = Math.abs(value).toFixed(2);
  const [euros, cents] = fixed.split(".");
  return { euros: (value < 0 ? "-" : "") + euros, cents };
}

export const money = (n: number) => `${n.toFixed(2).replace(".", ",")} €`;

/** 9.48, "€/kg" -> "9,48 €/kg" */
export const perUnit = (n: number, label?: string | null) => `${n.toFixed(2).replace(".", ",")} ${label ?? ""}`.trim();

export const signedMoney = (n: number) => (n > 0 ? "+" : n < 0 ? "−" : "") + money(Math.abs(n));

export function distance(km?: number | null) {
  if (km === null || km === undefined) return "";
  if (km < 1) return `${Math.max(10, Math.round((km * 1000) / 10) * 10)} m`;
  return `${km.toFixed(km < 10 ? 1 : 0).replace(".", ",")} km`;
}

export function relativeDate(iso: string) {
  const days = (Date.now() - new Date(iso).getTime()) / 86400000;
  if (days < 1 / 24) return "à l'instant";
  if (days < 1) return `il y a ${Math.round(days * 24)} h`;
  if (days < 2) return "hier";
  if (days < 7) return `il y a ${Math.floor(days)} jours`;
  if (days < 30) return `il y a ${Math.floor(days / 7)} sem.`;
  return `il y a ${Math.floor(days / 30)} mois`;
}

/** Normalise une saisie de prix ("4,19" / "4.1" / "4") -> "4.19" ou null. */
export function parsePrice(input: string): string | null {
  const clean = input.replace(/\s/g, "").replace(",", ".");
  if (!/^\d{1,3}(\.\d{0,2})?$/.test(clean)) return null;
  const n = Number(clean);
  if (!isFinite(n) || n < 0.05) return null;
  return n.toFixed(2);
}

/** Clé de contrôle EAN/UPC : évite d'envoyer une lecture ratée au serveur. */
export function isValidBarcode(code: string) {
  const digits = code.replace(/\D/g, "");
  if (![8, 12, 13, 14].includes(digits.length)) return false;
  const body = digits.slice(0, -1).split("").reverse();
  const sum = body.reduce((acc, d, i) => acc + Number(d) * (i % 2 === 0 ? 3 : 1), 0);
  if ((10 - (sum % 10)) % 10 === Number(digits[digits.length - 1])) return true;
  // UPC-E (8 chiffres, commence par 0 ou 1) : validé côté serveur après expansion
  return digits.length === 8 && (digits[0] === "0" || digits[0] === "1");
}

export const PROMO_TYPES: { value: string; label: string }[] = [
  { value: "sale", label: "Promotion" },
  { value: "loyalty", label: "Prix fidélité" },
  { value: "multi_buy", label: "2+1, 3 pour 2…" },
  { value: "bundle", label: "Lot" },
  { value: "clearance", label: "Date courte" },
  { value: "coupon", label: "Bon de réduction" },
];
