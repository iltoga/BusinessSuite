/**
 * Date parsing and formatting utilities
 */

export interface ParseDateOptions {
  formats?: ('ISO' | 'day-first' | 'month-first' | 'generic')[];
  strict?: boolean;
}

/**
 * Parse a value to a Date object
 *
 * @param value - The value to parse (string, Date, or null/undefined)
 * @param options - Parsing options
 * @returns Parsed Date object or null if invalid
 *
 * @example
 * parseDate('2024-01-15') // Date(2024-01-15)
 * parseDate('15-01-2024', { formats: ['day-first'] }) // Date(2024-01-15)
 * parseDate(null) // null
 */
export function parseDate(value: unknown, options: ParseDateOptions = {}): Date | null {
  // Handle Date objects
  if (value instanceof Date) {
    return isNaN(value.getTime()) ? null : value;
  }

  // Handle non-string values
  if (typeof value !== 'string') return null;

  const trimmed = value.trim();
  if (!trimmed) return null;

  const { formats = ['ISO'], strict = false } = options;

  // Try ISO format (YYYY-MM-DD)
  if (formats.includes('ISO')) {
    const isoMatch = trimmed.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
    if (isoMatch) {
      const [, year, month, day] = isoMatch.map(Number);
      const date = new Date(year, month - 1, day);
      if (date.getFullYear() === year && date.getMonth() === month - 1 && date.getDate() === day) {
        return date;
      }
    }
  }

  // Try day-first format (DD-MM-YYYY or DD/MM/YYYY)
  if (formats.includes('day-first')) {
    const dayFirstMatch = trimmed.match(/^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$/);
    if (dayFirstMatch) {
      const [, day, month, year] = dayFirstMatch.map(Number);
      const date = new Date(year, month - 1, day);
      if (date.getFullYear() === year && date.getMonth() === month - 1 && date.getDate() === day) {
        return date;
      }
    }
  }

  // Try month-first format (MM-DD-YYYY or MM/DD/YYYY)
  if (formats.includes('month-first')) {
    const monthFirstMatch = trimmed.match(/^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$/);
    if (monthFirstMatch) {
      const [, month, day, year] = monthFirstMatch.map(Number);
      const date = new Date(year, month - 1, day);
      if (date.getFullYear() === year && date.getMonth() === month - 1 && date.getDate() === day) {
        return date;
      }
    }
  }

  // Try generic parsing as last resort
  if (formats.includes('generic')) {
    const parsed = new Date(trimmed);
    if (!isNaN(parsed.getTime())) {
      return strict ? null : new Date(parsed.getFullYear(), parsed.getMonth(), parsed.getDate());
    }
  }

  return null;
}

/**
 * Format a Date object to string
 *
 * @param date - The date to format
 * @param format - Output format
 * @returns Formatted date string or empty string for null dates
 *
 * @example
 * formatDate(new Date(2024, 0, 15), 'yyyy-MM-dd') // '2024-01-15'
 * formatDate(new Date(2024, 0, 15), 'dd-MM-yyyy') // '15-01-2024'
 */
export function formatDate(date: Date | null | undefined, format = 'yyyy-MM-dd'): string {
  if (!date) return '';

  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');

  switch (format) {
    case 'yyyy-MM-dd':
      return `${year}-${month}-${day}`;
    case 'dd-MM-yyyy':
      return `${day}-${month}-${year}`;
    case 'dd/MM/yyyy':
      return `${day}/${month}/${year}`;
    case 'MM/dd/yyyy':
      return `${month}/${day}/${year}`;
    case 'yyyy-MM':
      return `${year}-${month}`;
    case 'MM-yyyy':
      return `${month}-${year}`;
    default:
      return `${year}-${month}-${day}`;
  }
}

/**
 * Check if a date is today
 */
export function isToday(date: Date | null | undefined): boolean {
  if (!date) return false;
  const today = new Date();
  return (
    date.getFullYear() === today.getFullYear() &&
    date.getMonth() === today.getMonth() &&
    date.getDate() === today.getDate()
  );
}

/**
 * Check if a date is in the past
 */
export function isPast(date: Date | null | undefined): boolean {
  if (!date) return false;
  return date.getTime() < new Date().getTime();
}

/**
 * Check if a date is in the future
 */
export function isFuture(date: Date | null | undefined): boolean {
  if (!date) return false;
  return date.getTime() > new Date().getTime();
}

/**
 * Get the difference in days between two dates
 */
export function daysDifference(
  date1: Date | null | undefined,
  date2: Date | null | undefined,
): number {
  if (!date1 || !date2) return 0;
  const msPerDay = 24 * 60 * 60 * 1000;
  return Math.floor((date2.getTime() - date1.getTime()) / msPerDay);
}

/**
 * Add days to a date
 */
export function addDays(date: Date, days: number): Date {
  const result = new Date(date);
  result.setDate(result.getDate() + days);
  return result;
}

// ─── API Date Utilities ────────────────────────────────────────────────
// The functions below are the canonical helpers for API-layer date values
// (ISO "YYYY-MM-DD" strings and locale-aware display strings).  They
// replace identical private implementations that were duplicated across
// multiple components.

const SUPPORTED_DATE_FORMATS = ['dd-MM-yyyy', 'yyyy-MM-dd', 'dd/MM/yyyy', 'MM/dd/yyyy'] as const;
export type SupportedDateFormat = (typeof SUPPORTED_DATE_FORMATS)[number];

/**
 * Normalize a user/config date-format string to a known Angular format.
 * Falls back to `'dd-MM-yyyy'` if unrecognised.
 */
export function normalizeDateFormat(format: string | null | undefined): SupportedDateFormat {
  const normalized = (format ?? '').trim();
  if ((SUPPORTED_DATE_FORMATS as readonly string[]).includes(normalized)) {
    return normalized as SupportedDateFormat;
  }
  return 'dd-MM-yyyy';
}

/**
 * Parse any API date value (Date | string | null/undefined) into a local
 * midnight Date, or `null` when the input is invalid.
 *
 * Handles:
 *  - `Date` instances (returns a local-midnight copy)
 *  - ISO `"YYYY-MM-DD"` strings (strict parse with calendar validation)
 *  - Generic date strings via `new Date()` as a fallback
 */
export function parseApiDate(value: unknown): Date | null {
  if (value instanceof Date && !Number.isNaN(value.getTime())) {
    return new Date(value.getFullYear(), value.getMonth(), value.getDate());
  }
  if (typeof value !== 'string') {
    return null;
  }
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  const match = trimmed.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
  if (!match) {
    const parsed = new Date(trimmed);
    if (Number.isNaN(parsed.getTime())) {
      return null;
    }
    return new Date(parsed.getFullYear(), parsed.getMonth(), parsed.getDate());
  }
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const date = new Date(year, month - 1, day);
  if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) {
    return null;
  }
  return date;
}

/**
 * Format a `Date` to an ISO API string (`"YYYY-MM-DD"`).
 */
export function formatDateForApi(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, '0');
  const day = String(value.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

/**
 * Convert an unknown value to an ISO API date string, or `null`.
 * Shorthand for `parseApiDate` → `formatDateForApi`.
 */
export function toApiDate(value: unknown): string | null {
  const parsed = parseApiDate(value);
  if (!parsed) {
    return null;
  }
  return formatDateForApi(parsed);
}

/**
 * Parse an ISO `"YYYY-MM-DD"` string into a **UTC** midnight Date, or `null`.
 * Stricter than `parseApiDate` — only accepts `YYYY-MM-DD` (dash separated, 3 parts).
 */
export function parseIsoDate(value?: string | null): Date | null {
  if (!value) {
    return null;
  }
  const parts = value.split('-');
  if (parts.length !== 3) {
    return null;
  }
  const year = Number(parts[0]);
  const month = Number(parts[1]);
  const day = Number(parts[2]);
  if (!Number.isFinite(year) || !Number.isFinite(month) || !Number.isFinite(day)) {
    return null;
  }
  return new Date(Date.UTC(year, month - 1, day));
}

/**
 * Check whether `value` falls within `[start, end]` (inclusive, date-only comparison).
 */
export function isDateInRange(value: Date, start: Date, end: Date): boolean {
  const dateValue = new Date(value.getFullYear(), value.getMonth(), value.getDate()).getTime();
  const startValue = new Date(start.getFullYear(), start.getMonth(), start.getDate()).getTime();
  const endValue = new Date(end.getFullYear(), end.getMonth(), end.getDate()).getTime();
  return dateValue >= startValue && dateValue <= endValue;
}

/**
 * Format an ISO API date string for locale-aware display using an Angular `formatDate`
 * callback.
 *
 * @param value   ISO date string (e.g. `"2024-06-15"`)
 * @param angularFormatDate  The `formatDate` function from `@angular/common`
 * @param dateFormat  The user-configured format string (normalised internally)
 * @param locale  The Angular LOCALE_ID value
 */
export function formatDateForDisplay(
  value: string | null | undefined,
  angularFormatDate: (value: string | number | Date, format: string, locale: string) => string,
  dateFormat: string | null | undefined,
  locale: string,
): string {
  if (!value) {
    return '—';
  }
  const parsed = parseApiDate(value);
  if (!parsed) {
    return value;
  }
  return angularFormatDate(parsed, normalizeDateFormat(dateFormat), locale);
}

/**
 * Get today's date as midnight in a specific IANA timezone.
 * Created as a UTC Date so comparisons with `parseIsoDate` results are consistent.
 *
 * @param timezone IANA timezone string (default: `'Asia/Singapore'`)
 */
export function getTodayInTimezoneDate(timezone = 'Asia/Singapore'): Date {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: timezone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date());
  const year = Number(parts.find((part) => part.type === 'year')?.value);
  const month = Number(parts.find((part) => part.type === 'month')?.value);
  const day = Number(parts.find((part) => part.type === 'day')?.value);
  if (!Number.isFinite(year) || !Number.isFinite(month) || !Number.isFinite(day)) {
    return new Date();
  }
  return new Date(Date.UTC(year, month - 1, day));
}
