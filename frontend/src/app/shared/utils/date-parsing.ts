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
export function parseDate(
  value: unknown,
  options: ParseDateOptions = {}
): Date | null {
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
    case 'yyyy-MM-dd': return `${year}-${month}-${day}`;
    case 'dd-MM-yyyy': return `${day}-${month}-${year}`;
    case 'dd/MM/yyyy': return `${day}/${month}/${year}`;
    case 'MM/dd/yyyy': return `${month}/${day}/${year}`;
    case 'yyyy-MM': return `${year}-${month}`;
    case 'MM-yyyy': return `${month}-${year}`;
    default: return `${year}-${month}-${day}`;
  }
}

/**
 * Check if a date is today
 */
export function isToday(date: Date | null | undefined): boolean {
  if (!date) return false;
  const today = new Date();
  return date.getFullYear() === today.getFullYear() &&
         date.getMonth() === today.getMonth() &&
         date.getDate() === today.getDate();
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
export function daysDifference(date1: Date | null | undefined, date2: Date | null | undefined): number {
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
