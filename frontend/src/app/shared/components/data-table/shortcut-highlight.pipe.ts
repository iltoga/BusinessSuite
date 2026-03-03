import { Pipe, PipeTransform } from '@angular/core';

@Pipe({ name: 'shortcutHighlight', standalone: true })
export class ShortcutHighlightPipe implements PipeTransform {
  transform(label: string | null | undefined, shortcut?: string): string {
    if (!label) return '';
    const safeLabel = sanitizeUntrustedLabel(label);

    // If a specific shortcut is provided, try to find it and bold it
    if (shortcut && shortcut.length === 1) {
      const char = shortcut.toLowerCase();
      const labelLower = safeLabel.toLowerCase();
      const index = labelLower.indexOf(char);

      if (index !== -1) {
        const prefix = escapeHtml(safeLabel.slice(0, index));
        const highlighted = escapeHtml(safeLabel.charAt(index));
        const suffix = escapeHtml(safeLabel.slice(index + 1));
        return `<span class="dt-shortcut">${prefix}<b>${highlighted}</b>${suffix}</span>`;
      }
    }

    // Fallback: bold the first character
    const first = escapeHtml(safeLabel.charAt(0));
    const rest = escapeHtml(safeLabel.slice(1));
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

function sanitizeUntrustedLabel(value: string): string {
  return value
    .replace(/\son[a-z]+\s*=\s*(".*?"|'.*?'|[^\s>]+)/gi, '')
    .replace(/javascript:/gi, '');
}
