import { Pipe, PipeTransform } from '@angular/core';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';

@Pipe({ name: 'shortcutHighlight', standalone: true })
export class ShortcutHighlightPipe implements PipeTransform {
  constructor(private sanitizer: DomSanitizer) {}

  transform(label: string | null | undefined): SafeHtml {
    if (!label) return '';
    const first = label.charAt(0);
    const rest = label.slice(1);
    const html = `<span class="dt-shortcut"><b>${first}</b>${rest}</span>`;
    return this.sanitizer.bypassSecurityTrustHtml(html);
  }
}
