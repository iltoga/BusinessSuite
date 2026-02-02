import { ThemeName } from '../theme.config';

export interface AppConfig {
  mockAuthEnabled: boolean;
  theme: ThemeName;
  dateFormat: string;
  // Optional: custom logo filenames placed under /assets
  logoFilename?: string;
  logoInvertedFilename?: string;
}

export const DEFAULT_APP_CONFIG: AppConfig = {
  mockAuthEnabled: false,
  theme: 'neutral',
  dateFormat: 'dd-MM-yyyy',
  logoFilename: 'logo_transparent.png',
  logoInvertedFilename: 'logo_inverted_transparent.png',
};
