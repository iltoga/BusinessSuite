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
    };

    const promise = service.loadConfig();
    const req = httpMock.expectOne('/api/app-config/');
    expect(req.request.method).toBe('GET');
    req.flush({ MOCK_AUTH_ENABLED: false, title: 'Backend', useOverlayMenu: true });
    await promise;

    expect(service.settings.MOCK_AUTH_ENABLED).toBe(false);
    expect(service.settings.title).toBe('Backend');
    expect(service.settings.useOverlayMenu).toBe(true);
  });

  it('keeps injected config if backend app-config request fails', async () => {
    (window as any).APP_CONFIG = { MOCK_AUTH_ENABLED: 'False', title: 'Injected' };

    const promise = service.loadConfig();
    const req = httpMock.expectOne('/api/app-config/');
    expect(req.request.method).toBe('GET');
    req.flush({ detail: 'error' }, { status: 500, statusText: 'Server Error' });
    await promise;

    expect(service.settings.MOCK_AUTH_ENABLED).toBe('False');
    expect(service.settings.title).toBe('Injected');
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
});
