const currencyFormatters = new Map<string, Intl.NumberFormat>();

export function money(value: number | null | undefined, currency = "USD"): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  let f = currencyFormatters.get(currency);
  if (!f) {
    f = new Intl.NumberFormat("en-US", { style: "currency", currency });
    currencyFormatters.set(currency, f);
  }
  return f.format(value);
}

export function compactMoney(value: number): string {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", notation: "compact", maximumFractionDigits: 1 }).format(value);
}

export function number(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(value);
}

export function percent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "—";
  return `${value.toFixed(digits)}%`;
}

export function signedPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return "n/a";
  return `${value > 0 ? "+" : ""}${value.toFixed(1)}%`;
}

export function date(value: string | null | undefined, opts: Intl.DateTimeFormatOptions = { dateStyle: "medium" }): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en-US", opts).format(new Date(value));
}

export function dateTime(value: string | null | undefined): string {
  return date(value, { dateStyle: "medium", timeStyle: "short" });
}

export function relative(value: string): string {
  const diff = (Date.now() - new Date(value).getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 86400 * 30) return `${Math.floor(diff / 86400)}d ago`;
  return date(value);
}

export function titleCase(value: string): string {
  return value.replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function discountPercent(price: number, final: number): number {
  if (!price || final >= price) return 0;
  return Math.round((1 - final / price) * 100);
}
