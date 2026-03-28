import { Directive, Input, TemplateRef, ViewContainerRef, inject, effect, Injector } from '@angular/core';
import { RBAC_RULES } from '@/core/tokens/rbac.token';

@Directive({
  selector: '[appCanWrite]',
  standalone: true
})
export class CanWriteDirective {
  private readonly templateRef = inject(TemplateRef);
  private readonly viewContainer = inject(ViewContainerRef);
  private readonly injector = inject(Injector);
  
  private readonly rbacRulesSignal = inject(RBAC_RULES);

  private hasView = false;
  private fieldName: string | null = null;

  @Input()
  set appCanWrite(fieldKey: string) {
    this.fieldName = fieldKey;
    this.updateView();
  }

  constructor() {
    effect(() => {
      this.rbacRulesSignal();
      this.updateView();
    }, { injector: this.injector });
  }

  private updateView() {
    if (!this.fieldName) return;
    
    const rules = this.rbacRulesSignal();
    const fieldRule = rules.fields?.[this.fieldName];
    const canWrite = fieldRule ? fieldRule.canWrite : true;

    if (canWrite && !this.hasView) {
      this.viewContainer.createEmbeddedView(this.templateRef);
      this.hasView = true;
    } else if (!canWrite && this.hasView) {
      this.viewContainer.clear();
      this.hasView = false;
    }
  }
}
