import { formatDate } from '@angular/common';
import { inject, LOCALE_ID, Pipe, PipeTransform } from '@angular/core';

import { ConfigService } from '@/core/services/config.service';

@Pipe({
  name: 'appDate',
  standalone: true,
})
export class AppDatePipe implements PipeTransform {
  private locale = inject(LOCALE_ID);
  private configService = inject(ConfigService);

  transform(value: unknown, ...args: unknown[]): unknown {
    if (!value || value === '') return null;

    try {
      const result = formatDate(
        value as string | number | Date,
        this.configService.settings.dateFormat,
        this.locale,
      );
      return result;
    } catch (e) {
      console.error('[AppDatePipe] Error formatting date:', e);
      return value;
    }
  }
}
