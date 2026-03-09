import { Injectable } from '@angular/core';
import { catchError, MonoTypeOperatorFunction, of, pipe, throwError } from 'rxjs';

import { GlobalToastService } from '@/core/services/toast.service';
import { extractServerErrorMessage } from '@/shared/utils/form-errors';

/**
 * Options for error handling
 */
export interface HandleErrorOptions {
  /** Custom error message */
  message?: string;
  /** Show toast notification (default: true) */
  showToast?: boolean;
  /** Log error to console (default: true in dev mode) */
  logError?: boolean;
  /** Return this value on error instead of null */
  returnValue?: any;
  /** Custom error handler function */
  onError?: (error: any) => void;
}

/**
 * RxJS operator for standardized error handling
 * 
 * @param toast - Toast service for notifications
 * @param defaultMessage - Default error message
 * @param options - Additional error handling options
 * 
 * @example
 * ```typescript
 * // Basic usage
 * this.service.getData()
 *   .pipe(handleError(this.toast, 'Failed to load data'))
 *   .subscribe();
 * 
 * // With custom options
 * this.service.saveData(data)
 *   .pipe(
 *     handleError(this.toast, 'Save failed', {
 *       showToast: true,
 *       logError: true,
 *       onError: (error) => console.error('Save error:', error),
 *     })
 *   )
 *   .subscribe();
 * 
 * // With return value on error
 * this.service.getOptionalData()
 *   .pipe(
 *     handleError(this.toast, 'Failed to load', { returnValue: [] })
 *   )
 *   .subscribe(data => console.log(data)); // Will receive [] on error
 * ```
 */
export function handleError<T>(
  toast: GlobalToastService,
  defaultMessage = 'Operation failed',
  options?: HandleErrorOptions,
): (source: any) => any {
  return catchError((error) => {
    // Extract user-friendly error message
    const message = extractServerErrorMessage(error) || options?.message || defaultMessage;

    // Show toast notification
    if (options?.showToast !== false) {
      toast.error(message);
    }

    // Log error if enabled
    if (options?.logError !== false) {
      console.error('[HTTP Error]', error);
    }

    // Call custom error handler if provided
    options?.onError?.(error);

    // Return error observable with custom return value or null
    const returnValue = options?.returnValue ?? null;
    return of(returnValue);
  });
}

/**
 * Error handler that re-throws the error after showing toast
 * Use when you want to show error but still let caller handle it
 */
export function handleErrorAndThrow(
  toast: GlobalToastService,
  defaultMessage = 'Operation failed',
): (source: any) => any {
  return catchError((error) => {
    const message = extractServerErrorMessage(error) || defaultMessage;
    toast.error(message);
    console.error('[HTTP Error]', error);
    return throwError(() => error);
  });
}

/**
 * Error handler specifically for silent operations (no toast)
 */
export function handleSilentError<T>(
  returnValue?: T,
): (source: any) => any {
  return catchError((error) => {
    console.error('[Silent Error]', error);
    return of(returnValue ?? null);
  });
}

/**
 * Injectable error handler for use in services
 */
@Injectable({ providedIn: 'root' })
export class ErrorHandlerService {
  constructor(private toast: GlobalToastService) {}

  /**
   * Create error handler with pre-configured toast service
   */
  create<T>(defaultMessage = 'Operation failed', options?: HandleErrorOptions) {
    return handleError<T>(this.toast, defaultMessage, options);
  }

  /**
   * Create error handler that re-throws
   */
  createAndThrow(defaultMessage = 'Operation failed') {
    return handleErrorAndThrow(this.toast, defaultMessage);
  }

  /**
   * Create silent error handler
   */
  createSilent<T>(returnValue?: T) {
    return handleSilentError<T>(returnValue);
  }
}
