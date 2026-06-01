import { PLATFORM_ID } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router } from '@angular/router';
import { of, Subject } from 'rxjs';

import { BackupsService } from '@/core/api';
import { AuthService } from '@/core/services/auth.service';
import { SseService } from '@/core/services/sse.service';
import { GlobalToastService } from '@/core/services/toast.service';
import { REQUEST_METADATA_CONTEXT } from '@/core/utils/request-metadata';

import { BackupsComponent } from './backups.component';

describe('BackupsComponent', () => {
  let component: BackupsComponent;
  let mockBackupsService: any;
  let mockSseService: any;
  let mockToastService: any;
  let backupStream$: Subject<any>;
  let restoreStream$: Subject<any>;

  beforeEach(() => {
    backupStream$ = new Subject();
    restoreStream$ = new Subject();

    mockBackupsService = {
      backupsStartJobCreate: vi.fn().mockReturnValue(
        of({
          jobId: 'backup-job-1',
          status: 'queued',
          progress: 0,
          queued: true,
          deduplicated: false,
          streamUrl: '/api/backups/start/?replay=1&job_id=backup-job-1',
        }),
      ),
      backupsRestoreJobCreate: vi.fn().mockReturnValue(
        of({
          jobId: 'restore-job-1',
          status: 'queued',
          progress: 0,
          queued: true,
          deduplicated: false,
        }),
      ),
      backupsRetrieve: vi.fn().mockReturnValue(of({ data: { backups: [] } })),
    };

    mockSseService = {
      connect: vi.fn((url: string) => {
        if (url.includes('/api/backups/restore/')) {
          return restoreStream$.asObservable();
        }
        return backupStream$.asObservable();
      }),
    };

    mockToastService = {
      success: vi.fn(),
      error: vi.fn(),
      info: vi.fn(),
      warning: vi.fn(),
    };

    TestBed.configureTestingModule({
      providers: [
        { provide: PLATFORM_ID, useValue: 'server' },
        {
          provide: Router,
          useValue: {
            navigate: vi.fn(),
            getCurrentNavigation: vi.fn().mockReturnValue(null),
          },
        },
        { provide: ActivatedRoute, useValue: { snapshot: { queryParams: {} } } },
        { provide: BackupsService, useValue: mockBackupsService },
        { provide: SseService, useValue: mockSseService },
        {
          provide: AuthService,
          useValue: {
            isSuperuser: vi.fn(() => true),
            isAdmin: vi.fn(() => true),
            isInAdminGroup: vi.fn(() => true),
          },
        },
        { provide: GlobalToastService, useValue: mockToastService },
      ],
    });

    component = TestBed.runInInjectionContext(() => new BackupsComponent());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('starts backups through the generated start endpoint before opening the returned stream URL', () => {
    const reloadSpy = vi.spyOn(component, 'reload');
    component.includeUsers.set(true);

    component.startBackup();

    expect(mockBackupsService.backupsStartJobCreate).toHaveBeenCalledWith(
      {
        includeUsers: true,
      },
      'body',
      false,
      expect.objectContaining({
        context: expect.anything(),
      }),
    );
    const requestContext = mockBackupsService.backupsStartJobCreate.mock.calls[0]?.[3]?.context;
    const requestMetadata = requestContext?.get(REQUEST_METADATA_CONTEXT);
    expect(requestMetadata).toEqual(
      expect.objectContaining({
        requestId: expect.any(String),
        idempotencyKey: expect.any(String),
      }),
    );
    expect(mockSseService.connect).toHaveBeenCalledWith(
      '/api/backups/start/?replay=1&job_id=backup-job-1',
      expect.objectContaining({
        useReplayCursor: true,
        requestMetadata,
      }),
    );

    backupStream$.next({ message: 'Backup finished', progress: 100 });

    expect(component.isOperationRunning()).toBe(false);
    expect(component.operationProgress()).toBe(100);
    expect(mockToastService.success).toHaveBeenCalledWith('Backup completed successfully');
    expect(reloadSpy).toHaveBeenCalledTimes(1);
  });

  it('starts restore through the generated endpoint and falls back to a job-based replay stream URL', () => {
    vi.stubGlobal(
      'confirm',
      vi.fn(() => true),
    );
    component.includeUsers.set(false);

    component.restoreBackup('backup-20260530.tar.zst');

    expect(mockBackupsService.backupsRestoreJobCreate).toHaveBeenCalledWith(
      {
        file: 'backup-20260530.tar.zst',
        includeUsers: false,
      },
      'body',
      false,
      expect.objectContaining({
        context: expect.anything(),
      }),
    );
    const requestContext = mockBackupsService.backupsRestoreJobCreate.mock.calls[0]?.[3]?.context;
    const requestMetadata = requestContext?.get(REQUEST_METADATA_CONTEXT);
    expect(requestMetadata).toEqual(
      expect.objectContaining({
        requestId: expect.any(String),
        idempotencyKey: expect.any(String),
      }),
    );
    expect(mockSseService.connect).toHaveBeenCalledWith(
      '/api/backups/restore/?replay=1&job_id=restore-job-1',
      expect.objectContaining({
        useReplayCursor: true,
        requestMetadata,
      }),
    );

    restoreStream$.next({ message: 'Restore finished', progress: 100 });

    expect(component.isOperationRunning()).toBe(false);
    expect(component.operationProgress()).toBe(100);
    expect(mockToastService.success).toHaveBeenCalledWith('Restore completed successfully');
  });
});
