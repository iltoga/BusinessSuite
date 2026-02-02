import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';

import { ZardButtonComponent } from '@/shared/components/button';
import { ZardIconComponent } from '@/shared/components/icon';

@Component({
  selector: 'app-pagination-controls',
  standalone: true,
  imports: [CommonModule, ZardButtonComponent, ZardIconComponent],
  templateUrl: './pagination-controls.component.html',
  styleUrls: ['./pagination-controls.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PaginationControlsComponent {
  page = input<number>(1);
  totalPages = input<number>(1);
  disabled = input<boolean>(false);

  pageChange = output<number>();

  readonly hasPrevious = computed(() => this.page() > 1);
  readonly hasNext = computed(() => this.page() < this.totalPages());

  goToFirst(): void {
    if (this.hasPrevious()) {
      this.pageChange.emit(1);
    }
  }

  goToPrevious(): void {
    if (this.hasPrevious()) {
      this.pageChange.emit(this.page() - 1);
    }
  }

  goToNext(): void {
    if (this.hasNext()) {
      this.pageChange.emit(this.page() + 1);
    }
  }

  goToLast(): void {
    if (this.hasNext()) {
      this.pageChange.emit(this.totalPages());
    }
  }
}
