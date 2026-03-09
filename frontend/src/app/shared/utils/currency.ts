/**
 * Currency formatting utilities
 */

export interface FormatCurrencyOptions {
  currency?: string;
  locale?: string;
  minimumFractionDigits?: number;
  maximumFractionDigits?: number;
}

/**
 * Format a numeric value as currency
 * 
 * @param value - The value to format (number, string, or null/undefined)
 * @param options - Formatting options
 * @returns Formatted currency string or '—' for invalid/empty values
 * 
 * @example
 * formatCurrency(1000000) // 'IDR 1.000.000'
 * formatCurrency(1000000, { currency: 'USD' }) // '$1,000,000.00'
 * formatCurrency(null) // '—'
 */
export function formatCurrency(
  value: string | number | null | undefined,
  options: FormatCurrencyOptions = {}
): string {
  if (value === null || value === undefined || value === '') return '—';
  
  const num = Number(value);
  if (Number.isNaN(num)) return String(value);
  
  const {
    currency = 'IDR',
    locale = 'id-ID',
    minimumFractionDigits = 0,
    maximumFractionDigits = 0,
  } = options;
  
  try {
    return new Intl.NumberFormat(locale, {
      style: 'currency',
      currency,
      minimumFractionDigits,
      maximumFractionDigits,
    }).format(num);
  } catch {
    return `${currency} ${num.toLocaleString(locale)}`;
  }
}

/**
 * Parse a currency string to a number
 * 
 * @param value - The currency string to parse
 * @returns Parsed number or null if invalid
 * 
 * @example
 * parseCurrency('IDR 1.000.000') // 1000000
 * parseCurrency('$1,000,000') // 1000000
 */
export function parseCurrency(value: string): number | null {
  if (!value) return null;
  const cleaned = value.replace(/[^0-9.-]/g, '');
  const parsed = parseFloat(cleaned);
  return Number.isFinite(parsed) ? parsed : null;
}

/**
 * Format a value as percentage
 * 
 * @param value - The value to format (0-1 or 0-100)
 * @param options - Formatting options
 * @returns Formatted percentage string
 * 
 * @example
 * formatPercentage(0.75) // '75%'
 * formatPercentage(75, { isDecimal: false }) // '75%'
 */
export function formatPercentage(
  value: number | null | undefined,
  options: { isDecimal?: boolean; locale?: string } = {}
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  
  const { isDecimal = true, locale = 'en-US' } = options;
  const num = isDecimal ? value * 100 : value;
  
  try {
    return new Intl.NumberFormat(locale, {
      style: 'percent',
      minimumFractionDigits: 0,
      maximumFractionDigits: 2,
    }).format(num / 100);
  } catch {
    return `${Math.round(num)}%`;
  }
}
