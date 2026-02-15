import { CommonModule } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  inject,
  OnInit,
  TemplateRef,
  ViewChild,
  signal,
} from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { EMPTY, catchError, finalize } from 'rxjs';

import { HolidaysService } from '@/core/api/api/holidays.service';
import { Holiday } from '@/core/api/model/holiday';
import { GlobalToastService } from '@/core/services/toast.service';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
import { ConfirmDialogComponent } from '@/shared/components/confirm-dialog/confirm-dialog.component';
import { ColumnConfig, DataTableComponent } from '@/shared/components/data-table/data-table.component';
import { ZardDialogService } from '@/shared/components/dialog';
import { ZardInputDirective } from '@/shared/components/input';

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
    ZardInputDirective,
  ],
  templateUrl: './holidays.component.html',
  styleUrls: ['./holidays.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class HolidaysComponent implements OnInit {
  @ViewChild('actionsTemplate', { static: true }) actionsTemplate!: TemplateRef<any>;
  @ViewChild('holidayModalTemplate', { static: true }) holidayModalTemplate!: TemplateRef<any>;

  private fb = inject(FormBuilder);
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

  columns: ColumnConfig[] = [
    { key: 'date', header: 'Date', sortable: true },
    { key: 'name', header: 'Name', sortable: true },
    { key: 'country', header: 'Country', sortable: true },
    { key: 'description', header: 'Description', sortable: false },
    { key: 'actions', header: '' },
  ];

  readonly holidayForm = this.fb.group({
    name: ['', Validators.required],
    date: ['', Validators.required],
    country: ['Indonesia', Validators.required],
    description: [''],
  });

  ngOnInit(): void {
    this.columns[this.columns.length - 1].template = this.actionsTemplate;
    this.loadHolidays();
  }

  private loadHolidays(): void {
    this.isLoading.set(true);
    this.holidaysApi
      .holidaysList('date')
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
    this.holidayForm.reset({ name: '', date: '', country: 'Indonesia', description: '' });
    this.openHolidayDialog('Add Holiday');
  }

  editHoliday(holiday: Holiday): void {
    this.editingHoliday.set(holiday);
    this.holidayForm.patchValue({
      name: holiday.name,
      date: holiday.date,
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
    const payload = {
      name: this.holidayForm.value.name!,
      date: this.holidayForm.value.date!,
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
}
