import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ServerManagementService } from '@/core/api';
import { GlobalToastService } from '@/core/services/toast.service';

import { ServerManagementAiWorkflowFacade } from './server-management-ai-workflow.facade';

const buildAiWorkflowStatus = (settingsMap: Record<string, unknown> = {}) => ({
  aiModels: {
    provider: 'openrouter',
    providerName: 'OpenRouter',
    defaultModel: 'google/gemini-2.5-flash-lite',
    settingsMap,
    runtimeSettings: [],
    workflowBindings: [],
    modelCatalog: { providers: {} },
    failover: {
      enabled: true,
      configuredProviderOrder: [],
      effectiveProviderOrder: [],
    },
    features: [],
  },
});

describe('ServerManagementAiWorkflowFacade', () => {
  let facade: ServerManagementAiWorkflowFacade;
  let httpMock: HttpTestingController;
  let mockToastService: {
    success: ReturnType<typeof vi.fn>;
    error: ReturnType<typeof vi.fn>;
    info: ReturnType<typeof vi.fn>;
  };
  let mockServerManagementService: {
    serverManagementOpenrouterStatusRetrieve: ReturnType<typeof vi.fn>;
  };

  beforeEach(async () => {
    mockToastService = {
      success: vi.fn(),
      error: vi.fn(),
      info: vi.fn(),
    };

    mockServerManagementService = {
      serverManagementOpenrouterStatusRetrieve: vi.fn().mockReturnValue(of(buildAiWorkflowStatus())),
    };

    await TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        ServerManagementAiWorkflowFacade,
        { provide: GlobalToastService, useValue: mockToastService },
        { provide: ServerManagementService, useValue: mockServerManagementService },
      ],
    }).compileComponents();

    facade = TestBed.inject(ServerManagementAiWorkflowFacade);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
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

    const req = httpMock.expectOne('/api/server-management/openrouter-status/');
    expect(req.request.method).toBe('PATCH');
    expect(req.request.body.settings).toEqual({ INVOICE_IMPORT_MODEL: null });
    req.flush(
      buildAiWorkflowStatus({
        LLM_PROVIDER: 'openrouter',
        INVOICE_IMPORT_MODEL: '',
      }),
    );

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

    const req = httpMock.expectOne('/api/server-management/openrouter-status/');
    expect(req.request.method).toBe('PATCH');
    expect(req.request.body.settings).toEqual({ INVOICE_IMPORT_MODEL: null });
    req.flush(
      buildAiWorkflowStatus({
        LLM_PROVIDER: 'openrouter',
        INVOICE_IMPORT_MODEL: '',
      }),
    );
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

    httpMock.expectNone('/api/server-management/openrouter-status/');
  });

  it('adds failover model to ordered list', () => {
    facade.aiWorkflowStatus.set(buildAiWorkflowStatus({ LLM_FALLBACK_MODEL_ORDER: ['gpt-5-mini'] }));
    facade.aiWorkflowDraft.set({ LLM_FALLBACK_MODEL_ORDER: ['gpt-5-mini'] });

    facade.addFallbackModel('google/gemini-3-flash-preview');

    const req = httpMock.expectOne('/api/server-management/openrouter-status/');
    expect(req.request.method).toBe('PATCH');
    expect(req.request.body.settings).toEqual({
      LLM_FALLBACK_MODEL_ORDER: ['gpt-5-mini', 'google/gemini-3-flash-preview'],
    });
    req.flush(
      buildAiWorkflowStatus({
        LLM_FALLBACK_MODEL_ORDER: ['gpt-5-mini', 'google/gemini-3-flash-preview'],
      }),
    );
  });

  it('reorders failover model list', () => {
    facade.aiWorkflowStatus.set(
      buildAiWorkflowStatus({ LLM_FALLBACK_MODEL_ORDER: ['gpt-5-mini', 'google/gemini-3-flash-preview'] }),
    );
    facade.aiWorkflowDraft.set({ LLM_FALLBACK_MODEL_ORDER: ['gpt-5-mini', 'google/gemini-3-flash-preview'] });

    facade.moveFallbackModel(1, -1);

    const req = httpMock.expectOne('/api/server-management/openrouter-status/');
    expect(req.request.body.settings).toEqual({
      LLM_FALLBACK_MODEL_ORDER: ['google/gemini-3-flash-preview', 'gpt-5-mini'],
    });
    req.flush(
      buildAiWorkflowStatus({
        LLM_FALLBACK_MODEL_ORDER: ['google/gemini-3-flash-preview', 'gpt-5-mini'],
      }),
    );
  });
});
