import { DragDropModule, moveItemInArray, type CdkDragDrop } from '@angular/cdk/drag-drop';
import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, effect, input, output, signal } from '@angular/core';

export interface SortableOption {
  id: number;
  label: string;
}

@Component({
  selector: 'app-sortable-multi-select',
  standalone: true,
  imports: [CommonModule, DragDropModule],
  templateUrl: './sortable-multi-select.component.html',
  styleUrls: ['./sortable-multi-select.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SortableMultiSelectComponent {
  options = input.required<readonly SortableOption[]>();
  selectedIds = input<number[]>([]);
  label = input<string>('');

  selectedIdsChange = output<number[]>();

  readonly selectedOrder = signal<number[]>([]);

  constructor() {
    effect(() => {
      this.selectedOrder.set([...(this.selectedIds() ?? [])]);
    });
  }

  isSelected(optionId: number): boolean {
    return this.selectedOrder().includes(optionId);
  }

  toggleOption(optionId: number, checked: boolean): void {
    const current = this.selectedOrder();
    if (checked && !current.includes(optionId)) {
      const next = [...current, optionId];
      this.selectedOrder.set(next);
      this.selectedIdsChange.emit(next);
      return;
    }

    if (!checked && current.includes(optionId)) {
      const next = current.filter((id) => id !== optionId);
      this.selectedOrder.set(next);
      this.selectedIdsChange.emit(next);
    }
  }

  reorder(event: CdkDragDrop<number[]>): void {
    const next = [...this.selectedOrder()];
    moveItemInArray(next, event.previousIndex, event.currentIndex);
    this.selectedOrder.set(next);
    this.selectedIdsChange.emit(next);
  }

  selectedOptions(): SortableOption[] {
    const optionsMap = new Map(this.options().map((option) => [option.id, option]));
    return this.selectedOrder()
      .map((id) => optionsMap.get(id))
      .filter(Boolean) as SortableOption[];
  }
}
