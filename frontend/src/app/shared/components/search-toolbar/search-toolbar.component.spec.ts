import { ElementRef, PLATFORM_ID } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import { SearchToolbarComponent } from './search-toolbar.component';

describe('SearchToolbarComponent keyboard shortcut', () => {
  let component: SearchToolbarComponent;
  let input: HTMLInputElement;

  beforeEach(() => {
    vi.useFakeTimers();

    TestBed.configureTestingModule({
      providers: [{ provide: PLATFORM_ID, useValue: 'browser' }],
    });

    component = TestBed.runInInjectionContext(() => new SearchToolbarComponent());

    input = document.createElement('input');
    input.scrollIntoView = vi.fn();
    document.body.appendChild(input);
    (component as any).searchInput = new ElementRef(input);
  });

  afterEach(() => {
    component.ngOnDestroy();
    input.remove();
    vi.useRealTimers();
  });

  it('should focus the input when pressing "s" and not typing in an input', () => {
    (component as any)._globalKeyHandler(new KeyboardEvent('keydown', { key: 's' }));

    vi.runAllTimers();

    expect(document.activeElement).toBe(input);
  });

  it('should emit tabOut when pressing Shift+T outside editable fields', () => {
    let emitted = 0;
    component.tabOut.subscribe(() => {
      emitted += 1;
    });

    (component as any)._globalKeyHandler(
      new KeyboardEvent('keydown', { key: 'T', shiftKey: true, bubbles: true }),
    );

    expect(emitted).toBe(1);
  });

  it('should clear and emit empty query on Escape in the search input', () => {
    const emitted: string[] = [];
    component.queryChange.subscribe((value) => emitted.push(value));

    (component as any).searchValue.set('bank fee');

    const escapeEvent = new KeyboardEvent('keydown', {
      key: 'Escape',
      bubbles: true,
      cancelable: true,
    });
    const preventDefaultSpy = vi.spyOn(escapeEvent, 'preventDefault');
    const stopPropagationSpy = vi.spyOn(escapeEvent, 'stopPropagation');

    component.handleInputKeydown(escapeEvent);

    expect(preventDefaultSpy).toHaveBeenCalled();
    expect(stopPropagationSpy).toHaveBeenCalled();
    expect((component as any).searchValue()).toBe('');
    expect(emitted).toEqual(['']);

    vi.advanceTimersByTime(60);
    expect(emitted).toEqual(['']);
  });

  it('should not emit queryChange when Escape comes from a different input', () => {
    const emitted: string[] = [];
    component.queryChange.subscribe((value) => emitted.push(value));

    const externalInput = document.createElement('input');
    document.body.appendChild(externalInput);

    try {
      externalInput.focus();
      component.onDocumentKeydown(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
      expect(emitted).toEqual([]);
    } finally {
      externalInput.remove();
    }
  });

  it('should not emit tabOut when Shift+T is pressed inside an input', () => {
    let emitted = 0;
    component.tabOut.subscribe(() => {
      emitted += 1;
    });

    input.focus();
    component.onDocumentKeydown(
      new KeyboardEvent('keydown', { key: 'T', shiftKey: true, bubbles: true }),
    );

    expect(emitted).toBe(0);
  });

  it('should debounce rapid input changes and emit only the latest value', () => {
    const emitted: string[] = [];
    component.queryChange.subscribe((value) => emitted.push(value));

    component.onInput({ target: { value: 'fi' } } as unknown as Event);
    vi.advanceTimersByTime(250);

    component.onInput({ target: { value: 'final term' } } as unknown as Event);
    vi.advanceTimersByTime(499);

    expect(emitted).toEqual([]);

    vi.advanceTimersByTime(1);

    expect(emitted).toEqual(['final term']);
  });

  it('should submit the latest pending query immediately on Enter without duplicate debounce emits', () => {
    const queryEmitted: string[] = [];
    const submitted: string[] = [];
    let tabOutCount = 0;

    component.queryChange.subscribe((value) => queryEmitted.push(value));
    component.submitted.subscribe((value) => submitted.push(value));
    component.tabOut.subscribe(() => {
      tabOutCount += 1;
    });

    component.onInput({ target: { value: 'latest search' } } as unknown as Event);
    vi.advanceTimersByTime(200);

    component.handleInputKeydown(
      new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }),
    );

    expect(queryEmitted).toEqual(['latest search']);
    expect(submitted).toEqual(['latest search']);
    expect(tabOutCount).toBe(1);

    vi.runAllTimers();

    expect(queryEmitted).toEqual(['latest search']);
  });
});
