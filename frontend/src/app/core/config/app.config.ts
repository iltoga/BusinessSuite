import { ThemeName } from '../theme.config';

export interface AppConfig {
  // Accept either a boolean or a case-insensitive string ('True'|'False'|'true'|'false')
  MOCK_AUTH_ENABLED: string | boolean;
  DEBUG?: boolean;
  theme: ThemeName;
  dateFormat: string;
  baseCurrency: string;
  calendarTodoColorId?: string;
  calendarDoneColorId?: string;
  // Optional: custom page title to show in the browser tab
  title?: string;
  // Firebase Cloud Messaging settings (optional; when absent push is disabled)
  fcmSenderId?: string;
  fcmVapidPublicKey?: string;
  fcmProjectId?: string;
  fcmProjectNumber?: string;
  fcmWebApiKey?: string;
  fcmWebAppId?: string;
  fcmWebAuthDomain?: string;
  fcmWebStorageBucket?: string;
  fcmWebMeasurementId?: string;
  uiScalePercent?: number | string;
  uiAutoScaleEnabled?: boolean | string;
  uiAutoScaleReferenceWidth?: number | string;
  uiAutoScaleMinPercent?: number | string;
  uiAutoScaleMaxPercent?: number | string;
  uiAutoScaleDesktopOnly?: boolean | string;
  useOverlayMenu?: boolean;
  skeletonDebounceDurationMs?: number | string;
  rbac?: {
    adminGroupName: string;
    managerGroupName: string;
  };
}

export const DEFAULT_APP_CONFIG: AppConfig = {
  // Keep string for compatibility, but boolean is supported
  MOCK_AUTH_ENABLED: 'False',
  DEBUG: false,
  theme: 'neutral',
  dateFormat: 'dd-MM-yyyy',
  baseCurrency: 'IDR',
  calendarTodoColorId: '5',
  calendarDoneColorId: '10',
  title: 'BusinessSuite',
  fcmSenderId: '',
  fcmVapidPublicKey: '',
  fcmProjectId: '',
  fcmProjectNumber: '',
  fcmWebApiKey: '',
  fcmWebAppId: '',
  fcmWebAuthDomain: '',
  fcmWebStorageBucket: '',
  fcmWebMeasurementId: '',
  uiScalePercent: 100,
  uiAutoScaleEnabled: false,
  uiAutoScaleReferenceWidth: 1440,
  uiAutoScaleMinPercent: 95,
  uiAutoScaleMaxPercent: 105,
  uiAutoScaleDesktopOnly: true,
  useOverlayMenu: false,
  skeletonDebounceDurationMs: 500,
  rbac: { adminGroupName: 'admin', managerGroupName: 'manager' },
};
