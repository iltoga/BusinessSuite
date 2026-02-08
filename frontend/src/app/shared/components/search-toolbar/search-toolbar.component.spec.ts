import { TestBed } from '@angular/core/testing';
import { SearchToolbarComponent } from './search-toolbar.component';

describe('SearchToolbarComponent keyboard shortcut', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [SearchToolbarComponent] }).compileComponents();
  });

  it('should focus the input when pressing "s" and not typing in an input', async () => {
    const fixture = TestBed.createComponent(SearchToolbarComponent);
    fixture.detectChanges();

    const comp = fixture.componentInstance;
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
});
