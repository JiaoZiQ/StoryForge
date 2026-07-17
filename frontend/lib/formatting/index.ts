export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? "—"
    : new Intl.DateTimeFormat("en", {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(date);
}

export function formatScore(value: number | null | undefined): string {
  return value == null ? "—" : value.toFixed(2);
}

export function humanize(value: string | null | undefined): string {
  return value
    ? value
        .replaceAll("_", " ")
        .replace(/\b\w/g, (letter) => letter.toUpperCase())
    : "—";
}

export function clipText(value: string, maximum = 180): string {
  return value.length <= maximum
    ? value
    : `${value.slice(0, maximum - 1).trimEnd()}…`;
}
