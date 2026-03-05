import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { catchError, EMPTY, finalize, Observable, of } from 'rxjs';

import { ServerManagementService } from '@/core/api';
import { GlobalToastService } from '@/core/services/toast.service';
import { TypeaheadOption } from '@/shared/components/typeahead-combobox';

import {
  AiModelDefinition,
  AiModelProviderCatalog,
  AiProviderModelOption,
  AiWorkflowFailoverProvider,
  AiWorkflowFeature,
  AiWorkflowStatusResponse,
  AiRuntimeSettingRow,
  AiWorkflowBinding,
} from './server-management-ai-workflow.models';

const CLEARABLE_WORKFLOW_MODEL_SETTINGS = new Set([
  'INVOICE_IMPORT_MODEL',
  'PASSPORT_OCR_MODEL',
  'DOCUMENT_CATEGORIZER_MODEL',
  'DOCUMENT_CATEGORIZER_MODEL_HIGH',
  'DOCUMENT_VALIDATOR_MODEL',
  'DOCUMENT_OCR_STRUCTURED_MODEL',
  'CHECK_PASSPORT_MODEL',
]);

@Injectable({
  providedIn: 'root',
})
export class ServerManagementAiWorkflowFacade {
  private readonly serverManagementApi = inject(ServerManagementService);
  private readonly http = inject(HttpClient);
  private readonly toast = inject(GlobalToastService);

  readonly aiWorkflowStatus = signal<AiWorkflowStatusResponse | null>(null);
  readonly aiWorkflowLoading = signal(false);
  readonly aiWorkflowSaving = signal(false);
  readonly aiWorkflowDraft = signal<Record<string, unknown>>({});
  readonly aiModelTypeaheadPageSize = 25;

  readonly allProviderModelLoader = (query?: string, page = 1): Observable<TypeaheadOption[]> =>
    of(this.queryTypeaheadModelOptions({ query, page }));

  readonly openrouterModelLoader = (query?: string, page = 1): Observable<TypeaheadOption[]> =>
    of(this.queryTypeaheadModelOptions({ query, page, provider: 'openrouter' }));

  readonly openaiModelLoader = (query?: string, page = 1): Observable<TypeaheadOption[]> =>
    of(this.queryTypeaheadModelOptions({ query, page, provider: 'openai' }));

  readonly groqModelLoader = (query?: string, page = 1): Observable<TypeaheadOption[]> =>
    of(this.queryTypeaheadModelOptions({ query, page, provider: 'groq' }));

  loadAiWorkflowStatus(): void {
    this.aiWorkflowLoading.set(true);
    this.serverManagementApi
      .serverManagementOpenrouterStatusRetrieve()
      .pipe(
        catchError(() => {
          this.toast.error('Failed to load AI workflow model settings');
          return EMPTY;
        }),
        finalize(() => this.aiWorkflowLoading.set(false)),
      )
      .subscribe((response) => {
        const normalized = this.normalizeAiWorkflowStatus(response);
        this.aiWorkflowStatus.set(normalized);
        this.aiWorkflowDraft.set(this.cloneAiSettingsMap(normalized.aiModels.settingsMap));
      });
  }

  saveAiWorkflowSettings(): void {
    this.patchAiWorkflowSettings(this.aiWorkflowDraft(), {
      errorPrefix: 'Failed to update AI settings',
      successMessage: 'AI runtime settings updated',
    });
  }

  resetAiWorkflowDraft(): void {
    const status = this.aiWorkflowStatus();
    if (!status) {
      return;
    }
    this.aiWorkflowDraft.set(this.cloneAiSettingsMap(status.aiModels.settingsMap));
  }

  getAiSettingValue(name: string | null | undefined): string {
    if (!name) {
      return '';
    }
    const value = this.aiWorkflowDraft()[name];
    if (Array.isArray(value)) {
      return value.map((item) => String(item)).join(',');
    }
    if (typeof value === 'boolean') {
      return value ? 'true' : 'false';
    }
    if (value === null || value === undefined) {
      return '';
    }
    return String(value);
  }

  getAiSettingBool(name: string | null | undefined): boolean {
    if (!name) {
      return false;
    }
    const value = this.aiWorkflowDraft()[name];
    if (typeof value === 'boolean') {
      return value;
    }
    return String(value ?? '')
      .trim()
      .toLowerCase() === 'true';
  }

  setAiSettingFromEvent(name: string | null | undefined, event: Event): void {
    if (!name) {
      return;
    }
    const target = event.target as HTMLInputElement | HTMLSelectElement;
    this.patchAiWorkflowSettings(
      { [name]: target.value ?? '' },
      { errorPrefix: `Failed to update ${name}` },
    );
  }

  setAiSettingNumberFromEvent(name: string, event: Event): void {
    const target = event.target as HTMLInputElement;
    const value = Number(target.value);
    this.patchAiWorkflowSettings(
      { [name]: Number.isFinite(value) ? value : 0 },
      { errorPrefix: `Failed to update ${name}` },
    );
  }

  setAiSettingBoolFromEvent(name: string, event: Event): void {
    const target = event.target as HTMLInputElement;
    this.patchAiWorkflowSettings(
      { [name]: Boolean(target.checked) },
      { errorPrefix: `Failed to update ${name}` },
    );
  }

  getPrimaryModelValue(): string {
    return (
      this.getAiSettingValue('LLM_DEFAULT_MODEL') ||
      this.aiWorkflowStatus()?.aiModels.defaultModel ||
      ''
    );
  }

  onPrimaryModelValueChange(value: string | string[] | null): void {
    const modelId = this.normalizeTypeaheadValue(value);
    if (!modelId) {
      return;
    }
    const provider = this.getProviderForModel(modelId, this.getCurrentPrimaryProvider());
    if (!provider) {
      this.toast.error(`Unable to resolve provider for model '${modelId}'.`);
      return;
    }

    const updates: Record<string, unknown> = {
      LLM_PROVIDER: provider,
      LLM_DEFAULT_MODEL: modelId,
    };

    this.patchAiWorkflowSettings(updates, {
      errorPrefix: 'Failed to update primary runtime model',
    });
  }

  onModelSettingComboboxChange(
    settingName: string | null | undefined,
    value: string | string[] | null,
  ): void {
    const normalizedSettingName = String(settingName ?? '').trim();
    if (!normalizedSettingName) {
      return;
    }
    const modelId = this.normalizeTypeaheadValue(value);
    if (!modelId) {
      if (CLEARABLE_WORKFLOW_MODEL_SETTINGS.has(normalizedSettingName)) {
        this.patchAiWorkflowSettings(
          { [normalizedSettingName]: null },
          { errorPrefix: `Failed to update ${normalizedSettingName}` },
        );
      }
      return;
    }
    if (normalizedSettingName === 'LLM_DEFAULT_MODEL') {
      this.onPrimaryModelValueChange(modelId);
      return;
    }
    this.patchAiWorkflowSettings(
      { [normalizedSettingName]: modelId },
      { errorPrefix: `Failed to update ${normalizedSettingName}` },
    );
  }

  resetAiWorkflowSetting(settingName: string | null | undefined): void {
    const normalizedSettingName = String(settingName ?? '').trim();
    if (!normalizedSettingName) {
      return;
    }
    this.patchAiWorkflowSettings(
      { [normalizedSettingName]: null },
      { errorPrefix: `Failed to reset ${normalizedSettingName}` },
    );
  }

  getDraftFallbackProviderOrder(): string[] {
    const raw = this.aiWorkflowDraft()['LLM_FALLBACK_PROVIDER_ORDER'];
    if (Array.isArray(raw)) {
      return raw.map((item) => String(item).trim().toLowerCase()).filter(Boolean);
    }
    if (raw === null || raw === undefined) {
      return [];
    }
    return String(raw)
      .split(',')
      .map((value) => value.trim().toLowerCase())
      .filter(Boolean);
  }

  toggleFallbackProvider(provider: string, enabled: boolean): void {
    const current = this.getDraftFallbackProviderOrder();
    const normalized = provider.trim().toLowerCase();
    const next = enabled
      ? current.includes(normalized)
        ? current
        : [...current, normalized]
      : current.filter((item) => item !== normalized);
    this.patchAiWorkflowSettings(
      { LLM_FALLBACK_PROVIDER_ORDER: next },
      { errorPrefix: 'Failed to update fallback provider order' },
    );
  }

  getModelProviderCatalogMap(): Record<string, AiModelProviderCatalog> {
    return this.aiWorkflowStatus()?.aiModels.modelCatalog.providers ?? {};
  }

  getProviderKeys(): string[] {
    return Object.keys(this.getModelProviderCatalogMap()).sort();
  }

  getProviderDisplayName(provider: string): string {
    return this.getModelProviderCatalogMap()[provider]?.name || provider;
  }

  getModelsForProvider(provider: string): AiModelDefinition[] {
    return this.getModelProviderCatalogMap()[provider]?.models ?? [];
  }

  getCurrentPrimaryProvider(): string {
    const candidate = String(this.getAiSettingValue('LLM_PROVIDER') || '').trim().toLowerCase();
    if (candidate) {
      return candidate;
    }
    return String(this.aiWorkflowStatus()?.aiModels.provider || 'openrouter').trim().toLowerCase();
  }

  getAllProviderModels(): AiProviderModelOption[] {
    const all: AiProviderModelOption[] = [];
    for (const provider of this.getProviderKeys()) {
      for (const model of this.getModelsForProvider(provider)) {
        all.push({ provider, model });
      }
    }
    return all;
  }

  getModelsForSetting(
    settingName: string | null | undefined,
    providerFallback?: string | null | undefined,
  ): AiModelDefinition[] {
    const normalizedSettingName = String(settingName ?? '').trim();
    const providerCatalog = this.getModelProviderCatalogMap();
    const providersByPriority = ['openrouter', 'openai'];
    const selectedProvider =
      String(providerFallback ?? '').trim() ||
      String(this.getAiSettingValue('LLM_PROVIDER') || '').trim() ||
      'openrouter';

    let models: AiModelDefinition[] = [];
    if (normalizedSettingName === 'OPENROUTER_DEFAULT_MODEL') {
      models = this.getModelsForProvider('openrouter');
    } else if (normalizedSettingName === 'OPENAI_DEFAULT_MODEL') {
      models = this.getModelsForProvider('openai');
    } else if (normalizedSettingName === 'GROQ_DEFAULT_MODEL') {
      models = this.getModelsForProvider('groq');
    } else if (normalizedSettingName === 'LLM_DEFAULT_MODEL') {
      const providerForDefault = this.getCurrentPrimaryProvider();
      models = this.getModelsForProvider(providerForDefault);
    } else {
      const merged: AiModelDefinition[] = [];
      const seen = new Set<string>();
      for (const provider of providersByPriority) {
        for (const model of this.getModelsForProvider(provider)) {
          if (seen.has(model.id)) {
            continue;
          }
          seen.add(model.id);
          merged.push(model);
        }
      }
      for (const provider of Object.keys(providerCatalog)) {
        for (const model of this.getModelsForProvider(provider)) {
          if (seen.has(model.id)) {
            continue;
          }
          seen.add(model.id);
          merged.push(model);
        }
      }
      models = merged.length > 0 ? merged : this.getModelsForProvider(selectedProvider);
    }

    const currentValue = this.getAiSettingValue(normalizedSettingName);
    return this.withCurrentModelOption(models, currentValue);
  }

  getFeatureProvider(feature: AiWorkflowFeature): string {
    const settingName = feature.providerSettingName;
    if (settingName) {
      const selected = String(this.aiWorkflowDraft()[settingName] ?? '').trim().toLowerCase();
      if (selected) {
        return selected;
      }
    }
    return feature.primaryProvider || this.aiWorkflowStatus()?.aiModels.provider || 'openrouter';
  }

  formatModelCapabilities(model: AiModelDefinition): string {
    const parts = [
      model.capabilities.vision ? 'vision' : null,
      model.capabilities.fileUpload ? 'file upload' : null,
      model.capabilities.reasoning ? 'reasoning' : null,
    ].filter(Boolean);
    return parts.length ? parts.join(' | ') : 'no capability metadata';
  }

  findModelDefinition(
    provider: string,
    modelId: string | null | undefined,
  ): AiModelDefinition | null {
    const normalizedModelId = String(modelId ?? '').trim();
    if (!normalizedModelId) {
      return null;
    }
    return this.getModelsForProvider(provider).find((model) => model.id === normalizedModelId) ?? null;
  }

  findModelDefinitionForSetting(
    settingName: string | null | undefined,
    providerFallback: string | null | undefined,
    modelId: string | null | undefined,
  ): AiModelDefinition | null {
    const normalizedModelId = String(modelId ?? '').trim();
    if (!normalizedModelId) {
      return null;
    }
    const preferredProvider = String(providerFallback ?? '').trim().toLowerCase() || null;
    const provider = this.getProviderForModel(normalizedModelId, preferredProvider);
    if (!provider) {
      return this.getModelsForSetting(settingName, providerFallback).find((model) => model.id === normalizedModelId) ?? null;
    }
    return this.findModelDefinition(provider, normalizedModelId);
  }

  getFailoverProviderBadgeType(
    provider: AiWorkflowFailoverProvider,
  ): 'default' | 'secondary' | 'destructive' {
    if (provider.active) {
      return 'default';
    }
    if (!provider.available) {
      return 'destructive';
    }
    return 'secondary';
  }

  getFailoverProviderStatus(provider: AiWorkflowFailoverProvider): string {
    if (provider.active) {
      return 'Active';
    }
    if (!provider.available) {
      return 'Unavailable';
    }
    return 'Configured';
  }

  private patchAiWorkflowSettings(
    updates: Record<string, unknown>,
    options?: {
      errorPrefix?: string;
      successMessage?: string;
    },
  ): void {
    if (this.aiWorkflowSaving() || !this.aiWorkflowStatus()) {
      return;
    }
    const updateEntries = Object.entries(updates).filter(
      ([rawName]) => String(rawName ?? '').trim().length > 0,
    );
    if (updateEntries.length === 0) {
      return;
    }

    const normalizedUpdates: Record<string, unknown> = {};
    updateEntries.forEach(([rawName, value]) => {
      normalizedUpdates[String(rawName)] = value;
    });

    const previousDraft = this.cloneAiSettingsMap(this.aiWorkflowDraft());
    this.aiWorkflowDraft.update((current) => ({ ...current, ...normalizedUpdates }));
    this.aiWorkflowSaving.set(true);

    this.http
      .patch('/api/server-management/openrouter-status/', {
        settings: normalizedUpdates,
      })
      .pipe(
        catchError((error) => {
          this.aiWorkflowDraft.set(previousDraft);
          const detail = error?.error?.detail;
          const fallbackPrefix = options?.errorPrefix || 'Failed to update AI settings';
          this.toast.error(detail ? `${fallbackPrefix}: ${detail}` : fallbackPrefix);
          return EMPTY;
        }),
        finalize(() => this.aiWorkflowSaving.set(false)),
      )
      .subscribe((response) => {
        const normalized = this.normalizeAiWorkflowStatus(response);
        this.aiWorkflowStatus.set(normalized);
        this.aiWorkflowDraft.set(this.cloneAiSettingsMap(normalized.aiModels.settingsMap));
        if (options?.successMessage) {
          this.toast.success(options.successMessage);
        }
      });
  }

  private normalizeTypeaheadValue(value: string | string[] | null): string {
    const single = Array.isArray(value) ? value[0] : value;
    return String(single ?? '').trim();
  }

  private getProviderForModel(
    modelId: string | null | undefined,
    preferredProvider?: string | null,
  ): string | null {
    const normalizedModelId = String(modelId ?? '').trim();
    if (!normalizedModelId) {
      return null;
    }

    const preferred = String(preferredProvider ?? '')
      .trim()
      .toLowerCase();
    if (
      preferred &&
      this.getModelsForProvider(preferred).some((model) => model.id === normalizedModelId)
    ) {
      return preferred;
    }

    for (const provider of this.getProviderKeys()) {
      if (this.getModelsForProvider(provider).some((model) => model.id === normalizedModelId)) {
        return provider;
      }
    }
    return null;
  }

  private queryTypeaheadModelOptions({
    query,
    page = 1,
    provider,
  }: {
    query?: string;
    page?: number;
    provider?: string | null;
  }): TypeaheadOption[] {
    const selectedProvider = String(provider ?? '')
      .trim()
      .toLowerCase();
    const source = selectedProvider
      ? this.getModelsForProvider(selectedProvider).map((model) => ({
          provider: selectedProvider,
          model,
        }))
      : this.getAllProviderModels();

    const normalizedQuery = String(query ?? '')
      .trim()
      .toLowerCase();
    const mapped = source
      .map((entry) => this.mapProviderModelToTypeahead(entry.provider, entry.model))
      .filter((option) => {
        if (!normalizedQuery) {
          return true;
        }
        const haystack = String(
          option.search ??
            `${option.label} ${option.code || ''} ${option.description || ''} ${option.display || ''}`,
        ).toLowerCase();
        return haystack.includes(normalizedQuery);
      });

    const safePage = Number.isFinite(page) && page > 0 ? page : 1;
    const start = (safePage - 1) * this.aiModelTypeaheadPageSize;
    const end = start + this.aiModelTypeaheadPageSize;
    return mapped.slice(start, end);
  }

  private mapProviderModelToTypeahead(provider: string, model: AiModelDefinition): TypeaheadOption {
    const providerName = this.getProviderDisplayName(provider);
    return {
      value: model.id,
      label: model.name,
      display: `${providerName} | ${model.name}`,
      code: providerName,
      description: model.id,
      search: `${providerName} ${provider} ${model.name} ${model.id} ${model.description}`.toLowerCase(),
    };
  }

  private normalizeAiWorkflowStatus(raw: any): AiWorkflowStatusResponse {
    const aiModelsRaw = raw?.aiModels ?? {};
    const failoverRaw = aiModelsRaw?.failover ?? {};
    const featuresRaw = Array.isArray(aiModelsRaw?.features) ? aiModelsRaw.features : [];
    const runtimeSettingsRaw = Array.isArray(aiModelsRaw?.runtimeSettings)
      ? aiModelsRaw.runtimeSettings
      : [];
    const workflowBindingsRaw = Array.isArray(aiModelsRaw?.workflowBindings)
      ? aiModelsRaw.workflowBindings
      : [];
    const modelCatalogRaw = aiModelsRaw?.modelCatalog ?? {};
    const settingsMapRaw =
      aiModelsRaw?.settingsMap && typeof aiModelsRaw.settingsMap === 'object'
        ? aiModelsRaw.settingsMap
        : {};
    const normalizedSettingsMap: Record<string, unknown> = {};
    Object.entries(settingsMapRaw).forEach(([rawKey, value]) => {
      normalizedSettingsMap[this.normalizeAiSettingName(rawKey)] = value;
    });

    const features: AiWorkflowFeature[] = featuresRaw.map((feature: any) => {
      const failoverProvidersRaw = Array.isArray(feature?.failoverProviders)
        ? feature.failoverProviders
        : [];
      const modelFailoverRaw = feature?.modelFailover ?? {};
      const provider = String(feature?.provider ?? aiModelsRaw?.provider ?? 'unknown');
      const providerName = String(
        feature?.providerName ?? feature?.primaryProviderName ?? aiModelsRaw?.providerName ?? provider,
      );
      const primaryProvider = String(feature?.primaryProvider ?? provider);
      const primaryProviderName = String(feature?.primaryProviderName ?? providerName);
      const primaryModel = String(
        feature?.primaryModel ?? feature?.effectiveModel ?? aiModelsRaw?.defaultModel ?? '',
      );

      return {
        feature: String(feature?.feature ?? 'Unknown AI Workflow'),
        purpose: String(feature?.purpose ?? ''),
        modelStrategy: String(feature?.modelStrategy ?? ''),
        provider,
        providerName,
        primaryProvider,
        primaryProviderName,
        primaryModel,
        effectiveModel: String(feature?.effectiveModel ?? primaryModel),
        providerSettingName: feature?.providerSettingName ?? null,
        modelSettingName: feature?.modelSettingName ?? null,
        modelFailoverSettingName: feature?.modelFailoverSettingName ?? null,
        failoverProviders: failoverProvidersRaw.map((providerRow: any) => {
          const providerKey = String(providerRow?.provider ?? 'unknown');
          return {
            provider: providerKey,
            providerName: String(providerRow?.providerName ?? providerKey),
            model: String(providerRow?.model ?? ''),
            available: Boolean(providerRow?.available),
            active: Boolean(providerRow?.active),
          };
        }),
        modelFailover: {
          enabled: Boolean(modelFailoverRaw?.enabled),
          model: modelFailoverRaw?.model ?? null,
          strategy: modelFailoverRaw?.strategy ?? null,
        },
      };
    });

    const runtimeSettings: AiRuntimeSettingRow[] = runtimeSettingsRaw.map((item: any) => ({
      name: String(item?.name ?? ''),
      valueType: String(item?.valueType ?? ''),
      scope: String(item?.scope ?? ''),
      description: String(item?.description ?? ''),
      defaultValue: item?.defaultValue,
      value: item?.value,
    }));

    const workflowBindings: AiWorkflowBinding[] = workflowBindingsRaw.map((item: any) => ({
      feature: String(item?.feature ?? ''),
      providerSettingName: item?.providerSettingName ?? null,
      modelSettingName: item?.modelSettingName ?? null,
      modelFailoverSettingName: item?.modelFailoverSettingName ?? null,
    }));

    const providersRaw =
      modelCatalogRaw?.providers && typeof modelCatalogRaw.providers === 'object'
        ? modelCatalogRaw.providers
        : {};
    const providers: Record<string, AiModelProviderCatalog> = {};
    Object.entries(providersRaw).forEach(([providerKey, providerValue]) => {
      const providerData = providerValue as any;
      const modelsRaw = Array.isArray(providerData?.models) ? providerData.models : [];
      providers[providerKey] = {
        name: String(providerData?.name ?? providerKey),
        models: modelsRaw.map((model: any) => ({
          id: String(model?.id ?? ''),
          name: String(model?.name ?? model?.id ?? ''),
          description: String(model?.description ?? ''),
          capabilities: {
            vision: Boolean(model?.capabilities?.vision),
            fileUpload: Boolean(model?.capabilities?.fileUpload),
            reasoning: Boolean(model?.capabilities?.reasoning),
          },
        })),
      };
    });

    return {
      aiModels: {
        provider: String(aiModelsRaw?.provider ?? 'unknown'),
        providerName: String(aiModelsRaw?.providerName ?? aiModelsRaw?.provider ?? 'unknown'),
        defaultModel: String(aiModelsRaw?.defaultModel ?? ''),
        settingsMap: this.cloneAiSettingsMap(normalizedSettingsMap),
        runtimeSettings,
        workflowBindings,
        modelCatalog: { providers },
        failover: {
          enabled: Boolean(failoverRaw?.enabled),
          configuredProviderOrder: Array.isArray(failoverRaw?.configuredProviderOrder)
            ? failoverRaw.configuredProviderOrder.map((provider: unknown) => String(provider))
            : [],
          effectiveProviderOrder: Array.isArray(failoverRaw?.effectiveProviderOrder)
            ? failoverRaw.effectiveProviderOrder.map((provider: unknown) => String(provider))
            : [],
          stickySeconds:
            typeof failoverRaw?.stickySeconds === 'number' ? failoverRaw.stickySeconds : undefined,
        },
        features,
      },
    };
  }

  private cloneAiSettingsMap(raw: Record<string, unknown>): Record<string, unknown> {
    const cloned: Record<string, unknown> = {};
    Object.entries(raw ?? {}).forEach(([key, value]) => {
      if (Array.isArray(value)) {
        cloned[key] = [...value];
      } else if (value && typeof value === 'object') {
        cloned[key] = { ...(value as Record<string, unknown>) };
      } else {
        cloned[key] = value;
      }
    });
    return cloned;
  }

  private withCurrentModelOption(
    models: AiModelDefinition[],
    currentModelId: string,
  ): AiModelDefinition[] {
    const normalizedCurrentModelId = String(currentModelId ?? '').trim();
    if (
      !normalizedCurrentModelId ||
      models.some((model) => model.id === normalizedCurrentModelId)
    ) {
      return models;
    }
    return [
      {
        id: normalizedCurrentModelId,
        name: `Custom model`,
        description: `Saved value (${normalizedCurrentModelId}) is not currently listed in llm_models.json.`,
        capabilities: {
          vision: false,
          fileUpload: false,
          reasoning: false,
        },
      },
      ...models,
    ];
  }

  private normalizeAiSettingName(rawName: string): string {
    const candidate = String(rawName || '').trim();
    if (!candidate) {
      return '';
    }
    return candidate
      .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
      .replace(/-/g, '_')
      .toUpperCase();
  }
}
