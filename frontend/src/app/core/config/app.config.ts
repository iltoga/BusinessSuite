import { ThemeName } from '../theme.config';

/**
 * Application configuration
 * Toggle these settings for development vs production
 */
export const APP_CONFIG = {
  /**
   * Enable mocked authentication for local dev (no real login required)
   * Set to `true` to bypass authentication during development
   * Set to `false` for production or to test real authentication
   */
  mockAuthEnabled: false, // <-- Toggle this to enable/disable mock auth

  /**
   * Application theme
   *
   * Available themes:
   * - 'neutral': Pure grayscale (default) - professional
   * - 'slate': Cool blue-gray - tech/SaaS
   * - 'gray': Balanced gray - enterprise apps
   * - 'zinc': Slightly cool gray - modern web apps
   * - 'stone': Warm gray - e-commerce/lifestyle
   * - 'blue': Corporate blue primary
   * - 'purple': Creative purple primary
   * - 'teal': Modern teal primary
   *
   * Change this value to switch the entire app theme
   */
  theme: 'neutral' as ThemeName, // <-- Change theme here
} as const;
