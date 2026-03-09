/**
 * Type guard and conversion utilities
 */

/**
 * Convert a value to a number, returning a default if invalid
 * 
 * @param value - The value to convert
 * @param defaultValue - Default value if conversion fails
 * @returns Converted number or default
 * 
 * @example
 * asNumber('123') // 123
 * asNumber(null, 0) // 0
 * asNumber('abc', -1) // -1
 */
export function asNumber(value: unknown, defaultValue = 0): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : defaultValue;
}

/**
 * Convert a value to a nullable number
 * 
 * @param value - The value to convert
 * @returns Converted number or null
 * 
 * @example
 * asNullableNumber('123') // 123
 * asNullableNumber(null) // null
 * asNullableNumber('') // null
 */
export function asNullableNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/**
 * Convert a value to a string, returning a default if null/undefined
 * 
 * @param value - The value to convert
 * @param defaultValue - Default value if conversion fails
 * @returns Converted string or default
 * 
 * @example
 * asString(123) // '123'
 * asString(null, 'N/A') // 'N/A'
 */
export function asString(value: unknown, defaultValue = ''): string {
  return value != null ? String(value) : defaultValue;
}

/**
 * Convert a value to a nullable string
 * 
 * @param value - The value to convert
 * @returns Converted string or null
 * 
 * @example
 * asNullableString(123) // '123'
 * asNullableString(null) // null
 */
export function asNullableString(value: unknown): string | null {
  return value != null ? String(value) : null;
}

/**
 * Convert a value to an array
 * 
 * @param value - The value to convert
 * @returns Array or empty array
 * 
 * @example
 * asArray([1, 2, 3]) // [1, 2, 3]
 * asArray(null) // []
 * asArray('test') // []
 */
export function asArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? value : [];
}

/**
 * Convert a value to a record (object)
 * 
 * @param value - The value to convert
 * @returns Record or empty object
 * 
 * @example
 * asRecord({ a: 1 }) // { a: 1 }
 * asRecord(null) // {}
 */
export function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

/**
 * Convert a value to a boolean
 * 
 * @param value - The value to convert
 * @param defaultValue - Default value if conversion fails
 * @returns Converted boolean or default
 * 
 * @example
 * asBoolean(true) // true
 * asBoolean('true') // true
 * asBoolean('yes') // true
 * asBoolean('1') // true
 * asBoolean(null, false) // false
 */
export function asBoolean(value: unknown, defaultValue = false): boolean {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'string') {
    return ['true', '1', 'yes', 'y'].includes(value.toLowerCase());
  }
  if (typeof value === 'number') {
    return value !== 0;
  }
  return defaultValue;
}

/**
 * Convert a value to a nullable boolean
 * 
 * @param value - The value to convert
 * @returns Converted boolean or null
 * 
 * @example
 * asNullableBoolean('true') // true
 * asNullableBoolean(null) // null
 */
export function asNullableBoolean(value: unknown): boolean | null {
  if (value === null || value === undefined) return null;
  return asBoolean(value);
}

/**
 * Safely access a nested property by path
 * 
 * @param obj - The object to access
 * @param path - Dot-separated path (e.g., 'user.address.city')
 * @param defaultValue - Default value if path doesn't exist
 * @returns Value at path or default
 * 
 * @example
 * getNestedProperty({ user: { name: 'John' } }, 'user.name') // 'John'
 * getNestedProperty({}, 'user.name', 'Unknown') // 'Unknown'
 */
export function getNestedProperty<T = unknown>(
  obj: Record<string, unknown>,
  path: string,
  defaultValue?: T
): T | undefined {
  const keys = path.split('.');
  let current: unknown = obj;
  
  for (const key of keys) {
    if (current == null || typeof current !== 'object') {
      return defaultValue;
    }
    current = (current as Record<string, unknown>)[key];
  }
  
  return (current as T) ?? defaultValue;
}

/**
 * Check if a value is null or undefined
 */
export function isNullOrUndefined(value: unknown): value is null | undefined {
  return value === null || value === undefined;
}

/**
 * Check if a value is empty (null, undefined, empty string, empty array, or empty object)
 */
export function isEmpty(value: unknown): boolean {
  if (value === null || value === undefined) return true;
  if (typeof value === 'string') return value.trim() === '';
  if (Array.isArray(value)) return value.length === 0;
  if (typeof value === 'object') return Object.keys(value).length === 0;
  return false;
}

/**
 * Deep clone an object
 */
export function deepClone<T>(obj: T): T {
  if (obj === null || typeof obj !== 'object') return obj;
  if (obj instanceof Date) return new Date(obj.getTime()) as T;
  if (Array.isArray(obj)) return obj.map(item => deepClone(item)) as T;
  
  const cloned: Record<string, unknown> = {};
  for (const key in obj) {
    if (Object.prototype.hasOwnProperty.call(obj, key)) {
      cloned[key] = deepClone(obj[key]);
    }
  }
  return cloned as T;
}
