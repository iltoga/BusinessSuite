import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { ConfigService } from './config.service';

describe('ConfigService', () => {
  let service: ConfigService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    delete (window as any).APP_CONFIG;

    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
      providers: [ConfigService],
    });

    service = TestBed.inject(ConfigService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
    delete (window as any).APP_CONFIG;
  });

  it('uses backend app-config as source of truth even when APP_CONFIG is injected', async () => {
    (window as any).APP_CONFIG = {
      MOCK_AUTH_ENABLED: 'True',
      title: 'Injected',
      useOverlayMenu: false,
      uiScalePercent: 95,
      uiAutoScaleEnabled: false,
      uiAutoScaleReferenceWidth: 1600,
      uiAutoScaleMinPercent: 92,
      uiAutoScaleMaxPercent: 108,
      uiAutoScaleDesktopOnly: true,
    };

    const promise = service.loadConfig();
    const req = httpMock.expectOne('/api/app-config/');
    expect(req.request.method).toBe('GET');
    req.flush({
      MOCK_AUTH_ENABLED: false,
      title: 'Backend',
      useOverlayMenu: true,
      baseCurrency: 'USD',
      uiScalePercent: 110,
      uiAutoScaleEnabled: true,
      uiAutoScaleReferenceWidth: 1920,
      uiAutoScaleMinPercent: 80,
      uiAutoScaleMaxPercent: 125,
      uiAutoScaleDesktopOnly: false,
    });
    await promise;

    expect(service.settings.MOCK_AUTH_ENABLED).toBe(false);
    expect(service.settings.title).toBe('Backend');
    expect(service.settings.useOverlayMenu).toBe(true);
    expect(service.settings.baseCurrency).toBe('USD');
    expect(service.settings.uiScalePercent).toBe(110);
    expect(service.settings.uiAutoScaleEnabled).toBe(true);
    expect(service.settings.uiAutoScaleReferenceWidth).toBe(1920);
    expect(service.settings.uiAutoScaleMinPercent).toBe(80);
    expect(service.settings.uiAutoScaleMaxPercent).toBe(125);
    expect(service.settings.uiAutoScaleDesktopOnly).toBe(false);
  });

  it('keeps injected config if backend app-config request fails', async () => {
    (window as any).APP_CONFIG = {
      MOCK_AUTH_ENABLED: 'False',
      title: 'Injected',
      uiScalePercent: 92,
      uiAutoScaleEnabled: true,
      uiAutoScaleReferenceWidth: 1440,
      uiAutoScaleMinPercent: 90,
      uiAutoScaleMaxPercent: 110,
      uiAutoScaleDesktopOnly: true,
    };

    const promise = service.loadConfig();
    const req = httpMock.expectOne('/api/app-config/');
    expect(req.request.method).toBe('GET');
    req.flush({ detail: 'error' }, { status: 500, statusText: 'Server Error' });
    await promise;

    expect(service.settings.MOCK_AUTH_ENABLED).toBe('False');
    expect(service.settings.title).toBe('Injected');
    expect(service.settings.baseCurrency).toBe('IDR');
    expect(service.settings.uiScalePercent).toBe(92);
    expect(service.settings.uiAutoScaleEnabled).toBe(true);
    expect(service.settings.uiAutoScaleReferenceWidth).toBe(1440);
    expect(service.settings.uiAutoScaleMinPercent).toBe(90);
    expect(service.settings.uiAutoScaleMaxPercent).toBe(110);
    expect(service.settings.uiAutoScaleDesktopOnly).toBe(true);
  });

  it('preserves SSR-injected FCM config when backend app-config omits FCM keys', async () => {
    (window as any).APP_CONFIG = {
      MOCK_AUTH_ENABLED: 'False',
      title: 'Injected',
      fcmProjectId: 'ssr-project',
      fcmWebApiKey: 'ssr-api-key',
      fcmWebAppId: 'ssr-app-id',
      fcmSenderId: 'ssr-sender',
      fcmVapidPublicKey: 'ssr-vapid',
    };

    const promise = service.loadConfig();
    const req = httpMock.expectOne('/api/app-config/');
    expect(req.request.method).toBe('GET');
    req.flush({ MOCK_AUTH_ENABLED: false, title: 'Backend' });
    await promise;

    expect(service.settings.MOCK_AUTH_ENABLED).toBe(false);
    expect(service.settings.title).toBe('Backend');
    expect(service.settings.fcmProjectId).toBe('ssr-project');
    expect(service.settings.fcmWebApiKey).toBe('ssr-api-key');
    expect(service.settings.fcmWebAppId).toBe('ssr-app-id');
    expect(service.settings.fcmSenderId).toBe('ssr-sender');
    expect(service.settings.fcmVapidPublicKey).toBe('ssr-vapid');
  });

  it('preserves SSR-injected auto-scale env values when backend omits those keys', async () => {
    (window as any).APP_CONFIG = {
      MOCK_AUTH_ENABLED: 'False',
      title: 'Injected',
      uiAutoScaleReferenceWidth: 1440,
      uiAutoScaleMinPercent: 95,
      uiAutoScaleMaxPercent: 105,
    };

    const promise = service.loadConfig();
    const req = httpMock.expectOne('/api/app-config/');
    expect(req.request.method).toBe('GET');
    req.flush({ MOCK_AUTH_ENABLED: false, title: 'Backend' });
    await promise;

    expect(service.settings.title).toBe('Backend');
    expect(service.settings.uiAutoScaleReferenceWidth).toBe(1440);
    expect(service.settings.uiAutoScaleMinPercent).toBe(95);
    expect(service.settings.uiAutoScaleMaxPercent).toBe(105);
  });

  it('uses backend auto-scale values when they are explicitly provided', async () => {
    (window as any).APP_CONFIG = {
      MOCK_AUTH_ENABLED: 'False',
      uiAutoScaleReferenceWidth: 1440,
      uiAutoScaleMinPercent: 95,
      uiAutoScaleMaxPercent: 105,
    };

    const promise = service.loadConfig();
    const req = httpMock.expectOne('/api/app-config/');
    expect(req.request.method).toBe('GET');
    req.flush({
      MOCK_AUTH_ENABLED: false,
      uiAutoScaleReferenceWidth: 1600,
      uiAutoScaleMinPercent: 90,
      uiAutoScaleMaxPercent: 110,
    });
    await promise;

    expect(service.settings.uiAutoScaleReferenceWidth).toBe(1600);
    expect(service.settings.uiAutoScaleMinPercent).toBe(90);
    expect(service.settings.uiAutoScaleMaxPercent).toBe(110);
  });
});
