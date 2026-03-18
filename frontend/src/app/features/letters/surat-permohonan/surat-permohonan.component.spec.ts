import { HttpHeaders, HttpResponse } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { vi } from 'vitest';

import { CountryCodesService } from '@/core/api/api/country-codes.service';
import { LettersService } from '@/core/api/api/letters.service';
import { GlobalToastService } from '@/core/services/toast.service';

import { SuratPermohonanComponent } from './surat-permohonan.component';

describe('SuratPermohonanComponent', () => {
  let component: SuratPermohonanComponent;
  let lettersService: {
    lettersCustomerDataRetrieve: ReturnType<typeof vi.fn>;
    lettersSuratPermohonanCreate: ReturnType<typeof vi.fn>;
  };

  beforeEach(() => {
    lettersService = {
      lettersCustomerDataRetrieve: vi.fn(),
      lettersSuratPermohonanCreate: vi.fn(),
    };

    lettersService.lettersCustomerDataRetrieve.mockReturnValue(
      of({
        name: 'Test User',
        gender: 'M',
        country: 'IDN',
        birthPlace: 'Jakarta',
        birthdate: '1990-01-01',
        passportNo: 'A123',
        passportExpDate: '2030-01-01',
        addressBali: 'Ubud',
      }),
    );
    lettersService.lettersSuratPermohonanCreate.mockReturnValue(
      of(
        new HttpResponse({
          body: new Blob(['ok']),
          headers: new HttpHeaders({
            'content-disposition': 'attachment; filename="surat_permohonan_test-user.docx"',
          }),
        }),
      ),
    );

    TestBed.configureTestingModule({
      providers: [
        { provide: LettersService, useValue: lettersService },
        {
          provide: CountryCodesService,
          useValue: {
            countryCodesList: vi.fn(() =>
              of([
                {
                  alpha3Code: 'IDN',
                  country: 'Indonesia',
                  countryIdn: 'Indonesia',
                },
              ]),
            ),
          },
        },
        {
          provide: GlobalToastService,
          useValue: {
            success: vi.fn(),
            error: vi.fn(),
          },
        },
      ],
    });

    component = TestBed.runInInjectionContext(() => new SuratPermohonanComponent());
    vi.spyOn(component as any, 'downloadBlob').mockImplementation(() => undefined);
  });

  it('submits a valid surat permohonan request', () => {
    component.form.patchValue({
      customerId: 1,
      docDate: new Date('2026-01-01'),
      visaType: 'voa',
      name: 'Test User',
    });

    component.generateLetter();

    expect(lettersService.lettersSuratPermohonanCreate).toHaveBeenCalledWith(
      expect.objectContaining({
        customerId: 1,
        docDate: '2026-01-01',
        visaType: 'voa',
        name: 'Test User',
      }),
      'response',
    );
  });
});
