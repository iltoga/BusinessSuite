import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { DataTableComponent, type ColumnConfig } from './data-table.component';

@Component({
  template: `
    <app-data-table [columns]="columns" [data]="data" [actions]="actions"></app-data-table>
  `,
  standalone: true,
  imports: [DataTableComponent],
})
class HostComponent {
  columns: ColumnConfig[] = [];
  data: any[] = [];
  actions: any[] | null = null;
}

describe('DataTableComponent (keyboard shortcuts)', () => {
  let fixture: any;
  let host: HostComponent;
  let dt: DataTableComponent<any>;

  const sampleRow = { id: 1, name: 'John Doe' };
  const columns: ColumnConfig[] = [{ key: 'name', header: 'Name' }];

  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [HostComponent] }).compileComponents();

    fixture = TestBed.createComponent(HostComponent);
    host = fixture.componentInstance;

    host.columns = columns;
    // do not call detectChanges here; tests will call it after setting desired inputs

    // dt will be found after first detectChanges in individual tests
    dt = null as any;
  });

  it('should auto-select when only one row is present', async () => {
    host.data = [sampleRow];
    fixture.detectChanges();

    const debug = fixture.debugElement.query(By.directive(DataTableComponent));
    dt = debug.componentInstance as DataTableComponent<any>;

    // effect runs; assert selectedRow is the only item
    expect(dt.selectedRow()).toBe(sampleRow);
  });

  it('selectRow should focus the provided row element when available', async () => {
    host.data = [sampleRow];
    fixture.detectChanges();

    const debug = fixture.debugElement.query(By.directive(DataTableComponent));
    dt = debug.componentInstance as DataTableComponent<any>;

    let focused = false;
    const tr: any = { focus: () => (focused = true), tabIndex: 0 };

    dt.selectRow(sampleRow, { currentTarget: tr } as unknown as Event);

    expect(dt.selectedRow()).toBe(sampleRow);
    expect(focused).toBe(true);
  });

  it('handleRowKeydown should trigger matching action by first letter', async () => {
    let called = false;
    const action = (r: any) => (called = r === sampleRow);
    const actions = [
      { label: 'Edit', icon: 'settings', action },
      { label: 'Delete', icon: 'trash', action: () => {} },
    ];

    host.data = [sampleRow];
    host.actions = actions;
    fixture.detectChanges();

    const debug = fixture.debugElement.query(By.directive(DataTableComponent));
    dt = debug.componentInstance as DataTableComponent<any>;

    dt.selectedRow.set(sampleRow);

    // Simulate keydown with target that is not input/textarea
    const event = {
      key: 'E',
      target: { tagName: 'DIV' },
      preventDefault: () => {},
      stopPropagation: () => {},
    } as unknown as KeyboardEvent;

    dt.handleRowKeydown(event, sampleRow);
    expect(called).toBe(true);

    // Ensure that key does not trigger when target is input
    called = false;
    const inputEvent = { ...event, target: { tagName: 'INPUT' } } as unknown as KeyboardEvent;
    dt.handleRowKeydown(inputEvent, sampleRow);
    expect(called).toBe(false);
  });
});
