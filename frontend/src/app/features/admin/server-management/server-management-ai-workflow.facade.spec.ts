import { provideHttpClient } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ServerManagementService } from '@/core/api';
import { GlobalToastService } from '@/core/services/toast.service';

import { ServerManagementAiWorkflowFacade } from './server-management-ai-workflow.facade';

const buildModelCatalog = () => ({
  providers: {
    openrouter: {
      name: 'OpenRouter',
      models: [
        {
          id: 'google/gemini-3-flash-preview',
          name: 'Gemini 3 Flash Preview',
          description: 'OpenRouter Gemini',
          capabilities: { vision: true, fileUpload: true, reasoning: true },
        },
        {
          id: 'google/gemini-2.5-flash-lite',
          name: 'Gemini 2.5 Flash Lite',
          description: 'OpenRouter Gemini Lite',
          capabilities: { vision: true, fileUpload: true, reasoning: true },
        },
      ],
    },
    groq: {
      name: 'Groq',
      models: [
        {
          id: 'qwen/qwen3-32b',
          name: 'Qwen 3 32B',
          description: 'Groq Qwen',
          capabilities: { vision: false, fileUpload: false, reasoning: true },
        },
        {
          id: 'meta-llama/llama-4-maverick-17b-128e-instruct',
          name: 'Llama 4 Maverick 17B',
          description: 'Groq Llama',
          capabilities: { vision: true, fileUpload: false, reasoning: true },
        },
      ],
    },
    openai: {
      name: 'OpenAI Direct',
      models: [
        {
          id: 'gpt-5-mini',
          name: 'GPT-5 Mini',
          description: 'OpenAI GPT-5 Mini',
          capabilities: { vision: true, fileUpload: true, reasoning: true },
        },
      ],
    },
  },
});

const buildAiWorkflowStatus = (
  settingsMap: Record<string, unknown> = {},
  overrides: Partial<Record<string, unknown>> = {},
) => ({
  aiModels: {
    provider: 'openrouter',
    providerName: 'OpenRouter',
    defaultModel: 'google/gemini-2.5-flash-lite',
    settingsMap,
    runtimeSettings: [],
    workflowBindings: [],
    modelCatalog: buildModelCatalog(),
    failover: {
      enabled: true,
      configuredProviderOrder: [],
      effectiveProviderOrder: [],
    },
    features: [],
    ...overrides,
  },
});

describe('ServerManagementAiWorkflowFacade', () => {
  let facade: ServerManagementAiWorkflowFacade;
  let mockToastService: {
    success: ReturnType<typeof vi.fn>;
    error: ReturnType<typeof vi.fn>;
    info: ReturnType<typeof vi.fn>;
  };
  let mockServerManagementService: {
    serverManagementOpenrouterStatusRetrieve: ReturnType<typeof vi.fn>;
    serverManagementOpenrouterStatusPartialUpdate: ReturnType<typeof vi.fn>;
  };

  beforeEach(async () => {
    mockToastService = {
      success: vi.fn(),
      error: vi.fn(),
      info: vi.fn(),
    };

    mockServerManagementService = {
      serverManagementOpenrouterStatusRetrieve: vi
        .fn()
        .mockReturnValue(of({ data: buildAiWorkflowStatus() })),
      serverManagementOpenrouterStatusPartialUpdate: vi
        .fn()
        .mockReturnValue(of({ data: buildAiWorkflowStatus() })),
    };

    await TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        ServerManagementAiWorkflowFacade,
        { provide: GlobalToastService, useValue: mockToastService },
        { provide: ServerManagementService, useValue: mockServerManagementService },
      ],
    }).compileComponents();

    facade = TestBed.inject(ServerManagementAiWorkflowFacade);
  });

  it('resets a workflow model setting by sending null', () => {
    facade.aiWorkflowStatus.set(
      buildAiWorkflowStatus({
        LLM_PROVIDER: 'openrouter',
        INVOICE_IMPORT_MODEL: 'gpt-5-mini',
      }),
    );
    facade.aiWorkflowDraft.set({
      LLM_PROVIDER: 'openrouter',
      INVOICE_IMPORT_MODEL: 'gpt-5-mini',
    });

    facade.resetAiWorkflowSetting('INVOICE_IMPORT_MODEL');

    expect(
      mockServerManagementService.serverManagementOpenrouterStatusPartialUpdate,
    ).toHaveBeenCalledWith({
      requestBody: { settings: { INVOICE_IMPORT_MODEL: null } },
    });

    expect(facade.getAiSettingValue('INVOICE_IMPORT_MODEL')).toBe('');
  });

  it('clears workflow model combobox values by sending null', () => {
    facade.aiWorkflowStatus.set(
      buildAiWorkflowStatus({
        LLM_PROVIDER: 'openrouter',
        INVOICE_IMPORT_MODEL: 'gpt-5-mini',
      }),
    );
    facade.aiWorkflowDraft.set({
      LLM_PROVIDER: 'openrouter',
      INVOICE_IMPORT_MODEL: 'gpt-5-mini',
    });

    facade.onModelSettingComboboxChange('INVOICE_IMPORT_MODEL', null);

    expect(
      mockServerManagementService.serverManagementOpenrouterStatusPartialUpdate,
    ).toHaveBeenCalledWith({
      requestBody: { settings: { INVOICE_IMPORT_MODEL: null } },
    });
  });

  it('ignores clear for non-workflow model settings', () => {
    facade.aiWorkflowStatus.set(
      buildAiWorkflowStatus({
        OPENAI_DEFAULT_MODEL: 'gpt-5-mini',
      }),
    );
    facade.aiWorkflowDraft.set({
      OPENAI_DEFAULT_MODEL: 'gpt-5-mini',
    });

    facade.onModelSettingComboboxChange('OPENAI_DEFAULT_MODEL', null);

    expect(
      mockServerManagementService.serverManagementOpenrouterStatusPartialUpdate,
    ).not.toHaveBeenCalled();
  });

  it('adds failover model to ordered list', () => {
    facade.aiWorkflowStatus.set(
      buildAiWorkflowStatus({
        LLM_FALLBACK_MODEL_CHAIN: [{ model: 'gpt-5-mini', timeoutSeconds: 120 }],
      }),
    );
    facade.aiWorkflowDraft.set({
      LLM_FALLBACK_MODEL_CHAIN: [{ model: 'gpt-5-mini', timeoutSeconds: 120 }],
    });

    facade.addFallbackModel('google/gemini-3-flash-preview');

    expect(
      mockServerManagementService.serverManagementOpenrouterStatusPartialUpdate,
    ).toHaveBeenCalledWith({
      requestBody: {
        settings: {
          LLM_FALLBACK_MODEL_CHAIN: [
            { model: 'gpt-5-mini', timeoutSeconds: 120 },
            { model: 'google/gemini-3-flash-preview', timeoutSeconds: 120 },
          ],
        },
      },
    });
  });

  it('reorders failover model list', () => {
    facade.aiWorkflowStatus.set(
      buildAiWorkflowStatus({
        LLM_FALLBACK_MODEL_CHAIN: [
          { model: 'gpt-5-mini', timeoutSeconds: 120 },
          { model: 'google/gemini-3-flash-preview', timeoutSeconds: 120 },
        ],
      }),
    );
    facade.aiWorkflowDraft.set({
      LLM_FALLBACK_MODEL_CHAIN: [
        { model: 'gpt-5-mini', timeoutSeconds: 120 },
        { model: 'google/gemini-3-flash-preview', timeoutSeconds: 120 },
      ],
    });

    facade.reorderFallbackChain(1, 0);

    expect(
      mockServerManagementService.serverManagementOpenrouterStatusPartialUpdate,
    ).toHaveBeenCalledWith({
      requestBody: {
        settings: {
          LLM_FALLBACK_MODEL_CHAIN: [
            { model: 'google/gemini-3-flash-preview', timeoutSeconds: 120 },
            { model: 'gpt-5-mini', timeoutSeconds: 120 },
          ],
        },
      },
    });
  });

  it('reads the active groq primary model from GROQ_DEFAULT_MODEL', () => {
    facade.aiWorkflowStatus.set(
      buildAiWorkflowStatus(
        {
          LLM_PROVIDER: 'groq',
          LLM_DEFAULT_MODEL: 'google/gemini-3-flash-preview',
          GROQ_DEFAULT_MODEL: 'qwen/qwen3-32b',
        },
        {
          provider: 'groq',
          providerName: 'Groq',
          defaultModel: 'qwen/qwen3-32b',
        },
      ),
    );
    facade.aiWorkflowDraft.set({
      LLM_PROVIDER: 'groq',
      LLM_DEFAULT_MODEL: 'google/gemini-3-flash-preview',
      GROQ_DEFAULT_MODEL: 'qwen/qwen3-32b',
    });

    expect(facade.getPrimaryModelValue()).toBe('qwen/qwen3-32b');
  });

  it('updates the active groq primary model without mutating the non-groq default', () => {
    facade.aiWorkflowStatus.set(
      buildAiWorkflowStatus(
        {
          LLM_PROVIDER: 'groq',
          LLM_DEFAULT_MODEL: 'google/gemini-3-flash-preview',
          GROQ_DEFAULT_MODEL: 'meta-llama/llama-4-maverick-17b-128e-instruct',
        },
        {
          provider: 'groq',
          providerName: 'Groq',
          defaultModel: 'meta-llama/llama-4-maverick-17b-128e-instruct',
        },
      ),
    );
    facade.aiWorkflowDraft.set({
      LLM_PROVIDER: 'groq',
      LLM_DEFAULT_MODEL: 'google/gemini-3-flash-preview',
      GROQ_DEFAULT_MODEL: 'meta-llama/llama-4-maverick-17b-128e-instruct',
    });
    mockServerManagementService.serverManagementOpenrouterStatusPartialUpdate.mockReturnValueOnce(
      of(
        buildAiWorkflowStatus(
          {
            LLM_PROVIDER: 'groq',
            LLM_DEFAULT_MODEL: 'google/gemini-3-flash-preview',
            GROQ_DEFAULT_MODEL: 'qwen/qwen3-32b',
          },
          {
            provider: 'groq',
            providerName: 'Groq',
            defaultModel: 'qwen/qwen3-32b',
          },
        ),
      ),
    );

    facade.onPrimaryModelValueChange('qwen/qwen3-32b');

    expect(
      mockServerManagementService.serverManagementOpenrouterStatusPartialUpdate,
    ).toHaveBeenCalledWith({
      requestBody: {
        settings: {
          LLM_PROVIDER: 'groq',
          GROQ_DEFAULT_MODEL: 'qwen/qwen3-32b',
        },
      },
    });

    expect(facade.getPrimaryModelValue()).toBe('qwen/qwen3-32b');
    expect(facade.getAiSettingValue('LLM_DEFAULT_MODEL')).toBe('google/gemini-3-flash-preview');
  });

  it('keeps the primary model unchanged when adding a failover model', () => {
    facade.aiWorkflowStatus.set(
      buildAiWorkflowStatus(
        {
          LLM_PROVIDER: 'groq',
          LLM_DEFAULT_MODEL: 'google/gemini-3-flash-preview',
          GROQ_DEFAULT_MODEL: 'qwen/qwen3-32b',
          LLM_FALLBACK_MODEL_CHAIN: [],
        },
        {
          provider: 'groq',
          providerName: 'Groq',
          defaultModel: 'qwen/qwen3-32b',
        },
      ),
    );
    facade.aiWorkflowDraft.set({
      LLM_PROVIDER: 'groq',
      LLM_DEFAULT_MODEL: 'google/gemini-3-flash-preview',
      GROQ_DEFAULT_MODEL: 'qwen/qwen3-32b',
      LLM_FALLBACK_MODEL_CHAIN: [],
    });
    mockServerManagementService.serverManagementOpenrouterStatusPartialUpdate.mockReturnValueOnce(
      of(
        buildAiWorkflowStatus(
          {
            LLM_PROVIDER: 'groq',
            LLM_DEFAULT_MODEL: 'google/gemini-3-flash-preview',
            GROQ_DEFAULT_MODEL: 'qwen/qwen3-32b',
            LLM_FALLBACK_MODEL_CHAIN: [
              { model: 'google/gemini-3-flash-preview', timeoutSeconds: 120 },
            ],
          },
          {
            provider: 'groq',
            providerName: 'Groq',
            defaultModel: 'qwen/qwen3-32b',
          },
        ),
      ),
    );

    facade.addFallbackModel('google/gemini-3-flash-preview');

    expect(
      mockServerManagementService.serverManagementOpenrouterStatusPartialUpdate,
    ).toHaveBeenCalledWith({
      requestBody: {
        settings: {
          LLM_FALLBACK_MODEL_CHAIN: [
            { model: 'google/gemini-3-flash-preview', timeoutSeconds: 120 },
          ],
        },
      },
    });

    expect(facade.getPrimaryModelValue()).toBe('qwen/qwen3-32b');
  });

  it('preserves multiple failover rows for the same provider when normalizing workflow status', () => {
    mockServerManagementService.serverManagementOpenrouterStatusRetrieve.mockReturnValue(
      of(
        buildAiWorkflowStatus(
          {
            LLM_PROVIDER: 'openrouter',
            LLM_DEFAULT_MODEL: 'qwen/qwen3.5-flash-02-23',
          },
          {
            features: [
              {
                feature: 'Invoice Import AI Parser',
                purpose: 'Extracts invoice/customer data from uploaded invoice files.',
                modelStrategy: 'Uses INVOICE_IMPORT_MODEL for this workflow.',
                provider: 'openrouter',
                providerName: 'OpenRouter',
                primaryProvider: 'openrouter',
                primaryProviderName: 'OpenRouter',
                primaryModel: 'qwen/qwen3.5-flash-02-23',
                effectiveModel: 'qwen/qwen3.5-flash-02-23',
                modelSettingName: 'INVOICE_IMPORT_MODEL',
                primaryTimeoutSettingName: 'INVOICE_IMPORT_TIMEOUT',
                primaryTimeoutSeconds: 15,
                failoverProviders: [
                  {
                    provider: 'openrouter',
                    providerName: 'OpenRouter',
                    model: 'google/gemini-3-flash-preview',
                    timeoutSeconds: 45,
                    available: true,
                    active: true,
                  },
                  {
                    provider: 'openrouter',
                    providerName: 'OpenRouter',
                    model: 'google/gemini-2.5-flash-lite',
                    timeoutSeconds: 120,
                    available: true,
                    active: true,
                  },
                ],
                modelFailover: {
                  enabled: false,
                  model: null,
                  strategy: null,
                },
              },
            ],
          },
        ),
      ),
    );

    facade.loadAiWorkflowStatus();

    const feature = facade.aiWorkflowStatus()?.aiModels.features[0];
    expect(feature?.failoverProviders).toEqual([
      {
        provider: 'openrouter',
        providerName: 'OpenRouter',
        model: 'google/gemini-3-flash-preview',
        timeoutSeconds: 45,
        available: true,
        active: true,
      },
      {
        provider: 'openrouter',
        providerName: 'OpenRouter',
        model: 'google/gemini-2.5-flash-lite',
        timeoutSeconds: 120,
        available: true,
        active: true,
      },
    ]);
    expect(feature?.primaryTimeoutSettingName).toBe('INVOICE_IMPORT_TIMEOUT');
    expect(feature?.primaryTimeoutSeconds).toBe(15);
  });
});
