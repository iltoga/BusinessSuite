import { ApplicationListComponent } from './application-list.component';

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
      query: () => string;
      page: () => number;
    };
    component.query = () => 'stefano';
    component.page = () => 3;

    expect(component.applicationDetailState({ id: 314 } as never)).toEqual({
      from: 'applications',
      focusId: 314,
      searchQuery: 'stefano',
      page: 3,
    });
  });
});
