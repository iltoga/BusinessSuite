import { PLATFORM_ID, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { of, Subject, throwError } from 'rxjs';

import { ServerManagementService } from '@/core/api';
import { DesktopBridgeService } from '@/core/services/desktop-bridge.service';
import { GlobalToastService } from '@/core/services/toast.service';

import { ServerManagementAiWorkflowFacade } from './server-management-ai-workflow.facade';
import { ServerManagementMediaCleanupStreamService } from './server-management-media-cleanup-stream.service';
import { ServerManagementComponent } from './server-management.component';

describe('ServerManagementComponent - Cache Controls', () => {
  let component: ServerManagementComponent;
  let mockToastService: any;
  let mockServerManagementService: any;
  let mockMediaCleanupStreamService: any;
  let mediaCleanup$: Subject<any>;
  let aiFacadeMock: any;

  beforeEach(() => {
    mockToastService = {
      success: vi.fn(),
      error: vi.fn(),
      info: vi.fn(),
    };

    mediaCleanup$ = new Subject();
    mockMediaCleanupStreamService = {
      connect: vi.fn(() => mediaCleanup$.asObservable()),
    };

    mockServerManagementService = {
      serverManagementClearCacheCreate: vi
        .fn()
        .mockReturnValue(of({ ok: true, message: 'Cache cleared' })),
      serverManagementMediaDiagnosticRetrieve: vi
        .fn()
        .mockReturnValue(of({ ok: true, results: [], settings: null })),
      serverManagementMediaRepairCreate: vi.fn().mockReturnValue(of({ ok: true, repairs: [] })),
      serverManagementMediaCleanupCreate: vi.fn(),
      serverManagementLocalResilienceRetrieve: vi.fn().mockReturnValue(
        of({
          enabled: false,
          encryptionRequired: true,
          desktopMode: 'localPrimary',
          vaultEpoch: 1,
        }),
      ),
      serverManagementLocalResiliencePartialUpdate: vi.fn().mockReturnValue(
        of({
          enabled: true,
          encryptionRequired: true,
          desktopMode: 'localPrimary',
          vaultEpoch: 1,
        }),
      ),
      serverManagementLocalResilienceResetVaultCreate: vi
        .fn()
        .mockReturnValue(
          of({ ok: true, message: 'Local media vault reset requested', vaultEpoch: 2 }),
        ),
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
      serverManagementUiSettingsRetrieve: vi.fn().mockReturnValue(of({ useOverlayMenu: false })),
      serverManagementUiSettingsPartialUpdate: vi
        .fn()
        .mockReturnValue(of({ useOverlayMenu: true })),
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
      serverManagementCacheStatusRetrieve: vi.fn().mockReturnValue(
        of({
          enabled: true,
          version: 1,
          message: 'Cache is enabled',
          cacheBackend: 'django_redis.cache.RedisCache',
        }),
      ),
      serverManagementCacheDisableCreate: vi
        .fn()
        .mockReturnValue(
          of({ enabled: false, version: 1, message: 'Cache disabled successfully' }),
        ),
      serverManagementCacheEnableCreate: vi
        .fn()
        .mockReturnValue(of({ enabled: true, version: 1, message: 'Cache enabled successfully' })),
    };

    aiFacadeMock = {
      aiWorkflowStatus: signal(null),
      aiWorkflowLoading: signal(false),
      aiWorkflowSaving: signal(false),
      aiWorkflowDraft: signal<Record<string, string>>({}),
      aiModelTypeaheadPageSize: signal(25),
      allProviderModelLoader: vi.fn(),
      openrouterModelLoader: vi.fn(),
      openaiModelLoader: vi.fn(),
      groqModelLoader: vi.fn(),
      loadAiWorkflowStatus: vi.fn(),
      saveAiWorkflowSettings: vi.fn(),
      resetAiWorkflowDraft: vi.fn(),
      getAiSettingValue: vi.fn(() => ''),
      getAiSettingBool: vi.fn(() => false),
      setAiSettingFromEvent: vi.fn(),
      setAiSettingNumberFromEvent: vi.fn(),
      setAiSettingBoolFromEvent: vi.fn(),
      getPrimaryModelValue: vi.fn(() => ''),
      onPrimaryModelValueChange: vi.fn(),
      onModelSettingComboboxChange: vi.fn(),
      getDraftFallbackProviderOrder: vi.fn(() => []),
      toggleFallbackProvider: vi.fn(),
      getModelProviderCatalogMap: vi.fn(() => ({})),
      getProviderKeys: vi.fn(() => []),
      getProviderDisplayName: vi.fn((provider: string) => provider),
      getModelsForProvider: vi.fn(() => []),
      getCurrentPrimaryProvider: vi.fn(() => 'openrouter'),
      getAllProviderModels: vi.fn(() => []),
      getModelsForSetting: vi.fn(() => []),
      getFeatureProvider: vi.fn(() => 'openrouter'),
      formatModelCapabilities: vi.fn(() => ''),
      findModelDefinition: vi.fn(() => null),
      findModelDefinitionForSetting: vi.fn(() => null),
    };

    TestBed.configureTestingModule({
      providers: [
        { provide: PLATFORM_ID, useValue: 'browser' },
        { provide: ServerManagementService, useValue: mockServerManagementService },
        {
          provide: ServerManagementMediaCleanupStreamService,
          useValue: mockMediaCleanupStreamService,
        },
        {
          provide: DesktopBridgeService,
          useValue: {
            isDesktop: vi.fn(() => false),
            getRuntimeStatus: vi.fn(),
            getSyncStatus: vi.fn(),
            getVaultStatus: vi.fn(),
            setVaultEpoch: vi.fn(),
          },
        },
        { provide: GlobalToastService, useValue: mockToastService },
        { provide: ServerManagementAiWorkflowFacade, useValue: aiFacadeMock },
      ],
    });

    component = TestBed.runInInjectionContext(() => new ServerManagementComponent());
  });

  it('loads cache status and related settings on init', () => {
    component.ngOnInit();

    expect(mockServerManagementService.serverManagementCacheStatusRetrieve).toHaveBeenCalledTimes(
      1,
    );
    expect(
      mockServerManagementService.serverManagementLocalResilienceRetrieve,
    ).toHaveBeenCalledTimes(1);
    expect(mockServerManagementService.serverManagementCacheHealthRetrieve).toHaveBeenCalledTimes(
      1,
    );
    expect(component.cacheStatus()).toMatchObject({ enabled: true, version: 1 });
    expect(component.cacheHealth()?.ok).toBe(true);
  });

  it('toggles cache based on current status', () => {
    component.cacheStatus.set({ enabled: true, version: 1, message: 'Cache is enabled' });
    component.toggleCache();

    expect(mockServerManagementService.serverManagementCacheDisableCreate).toHaveBeenCalledTimes(1);
    expect(component.cacheStatus()?.enabled).toBe(false);
    expect(mockToastService.success).toHaveBeenCalledWith('Cache disabled successfully');
  });

  it('clears cache and refreshes status', () => {
    component.clearAllCache();

    expect(mockServerManagementService.serverManagementClearCacheCreate).toHaveBeenCalledTimes(1);
    expect(mockToastService.success).toHaveBeenCalledWith('Cache cleared');
    expect(mockServerManagementService.serverManagementCacheStatusRetrieve).toHaveBeenCalledTimes(
      1,
    );
  });

  it('reports cache health check errors', () => {
    mockServerManagementService.serverManagementCacheHealthRetrieve.mockReturnValueOnce(
      throwError(() => new Error('Network error')),
    );

    component.runCacheHealthCheck();

    expect(mockToastService.error).toHaveBeenCalledWith('Failed to run cache health check');
  });

  it('runs media cleanup dry-run and stores the streamed result', () => {
    component.cleanupDryRun.set(true);
    component.runMediaCleanup();

    mediaCleanup$.next({
      event: 'media_cleanup_finished',
      cleanup: {
        ok: true,
        message: 'Dry run complete. Found 1 unlinked media files.',
        dryRun: true,
        prefixes: ['documents'],
        scannedFiles: 2,
        referencedFiles: 1,
        orphanedFiles: 1,
        deletedFiles: 0,
        totalOrphanBytes: 20,
        files: [{ path: 'documents/orphan.pdf', sizeBytes: 20 }],
        errors: [],
        storage: { provider: 's3', backend: 'storages.backends.s3boto3.S3Boto3Storage' },
      },
    });

    expect(mockMediaCleanupStreamService.connect).toHaveBeenCalledWith(true);
    expect(component.cleanupResult()?.orphanedFiles).toBe(1);
    expect(mockToastService.success).toHaveBeenCalledWith('Preview found 1 unlinked files');
  });

  it('does not treat semantic local vault reset failures as success', () => {
    mockServerManagementService.serverManagementLocalResilienceResetVaultCreate.mockReturnValueOnce(
      of({ ok: false, message: 'Vault reset blocked' }),
    );

    component.resetLocalVault();

    expect(mockToastService.error).toHaveBeenCalledWith('Vault reset blocked');
    expect(mockToastService.success).not.toHaveBeenCalledWith('Vault reset blocked');
  });

  it('exposes button state through signals', () => {
    component.cacheStatus.set({ enabled: false, version: 1, message: 'Cache is disabled' });
    component.cacheLoading.set(true);

    expect(component.cacheStatus()?.enabled).toBe(false);
    expect(component.cacheLoading()).toBe(true);
  });

  it('delegates AI workflow actions to the facade', () => {
    component.saveAiWorkflowSettings();
    component.onModelSettingComboboxChange('OPENAI_DEFAULT_MODEL', 'gpt-5');
    component.onPrimaryModelValueChange('meta-llama/llama-4-maverick-17b-128e-instruct');

    expect(aiFacadeMock.saveAiWorkflowSettings).toHaveBeenCalledTimes(1);
    expect(aiFacadeMock.onModelSettingComboboxChange).toHaveBeenCalledWith(
      'OPENAI_DEFAULT_MODEL',
      'gpt-5',
    );
    expect(aiFacadeMock.onPrimaryModelValueChange).toHaveBeenCalledWith(
      'meta-llama/llama-4-maverick-17b-128e-instruct',
    );
  });
});
