import { HelpContext, HelpService } from '@/shared/services/help.service';
import { Directive, ElementRef, HostListener, Input, inject } from '@angular/core';

@Directive({
  selector: '[contextHelp]',
  standalone: true,
})
export class ContextHelpDirective {
  private readonly el = inject(ElementRef<HTMLElement>);
  private readonly help = inject(HelpService);

  // Accept either helpId string or full HelpContext object
  @Input('contextHelp')
  public helpData: string | HelpContext | null = null;

  @HostListener('focusin')
  @HostListener('mouseenter')
  activate() {
    if (!this.helpData) return;

    if (typeof this.helpData === 'string') {
      // If only an id is provided, ask HelpService to set by id
      this.help.setContextById(this.helpData);
    } else {
      // If object provided, directly set and optionally register
      const ctx = this.helpData as HelpContext;
      if (ctx.id) this.help.register(ctx.id, ctx);
      this.help.setContext(ctx);
    }
  }

  @HostListener('focusout')
  @HostListener('mouseleave')
  deactivate() {
    // keep current context (page-level context will still apply). No-op to avoid flicker.
  }
}
