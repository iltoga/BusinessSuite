export interface AiWorkflowFailoverProvider {
  provider: string;
  providerName: string;
  model: string;
  available: boolean;
  active: boolean;
}

export interface AiWorkflowModelFailover {
  enabled: boolean;
  model?: string | null;
  strategy?: string | null;
}

export interface AiWorkflowFeature {
  feature: string;
  purpose: string;
  modelStrategy: string;
  provider: string;
  providerName: string;
  primaryProvider: string;
  primaryProviderName: string;
  primaryModel: string;
  effectiveModel: string;
  providerSettingName?: string | null;
  modelSettingName?: string | null;
  modelFailoverSettingName?: string | null;
  failoverProviders: AiWorkflowFailoverProvider[];
  modelFailover: AiWorkflowModelFailover;
}

export interface AiModelCapabilities {
  vision: boolean;
  fileUpload: boolean;
  reasoning: boolean;
}

export interface AiModelDefinition {
  id: string;
  name: string;
  description: string;
  capabilities: AiModelCapabilities;
}

export interface AiModelProviderCatalog {
  name: string;
  models: AiModelDefinition[];
}

export interface AiProviderModelOption {
  provider: string;
  model: AiModelDefinition;
}

export interface AiRuntimeSettingRow {
  name: string;
  valueType: string;
  scope: string;
  description: string;
  defaultValue?: unknown;
  value?: unknown;
}

export interface AiWorkflowBinding {
  feature: string;
  providerSettingName?: string | null;
  modelSettingName?: string | null;
  modelFailoverSettingName?: string | null;
}

export interface AiWorkflowStatusResponse {
  aiModels: {
    provider: string;
    providerName: string;
    defaultModel: string;
    settingsMap: Record<string, unknown>;
    runtimeSettings: AiRuntimeSettingRow[];
    workflowBindings: AiWorkflowBinding[];
    modelCatalog: {
      providers: Record<string, AiModelProviderCatalog>;
    };
    failover: {
      enabled: boolean;
      configuredProviderOrder: string[];
      effectiveProviderOrder: string[];
      stickySeconds?: number;
    };
    features: AiWorkflowFeature[];
  };
}
