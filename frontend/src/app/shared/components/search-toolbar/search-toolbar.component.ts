import { CommonModule } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  input,
  linkedSignal,
  output,
  type OnDestroy,
} from '@angular/core';

import { ZardButtonComponent } from '@/shared/components/button';
import { ZardIconComponent } from '@/shared/components/icon';
import { ZardInputDirective } from '@/shared/components/input';

@Component({
  selector: 'app-search-toolbar',
  standalone: true,
  imports: [CommonModule, ZardButtonComponent, ZardIconComponent, ZardInputDirective],
  templateUrl: './search-toolbar.component.html',
  styleUrls: ['./search-toolbar.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SearchToolbarComponent implements OnDestroy {
  query = input<string>('');
  placeholder = input<string>('Search...');
  debounceMs = input<number>(500);
  isLoading = input<boolean>(false);
  disabled = input<boolean>(false);

  queryChange = output<string>();
  submitted = output<string>();

  protected readonly searchValue = linkedSignal(() => this.query());
  private debounceHandle?: ReturnType<typeof setTimeout>;

  onInput(event: Event): void {
    const value = (event.target as HTMLInputElement | null)?.value ?? '';
    this.searchValue.set(value);
    this.scheduleEmit(value);
  }

  submitSearch(): void {
    const value = this.searchValue();
    if (this.debounceHandle) {
      clearTimeout(this.debounceHandle);
    }
    this.queryChange.emit(value);
    this.submitted.emit(value);
  }

  private scheduleEmit(value: string): void {
    if (this.debounceHandle) {
      clearTimeout(this.debounceHandle);
    }

    const wait = this.debounceMs();
    this.debounceHandle = setTimeout(() => {
      this.queryChange.emit(value);
    }, wait);
  }

  ngOnDestroy(): void {
    if (this.debounceHandle) {
      clearTimeout(this.debounceHandle);
    }
  }
}
