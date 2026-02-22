import { Pipe, PipeTransform } from '@angular/core';

@Pipe({ name: 'shortcutHighlight', standalone: true })
export class ShortcutHighlightPipe implements PipeTransform {
  transform(label: string | null | undefined, shortcut?: string): string {
    if (!label) return '';

    // If a specific shortcut is provided, try to find it and bold it
    if (shortcut && shortcut.length === 1) {
      const char = shortcut.toLowerCase();
      const labelLower = label.toLowerCase();
      const index = labelLower.indexOf(char);

      if (index !== -1) {
        const prefix = escapeHtml(label.slice(0, index));
        const highlighted = escapeHtml(label.charAt(index));
        const suffix = escapeHtml(label.slice(index + 1));
        return `<span class="dt-shortcut">${prefix}<b>${highlighted}</b>${suffix}</span>`;
      }
    }

    // Fallback: bold the first character
    const first = escapeHtml(label.charAt(0));
    const rest = escapeHtml(label.slice(1));
    return `<span class="dt-shortcut"><b>${first}</b>${rest}</span>`;
  }
}

function escapeHtml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}
