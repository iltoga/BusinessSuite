import { Directive, Input, TemplateRef, ViewContainerRef, inject, effect, Injector } from '@angular/core';
import { RBAC_RULES } from '@/core/tokens/rbac.token';

@Directive({
  selector: '[appCanRead]',
  standalone: true
})
export class CanReadDirective {
  private readonly templateRef = inject(TemplateRef);
  private readonly viewContainer = inject(ViewContainerRef);
  private readonly injector = inject(Injector);
  
  // Inject the dynamically updating global signal
  private readonly rbacRulesSignal = inject(RBAC_RULES);

  private hasView = false;
  private fieldName: string | null = null;

  @Input()
  set appCanRead(fieldKey: string) {
    this.fieldName = fieldKey;
    this.updateView();
  }

  constructor() {
    // Whenever the RBAC token signal updates (like during login), we re-evaluate
    effect(() => {
      // Access the signal to track it
      this.rbacRulesSignal();
      this.updateView();
    }, { injector: this.injector });
  }

  private updateView() {
    if (!this.fieldName) return;
    
    const rules = this.rbacRulesSignal();
    const fieldRule = rules.fields?.[this.fieldName];
    // If no specific rule exists, default to allow
    const canRead = fieldRule ? fieldRule.canRead : true;

    if (canRead && !this.hasView) {
      this.viewContainer.createEmbeddedView(this.templateRef);
      this.hasView = true;
    } else if (!canRead && this.hasView) {
      this.viewContainer.clear();
      this.hasView = false;
    }
  }
}
