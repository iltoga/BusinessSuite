
import { ChangeDetectionStrategy, Component, inject, input } from '@angular/core';

import { ZardBadgeComponent } from '@/shared/components/badge';
import { ZardButtonComponent } from '@/shared/components/button';
import { TypeaheadComboboxComponent } from '@/shared/components/typeahead-combobox';

import { ServerManagementAiWorkflowFacade } from './server-management-ai-workflow.facade';
import {
  AiModelDefinition,
  AiWorkflowFailoverProvider,
  AiWorkflowFeature,
} from './server-management-ai-workflow.models';

@Component({
  selector: 'app-server-management-ai-workflow-feature-card',
  standalone: true,
  imports: [ZardBadgeComponent, ZardButtonComponent, TypeaheadComboboxComponent],
  template: `
    @if (feature(); as featureDef) {
      <div class="rounded border border-border/70 bg-muted/20 p-4">
        <div class="text-sm font-semibold">{{ featureDef.feature }}</div>
        <p class="mt-1 text-xs text-muted-foreground">
          {{ featureDef.purpose }}
        </p>

        <div class="mt-3 grid grid-cols-1 gap-4 xl:grid-cols-2">
          <div class="rounded border border-border/70 bg-background p-3">
            <label class="text-xs font-medium uppercase tracking-wide text-muted-foreground"
              >Primary Runtime</label
            >
            <p class="mt-2 text-xs">
              Provider:
              <span class="font-medium">{{
                getProviderDisplayName(getFeatureProvider(featureDef))
              }}</span>
            </p>
            @if (featureDef.modelSettingName) {
              @if (featureDef.modelSettingName === 'LLM_DEFAULT_MODEL') {
                <p class="mt-2 text-xs">
                  Model:
                  <span class="font-mono wrap-break-word">{{
                    getPrimaryModelValue() || featureDef.primaryModel
                  }}</span>
                </p>
                <p class="mt-1 text-xs text-muted-foreground">
                  Uses the global Primary Runtime Model from Runtime Defaults.
                </p>
              } @else {
                <div class="mt-2 grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1fr)_160px]">
                  <div>
                    <label class="block text-xs text-muted-foreground">Model</label>
                    <div class="mt-1 flex items-start gap-2">
                      <app-typeahead-combobox
                        class="block min-w-0 flex-1"
                        [placeholder]="'Select provider/model...'"
                        [searchPlaceholder]="'Search provider or model...'"
                        [emptyText]="'No models found.'"
                        [value]="getAiSettingValue(featureDef.modelSettingName)"
                        [disabled]="aiWorkflowSaving()"
                        [zWidth]="'full'"
                        [pageSize]="aiModelTypeaheadPageSize"
                        [loadOptions]="allProviderModelLoader"
                        (valueChange)="
                          onModelSettingComboboxChange(featureDef.modelSettingName, $event)
                        "
                      ></app-typeahead-combobox>
                      <button
                        z-button
                        zType="outline"
                        class="h-10 shrink-0"
                        [zDisabled]="
                          aiWorkflowSaving() || !getAiSettingValue(featureDef.modelSettingName)
                        "
                        (click)="resetAiWorkflowSetting(featureDef.modelSettingName)"
                      >
                        Reset
                      </button>
                    </div>
                  </div>
                  @if (featureDef.primaryTimeoutSettingName) {
                    <div>
                      <label class="block text-xs text-muted-foreground">Primary Timeout</label>
                      <input
                        type="number"
                        min="1"
                        class="mt-1 h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                        [value]="getAiSettingValue(featureDef.primaryTimeoutSettingName)"
                        [disabled]="aiWorkflowSaving()"
                        (change)="
                          setAiSettingNumberFromEvent(featureDef.primaryTimeoutSettingName, $event)
                        "
                      />
                    </div>
                  }
                </div>
                @if (!getAiSettingValue(featureDef.modelSettingName)) {
                  <p class="mt-2 text-xs text-muted-foreground">
                    Inheriting primary model:
                    <span class="font-mono wrap-break-word">{{
                      featureDef.primaryModel || getPrimaryModelValue() || 'n/a'
                    }}</span>
                  </p>
                }
              }
              @if (
                findModelDefinitionForSetting(
                  featureDef.modelSettingName,
                  getFeatureProvider(featureDef),
                  getAiSettingValue(featureDef.modelSettingName)
                );
                as selectedModel
              ) {
                <p class="mt-2 text-xs text-muted-foreground">
                  {{ selectedModel.description }} • {{ formatModelCapabilities(selectedModel) }}
                </p>
              }
              @if (featureDef.primaryTimeoutSeconds) {
                <p class="mt-2 text-xs text-muted-foreground">
                  Router moves to the failover chain if this primary attempt errors or exceeds
                  {{ featureDef.primaryTimeoutSeconds }}s.
                </p>
              }
            } @else {
              <p class="text-xs">
                Model:
                <span class="font-mono wrap-break-word">{{ featureDef.primaryModel }}</span>
              </p>
            }
            <p class="mt-2 text-xs text-muted-foreground">
              {{ featureDef.modelStrategy }}
            </p>
          </div>

          <div class="rounded border border-border/70 bg-background p-3">
            <label class="text-xs font-medium uppercase tracking-wide text-muted-foreground"
              >Failover Providers</label
            >
            @if (featureDef.failoverProviders.length === 0) {
              <p class="mt-2 text-xs text-muted-foreground">No failover providers configured.</p>
            } @else {
              <div class="mt-2 space-y-2">
                @for (failover of featureDef.failoverProviders; track trackFailoverProvider(failover)) {
                  <div
                    class="flex flex-wrap items-center justify-between gap-2 rounded border border-border/70 bg-muted/30 p-2"
                  >
                    <div class="min-w-0">
                      <p class="text-xs font-medium">{{ failover.providerName }}</p>
                      <p class="text-xs font-mono wrap-break-word">
                        {{ failover.model || 'n/a' }}
                      </p>
                      @if (failover.timeoutSeconds) {
                        <p class="mt-1 text-xs text-muted-foreground">
                          Timeout: {{ failover.timeoutSeconds }}s
                        </p>
                      }
                    </div>
                    <z-badge [zType]="getFailoverProviderBadgeType(failover)">
                      {{ getFailoverProviderStatus(failover) }}
                    </z-badge>
                  </div>
                }
              </div>
            }
          </div>
        </div>

        @if (featureDef.modelFailoverSettingName) {
          <div class="mt-3 rounded border border-border/70 bg-background p-3">
            <label class="text-xs font-medium uppercase tracking-wide text-muted-foreground"
              >Model Failover</label
            >
            <div class="mt-2 flex items-start gap-2">
              <app-typeahead-combobox
                class="block min-w-0 flex-1"
                [placeholder]="'Select failover provider/model...'"
                [searchPlaceholder]="'Search provider or model...'"
                [emptyText]="'No models found.'"
                [value]="getAiSettingValue(featureDef.modelFailoverSettingName)"
                [disabled]="aiWorkflowSaving()"
                [zWidth]="'full'"
                [pageSize]="aiModelTypeaheadPageSize"
                [loadOptions]="allProviderModelLoader"
                (valueChange)="
                  onModelSettingComboboxChange(featureDef.modelFailoverSettingName, $event)
                "
              ></app-typeahead-combobox>
              <button
                z-button
                zType="outline"
                class="h-10 shrink-0"
                [zDisabled]="
                  aiWorkflowSaving() || !getAiSettingValue(featureDef.modelFailoverSettingName)
                "
                (click)="resetAiWorkflowSetting(featureDef.modelFailoverSettingName)"
              >
                Reset
              </button>
            </div>
            @if (
              findModelDefinitionForSetting(
                featureDef.modelFailoverSettingName,
                getFeatureProvider(featureDef),
                getAiSettingValue(featureDef.modelFailoverSettingName)
              );
              as selectedFailoverModel
            ) {
              <p class="mt-2 text-xs text-muted-foreground">
                {{ selectedFailoverModel.description }} •
                {{ formatModelCapabilities(selectedFailoverModel) }}
              </p>
            }
            @if (featureDef.modelFailover.strategy) {
              <p class="mt-1 text-xs text-muted-foreground">
                {{ featureDef.modelFailover.strategy }}
              </p>
            }
          </div>
        }
      </div>
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ServerManagementAiWorkflowFeatureCardComponent {
  private readonly facade = inject(ServerManagementAiWorkflowFacade);

  readonly feature = input.required<AiWorkflowFeature>();
  readonly aiWorkflowSaving = this.facade.aiWorkflowSaving;
  readonly aiModelTypeaheadPageSize = this.facade.aiModelTypeaheadPageSize;
  readonly allProviderModelLoader = this.facade.allProviderModelLoader;

  readonly getPrimaryModelValue = () => this.facade.getPrimaryModelValue();
  readonly getAiSettingValue = (name: string | null | undefined) =>
    this.facade.getAiSettingValue(name);
  readonly onModelSettingComboboxChange = (
    settingName: string | null | undefined,
    value: string | string[] | null,
  ) => this.facade.onModelSettingComboboxChange(settingName, value);
  readonly setAiSettingNumberFromEvent = (name: string, event: Event) =>
    this.facade.setAiSettingNumberFromEvent(name, event);
  readonly resetAiWorkflowSetting = (settingName: string | null | undefined) =>
    this.facade.resetAiWorkflowSetting(settingName);
  readonly getProviderDisplayName = (provider: string) =>
    this.facade.getProviderDisplayName(provider);
  readonly getFeatureProvider = (feature: AiWorkflowFeature) =>
    this.facade.getFeatureProvider(feature);
  readonly findModelDefinitionForSetting = (
    settingName: string | null | undefined,
    providerFallback: string | null | undefined,
    modelId: string | null | undefined,
  ) => this.facade.findModelDefinitionForSetting(settingName, providerFallback, modelId);
  readonly formatModelCapabilities = (model: AiModelDefinition) =>
    this.facade.formatModelCapabilities(model);
  readonly getFailoverProviderBadgeType = (provider: AiWorkflowFailoverProvider) =>
    this.facade.getFailoverProviderBadgeType(provider);
  readonly getFailoverProviderStatus = (provider: AiWorkflowFailoverProvider) =>
    this.facade.getFailoverProviderStatus(provider);
  readonly trackFailoverProvider = (provider: AiWorkflowFailoverProvider) =>
    `${provider.provider}:${provider.model}`;
}
