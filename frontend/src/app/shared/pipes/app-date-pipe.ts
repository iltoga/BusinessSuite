import { formatDate } from '@angular/common';
import { inject, LOCALE_ID, Pipe, PipeTransform } from '@angular/core';

import { APP_CONFIG } from '@/core/config/app.config';

@Pipe({
  name: 'appDate',
  standalone: true,
})
export class AppDatePipe implements PipeTransform {
  private locale = inject(LOCALE_ID);

  transform(value: unknown, ...args: unknown[]): unknown {
    if (!value || value === '') return null;
    
    // Debug log to see what's happening
    console.log('[AppDatePipe] Formatting value:', value, 'with format:', APP_CONFIG.dateFormat);
    
    try {
      const result = formatDate(value as string | number | Date, APP_CONFIG.dateFormat, this.locale);
      console.log('[AppDatePipe] Result:', result);
      return result;
    } catch (e) {
      console.error('[AppDatePipe] Error formatting date:', e);
      return value;
    }
  }
}
