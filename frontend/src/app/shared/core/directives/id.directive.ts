import { Directive, inject, Injectable, input, signal } from '@angular/core';

@Injectable({ providedIn: 'root' })
class ZardIdInternalService {
  private counter = 0;
  generate(prefix: string) {
    return `${prefix}-${++this.counter}`;
  }
}

@Directive({
  selector: '[zardId]',
  exportAs: 'zardId',
})
export class ZardIdDirective {
  private idService = inject(ZardIdInternalService);

  readonly zardId = input('ssr');

  // Use a simple non-computed property for the ID to ensure it is generated once per instance
  // and stays stable. Computed signals should be pure.
  public readonly id = signal('');

  constructor() {
    // Generate the ID once on initialization
    this.id.set(this.idService.generate(this.zardId()));
  }
}
