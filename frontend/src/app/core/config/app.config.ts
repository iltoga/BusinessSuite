import { ThemeName } from '../theme.config';

export interface AppConfig {
  // Accept either a boolean or a case-insensitive string ('True'|'False'|'true'|'false')
  MOCK_AUTH_ENABLED: string | boolean;
  theme: ThemeName;
  dateFormat: string;
  calendarTodoColorId?: string;
  calendarDoneColorId?: string;
  // Optional: custom page title to show in the browser tab
  title?: string;
}

export const DEFAULT_APP_CONFIG: AppConfig = {
  // Keep string for compatibility, but boolean is supported
  MOCK_AUTH_ENABLED: 'False',
  theme: 'neutral',
  dateFormat: 'dd-MM-yyyy',
  calendarTodoColorId: '5',
  calendarDoneColorId: '10',
  title: 'BusinessSuite',
};
