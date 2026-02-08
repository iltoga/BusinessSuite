import { Pipe, PipeTransform } from '@angular/core';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';

@Pipe({ name: 'shortcutHighlight', standalone: true })
export class ShortcutHighlightPipe implements PipeTransform {
  constructor(private sanitizer: DomSanitizer) {}

  transform(label: string | null | undefined, shortcut?: string): SafeHtml {
    if (!label) return '';

    // If a specific shortcut is provided, try to find it and bold it
    if (shortcut && shortcut.length === 1) {
      const char = shortcut.toLowerCase();
      const labelLower = label.toLowerCase();
      const index = labelLower.indexOf(char);

      if (index !== -1) {
        const prefix = label.slice(0, index);
        const highlighted = label.charAt(index);
        const suffix = label.slice(index + 1);
        const html = `<span class="dt-shortcut">${prefix}<b>${highlighted}</b>${suffix}</span>`;
        return this.sanitizer.bypassSecurityTrustHtml(html);
      }
    }

    // Fallback: bold the first character
    const first = label.charAt(0);
    const rest = label.slice(1);
    const html = `<span class="dt-shortcut"><b>${first}</b>${rest}</span>`;
    return this.sanitizer.bypassSecurityTrustHtml(html);
  }
}
