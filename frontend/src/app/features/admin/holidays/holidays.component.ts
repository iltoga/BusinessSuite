import { CommonModule } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  DestroyRef,
  inject,
  OnInit,
  TemplateRef,
  ViewChild,
  signal,
} from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { EMPTY, catchError, finalize } from 'rxjs';

import { HolidaysService } from '@/core/api/api/holidays.service';
import { Holiday } from '@/core/api/model/holiday';
import { GlobalToastService } from '@/core/services/toast.service';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
import { ConfirmDialogComponent } from '@/shared/components/confirm-dialog/confirm-dialog.component';
import { ZardDateInputComponent } from '@/shared/components/date-input';
import {
  ColumnConfig,
  DataTableComponent,
} from '@/shared/components/data-table/data-table.component';
import { ZardDialogService } from '@/shared/components/dialog';
import { ZardInputDirective } from '@/shared/components/input';
import { AppDatePipe } from '@/shared/pipes/app-date-pipe';

@Component({
  selector: 'app-holidays',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    ZardCardComponent,
    ZardButtonComponent,
    DataTableComponent,
    ConfirmDialogComponent,
    ZardDateInputComponent,
    ZardInputDirective,
    AppDatePipe,
  ],
  templateUrl: './holidays.component.html',
  styleUrls: ['./holidays.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class HolidaysComponent implements OnInit {
  @ViewChild('actionsTemplate', { static: true }) actionsTemplate!: TemplateRef<any>;
  @ViewChild('dateTemplate', { static: true }) dateTemplate!: TemplateRef<any>;
  @ViewChild('holidayModalTemplate', { static: true }) holidayModalTemplate!: TemplateRef<any>;

  private fb = inject(FormBuilder);
  private destroyRef = inject(DestroyRef);
  private holidaysApi = inject(HolidaysService);
  private toast = inject(GlobalToastService);
  private dialogService = inject(ZardDialogService);

  private dialogRef: any = null;

  readonly holidays = signal<Holiday[]>([]);
  readonly isLoading = signal(true);
  readonly isSaving = signal(false);
  readonly isDialogOpen = signal(false);
  readonly editingHoliday = signal<Holiday | null>(null);
  readonly showConfirmDelete = signal(false);
  readonly selectedDateFilter = signal<Date | null>(null);
  readonly selectedCountryFilter = signal('ID');
  readonly selectedYearFilter = signal<number>(new Date().getFullYear());
  readonly selectedMonthFilter = signal<number | null>(null);
  readonly ordering = signal<string>('date');

  readonly filteredHolidays = computed(() => {
    const selectedCountry = this.normalizeCountryCode(this.selectedCountryFilter()) || 'ID';
    const selectedDate = this.selectedDateFilter();
    const selectedDateIso = selectedDate ? this.toIsoDateString(selectedDate) : null;
    const selectedYear = this.selectedYearFilter();
    const selectedMonth = this.selectedMonthFilter();

    return this.holidays().filter((holiday) => {
      const holidayCountry = this.normalizeCountryCode(holiday.country);
      if (holidayCountry !== selectedCountry) {
        return false;
      }

      const holidayDate = this.parseDateInput(holiday.date);
      if (!holidayDate) {
        return false;
      }

      // Weekend days are constant and should not be shown in this admin view.
      if (holiday.isWeekend || this.isWeekendDate(holidayDate)) {
        return false;
      }

      if (holidayDate.getFullYear() !== selectedYear) {
        return false;
      }

      if (selectedMonth !== null && holidayDate.getMonth() + 1 !== selectedMonth) {
        return false;
      }

      if (!selectedDateIso) {
        return true;
      }

      return holiday.date === selectedDateIso;
    });
  });

  columns: ColumnConfig[] = [
    { key: 'date', header: 'Date', sortable: true },
    { key: 'name', header: 'Name', sortable: true },
    { key: 'country', header: 'Country', sortable: true },
    { key: 'description', header: 'Description', sortable: false },
    { key: 'actions', header: '' },
  ];

  readonly holidayForm = this.fb.group({
    name: ['', Validators.required],
    date: [null as Date | null, Validators.required],
    country: ['ID', Validators.required],
    description: [''],
  });

  readonly filterForm = this.fb.group({
    date: [null as Date | null],
    country: ['ID', Validators.required],
    year: [new Date().getFullYear(), Validators.required],
    month: [null as number | null],
  });

  ngOnInit(): void {
    this.columns[0].template = this.dateTemplate;
    this.columns[this.columns.length - 1].template = this.actionsTemplate;

    this.filterForm.controls.country.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((value) => {
        const normalized = this.normalizeCountryCode(value) || 'ID';
        this.selectedCountryFilter.set(normalized);
      });

    this.filterForm.controls.date.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((value) => this.applyDateFilter(value));

    this.filterForm.controls.year.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((value) => {
        const normalized = this.normalizeYear(value);
        this.selectedYearFilter.set(normalized);
        if (normalized !== value) {
          this.filterForm.controls.year.setValue(normalized, { emitEvent: false });
        }
      });

    this.filterForm.controls.month.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((value) => {
        const normalized = this.normalizeMonth(value);
        this.selectedMonthFilter.set(normalized);
        if (normalized !== value) {
          this.filterForm.controls.month.setValue(normalized, { emitEvent: false });
        }
      });

    this.loadHolidays();
  }

  private loadHolidays(): void {
    this.isLoading.set(true);
    this.holidaysApi
      .holidaysList(this.ordering())
      .pipe(
        catchError(() => {
          this.toast.error('Failed to load holidays');
          return EMPTY;
        }),
        finalize(() => this.isLoading.set(false)),
      )
      .subscribe((data) => this.holidays.set(data ?? []));
  }

  createHoliday(): void {
    this.editingHoliday.set(null);
    this.holidayForm.reset({ name: '', date: null, country: 'ID', description: '' });
    this.openHolidayDialog('Add Holiday');
  }

  onCountryFilterInput(event: Event): void {
    const target = event.target as HTMLInputElement | null;
    const normalized = this.normalizeCountryCode(target?.value) || 'ID';
    this.filterForm.controls.country.setValue(normalized, { emitEvent: true });
  }

  onSortChange(event: { column: string; direction: 'asc' | 'desc' }): void {
    const column = event.column;
    const currentOrdering = this.ordering();

    let nextOrdering: string;
    if (currentOrdering === column) {
      nextOrdering = `-${column}`;
    } else if (currentOrdering === `-${column}`) {
      nextOrdering = column;
    } else {
      nextOrdering = event.direction === 'desc' ? `-${column}` : column;
    }

    this.ordering.set(nextOrdering);
    this.loadHolidays();
  }

  clearDateFilter(): void {
    this.filterForm.controls.date.setValue(null);
    this.filterForm.controls.month.setValue(null);
  }

  editHoliday(holiday: Holiday): void {
    this.editingHoliday.set(holiday);
    this.holidayForm.patchValue({
      name: holiday.name,
      date: this.parseDateInput(holiday.date),
      country: holiday.country,
      description: holiday.description ?? '',
    });
    this.openHolidayDialog('Edit Holiday');
  }

  saveHoliday(): void {
    if (this.holidayForm.invalid) {
      this.holidayForm.markAllAsTouched();
      return;
    }

    this.isSaving.set(true);
    const normalizedDate = this.toIsoDateString(this.holidayForm.value.date);
    if (!normalizedDate) {
      this.isSaving.set(false);
      this.toast.error('Invalid date format');
      return;
    }

    const payload = {
      name: this.holidayForm.value.name!,
      date: normalizedDate,
      country: this.holidayForm.value.country!,
      description: this.holidayForm.value.description || '',
    } as Holiday;

    const current = this.editingHoliday();
    const request = current
      ? this.holidaysApi.holidaysUpdate(current.id, payload)
      : this.holidaysApi.holidaysCreate(payload);

    request
      .pipe(
        catchError(() => {
          this.toast.error('Failed to save holiday');
          return EMPTY;
        }),
        finalize(() => this.isSaving.set(false)),
      )
      .subscribe(() => {
        this.toast.success(`Holiday ${current ? 'updated' : 'created'} successfully`);
        this.closeForm();
        this.loadHolidays();
      });
  }

  deleteHoliday(holiday: Holiday): void {
    this.editingHoliday.set(holiday);
    this.showConfirmDelete.set(true);
  }

  confirmDelete(): void {
    const current = this.editingHoliday();
    if (!current) return;

    this.holidaysApi
      .holidaysDestroy(current.id)
      .pipe(
        catchError(() => {
          this.toast.error('Failed to delete holiday');
          return EMPTY;
        }),
      )
      .subscribe(() => {
        this.toast.success('Holiday deleted successfully');
        this.showConfirmDelete.set(false);
        this.editingHoliday.set(null);
        this.loadHolidays();
      });
  }

  closeForm(): void {
    if (this.dialogRef) {
      this.dialogRef.close();
      this.dialogRef = null;
    }
    this.isDialogOpen.set(false);
    this.editingHoliday.set(null);
  }

  private openHolidayDialog(title: string): void {
    this.dialogRef = this.dialogService.create({
      zTitle: title,
      zContent: this.holidayModalTemplate,
      zHideFooter: true,
      zClosable: true,
      zWidth: '620px',
      zOnCancel: () => {
        this.isDialogOpen.set(false);
        this.editingHoliday.set(null);
        this.dialogRef = null;
      },
    });
    this.isDialogOpen.set(true);
  }

  private applyDateFilter(value: unknown): void {
    const parsedDate = this.parseDateInput(value);
    this.selectedDateFilter.set(parsedDate);
    if (!parsedDate) return;

    const selectedCountry = this.normalizeCountryCode(this.selectedCountryFilter()) || 'ID';
    const selectedIsoDate = this.toIsoDateString(parsedDate);
    if (!selectedIsoDate) return;

    const holidayExists = this.holidays().some(
      (holiday) =>
        holiday.date === selectedIsoDate &&
        this.normalizeCountryCode(holiday.country) === selectedCountry,
    );

    if (holidayExists || this.isDialogOpen()) {
      return;
    }

    this.editingHoliday.set(null);
    this.holidayForm.reset({
      name: '',
      date: parsedDate,
      country: selectedCountry,
      description: '',
    });
    this.openHolidayDialog('Add Holiday');
  }

  private toIsoDateString(value: unknown): string | null {
    const date = this.parseDateInput(value);
    if (!date) return null;

    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  private parseDateInput(value: unknown): Date | null {
    if (value instanceof Date && !Number.isNaN(value.getTime())) {
      return new Date(value.getFullYear(), value.getMonth(), value.getDate());
    }
    if (typeof value !== 'string') return null;

    const raw = value.trim();
    if (!raw) return null;

    const isoMatch = raw.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
    if (isoMatch) {
      return this.buildDate(Number(isoMatch[1]), Number(isoMatch[2]), Number(isoMatch[3]));
    }

    const dayFirstMatch = raw.match(/^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$/);
    if (dayFirstMatch) {
      return this.buildDate(Number(dayFirstMatch[3]), Number(dayFirstMatch[2]), Number(dayFirstMatch[1]));
    }

    const parsed = new Date(raw);
    if (!Number.isNaN(parsed.getTime())) {
      return new Date(parsed.getFullYear(), parsed.getMonth(), parsed.getDate());
    }
    return null;
  }

  private buildDate(year: number, month: number, day: number): Date | null {
    const date = new Date(year, month - 1, day);
    if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) {
      return null;
    }
    return date;
  }

  private normalizeCountryCode(value: string | null | undefined): string {
    return (value ?? '').trim().toUpperCase();
  }

  private isWeekendDate(date: Date): boolean {
    const day = date.getDay();
    return day === 0 || day === 6;
  }

  private normalizeYear(value: unknown): number {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) {
      return new Date().getFullYear();
    }
    const intValue = Math.trunc(parsed);
    return intValue > 0 ? intValue : new Date().getFullYear();
  }

  private normalizeMonth(value: unknown): number | null {
    if (value === null || value === undefined || value === '') {
      return null;
    }
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) {
      return null;
    }
    const intValue = Math.trunc(parsed);
    if (intValue < 1) return null;
    if (intValue > 12) return 12;
    return intValue;
  }
}
