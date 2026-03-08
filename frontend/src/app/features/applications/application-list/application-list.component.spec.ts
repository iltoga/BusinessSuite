import { describe, it, expect } from 'vitest';
import { ApplicationListComponent } from './application-list.component';
import { signal } from '@angular/core';

describe('ApplicationListComponent invoice availability', () => {
  it('allows invoice creation for uninvoiced pending applications', () => {
    const component = Object.create(ApplicationListComponent.prototype) as ApplicationListComponent;

    expect(
      component.canCreateInvoice({
        hasInvoice: false,
      } as never),
    ).toBe(true);
  });

  it('blocks invoice creation when an invoice already exists', () => {
    const component = Object.create(ApplicationListComponent.prototype) as ApplicationListComponent;

    expect(
      component.canCreateInvoice({
        hasInvoice: true,
      } as never),
    ).toBe(false);
  });
});

describe('ApplicationListComponent navigation state', () => {
  it('builds application detail state from the current list filters', () => {
    const component = Object.create(ApplicationListComponent.prototype) as ApplicationListComponent & {
      query: { (): string; set: (val: string) => void };
      page: { (): number; set: (val: number) => void };
    };
    
    // Initialize signals properly
    component.query = signal('stefano') as any;
    component.page = signal(3) as any;

    expect(component.applicationDetailState({ id: 314 } as never)).toEqual({
      from: 'applications',
      focusId: 314,
      searchQuery: 'stefano',
      page: 3,
    });
  });
});
