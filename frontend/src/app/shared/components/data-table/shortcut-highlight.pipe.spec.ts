import { ShortcutHighlightPipe } from './shortcut-highlight.pipe';

describe('ShortcutHighlightPipe', () => {
  let pipe: ShortcutHighlightPipe;

  beforeEach(() => {
    pipe = new ShortcutHighlightPipe();
  });

  it('highlights the provided shortcut character', () => {
    const value = pipe.transform('Delete', 'e');
    expect(value).toContain('<b>e</b>');
    expect(value).toContain('D');
  });

  it('escapes unsafe html content in labels', () => {
    const value = pipe.transform('<img src=x onerror=alert(1)>', 'i');
    expect(value).toContain('&lt;');
    expect(value).not.toContain('<img');
    expect(value).not.toContain('onerror=');
  });

  it('falls back to highlighting the first character', () => {
    const value = pipe.transform('Archive');
    expect(value).toContain('<b>A</b>');
    expect(value).toContain('rchive');
  });
});
