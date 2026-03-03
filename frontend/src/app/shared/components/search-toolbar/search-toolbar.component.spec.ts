import { TestBed } from '@angular/core/testing';
import { SearchToolbarComponent } from './search-toolbar.component';

describe('SearchToolbarComponent keyboard shortcut', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [SearchToolbarComponent] }).compileComponents();
  });

  it('should focus the input when pressing "s" and not typing in an input', async () => {
    const fixture = TestBed.createComponent(SearchToolbarComponent);
    fixture.detectChanges();

    const input = fixture.nativeElement.querySelector('input');
    expect(input).toBeTruthy();

    // ensure focus is nowhere
    (document.activeElement as HTMLElement | null)?.blur?.();

    // dispatch 's' key
    const e = new KeyboardEvent('keydown', { key: 's' });
    document.dispatchEvent(e);

    // give the component a moment to perform deferred focus
    await new Promise((resolve) => setTimeout(resolve, 100));

    // input should now be focused
    expect(document.activeElement).toBe(input);
  });

  it('should emit tabOut when pressing Shift+T outside editable fields', () => {
    const fixture = TestBed.createComponent(SearchToolbarComponent);
    fixture.detectChanges();

    const comp = fixture.componentInstance;
    let emitted = 0;
    comp.tabOut.subscribe(() => {
      emitted += 1;
    });

    (document.activeElement as HTMLElement | null)?.blur?.();

    const e = new KeyboardEvent('keydown', { key: 'T', shiftKey: true, bubbles: true });
    document.dispatchEvent(e);

    expect(emitted).toBe(1);
  });

  it('should clear and emit empty query on Escape in the search input', async () => {
    const fixture = TestBed.createComponent(SearchToolbarComponent);
    fixture.componentRef.setInput('query', 'bank');
    fixture.componentRef.setInput('debounceMs', 50);
    fixture.detectChanges();

    const comp = fixture.componentInstance;
    const emitted: string[] = [];
    comp.queryChange.subscribe((value) => emitted.push(value));

    const input = fixture.nativeElement.querySelector('input') as HTMLInputElement;
    input.focus();

    input.value = 'bank fee';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    fixture.detectChanges();

    const escapeEvent = new KeyboardEvent('keydown', {
      key: 'Escape',
      bubbles: true,
      cancelable: true,
    });
    const notCancelled = input.dispatchEvent(escapeEvent);
    fixture.detectChanges();

    expect(notCancelled).toBe(false);
    expect(input.value).toBe('');
    expect(emitted).toEqual(['']);

    // Ensure stale debounced terms are not emitted after clearing.
    await new Promise((resolve) => setTimeout(resolve, 60));
    expect(emitted).toEqual(['']);
  });

  it('should not emit queryChange when Escape comes from a different input', () => {
    const fixture = TestBed.createComponent(SearchToolbarComponent);
    fixture.detectChanges();

    const comp = fixture.componentInstance;
    const emitted: string[] = [];
    comp.queryChange.subscribe((value) => emitted.push(value));

    const externalInput = document.createElement('input');
    document.body.appendChild(externalInput);
    try {
      externalInput.focus();
      const escapeEvent = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true });
      externalInput.dispatchEvent(escapeEvent);
      expect(emitted).toEqual([]);
    } finally {
      externalInput.remove();
    }
  });

  it('should not emit tabOut when Shift+T is pressed inside an input', () => {
    const fixture = TestBed.createComponent(SearchToolbarComponent);
    fixture.detectChanges();

    const comp = fixture.componentInstance;
    let emitted = 0;
    comp.tabOut.subscribe(() => {
      emitted += 1;
    });

    const input = fixture.nativeElement.querySelector('input') as HTMLInputElement;
    input.focus();

    const e = new KeyboardEvent('keydown', { key: 'T', shiftKey: true, bubbles: true });
    document.dispatchEvent(e);

    expect(emitted).toBe(0);
  });
});
