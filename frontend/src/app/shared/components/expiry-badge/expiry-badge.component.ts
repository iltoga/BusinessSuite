import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { ZardBadgeComponent } from '@/shared/components/badge';

export type ExpiryStatus = 'missing' | 'expired' | 'expiring-soon' | 'valid';

@Component({
  selector: 'app-expiry-badge',
  standalone: true,
  imports: [CommonModule, ZardBadgeComponent],
  templateUrl: './expiry-badge.component.html',
  styleUrls: ['./expiry-badge.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ExpiryBadgeComponent {
  date = input<string | Date | null>(null);
  warningDays = input<number>(183);
  emptyLabel = input<string>('—');

  protected readonly parsedDate = computed(() => {
    const value = this.date();
    if (!value) return null;
    return value instanceof Date ? value : new Date(value);
  });

  protected readonly status = computed<ExpiryStatus>(() => {
    const parsed = this.parsedDate();
    if (!parsed || Number.isNaN(parsed.getTime())) return 'missing';

    const today = new Date();
    const warningMs = this.warningDays() * 24 * 60 * 60 * 1000;
    if (parsed.getTime() < today.getTime()) return 'expired';
    if (parsed.getTime() <= today.getTime() + warningMs) return 'expiring-soon';
    return 'valid';
  });

  protected readonly formattedDate = computed(() => {
    const parsed = this.parsedDate();
    if (!parsed || Number.isNaN(parsed.getTime())) return this.emptyLabel();
    return parsed.toISOString().slice(0, 10);
  });
}
