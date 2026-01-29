import { CountryCodesService } from '@/core/api/api/country-codes.service';
import { LettersService } from '@/core/api/api/letters.service';
import type { CountryCode } from '@/core/api/model/country-code';
import type { SuratPermohonanCustomerData } from '@/core/api/model/surat-permohonan-customer-data';
import type { SuratPermohonanRequest } from '@/core/api/model/surat-permohonan-request';
import { GlobalToastService } from '@/core/services/toast.service';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
import { ZardComboboxComponent, type ZardComboboxOption } from '@/shared/components/combobox';
import { CustomerSelectComponent } from '@/shared/components/customer-select';
import { ZardDateInputComponent } from '@/shared/components/date-input';
import { ZardIconComponent } from '@/shared/components/icon';
import { ZardInputDirective } from '@/shared/components/input';
import { CommonModule } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  computed,
  inject,
  signal,
  type OnInit,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { finalize } from 'rxjs';

@Component({
  selector: 'app-surat-permohonan',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    RouterLink,
    ZardButtonComponent,
    ZardCardComponent,
    ZardInputDirective,
    ZardComboboxComponent,
    CustomerSelectComponent,
    ZardDateInputComponent,
    ZardIconComponent,
  ],
  templateUrl: './surat-permohonan.component.html',
  styleUrls: ['./surat-permohonan.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SuratPermohonanComponent implements OnInit {
  private fb = inject(FormBuilder);
  private lettersApi = inject(LettersService);
  private countriesApi = inject(CountryCodesService);
  private toast = inject(GlobalToastService);
  private destroyRef = inject(DestroyRef);

  readonly countries = signal<CountryCode[]>([]);
  readonly isGenerating = signal(false);

  readonly visaTypeOptions = [
    { value: 'voa', label: 'VOA' },
    { value: 'C1', label: 'C1' },
  ];

  readonly countryOptions = computed<ZardComboboxOption[]>(() =>
    this.countries().map((country) => ({
      value: country.alpha3Code ?? '',
      label: country.countryIdn || country.country || country.alpha3Code || 'Unknown',
    })),
  );

  readonly form = this.fb.group({
    customerId: [null as number | null, Validators.required],
    docDate: [new Date(), Validators.required],
    visaType: ['voa', Validators.required],
    name: ['', Validators.required],
    gender: [''],
    country: [null as string | null],
    birthPlace: [''],
    birthdate: [null as Date | null],
    passportNo: [''],
    passportExpDate: [null as Date | null],
    addressBali: [''],
  });

  ngOnInit(): void {
    this.loadCountries();

    this.form
      .get('customerId')
      ?.valueChanges.pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((customerId) => {
        if (customerId) {
          this.loadCustomerData(customerId);
        } else {
          this.resetCustomerFields();
        }
      });
  }

  generateLetter(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    const payload = this.buildRequestPayload();
    if (!payload) {
      return;
    }

    this.isGenerating.set(true);
    this.lettersApi
      .lettersSuratPermohonanCreate(payload, 'response')
      .pipe(
        finalize(() => {
          this.isGenerating.set(false);
        }),
      )
      .subscribe({
        next: (response) => {
          const blob = response.body as Blob | null;
          if (!blob) {
            this.toast.error('No file received from server');
            return;
          }

          const filename =
            this.getFilenameFromHeader(response.headers.get('content-disposition')) ||
            `surat_permohonan_${payload.name || 'customer'}.docx`;
          this.downloadBlob(blob, filename);
          this.toast.success('Letter generated successfully');
        },
        error: () => {
          this.toast.error('Failed to generate letter');
        },
      });
  }

  private loadCountries(): void {
    this.countriesApi.countryCodesList(undefined, undefined).subscribe({
      next: (countries) => {
        this.countries.set(countries ?? []);
      },
      error: () => {
        this.toast.error('Failed to load countries');
      },
    });
  }

  private loadCustomerData(customerId: number): void {
    this.lettersApi.lettersCustomerDataRetrieve(customerId).subscribe({
      next: (data: SuratPermohonanCustomerData) => {
        this.form.patchValue({
          name: data.name ?? '',
          gender: data.gender ?? '',
          country: data.country ?? null,
          birthPlace: data.birthPlace ?? '',
          birthdate: this.parseDate(data.birthdate),
          passportNo: data.passportNo ?? '',
          passportExpDate: this.parseDate(data.passportExpDate),
          addressBali: data.addressBali ?? '',
        });
      },
      error: () => {
        this.toast.error('Failed to load customer data');
      },
    });
  }

  private resetCustomerFields(): void {
    this.form.patchValue({
      name: '',
      gender: '',
      country: null,
      birthPlace: '',
      birthdate: null,
      passportNo: '',
      passportExpDate: null,
      addressBali: '',
    });
  }

  private buildRequestPayload(): SuratPermohonanRequest | null {
    const raw = this.form.getRawValue();
    if (!raw.customerId) {
      this.toast.error('Customer is required');
      return null;
    }

    return {
      customerId: raw.customerId,
      docDate: this.formatDate(raw.docDate),
      visaType: raw.visaType ?? '',
      name: raw.name ?? '',
      gender: raw.gender ?? '',
      country: raw.country ?? '',
      birthPlace: raw.birthPlace ?? '',
      birthdate: this.formatDate(raw.birthdate),
      passportNo: raw.passportNo ?? '',
      passportExpDate: this.formatDate(raw.passportExpDate),
      addressBali: raw.addressBali ?? '',
    };
  }

  private parseDate(value?: string | null): Date | null {
    if (!value) {
      return null;
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return null;
    }
    return date;
  }

  private formatDate(value: Date | null): string | undefined {
    if (!value || Number.isNaN(value.getTime())) {
      return undefined;
    }
    const year = value.getFullYear();
    const month = String(value.getMonth() + 1).padStart(2, '0');
    const day = String(value.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  private downloadBlob(blob: Blob, filename: string): void {
    const url = window.URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    anchor.click();
    window.URL.revokeObjectURL(url);
  }

  private getFilenameFromHeader(contentDisposition: string | null): string | null {
    if (!contentDisposition) {
      return null;
    }
    const match = /filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i.exec(contentDisposition);
    if (match) {
      return decodeURIComponent(match[1] || match[2]);
    }
    return null;
  }
}
