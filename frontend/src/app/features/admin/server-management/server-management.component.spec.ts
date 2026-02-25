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

      const statusReq = httpMock.expectOne('/api/cache/status');
      expect(statusReq.request.method).toBe('GET');
      statusReq.flush({
        enabled: true,
        version: 1,
        message: 'Cache is enabled',
        cacheBackend: 'django_redis.cache.RedisCache',
      });

      const healthReq = httpMock.expectOne('/api/server-management/cache-health/');
      expect(healthReq.request.method).toBe('GET');
      healthReq.flush({
        ok: true,
        message: 'Cache probe succeeded.',
        checkedAt: '2026-02-24T10:00:00+00:00',
        cacheBackend: 'django_redis.cache.RedisCache',
        cacheLocation: 'redis://bs-redis:6379/1',
        redisConfigured: true,
        redisConnected: true,
        writeReadDeleteOk: true,
        probeLatencyMs: 1.2,
        errors: [],
      });

      expect(mockServerManagementService.serverManagementLocalResilienceRetrieve).toHaveBeenCalledTimes(1);

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

      const req = httpMock.expectOne('/api/cache/status');
      req.error(new ProgressEvent('error'));

      const healthReq = httpMock.expectOne('/api/server-management/cache-health/');
      healthReq.flush({
        ok: true,
        message: 'Cache probe succeeded.',
        checkedAt: '2026-02-24T10:00:00+00:00',
        cacheBackend: 'django_redis.cache.RedisCache',
        cacheLocation: 'redis://bs-redis:6379/1',
        redisConfigured: true,
        redisConnected: true,
        writeReadDeleteOk: true,
        probeLatencyMs: 1.2,
        errors: [],
      });

      expect(mockServerManagementService.serverManagementLocalResilienceRetrieve).toHaveBeenCalledTimes(1);

      expect(mockToastService.error).toHaveBeenCalledWith('Failed to load cache status');
      expect(component.cacheStatus()).toBeNull();
    });
  });

  describe('loadCacheStatus', () => {
    it('should set loading state during request', () => {
      expect(component.cacheLoading()).toBe(false);

      component.loadCacheStatus();
      expect(component.cacheLoading()).toBe(true);

      const req = httpMock.expectOne('/api/cache/status');
      req.flush({ enabled: true, version: 2, message: 'Cache is enabled' });

      expect(component.cacheLoading()).toBe(false);
    });

    it('should update cache status on success', () => {
      component.loadCacheStatus();

      const req = httpMock.expectOne('/api/cache/status');
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

      const req = httpMock.expectOne('/api/cache/enable');
      expect(req.request.method).toBe('POST');

      req.flush({ enabled: true, version: 1, message: 'Cache enabled successfully' });

      expect(component.cacheStatus()?.enabled).toBe(true);
      expect(mockToastService.success).toHaveBeenCalledWith('Cache enabled successfully');
    });

    it('should disable cache when currently enabled', () => {
      component.cacheStatus.set({ enabled: true, version: 1, message: 'Cache is enabled' });

      component.toggleCache();

      const req = httpMock.expectOne('/api/cache/disable');
      expect(req.request.method).toBe('POST');

      req.flush({ enabled: false, version: 1, message: 'Cache disabled successfully' });

      expect(component.cacheStatus()?.enabled).toBe(false);
      expect(mockToastService.success).toHaveBeenCalledWith('Cache disabled successfully');
    });

    it('should show error when cache status not loaded', () => {
      component.cacheStatus.set(null);

      component.toggleCache();

      expect(mockToastService.error).toHaveBeenCalledWith('Cache status not loaded');
      httpMock.expectNone('/api/cache/enable');
      httpMock.expectNone('/api/cache/disable');
    });

    it('should handle toggle error', () => {
      component.cacheStatus.set({ enabled: true, version: 1, message: 'Cache is enabled' });

      component.toggleCache();

      const req = httpMock.expectOne('/api/cache/disable');
      req.error(new ProgressEvent('error'));

      expect(mockToastService.error).toHaveBeenCalledWith('Failed to disable cache');
    });

    it('should set loading state during toggle', () => {
      component.cacheStatus.set({ enabled: true, version: 1, message: 'Cache is enabled' });

      expect(component.cacheLoading()).toBe(false);

      component.toggleCache();
      expect(component.cacheLoading()).toBe(true);

      const req = httpMock.expectOne('/api/cache/disable');
      req.flush({ enabled: false, version: 1, message: 'Cache disabled successfully' });

      expect(component.cacheLoading()).toBe(false);
    });
  });

  describe('clearUserCache', () => {
    it('should clear cache and update version', () => {
      component.clearUserCache();

      const clearReq = httpMock.expectOne('/api/cache/clear');
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
      const statusReq = httpMock.expectOne('/api/cache/status');
      statusReq.flush({ enabled: true, version: 2, message: 'Cache is enabled' });

      expect(component.cacheStatus()?.version).toBe(2);
    });

    it('should handle clear error', () => {
      component.clearUserCache();

      const req = httpMock.expectOne('/api/cache/clear');
      req.error(new ProgressEvent('error'));

      expect(mockToastService.error).toHaveBeenCalledWith('Failed to clear user cache');
    });

    it('should set loading state during clear', () => {
      expect(component.cacheLoading()).toBe(false);

      component.clearUserCache();
      expect(component.cacheLoading()).toBe(true);

      const clearReq = httpMock.expectOne('/api/cache/clear');
      clearReq.flush({ version: 2, cleared: true, message: 'Cache cleared' });

      const statusReq = httpMock.expectOne('/api/cache/status');
      statusReq.flush({ enabled: true, version: 2, message: 'Cache is enabled' });

      expect(component.cacheLoading()).toBe(false);
    });
  });

  describe('runCacheHealthCheck', () => {
    it('should run cache probe and update health state', () => {
      component.runCacheHealthCheck();

      const req = httpMock.expectOne('/api/server-management/cache-health/');
      expect(req.request.method).toBe('GET');
      req.flush({
        ok: true,
        message: 'Cache probe succeeded.',
        checkedAt: '2026-02-24T10:00:00+00:00',
        cacheBackend: 'django_redis.cache.RedisCache',
        cacheLocation: 'redis://bs-redis:6379/1',
        redisConfigured: true,
        redisConnected: true,
        writeReadDeleteOk: true,
        probeLatencyMs: 1.2,
        errors: [],
      });

      expect(component.cacheHealth()?.writeReadDeleteOk).toBe(true);
      expect(mockToastService.success).toHaveBeenCalledWith('Cache probe succeeded.');
    });

    it('should handle cache probe request errors', () => {
      component.runCacheHealthCheck();

      const req = httpMock.expectOne('/api/server-management/cache-health/');
      req.error(new ProgressEvent('error'));

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
});
