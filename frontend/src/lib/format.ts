const currency = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
const currencyCents = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' });
const dateFmt = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
const dateTimeFmt = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  day: 'numeric',
  year: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
});
const relative = new Intl.RelativeTimeFormat('en-US', { numeric: 'auto' });

/** Money arrives from the API as a decimal string. */
export function money(value: string | number | null | undefined, cents = false): string {
  if (value == null) return '—';
  const n = typeof value === 'string' ? Number(value) : value;
  return (cents ? currencyCents : currency).format(n);
}

export function date(value: string | null | undefined): string {
  return value ? dateFmt.format(new Date(value)) : '—';
}

export function dateTime(value: string | null | undefined): string {
  return value ? dateTimeFmt.format(new Date(value)) : '—';
}

export function timeAgo(value: string | null | undefined, now = Date.now()): string {
  if (!value) return '—';
  const seconds = (new Date(value).getTime() - now) / 1000;
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ['year', 31_536_000],
    ['month', 2_592_000],
    ['week', 604_800],
    ['day', 86_400],
    ['hour', 3_600],
    ['minute', 60],
  ];
  for (const [unit, size] of units) {
    if (Math.abs(seconds) >= size) return relative.format(Math.round(seconds / size), unit);
  }
  return 'just now';
}

export function score(value: number | null | undefined): string {
  return value == null ? '—' : String(Math.round(value));
}

/** "credit_balance_refund" → "Credit balance refund" */
export function label(value: string | null | undefined): string {
  if (!value) return '—';
  return value.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase());
}
