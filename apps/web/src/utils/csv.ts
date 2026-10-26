export interface CsvColumn<T> { key: string; header: string; value: (row: T) => unknown }

function cell(v: unknown): string {
  if (v === null || v === undefined) return "";
  const s = typeof v === "object" ? JSON.stringify(v) : String(v);
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export function toCsv<T>(rows: readonly T[], cols: readonly CsvColumn<T>[]): string {
  return [cols.map((c) => cell(c.header)).join(","), ...rows.map((r) => cols.map((c) => cell(c.value(r))).join(","))].join("\n") + "\n";
}
