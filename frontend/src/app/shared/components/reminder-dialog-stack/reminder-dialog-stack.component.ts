import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject } from '@angular/core';

import { ReminderDialogService } from '@/core/services/reminder-dialog.service';
import { ZardIconComponent } from '@/shared/components/icon';

@Component({
  selector: 'app-reminder-dialog-stack',
  standalone: true,
  imports: [CommonModule, ZardIconComponent],
  templateUrl: './reminder-dialog-stack.component.html',
  styleUrls: ['./reminder-dialog-stack.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ReminderDialogStackComponent {
  private readonly reminderDialogs = inject(ReminderDialogService);
  private readonly timeFormatter = new Intl.DateTimeFormat(undefined, {
    hour: '2-digit',
    minute: '2-digit',
  });

  readonly items = this.reminderDialogs.items;
  readonly hasItems = this.reminderDialogs.hasItems;

  close(id: string): void {
    this.reminderDialogs.close(id);
  }

  receivedAtLabel(value: string): string {
    if (!value) {
      return this.timeFormatter.format(new Date());
    }

    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
      return this.timeFormatter.format(new Date());
    }
    return this.timeFormatter.format(parsed);
  }
}
