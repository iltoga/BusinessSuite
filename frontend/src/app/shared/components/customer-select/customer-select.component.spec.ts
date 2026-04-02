import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { vi } from 'vitest';

import { CustomersService } from '@/core/api/api/customers.service';
import { CustomerSelectComponent } from './customer-select.component';

describe('CustomerSelectComponent', () => {
  it('loads customers using case-insensitive last-name ordering', async () => {
    const customersSpy = {
      customersList: vi.fn().mockReturnValue(
        of({
          results: [
            {
              id: 1,
              firstName: 'Stefano',
              lastName: 'GALASSI',
              fullName: 'STEFANO GALASSI',
              fullNameWithCompany: 'STEFANO GALASSI',
            },
            {
              id: 2,
              firstName: 'Aliaksei',
              lastName: 'Chaichyts',
              fullName: 'Aliaksei Chaichyts',
              fullNameWithCompany: 'Aliaksei Chaichyts',
            },
            {
              id: 3,
              firstName: 'Anna',
              lastName: 'abramov',
              fullName: 'Anna abramov',
              fullNameWithCompany: 'Anna abramov',
            },
          ],
        }),
      ),
      customersRetrieve: vi.fn(),
    };

    TestBed.configureTestingModule({
      providers: [{ provide: CustomersService, useValue: customersSpy }],
    });

    const component = TestBed.runInInjectionContext(() => new CustomerSelectComponent());

    expect(customersSpy.customersList).toHaveBeenCalledWith({
      ordering: 'sort_last_name,sort_first_name,sort_company_name',
      page: 1,
      pageSize: 20,
      search: undefined,
    });
    expect(component.options().map((option) => option.label)).toEqual([
      'Anna abramov',
      'Aliaksei Chaichyts',
      'STEFANO GALASSI',
    ]);
  });

  it('keeps a fetched selected customer in alphabetical position', async () => {
    const customersSpy = {
      customersList: vi.fn().mockReturnValue(
        of({
          results: [
            {
              id: 1,
              firstName: 'Stefano',
              lastName: 'GALASSI',
              fullName: 'STEFANO GALASSI',
              fullNameWithCompany: 'STEFANO GALASSI',
            },
            {
              id: 2,
              firstName: 'Aliaksei',
              lastName: 'Chaichyts',
              fullName: 'Aliaksei Chaichyts',
              fullNameWithCompany: 'Aliaksei Chaichyts',
            },
          ],
        }),
      ),
      customersRetrieve: vi.fn().mockReturnValue(
        of({
          id: 3,
          firstName: 'Anna',
          lastName: 'abramov',
          fullName: 'Anna abramov',
          fullNameWithCompany: 'Anna abramov',
        }),
      ),
    };

    TestBed.configureTestingModule({
      providers: [{ provide: CustomersService, useValue: customersSpy }],
    });

    const component = TestBed.runInInjectionContext(() => new CustomerSelectComponent());

    component.writeValue(3);

    expect(customersSpy.customersRetrieve).toHaveBeenCalledWith({ id: 3 });
    expect(component.options().map((option) => option.label)).toEqual([
      'Anna abramov',
      'Aliaksei Chaichyts',
      'STEFANO GALASSI',
    ]);
  });
});
