import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject } from '@angular/core';

import { ZardBadgeComponent } from '@/shared/components/badge';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
import { TypeaheadComboboxComponent } from '@/shared/components/typeahead-combobox';

import { ServerManagementAiWorkflowFailoverChainComponent } from './server-management-ai-workflow-failover-chain.component';
import { ServerManagementAiWorkflowFacade } from './server-management-ai-workflow.facade';
import { ServerManagementAiWorkflowFeatureCardComponent } from './server-management-ai-workflow-feature-card.component';

@Component({
  selector: 'app-server-management-ai-workflow',
  standalone: true,
  imports: [
    CommonModule,
    ZardCardComponent,
    ZardButtonComponent,
    ZardBadgeComponent,
    TypeaheadComboboxComponent,
    ServerManagementAiWorkflowFailoverChainComponent,
    ServerManagementAiWorkflowFeatureCardComponent,
  ],
  templateUrl: './server-management-ai-workflow.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ServerManagementAiWorkflowComponent {
  private readonly facade = inject(ServerManagementAiWorkflowFacade);

  readonly aiWorkflowStatus = this.facade.aiWorkflowStatus;
  readonly aiWorkflowLoading = this.facade.aiWorkflowLoading;
  readonly aiWorkflowSaving = this.facade.aiWorkflowSaving;
  readonly aiWorkflowDraft = this.facade.aiWorkflowDraft;
  readonly aiModelTypeaheadPageSize = this.facade.aiModelTypeaheadPageSize;

  readonly allProviderModelLoader = this.facade.allProviderModelLoader;
  readonly openrouterModelLoader = this.facade.openrouterModelLoader;
  readonly openaiModelLoader = this.facade.openaiModelLoader;
  readonly groqModelLoader = this.facade.groqModelLoader;

  readonly loadAiWorkflowStatus = () => this.facade.loadAiWorkflowStatus();
  readonly getPrimaryModelValue = () => this.facade.getPrimaryModelValue();
  readonly onPrimaryModelValueChange = (value: string | string[] | null) =>
    this.facade.onPrimaryModelValueChange(value);
  readonly getAiSettingValue = (name: string | null | undefined) =>
    this.facade.getAiSettingValue(name);
  readonly getAiSettingBool = (name: string | null | undefined) =>
    this.facade.getAiSettingBool(name);
  readonly setAiSettingNumberFromEvent = (name: string, event: Event) =>
    this.facade.setAiSettingNumberFromEvent(name, event);
  readonly onModelSettingComboboxChange = (
    settingName: string | null | undefined,
    value: string | string[] | null,
  ) => this.facade.onModelSettingComboboxChange(settingName, value);
  readonly resetAiWorkflowSetting = (settingName: string | null | undefined) =>
    this.facade.resetAiWorkflowSetting(settingName);
  readonly setAiSettingBoolFromEvent = (name: string, event: Event) =>
    this.facade.setAiSettingBoolFromEvent(name, event);
  readonly getProviderKeys = () => this.facade.getProviderKeys();
  readonly getProviderDisplayName = (provider: string) =>
    this.facade.getProviderDisplayName(provider);
  readonly getProviderForModelLabel = (modelId: string) =>
    this.facade.getProviderForModelLabel(modelId);
  readonly getConfiguredFailoverOrderLabel = (status: any) =>
    this.facade.getConfiguredFailoverOrderLabel(status);
  readonly getFeatureProvider = (feature: any) => this.facade.getFeatureProvider(feature);
  readonly findModelDefinitionForSetting = (
    settingName: string | null | undefined,
    providerFallback: string | null | undefined,
    modelId: string | null | undefined,
  ) => this.facade.findModelDefinitionForSetting(settingName, providerFallback, modelId);
  readonly formatModelCapabilities = (model: any) => this.facade.formatModelCapabilities(model);
  readonly getFailoverProviderBadgeType = (provider: any) =>
    this.facade.getFailoverProviderBadgeType(provider);
  readonly getFailoverProviderStatus = (provider: any) =>
    this.facade.getFailoverProviderStatus(provider);
}
