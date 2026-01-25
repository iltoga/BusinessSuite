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
  mockAuthEnabled: true, // <-- Toggle this to enable/disable mock auth
} as const;
