import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { DataTableComponent, type ColumnConfig } from './data-table.component';

@Component({
  template: `
    <app-data-table
      [columns]="columns"
      [data]="data"
      [actions]="actions"
      [currentPage]="currentPage"
      [totalPages]="totalPages"
      (pageChange)="onPageChange($event)"
    ></app-data-table>
  `,
  standalone: true,
  imports: [DataTableComponent],
})
class HostComponent {
  columns: ColumnConfig[] = [];
  data: any[] = [];
  actions: any[] | null = null;
  currentPage = 1;
  totalPages = 1;
  lastPageEmitted: number | null = null;
  onPageChange(p: number) {
    this.lastPageEmitted = p;
  }
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

  it('should focus first row when container is focused and none selected', async () => {
    host.data = [{ id: 1 }, { id: 2 }];
    fixture.detectChanges();

    const debug = fixture.debugElement.query(By.directive(DataTableComponent));
    dt = debug.componentInstance as DataTableComponent<any>;

    const wrapper = fixture.debugElement.query(By.css('.data-table-focus-trap'));
    // simulate focus event
    wrapper.triggerEventHandler('focus', new Event('focus'));
    fixture.detectChanges();

    expect(dt.selectedRow()).toBe(host.data[0]);
  });

  it('handleRowNavigationKeydown should navigate on Arrow keys', async () => {
    host.data = [{ id: 1 }, { id: 2 }, { id: 3 }];
    fixture.detectChanges();

    const debug = fixture.debugElement.query(By.directive(DataTableComponent));
    dt = debug.componentInstance as DataTableComponent<any>;

    // simulate keydown Tab (handled at document level) to select first row
    (dt as any)._handleNavigationKey({
      key: 'Tab',
      ctrlKey: false,
      preventDefault: () => {},
      stopPropagation: () => {},
    } as unknown as KeyboardEvent);
    expect(dt.selectedRow()).toBe(host.data[0]);

    // ArrowDown -> second
    dt.handleRowNavigationKeydown({
      key: 'ArrowDown',
      preventDefault: () => {},
      stopPropagation: () => {},
    } as unknown as KeyboardEvent);
    expect(dt.selectedRow()).toBe(host.data[1]);

    // ArrowUp -> wraps to previous (first)
    dt.handleRowNavigationKeydown({
      key: 'ArrowUp',
      preventDefault: () => {},
      stopPropagation: () => {},
    } as unknown as KeyboardEvent);
    expect(dt.selectedRow()).toBe(host.data[0]);
  });

  it('Tab should move selection to next row (wraps)', async () => {
    host.data = [{ id: 1 }, { id: 2 }, { id: 3 }];
    fixture.detectChanges();

    const debug = fixture.debugElement.query(By.directive(DataTableComponent));
    dt = debug.componentInstance as DataTableComponent<any>;

    const wrapper = fixture.debugElement.query(By.css('.data-table-focus-trap'));

    // first Tab -> select first row
    wrapper.triggerEventHandler('keydown', new KeyboardEvent('keydown', { key: 'Tab' }));
    fixture.detectChanges();
    expect(dt.selectedRow()).toBe(host.data[0]);

    // next Tab -> second row
    wrapper.triggerEventHandler('keydown', new KeyboardEvent('keydown', { key: 'Tab' }));
    fixture.detectChanges();
    expect(dt.selectedRow()).toBe(host.data[1]);

    // two more tabs -> wrap to first
    wrapper.triggerEventHandler('keydown', new KeyboardEvent('keydown', { key: 'Tab' }));
    fixture.detectChanges();
    wrapper.triggerEventHandler('keydown', new KeyboardEvent('keydown', { key: 'Tab' }));
    fixture.detectChanges();
    expect(dt.selectedRow()).toBe(host.data[0]);
  });

  it('Ctrl+Tab or ArrowUp should move to previous row (wraps)', async () => {
    host.data = [{ id: 1 }, { id: 2 }, { id: 3 }];
    fixture.detectChanges();

    const debug = fixture.debugElement.query(By.directive(DataTableComponent));
    dt = debug.componentInstance as DataTableComponent<any>;

    const wrapper = fixture.debugElement.query(By.css('.data-table-focus-trap'));

    // Start from first row
    wrapper.triggerEventHandler('keydown', new KeyboardEvent('keydown', { key: 'Tab' }));
    fixture.detectChanges();
    expect(dt.selectedRow()).toBe(host.data[0]);

    // Ctrl+Tab -> previous -> wraps to last
    wrapper.triggerEventHandler(
      'keydown',
      new KeyboardEvent('keydown', { key: 'Tab', ctrlKey: true }),
    );
    fixture.detectChanges();
    expect(dt.selectedRow()).toBe(host.data[2]);

    // ArrowUp -> previous -> second element
    wrapper.triggerEventHandler('keydown', new KeyboardEvent('keydown', { key: 'ArrowUp' }));
    fixture.detectChanges();
    expect(dt.selectedRow()).toBe(host.data[1]);
  });

  it('ArrowLeft and ArrowRight should emit pageChange', () => {
    host.data = [{ id: 1 }];
    host.currentPage = 2;
    host.totalPages = 3;
    fixture.detectChanges();

    const debug = fixture.debugElement.query(By.directive(DataTableComponent));
    dt = debug.componentInstance as DataTableComponent<any>;

    // ArrowRight -> page 3
    dt.handleRowNavigationKeydown({
      key: 'ArrowRight',
      preventDefault: () => {},
      stopPropagation: () => {},
    } as unknown as KeyboardEvent);
    expect(host.lastPageEmitted).toBe(3);

    // Reset and ArrowLeft -> page 1
    host.lastPageEmitted = null;
    dt.handleRowNavigationKeydown({
      key: 'ArrowLeft',
      preventDefault: () => {},
      stopPropagation: () => {},
    } as unknown as KeyboardEvent);
    expect(host.lastPageEmitted).toBe(1);

    // Shift+ArrowRight -> last page (3)
    host.lastPageEmitted = null;
    dt.handleRowNavigationKeydown({
      key: 'ArrowRight',
      shiftKey: true,
      preventDefault: () => {},
      stopPropagation: () => {},
    } as unknown as KeyboardEvent);
    expect(host.lastPageEmitted).toBe(3);

    // Shift+ArrowLeft -> first page (1)
    host.lastPageEmitted = null;
    dt.handleRowNavigationKeydown({
      key: 'ArrowLeft',
      shiftKey: true,
      preventDefault: () => {},
      stopPropagation: () => {},
    } as unknown as KeyboardEvent);
    expect(host.lastPageEmitted).toBe(1);
  });
});
