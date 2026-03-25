import { HttpClient } from '@angular/common/http';
import { PLATFORM_ID } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';

import { AuthService } from '@/core/services/auth.service';
import { ConfigService } from '@/core/services/config.service';
import { DesktopBridgeService } from '@/core/services/desktop-bridge.service';
import { PushNotificationsService } from '@/core/services/push-notifications.service';
import { PushProxyFetchService } from '@/core/services/push-proxy-fetch.service';
import { ReminderDialogService } from '@/core/services/reminder-dialog.service';
import { GlobalToastService } from '@/core/services/toast.service';

describe('PushNotificationsService', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        PushNotificationsService,
        { provide: PLATFORM_ID, useValue: 'browser' },
        {
          provide: HttpClient,
          useValue: {},
        },
        {
          provide: AuthService,
          useValue: {
            token: vi.fn(() => null),
            isAuthenticated: vi.fn(() => false),
          },
        },
        {
          provide: ConfigService,
          useValue: {
            settings: {
              fcmSenderId: '1234567890',
              fcmProjectId: 'business-suite',
              fcmWebApiKey: 'api-key',
              fcmWebAppId: 'app-id',
              fcmVapidPublicKey: 'vapid-key',
            },
          },
        },
        {
          provide: DesktopBridgeService,
          useValue: {},
        },
        {
          provide: PushProxyFetchService,
          useValue: {
            runWithGoogleApisProxy: vi.fn(async (callback: () => Promise<string>) => callback()),
          },
        },
        {
          provide: ReminderDialogService,
          useValue: {},
        },
        {
          provide: GlobalToastService,
          useValue: {},
        },
      ],
    });

    Object.defineProperty(navigator, 'serviceWorker', {
      configurable: true,
      value: {},
    });

    vi.stubGlobal('Notification', {
      permission: 'default',
      requestPermission: vi.fn(),
    });
  });

  it('fails soft when Firebase scripts cannot load', async () => {
    const service = TestBed.inject(PushNotificationsService);
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const appendSpy = vi.spyOn(document.head, 'appendChild').mockImplementation((node: any) => {
      queueMicrotask(() => node.onerror?.(new Event('error')));
      return node;
    });
    vi.spyOn(document, 'getElementById').mockReturnValue(null);

    await service.initialize();

    expect(appendSpy).toHaveBeenCalled();
    expect(warnSpy).toHaveBeenCalledWith(
      '[PushNotificationsService] Firebase SDK unavailable; push notifications disabled.',
      expect.objectContaining({ message: expect.stringContaining('Failed to load script') }),
    );
    expect(errorSpy).not.toHaveBeenCalled();

    warnSpy.mockRestore();
    errorSpy.mockRestore();
    appendSpy.mockRestore();
  });
});
