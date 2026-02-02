import { formatDate } from '@angular/common';
import { inject, LOCALE_ID, Pipe, PipeTransform } from '@angular/core';

import { ConfigService } from '@/core/services/config.service';

export type AppDateFormat = 'date' | 'datetime' | 'time';

@Pipe({
  name: 'appDate',
  standalone: true,
})
export class AppDatePipe implements PipeTransform {
  private locale = inject(LOCALE_ID);
  private configService = inject(ConfigService);

  transform(value: unknown, format: AppDateFormat = 'date'): unknown {
    if (!value || value === '') return null;

    try {
      let formatString: string;

      switch (format) {
        case 'datetime':
          formatString = `${this.configService.settings.dateFormat} HH:mm:ss`;
          break;
        case 'time':
          formatString = 'HH:mm:ss';
          break;
        case 'date':
        default:
          formatString = this.configService.settings.dateFormat;
          break;
      }

      const result = formatDate(value as string | number | Date, formatString, this.locale);
      return result;
    } catch (e) {
      console.error('[AppDatePipe] Error formatting date:', e);
      return value;
    }
  }
}
