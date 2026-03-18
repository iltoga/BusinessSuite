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
});
