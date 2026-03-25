import { CdkDragDrop, DragDropModule } from '@angular/cdk/drag-drop';

import { ChangeDetectionStrategy, Component, inject } from '@angular/core';

import { ZardButtonComponent } from '@/shared/components/button';
import { ZardInputDirective } from '@/shared/components/input';
import { TypeaheadComboboxComponent } from '@/shared/components/typeahead-combobox';

import { ServerManagementAiWorkflowFacade } from './server-management-ai-workflow.facade';

@Component({
  selector: 'app-server-management-ai-workflow-failover-chain',
  standalone: true,
  imports: [
    DragDropModule,
    ZardButtonComponent,
    ZardInputDirective,
    TypeaheadComboboxComponent
],
  template: `
    <div class="mt-3 rounded border border-border/70 bg-muted/20 p-3">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p class="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Failover Model Chain
          </p>
          <p class="mt-1 text-xs text-muted-foreground">
            Primary model stays separate. Retries start from the first chain step only.
          </p>
        </div>
        <div class="min-w-0 flex-1 sm:max-w-md">
          <app-typeahead-combobox
            class="block"
            [placeholder]="'Add model to failover chain...'"
            [searchPlaceholder]="'Search provider or model...'"
            [emptyText]="'No models found.'"
            [value]="''"
            [disabled]="aiWorkflowSaving()"
            [zWidth]="'full'"
            [pageSize]="aiModelTypeaheadPageSize"
            [loadOptions]="allProviderModelLoader"
            (valueChange)="addFallbackChainStep($event)"
          ></app-typeahead-combobox>
        </div>
      </div>

      @if (getDraftFallbackModelChain().length === 0) {
        <div class="mt-3 rounded border border-dashed border-border/70 bg-background/60 px-4 py-6">
          <p class="text-sm text-muted-foreground">
            No failover steps configured. Add one or more models to define the retry chain.
          </p>
        </div>
      } @else {
        <div
          cdkDropList
          class="mt-3 flex flex-col gap-3"
          (cdkDropListDropped)="onDrop($event)"
        >
          @for (step of getDraftFallbackModelChain(); track step.model; let idx = $index) {
            <div
              cdkDrag
              class="rounded-lg border border-border/70 bg-background p-3 shadow-sm"
            >
              <div class="grid grid-cols-1 gap-3 xl:grid-cols-[auto_minmax(0,1fr)_13rem_auto] xl:items-end">
                <div class="flex items-center gap-2 text-xs text-muted-foreground">
                  <button
                    type="button"
                    class="cursor-grab rounded border border-border/70 px-2 py-2 font-mono active:cursor-grabbing"
                    cdkDragHandle
                  >
                    #{{ idx + 1 }}
                  </button>
                  <span>Drag</span>
                </div>

                <div>
                  <label class="text-xs font-medium uppercase tracking-wide text-muted-foreground"
                    >Model</label
                  >
                  <app-typeahead-combobox
                    class="mt-1 block"
                    [placeholder]="'Select provider/model...'"
                    [searchPlaceholder]="'Search provider or model...'"
                    [emptyText]="'No models found.'"
                    [value]="step.model"
                    [disabled]="aiWorkflowSaving()"
                    [zWidth]="'full'"
                    [pageSize]="aiModelTypeaheadPageSize"
                    [loadOptions]="allProviderModelLoader"
                    (valueChange)="updateFallbackChainModel(idx, $event)"
                  ></app-typeahead-combobox>
                  <p class="mt-2 text-xs text-muted-foreground">
                    {{ getProviderForModelLabel(step.model) }} • {{ step.model }}
                  </p>
                </div>

                <div>
                  <label class="text-xs font-medium uppercase tracking-wide text-muted-foreground"
                    >Timeout Seconds</label
                  >
                  <input
                    z-input
                    type="number"
                    min="1"
                    step="1"
                    class="mt-1"
                    [value]="step.timeoutSeconds.toString()"
                    [disabled]="aiWorkflowSaving()"
                    (change)="onTimeoutChange(idx, $event)"
                  />
                </div>

                <div class="flex justify-end">
                  <button
                    z-button
                    zType="outline"
                    [zDisabled]="aiWorkflowSaving()"
                    (click)="removeFallbackChainStep(idx)"
                  >
                    Remove
                  </button>
                </div>
              </div>
            </div>
          }
        </div>
      }
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ServerManagementAiWorkflowFailoverChainComponent {
  private readonly facade = inject(ServerManagementAiWorkflowFacade);

  readonly aiWorkflowSaving = this.facade.aiWorkflowSaving;
  readonly aiModelTypeaheadPageSize = this.facade.aiModelTypeaheadPageSize;
  readonly allProviderModelLoader = this.facade.allProviderModelLoader;

  readonly getDraftFallbackModelChain = () => this.facade.getDraftFallbackModelChain();
  readonly getProviderForModelLabel = (modelId: string) => this.facade.getProviderForModelLabel(modelId);
  readonly addFallbackChainStep = (value: string | string[] | null) =>
    this.facade.addFallbackChainStep(value);
  readonly updateFallbackChainModel = (index: number, value: string | string[] | null) =>
    this.facade.updateFallbackChainModel(index, value);
  readonly removeFallbackChainStep = (index: number) => this.facade.removeFallbackChainStep(index);

  onDrop(event: CdkDragDrop<unknown>): void {
    this.facade.reorderFallbackChain(event.previousIndex, event.currentIndex);
  }

  onTimeoutChange(index: number, event: Event): void {
    const target = event.target as HTMLInputElement;
    this.facade.updateFallbackChainTimeout(index, target.value);
  }
}
