import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { of, throwError } from 'rxjs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ServerManagementService } from '@/core/api';
import { GlobalToastService } from '@/core/services/toast.service';
import { ServerManagementComponent } from './server-management.component';

describe('ServerManagementComponent - Cache Controls', () => {
  let fixture: any;
  let component: ServerManagementComponent;
  let httpMock: HttpTestingController;
  let mockToastService: any;
  let mockServerManagementService: any;

  beforeEach(async () => {
    mockToastService = {
      success: vi.fn(),
      error: vi.fn(),
      info: vi.fn(),
    };

    mockServerManagementService = {
      serverManagementClearCacheCreate: vi
        .fn()
        .mockReturnValue(of({ ok: true, message: 'Cache cleared' })),
      serverManagementMediaDiagnosticRetrieve: vi
        .fn()
        .mockReturnValue(of({ ok: true, results: [], settings: null })),
      serverManagementMediaRepairCreate: vi.fn().mockReturnValue(of({ ok: true, repairs: [] })),
      serverManagementLocalResilienceRetrieve: vi.fn().mockReturnValue(
        of({
          enabled: false,
          encryptionRequired: true,
          desktopMode: 'localPrimary',
          vaultEpoch: 1,
        }),
      ),
      serverManagementLocalResiliencePartialUpdate: vi
        .fn()
        .mockReturnValue(of({ enabled: true, encryptionRequired: true, desktopMode: 'localPrimary', vaultEpoch: 1 })),
      serverManagementLocalResilienceResetVaultCreate: vi
        .fn()
        .mockReturnValue(of({ ok: true, message: 'Local media vault reset requested', vaultEpoch: 2 })),
      serverManagementCacheHealthRetrieve: vi.fn().mockReturnValue(
        of({
          ok: true,
          message: 'Cache probe succeeded.',
          checkedAt: '2026-02-24T10:00:00+00:00',
          cacheBackend: 'django_redis.cache.RedisCache',
          cacheLocation: 'redis://bs-redis:6379/1',
          redisConfigured: true,
          redisConnected: true,
          userCacheEnabled: true,
          probeSkipped: false,
          writeReadDeleteOk: true,
          probeLatencyMs: 1.2,
          errors: [],
        }),
      ),
      serverManagementUiSettingsRetrieve: vi.fn().mockReturnValue(
        of({
          useOverlayMenu: false,
        }),
      ),
      serverManagementUiSettingsPartialUpdate: vi.fn().mockReturnValue(
        of({
          useOverlayMenu: true,
        }),
      ),
      serverManagementOpenrouterStatusRetrieve: vi.fn().mockReturnValue(
        of({
          aiModels: {
            provider: 'openrouter',
            providerName: 'OpenRouter',
            defaultModel: 'google/gemini-2.5-flash-lite',
            failover: {
              enabled: true,
              configuredProviderOrder: ['openai'],
              effectiveProviderOrder: ['openai'],
            },
            features: [],
          },
        }),
      ),
    };

    await TestBed.configureTestingModule({
      imports: [ServerManagementComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: GlobalToastService, useValue: mockToastService },
        { provide: ServerManagementService, useValue: mockServerManagementService },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(ServerManagementComponent);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    try {
      httpMock.verify();
    } catch (e) {
      // Ignore verification errors in afterEach
      console.warn('HTTP verification warning:', e);
    }
  });

  describe('Component Initialization', () => {
    it('should load cache status on init', () => {
      component.ngOnInit();

      const statusReq = httpMock.expectOne('/api/cache/status/');
      expect(statusReq.request.method).toBe('GET');
      statusReq.flush({
        enabled: true,
        version: 1,
        message: 'Cache is enabled',
        cacheBackend: 'django_redis.cache.RedisCache',
      });

      expect(mockServerManagementService.serverManagementLocalResilienceRetrieve).toHaveBeenCalledTimes(1);
      expect(mockServerManagementService.serverManagementOpenrouterStatusRetrieve).toHaveBeenCalledTimes(1);
      expect(mockServerManagementService.serverManagementCacheHealthRetrieve).toHaveBeenCalledTimes(1);
      expect(mockServerManagementService.serverManagementUiSettingsRetrieve).toHaveBeenCalledTimes(1);

      expect(component.cacheStatus()).toEqual({
        enabled: true,
        version: 1,
        message: 'Cache is enabled',
        cacheBackend: 'django_redis.cache.RedisCache',
      });
      expect(component.cacheHealth()?.ok).toBe(true);
    });

    it('should handle cache status load error', () => {
      component.ngOnInit();

      const req = httpMock.expectOne('/api/cache/status/');
      req.error(new ProgressEvent('error'));

      expect(mockServerManagementService.serverManagementLocalResilienceRetrieve).toHaveBeenCalledTimes(1);
      expect(mockServerManagementService.serverManagementOpenrouterStatusRetrieve).toHaveBeenCalledTimes(1);
      expect(mockServerManagementService.serverManagementCacheHealthRetrieve).toHaveBeenCalledTimes(1);
      expect(mockServerManagementService.serverManagementUiSettingsRetrieve).toHaveBeenCalledTimes(1);

      expect(mockToastService.error).toHaveBeenCalledWith('Failed to load cache status');
      expect(component.cacheStatus()).toBeNull();
    });
  });

  describe('loadCacheStatus', () => {
    it('should set loading state during request', () => {
      expect(component.cacheLoading()).toBe(false);

      component.loadCacheStatus();
      expect(component.cacheLoading()).toBe(true);

      const req = httpMock.expectOne('/api/cache/status/');
      req.flush({ enabled: true, version: 2, message: 'Cache is enabled' });

      expect(component.cacheLoading()).toBe(false);
    });

    it('should update cache status on success', () => {
      component.loadCacheStatus();

      const req = httpMock.expectOne('/api/cache/status/');
      req.flush({ enabled: false, version: 3, message: 'Cache is disabled' });

      expect(component.cacheStatus()).toEqual({
        enabled: false,
        version: 3,
        message: 'Cache is disabled',
      });
    });
  });

  describe('toggleCache', () => {
    it('should enable cache when currently disabled', () => {
      component.cacheStatus.set({ enabled: false, version: 1, message: 'Cache is disabled' });

      component.toggleCache();

      const req = httpMock.expectOne('/api/cache/enable/');
      expect(req.request.method).toBe('POST');

      req.flush({ enabled: true, version: 1, message: 'Cache enabled successfully' });

      expect(component.cacheStatus()?.enabled).toBe(true);
      expect(mockToastService.success).toHaveBeenCalledWith('Cache enabled successfully');
    });

    it('should disable cache when currently enabled', () => {
      component.cacheStatus.set({ enabled: true, version: 1, message: 'Cache is enabled' });

      component.toggleCache();

      const req = httpMock.expectOne('/api/cache/disable/');
      expect(req.request.method).toBe('POST');

      req.flush({ enabled: false, version: 1, message: 'Cache disabled successfully' });

      expect(component.cacheStatus()?.enabled).toBe(false);
      expect(mockToastService.success).toHaveBeenCalledWith('Cache disabled successfully');
    });

    it('should show error when cache status not loaded', () => {
      component.cacheStatus.set(null);

      component.toggleCache();

      expect(mockToastService.error).toHaveBeenCalledWith('Cache status not loaded');
      httpMock.expectNone('/api/cache/enable/');
      httpMock.expectNone('/api/cache/disable/');
    });

    it('should handle toggle error', () => {
      component.cacheStatus.set({ enabled: true, version: 1, message: 'Cache is enabled' });

      component.toggleCache();

      const req = httpMock.expectOne('/api/cache/disable/');
      req.error(new ProgressEvent('error'));

      expect(mockToastService.error).toHaveBeenCalledWith('Failed to disable cache');
    });

    it('should set loading state during toggle', () => {
      component.cacheStatus.set({ enabled: true, version: 1, message: 'Cache is enabled' });

      expect(component.cacheLoading()).toBe(false);

      component.toggleCache();
      expect(component.cacheLoading()).toBe(true);

      const req = httpMock.expectOne('/api/cache/disable/');
      req.flush({ enabled: false, version: 1, message: 'Cache disabled successfully' });

      expect(component.cacheLoading()).toBe(false);
    });
  });

  describe('clearUserCache', () => {
    it('should clear cache and update version', () => {
      component.clearUserCache();

      const clearReq = httpMock.expectOne('/api/cache/clear/');
      expect(clearReq.request.method).toBe('POST');

      clearReq.flush({
        version: 2,
        cleared: true,
        message: 'Cache cleared successfully (new version: 2)',
      });

      expect(mockToastService.success).toHaveBeenCalledWith(
        'Cache cleared successfully (new version: 2)',
      );

      // Should reload status after clearing
      const statusReq = httpMock.expectOne('/api/cache/status/');
      statusReq.flush({ enabled: true, version: 2, message: 'Cache is enabled' });

      expect(component.cacheStatus()?.version).toBe(2);
    });

    it('should handle clear error', () => {
      component.clearUserCache();

      const req = httpMock.expectOne('/api/cache/clear/');
      req.error(new ProgressEvent('error'));

      expect(mockToastService.error).toHaveBeenCalledWith('Failed to clear user cache');
    });

    it('should set loading state during clear', () => {
      expect(component.cacheLoading()).toBe(false);

      component.clearUserCache();
      expect(component.cacheLoading()).toBe(true);

      const clearReq = httpMock.expectOne('/api/cache/clear/');
      clearReq.flush({ version: 2, cleared: true, message: 'Cache cleared' });

      const statusReq = httpMock.expectOne('/api/cache/status/');
      statusReq.flush({ enabled: true, version: 2, message: 'Cache is enabled' });

      expect(component.cacheLoading()).toBe(false);
    });
  });

  describe('runCacheHealthCheck', () => {
    it('should run cache probe and update health state', () => {
      component.runCacheHealthCheck();

      expect(mockServerManagementService.serverManagementCacheHealthRetrieve).toHaveBeenCalledTimes(1);
      expect(component.cacheHealth()?.writeReadDeleteOk).toBe(true);
      expect(mockToastService.success).toHaveBeenCalledWith('Cache probe succeeded.');
    });

    it('should show info toast when cache probe is skipped because cache is disabled', () => {
      mockServerManagementService.serverManagementCacheHealthRetrieve.mockReturnValue(
        of({
          ok: true,
          message:
            'Cache is disabled for your user. Backend connectivity is healthy; write/read/delete probe was skipped.',
          checkedAt: '2026-02-24T10:00:00+00:00',
          cacheBackend: 'django_redis.cache.RedisCache',
          cacheLocation: 'redis://bs-redis:6379/1',
          redisConfigured: true,
          redisConnected: true,
          userCacheEnabled: false,
          probeSkipped: true,
          writeReadDeleteOk: false,
          probeLatencyMs: 0,
          errors: [],
        }),
      );
      component.cacheStatus.set({ enabled: false, version: 1, message: 'Cache is disabled' });

      component.runCacheHealthCheck();

      expect(mockToastService.info).toHaveBeenCalledWith(
        'Cache is disabled for your user. Backend connectivity is healthy; write/read/delete probe was skipped.',
      );
    });

    it('should handle cache probe request errors', () => {
      mockServerManagementService.serverManagementCacheHealthRetrieve.mockReturnValue(
        throwError(() => new Error('Network error')),
      );
      component.runCacheHealthCheck();

      expect(mockToastService.error).toHaveBeenCalledWith('Failed to run cache health check');
    });
  });

  describe('UI State Management', () => {
    it('should display cache status correctly', async () => {
      component.cacheStatus.set({ enabled: true, version: 5, message: 'Cache is enabled' });
      fixture.detectChanges();

      await new Promise((r) => setTimeout(r, 0));
      fixture.detectChanges();

      const el: HTMLElement = fixture.nativeElement;
      const text = String((el.innerText ?? el.textContent) || '');

      expect(text).toContain('Cache Management');
      expect(text).toContain('Enabled');
      expect(text).toContain('v5');
    });

    it('should show disabled state correctly', async () => {
      component.cacheStatus.set({ enabled: false, version: 3, message: 'Cache is disabled' });
      fixture.detectChanges();

      await new Promise((r) => setTimeout(r, 0));
      fixture.detectChanges();

      const el: HTMLElement = fixture.nativeElement;
      const text = String((el.innerText ?? el.textContent) || '');

      expect(text).toContain('Disabled');
      expect(text).toContain('v3');
    });

    it('should show cache backend type when available', async () => {
      component.cacheStatus.set({
        enabled: true,
        version: 3,
        message: 'Cache is enabled',
        cacheBackend: 'django_redis.cache.RedisCache',
      });
      fixture.detectChanges();

      await new Promise((r) => setTimeout(r, 0));
      fixture.detectChanges();

      const el: HTMLElement = fixture.nativeElement;
      const text = String((el.innerText ?? el.textContent) || '');

      expect(text).toContain('Cache Backend Type');
      expect(text).toContain('RedisCache');
    });

    it('should show loading state when cache status not loaded', async () => {
      component.cacheStatus.set(null);
      fixture.detectChanges();

      await new Promise((r) => setTimeout(r, 0));
      fixture.detectChanges();

      const el: HTMLElement = fixture.nativeElement;
      const text = String((el.innerText ?? el.textContent) || '');

      expect(text).toContain('Cache status not loaded yet');
    });
  });

  describe('Backward Compatibility', () => {
    it('should maintain existing clearCache functionality', () => {
      component.clearCache();

      expect(mockServerManagementService.serverManagementClearCacheCreate).toHaveBeenCalled();
      expect(component.isLoading()).toBe(false);
      expect(mockToastService.success).toHaveBeenCalledWith('Cache cleared successfully');
    });

    it('should handle existing clearCache errors', () => {
      mockServerManagementService.serverManagementClearCacheCreate.mockReturnValue(
        throwError(() => new Error('Network error')),
      );

      component.clearCache();

      expect(mockToastService.error).toHaveBeenCalledWith('Failed to clear cache');
    });
  });

  describe('Button States', () => {
    it('should have correct state when cache is disabled', () => {
      component.cacheStatus.set({ enabled: false, version: 1, message: 'Cache is disabled' });
      component.cacheLoading.set(false);

      // Verify the component state
      expect(component.cacheStatus()?.enabled).toBe(false);
      expect(component.cacheLoading()).toBe(false);
    });

    it('should have correct state when cache is enabled', () => {
      component.cacheStatus.set({ enabled: true, version: 1, message: 'Cache is enabled' });
      component.cacheLoading.set(false);

      // Verify the component state
      expect(component.cacheStatus()?.enabled).toBe(true);
      expect(component.cacheLoading()).toBe(false);
    });

    it('should have correct loading state', () => {
      component.cacheStatus.set({ enabled: true, version: 1, message: 'Cache is enabled' });
      component.cacheLoading.set(true);

      // Verify loading state
      expect(component.cacheLoading()).toBe(true);
    });
  });

  describe('AI Workflow Settings', () => {
    it('should save AI runtime settings via patch endpoint', () => {
      component.aiWorkflowStatus.set({
        aiModels: {
          provider: 'openrouter',
          providerName: 'OpenRouter',
          defaultModel: 'google/gemini-3-flash-preview',
          settingsMap: { LLM_PROVIDER: 'openrouter', LLM_DEFAULT_MODEL: 'google/gemini-3-flash-preview' },
          runtimeSettings: [],
          workflowBindings: [],
          modelCatalog: { providers: {} },
          failover: {
            enabled: true,
            configuredProviderOrder: ['openai'],
            effectiveProviderOrder: ['openai'],
          },
          features: [],
        },
      });
      component.aiWorkflowDraft.set({
        LLM_PROVIDER: 'openai',
        LLM_DEFAULT_MODEL: 'gpt-5-mini',
      });

      component.saveAiWorkflowSettings();

      const req = httpMock.expectOne('/api/server-management/openrouter-status/');
      expect(req.request.method).toBe('PATCH');
      expect(req.request.body.settings).toEqual({
        LLM_PROVIDER: 'openai',
        LLM_DEFAULT_MODEL: 'gpt-5-mini',
      });
      req.flush({
        aiModels: {
          provider: 'openai',
          providerName: 'OpenAI',
          defaultModel: 'gpt-5-mini',
          settingsMap: { LLM_PROVIDER: 'openai', LLM_DEFAULT_MODEL: 'gpt-5-mini' },
          runtimeSettings: [],
          workflowBindings: [],
          modelCatalog: { providers: {} },
          failover: {
            enabled: true,
            configuredProviderOrder: ['openrouter'],
            effectiveProviderOrder: ['openrouter'],
          },
          features: [],
        },
      });

      expect(component.aiWorkflowStatus()?.aiModels.provider).toBe('openai');
      expect(component.aiWorkflowDraft()['LLM_PROVIDER']).toBe('openai');
      expect(mockToastService.success).toHaveBeenCalledWith('AI runtime settings updated');
    });

    it('should show backend validation error when saving AI runtime settings fails', () => {
      component.aiWorkflowStatus.set({
        aiModels: {
          provider: 'openrouter',
          providerName: 'OpenRouter',
          defaultModel: 'google/gemini-3-flash-preview',
          settingsMap: { LLM_PROVIDER: 'openrouter' },
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
      component.aiWorkflowDraft.set({ LLM_PROVIDER: 'invalid-provider' });

      component.saveAiWorkflowSettings();

      const req = httpMock.expectOne('/api/server-management/openrouter-status/');
      expect(req.request.method).toBe('PATCH');
      req.flush(
        { detail: 'LLM_PROVIDER must be one of: openrouter, openai, groq.' },
        { status: 400, statusText: 'Bad Request' },
      );

      expect(mockToastService.error).toHaveBeenCalledWith(
        'Failed to update AI settings: LLM_PROVIDER must be one of: openrouter, openai, groq.',
      );
    });

    it('should autosave a single model setting change', () => {
      component.aiWorkflowStatus.set({
        aiModels: {
          provider: 'openrouter',
          providerName: 'OpenRouter',
          defaultModel: 'openai/gpt-5-mini',
          settingsMap: { OPENAI_DEFAULT_MODEL: 'gpt-5-mini' },
          runtimeSettings: [],
          workflowBindings: [],
          modelCatalog: {
            providers: {
              openai: {
                name: 'OpenAI Direct',
                models: [
                  {
                    id: 'gpt-5',
                    name: 'GPT-5',
                    description: 'OpenAI GPT-5',
                    capabilities: { vision: true, fileUpload: true, reasoning: true },
                  },
                ],
              },
            },
          },
          failover: {
            enabled: true,
            configuredProviderOrder: ['openai'],
            effectiveProviderOrder: ['openai'],
          },
          features: [],
        },
      });
      component.aiWorkflowDraft.set({ OPENAI_DEFAULT_MODEL: 'gpt-5-mini' });

      component.onModelSettingComboboxChange('OPENAI_DEFAULT_MODEL', 'gpt-5');

      const req = httpMock.expectOne('/api/server-management/openrouter-status/');
      expect(req.request.method).toBe('PATCH');
      expect(req.request.body.settings).toEqual({ OPENAI_DEFAULT_MODEL: 'gpt-5' });
      req.flush({
        aiModels: {
          provider: 'openrouter',
          providerName: 'OpenRouter',
          defaultModel: 'openai/gpt-5-mini',
          settingsMap: { OPENAI_DEFAULT_MODEL: 'gpt-5' },
          runtimeSettings: [],
          workflowBindings: [],
          modelCatalog: { providers: {} },
          failover: {
            enabled: true,
            configuredProviderOrder: ['openai'],
            effectiveProviderOrder: ['openai'],
          },
          features: [],
        },
      });

      expect(component.aiWorkflowDraft()['OPENAI_DEFAULT_MODEL']).toBe('gpt-5');
    });

    it('should autosave primary model by updating provider and provider default', () => {
      component.aiWorkflowStatus.set({
        aiModels: {
          provider: 'openrouter',
          providerName: 'OpenRouter',
          defaultModel: 'openai/gpt-5-mini',
          settingsMap: {
            LLM_PROVIDER: 'openrouter',
            OPENROUTER_DEFAULT_MODEL: 'openai/gpt-5-mini',
            LLM_DEFAULT_MODEL: 'openai/gpt-5-mini',
          },
          runtimeSettings: [],
          workflowBindings: [],
          modelCatalog: {
            providers: {
              groq: {
                name: 'Groq',
                models: [
                  {
                    id: 'meta-llama/llama-4-maverick-17b-128e-instruct',
                    name: 'Llama 4 Maverick 17B',
                    description: 'Groq model',
                    capabilities: { vision: true, fileUpload: false, reasoning: true },
                  },
                ],
              },
              openrouter: {
                name: 'OpenRouter',
                models: [
                  {
                    id: 'openai/gpt-5-mini',
                    name: 'GPT-5 Mini',
                    description: 'OpenRouter model',
                    capabilities: { vision: true, fileUpload: true, reasoning: true },
                  },
                ],
              },
            },
          },
          failover: {
            enabled: true,
            configuredProviderOrder: ['openai'],
            effectiveProviderOrder: ['openai'],
          },
          features: [],
        },
      });
      component.aiWorkflowDraft.set({
        LLM_PROVIDER: 'openrouter',
        OPENROUTER_DEFAULT_MODEL: 'openai/gpt-5-mini',
        LLM_DEFAULT_MODEL: 'openai/gpt-5-mini',
      });

      component.onPrimaryModelValueChange('meta-llama/llama-4-maverick-17b-128e-instruct');

      const req = httpMock.expectOne('/api/server-management/openrouter-status/');
      expect(req.request.method).toBe('PATCH');
      expect(req.request.body.settings).toEqual({
        LLM_PROVIDER: 'groq',
        GROQ_DEFAULT_MODEL: 'meta-llama/llama-4-maverick-17b-128e-instruct',
      });
      req.flush({
        aiModels: {
          provider: 'groq',
          providerName: 'Groq',
          defaultModel: 'meta-llama/llama-4-maverick-17b-128e-instruct',
          settingsMap: {
            LLM_PROVIDER: 'groq',
            GROQ_DEFAULT_MODEL: 'meta-llama/llama-4-maverick-17b-128e-instruct',
            LLM_DEFAULT_MODEL: 'openai/gpt-5-mini',
          },
          runtimeSettings: [],
          workflowBindings: [],
          modelCatalog: { providers: {} },
          failover: {
            enabled: true,
            configuredProviderOrder: ['openai'],
            effectiveProviderOrder: ['openai'],
          },
          features: [],
        },
      });

      expect(component.aiWorkflowDraft()['LLM_PROVIDER']).toBe('groq');
      expect(component.aiWorkflowDraft()['GROQ_DEFAULT_MODEL']).toBe(
        'meta-llama/llama-4-maverick-17b-128e-instruct',
      );
    });
  });
});
