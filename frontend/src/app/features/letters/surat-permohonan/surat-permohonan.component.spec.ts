import { HttpResponse } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { vi } from 'vitest';

import { CountryCodesService } from '@/core/api/api/country-codes.service';
import { CustomersService } from '@/core/api/api/customers.service';
import { LettersService } from '@/core/api/api/letters.service';
import { GlobalToastService } from '@/core/services/toast.service';
import { SuratPermohonanComponent } from './surat-permohonan.component';

describe('SuratPermohonanComponent', () => {
  let component: SuratPermohonanComponent;
  let lettersService: any;

  beforeEach(async () => {
    const lettersSpy = {
      lettersCustomerDataRetrieve: vi.fn(),
      lettersSuratPermohonanCreate: vi.fn(),
    };
    const countriesSpy = {
      countryCodesList: vi.fn(),
    };
    const customersSpy = {
      customersList: vi.fn(),
      customersRetrieve: vi.fn(),
    };
    const toastSpy = {
      success: vi.fn(),
      error: vi.fn(),
    };

    lettersSpy.lettersCustomerDataRetrieve.mockReturnValue(
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
    lettersSpy.lettersSuratPermohonanCreate.mockReturnValue(
      of(new HttpResponse({ body: new Blob(['ok']) })),
    );
    countriesSpy.countryCodesList.mockReturnValue(
      of([
        {
          alpha3Code: 'IDN',
          country: 'Indonesia',
          countryIdn: 'Indonesia',
        },
      ]),
    );
    customersSpy.customersList.mockReturnValue(of({ results: [] }));
    customersSpy.customersRetrieve.mockReturnValue(
      of({ id: 1, fullName: 'Test User', fullNameWithCompany: 'Test User' }),
    );

    await TestBed.configureTestingModule({
      imports: [SuratPermohonanComponent],
      providers: [
        { provide: LettersService, useValue: lettersSpy },
        { provide: CountryCodesService, useValue: countriesSpy },
        { provide: CustomersService, useValue: customersSpy },
        { provide: GlobalToastService, useValue: toastSpy },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(SuratPermohonanComponent);
    component = fixture.componentInstance;
    lettersService = TestBed.inject(LettersService);
  });

  it('submits a valid surat permohonan request', () => {
    component.form.patchValue({
      customerId: 1,
      docDate: new Date('2026-01-01'),
      visaType: 'voa',
      name: 'Test User',
    });

    component.generateLetter();

    expect(lettersService.lettersSuratPermohonanCreate).toHaveBeenCalled();
  });
});
