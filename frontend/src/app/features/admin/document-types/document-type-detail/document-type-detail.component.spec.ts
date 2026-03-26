import { PLATFORM_ID } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, convertToParamMap } from '@angular/router';

import { DocumentTypesService } from '@/core/api';
import { GlobalToastService } from '@/core/services/toast.service';

import { DocumentTypeDetailComponent } from './document-type-detail.component';

describe('DocumentTypeDetailComponent', () => {
  let component: DocumentTypeDetailComponent;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        { provide: PLATFORM_ID, useValue: 'browser' },
        { provide: Router, useValue: { navigate: vi.fn(() => Promise.resolve(true)) } },
        {
          provide: DocumentTypesService,
          useValue: {
            documentTypesRetrieve: vi.fn(),
          },
        },
        {
          provide: GlobalToastService,
          useValue: {
            error: vi.fn(),
          },
        },
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { paramMap: convertToParamMap({}) } },
        },
      ],
    });

    component = TestBed.runInInjectionContext(() => new DocumentTypeDetailComponent());
  });

  it('starts in a loading state to avoid flashing not-found before ngOnInit loads data', () => {
    expect(component.isLoading()).toBe(true);
  });
});
