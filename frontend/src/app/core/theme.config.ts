/**
 * BusinessSuite Theme Configuration
 *
 * This file defines the theme colors for the application.
 * You can customize colors here to change the entire application theme.
 *
 * Colors are defined in OKLCH format for better perceptual uniformity.
 * Format: oklch(lightness chroma hue)
 * - Lightness: 0 (black) to 1 (white)
 * - Chroma: 0 (gray) to ~0.4 (saturated color)
 * - Hue: 0-360 degrees (color wheel)
 *
 * Quick reference for hues:
 * - Red: ~30°
 * - Yellow/Warning: ~83°
 * - Green/Success: ~155°
 * - Blue: ~265°
 * - Purple: ~304°
 */

export interface ThemeColors {
  // Base colors
  background: string;
  foreground: string;

  // Card colors
  card: string;
  cardForeground: string;

  // Primary brand colors
  primary: string;
  primaryForeground: string;

  // Secondary colors
  secondary: string;
  secondaryForeground: string;

  // Muted/subtle colors
  muted: string;
  mutedForeground: string;

  // Accent colors
  accent: string;
  accentForeground: string;

  // Semantic colors
  destructive: string; // Red - for delete, error actions
  warning: string; // Yellow/Orange - for edit, caution actions
  success: string; // Green - for success, create actions

  // Border and input
  border: string;
  input: string;
  ring: string;
}

/**
 * Light theme configuration
 */
export const lightTheme: ThemeColors = {
  background: 'oklch(1 0 0)',
  foreground: 'oklch(0.145 0 0)',

  card: 'oklch(1 0 0)',
  cardForeground: 'oklch(0.145 0 0)',

  primary: 'oklch(0.205 0 0)',
  primaryForeground: 'oklch(0.985 0 0)',

  secondary: 'oklch(0.97 0 0)',
  secondaryForeground: 'oklch(0.205 0 0)',

  muted: 'oklch(0.97 0 0)',
  mutedForeground: 'oklch(0.556 0 0)',

  accent: 'oklch(0.97 0 0)',
  accentForeground: 'oklch(0.205 0 0)',

  // Semantic colors - easily customizable
  destructive: 'oklch(0.577 0.245 27.325)', // Red
  warning: 'oklch(0.754 0.149 83.317)', // Yellow/Orange
  success: 'oklch(0.596 0.163 155.825)', // Green

  border: 'oklch(0.922 0 0)',
  input: 'oklch(0.922 0 0)',
  ring: 'oklch(0.708 0 0)',
};

/**
 * Dark theme configuration
 */
export const darkTheme: ThemeColors = {
  background: 'oklch(0.145 0 0)',
  foreground: 'oklch(0.985 0 0)',

  card: 'oklch(0.205 0 0)',
  cardForeground: 'oklch(0.985 0 0)',

  primary: 'oklch(0.922 0 0)',
  primaryForeground: 'oklch(0.205 0 0)',

  secondary: 'oklch(0.269 0 0)',
  secondaryForeground: 'oklch(0.985 0 0)',

  muted: 'oklch(0.269 0 0)',
  mutedForeground: 'oklch(0.708 0 0)',

  accent: 'oklch(0.269 0 0)',
  accentForeground: 'oklch(0.985 0 0)',

  // Semantic colors - same as light theme but can be adjusted
  destructive: 'oklch(0.704 0.191 22.216)', // Red (slightly adjusted for dark mode)
  warning: 'oklch(0.754 0.149 83.317)', // Yellow/Orange
  success: 'oklch(0.596 0.163 155.825)', // Green

  border: 'oklch(1 0 0 / 10%)',
  input: 'oklch(1 0 0 / 15%)',
  ring: 'oklch(0.556 0 0)',
};

/**
 * Alternative theme example: Blue theme
 * Uncomment and use this in styles.css to apply
 */
export const blueTheme: Partial<ThemeColors> = {
  primary: 'oklch(0.488 0.243 264.376)', // Blue primary
  destructive: 'oklch(0.577 0.245 27.325)', // Red
  warning: 'oklch(0.754 0.149 50)', // Orange
  success: 'oklch(0.596 0.163 155.825)', // Green
};

/**
 * Alternative theme example: Purple theme
 * Uncomment and use this in styles.css to apply
 */
export const purpleTheme: Partial<ThemeColors> = {
  primary: 'oklch(0.627 0.265 303.9)', // Purple primary
  destructive: 'oklch(0.577 0.245 27.325)', // Red
  warning: 'oklch(0.754 0.149 83.317)', // Yellow
  success: 'oklch(0.596 0.163 155.825)', // Green
};

/**
 * Alternative theme example: Green theme
 * Uncomment and use this in styles.css to apply
 */
export const greenTheme: Partial<ThemeColors> = {
  primary: 'oklch(0.596 0.163 155.825)', // Green primary
  destructive: 'oklch(0.577 0.245 27.325)', // Red
  warning: 'oklch(0.754 0.149 83.317)', // Yellow
  success: 'oklch(0.488 0.243 264.376)', // Blue (swapped with primary)
};
