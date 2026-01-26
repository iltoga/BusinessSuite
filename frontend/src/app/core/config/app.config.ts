import { ThemeName } from '../theme.config';

export interface AppConfig {
  mockAuthEnabled: boolean;
  theme: ThemeName;
  dateFormat: string;
}

export const DEFAULT_APP_CONFIG: AppConfig = {
  mockAuthEnabled: false,
  theme: 'neutral',
  dateFormat: 'dd-MM-yyyy',
};
