/**
 * BusinessSuite Theme Configuration
 *
 * Complete theme system based on Zard UI with support for multiple base themes
 * and custom color schemes.
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
 * - Cyan/Teal: ~185°
 * - Blue: ~265°
 * - Purple: ~304°
 *
 * Available themes:
 * - 'neutral' (default): Pure grayscale, no hue shift
 * - 'slate': Cool blue-gray undertone
 * - 'gray': Balanced gray with minimal saturation
 * - 'zinc': Slightly cool gray
 * - 'stone': Warm gray undertone
 * - 'blue': Corporate blue primary
 * - 'purple': Creative purple primary
 * - 'teal': Modern teal primary
 */

export type ThemeName =
  | 'neutral'
  | 'slate'
  | 'gray'
  | 'zinc'
  | 'stone'
  | 'blue'
  | 'purple'
  | 'teal';

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

  // Semantic colors (custom additions to Zard UI)
  destructive: string; // Red - for delete, error actions
  destructiveForeground?: string;
  warning: string; // Yellow/Orange - for edit, caution actions
  warningForeground?: string;
  success: string; // Green - for success, create actions
  successForeground?: string;

  // Border and input
  border: string;
  input: string;
  ring: string;

  // Popover
  popover: string;
  popoverForeground: string;

  // Chart colors
  chart1?: string;
  chart2?: string;
  chart3?: string;
  chart4?: string;
  chart5?: string;

  // Sidebar (optional)
  sidebar?: string;
  sidebarForeground?: string;
  sidebarPrimary?: string;
  sidebarPrimaryForeground?: string;
  sidebarAccent?: string;
  sidebarAccentForeground?: string;
  sidebarBorder?: string;
  sidebarRing?: string;
}

// ====================
// ZARD UI BASE THEMES
// ====================

/**
 * Neutral Theme (Default)
 * Pure grayscale with no hue shift - professional and unbiased
 * Best for: Professional apps, data-heavy interfaces
 */
export const neutralLight: ThemeColors = {
  background: 'oklch(1 0 0)',
  foreground: 'oklch(0.145 0 0)',
  card: 'oklch(1 0 0)',
  cardForeground: 'oklch(0.145 0 0)',
  popover: 'oklch(1 0 0)',
  popoverForeground: 'oklch(0.145 0 0)',
  primary: 'oklch(0.205 0 0)',
  primaryForeground: 'oklch(0.985 0 0)',
  secondary: 'oklch(0.97 0 0)',
  secondaryForeground: 'oklch(0.205 0 0)',
  muted: 'oklch(0.97 0 0)',
  mutedForeground: 'oklch(0.556 0 0)',
  accent: 'oklch(0.97 0 0)',
  accentForeground: 'oklch(0.205 0 0)',
  destructive: 'oklch(0.577 0.245 27.325)',
  warning: 'oklch(0.754 0.149 83.317)',
  success: 'oklch(0.596 0.163 155.825)',
  border: 'oklch(0.922 0 0)',
  input: 'oklch(0.922 0 0)',
  ring: 'oklch(0.708 0 0)',
  chart1: 'oklch(0.646 0.222 41.116)',
  chart2: 'oklch(0.6 0.118 184.704)',
  chart3: 'oklch(0.398 0.07 227.392)',
  chart4: 'oklch(0.828 0.189 84.429)',
  chart5: 'oklch(0.769 0.188 70.08)',
};

/**
 * Slate Theme
 * Cool blue-gray with slight blue undertone
 * Best for: Tech products, developer tools, modern SaaS
 */
export const slateLight: ThemeColors = {
  background: 'oklch(1 0 0)',
  foreground: 'oklch(0.129 0.042 264.695)',
  card: 'oklch(1 0 0)',
  cardForeground: 'oklch(0.129 0.042 264.695)',
  popover: 'oklch(1 0 0)',
  popoverForeground: 'oklch(0.129 0.042 264.695)',
  primary: 'oklch(0.208 0.042 265.755)',
  primaryForeground: 'oklch(0.984 0.003 247.858)',
  secondary: 'oklch(0.968 0.007 247.896)',
  secondaryForeground: 'oklch(0.208 0.042 265.755)',
  muted: 'oklch(0.968 0.007 247.896)',
  mutedForeground: 'oklch(0.554 0.046 257.417)',
  accent: 'oklch(0.968 0.007 247.896)',
  accentForeground: 'oklch(0.208 0.042 265.755)',
  destructive: 'oklch(0.577 0.245 27.325)',
  warning: 'oklch(0.754 0.149 83.317)',
  success: 'oklch(0.596 0.163 155.825)',
  border: 'oklch(0.929 0.013 255.508)',
  input: 'oklch(0.929 0.013 255.508)',
  ring: 'oklch(0.704 0.04 256.788)',
  chart1: 'oklch(0.646 0.222 41.116)',
  chart2: 'oklch(0.6 0.118 184.704)',
  chart3: 'oklch(0.398 0.07 227.392)',
  chart4: 'oklch(0.828 0.189 84.429)',
  chart5: 'oklch(0.769 0.188 70.08)',
};

/**
 * Gray Theme
 * Balanced gray with minimal saturation
 * Best for: Enterprise apps, dashboards, CRM systems
 */
export const grayLight: ThemeColors = {
  background: 'oklch(1 0 0)',
  foreground: 'oklch(0.13 0.028 261.692)',
  card: 'oklch(1 0 0)',
  cardForeground: 'oklch(0.13 0.028 261.692)',
  popover: 'oklch(1 0 0)',
  popoverForeground: 'oklch(0.13 0.028 261.692)',
  primary: 'oklch(0.21 0.034 264.665)',
  primaryForeground: 'oklch(0.985 0.002 247.839)',
  secondary: 'oklch(0.967 0.003 264.542)',
  secondaryForeground: 'oklch(0.21 0.034 264.665)',
  muted: 'oklch(0.967 0.003 264.542)',
  mutedForeground: 'oklch(0.551 0.027 264.364)',
  accent: 'oklch(0.967 0.003 264.542)',
  accentForeground: 'oklch(0.21 0.034 264.665)',
  destructive: 'oklch(0.577 0.245 27.325)',
  warning: 'oklch(0.754 0.149 83.317)',
  success: 'oklch(0.596 0.163 155.825)',
  border: 'oklch(0.928 0.006 264.531)',
  input: 'oklch(0.928 0.006 264.531)',
  ring: 'oklch(0.707 0.022 261.325)',
  chart1: 'oklch(0.646 0.222 41.116)',
  chart2: 'oklch(0.6 0.118 184.704)',
  chart3: 'oklch(0.398 0.07 227.392)',
  chart4: 'oklch(0.828 0.189 84.429)',
  chart5: 'oklch(0.769 0.188 70.08)',
};

/**
 * Zinc Theme
 * Slightly cool gray with subtle blue-gray tint
 * Best for: Modern web apps, content platforms
 */
export const zincLight: ThemeColors = {
  background: 'oklch(1 0 0)',
  foreground: 'oklch(0.141 0.005 285.823)',
  card: 'oklch(1 0 0)',
  cardForeground: 'oklch(0.141 0.005 285.823)',
  popover: 'oklch(1 0 0)',
  popoverForeground: 'oklch(0.141 0.005 285.823)',
  primary: 'oklch(0.21 0.006 285.885)',
  primaryForeground: 'oklch(0.985 0 0)',
  secondary: 'oklch(0.967 0.001 286.375)',
  secondaryForeground: 'oklch(0.21 0.006 285.885)',
  muted: 'oklch(0.967 0.001 286.375)',
  mutedForeground: 'oklch(0.552 0.016 285.938)',
  accent: 'oklch(0.967 0.001 286.375)',
  accentForeground: 'oklch(0.21 0.006 285.885)',
  destructive: 'oklch(0.577 0.245 27.325)',
  warning: 'oklch(0.754 0.149 83.317)',
  success: 'oklch(0.596 0.163 155.825)',
  border: 'oklch(0.92 0.004 286.32)',
  input: 'oklch(0.92 0.004 286.32)',
  ring: 'oklch(0.705 0.015 286.067)',
  chart1: 'oklch(0.646 0.222 41.116)',
  chart2: 'oklch(0.6 0.118 184.704)',
  chart3: 'oklch(0.398 0.07 227.392)',
  chart4: 'oklch(0.828 0.189 84.429)',
  chart5: 'oklch(0.769 0.188 70.08)',
};

/**
 * Stone Theme
 * Warm gray with slight warm undertone
 * Best for: E-commerce, lifestyle apps, hospitality
 */
export const stoneLight: ThemeColors = {
  background: 'oklch(1 0 0)',
  foreground: 'oklch(0.147 0.004 49.25)',
  card: 'oklch(1 0 0)',
  cardForeground: 'oklch(0.147 0.004 49.25)',
  popover: 'oklch(1 0 0)',
  popoverForeground: 'oklch(0.147 0.004 49.25)',
  primary: 'oklch(0.216 0.006 56.043)',
  primaryForeground: 'oklch(0.985 0.001 106.423)',
  secondary: 'oklch(0.97 0.001 106.424)',
  secondaryForeground: 'oklch(0.216 0.006 56.043)',
  muted: 'oklch(0.97 0.001 106.424)',
  mutedForeground: 'oklch(0.553 0.013 58.071)',
  accent: 'oklch(0.97 0.001 106.424)',
  accentForeground: 'oklch(0.216 0.006 56.043)',
  destructive: 'oklch(0.577 0.245 27.325)',
  warning: 'oklch(0.754 0.149 83.317)',
  success: 'oklch(0.596 0.163 155.825)',
  border: 'oklch(0.923 0.003 48.717)',
  input: 'oklch(0.923 0.003 48.717)',
  ring: 'oklch(0.709 0.01 56.259)',
  chart1: 'oklch(0.646 0.222 41.116)',
  chart2: 'oklch(0.6 0.118 184.704)',
  chart3: 'oklch(0.398 0.07 227.392)',
  chart4: 'oklch(0.828 0.189 84.429)',
  chart5: 'oklch(0.769 0.188 70.08)',
};

// ====================
// DARK MODE VARIANTS
// ====================

export const neutralDark: ThemeColors = {
  background: 'oklch(0.145 0 0)',
  foreground: 'oklch(0.985 0 0)',
  card: 'oklch(0.205 0 0)',
  cardForeground: 'oklch(0.985 0 0)',
  popover: 'oklch(0.205 0 0)',
  popoverForeground: 'oklch(0.985 0 0)',
  primary: 'oklch(0.922 0 0)',
  primaryForeground: 'oklch(0.205 0 0)',
  secondary: 'oklch(0.269 0 0)',
  secondaryForeground: 'oklch(0.985 0 0)',
  muted: 'oklch(0.269 0 0)',
  mutedForeground: 'oklch(0.708 0 0)',
  accent: 'oklch(0.269 0 0)',
  accentForeground: 'oklch(0.985 0 0)',
  destructive: 'oklch(0.704 0.191 22.216)',
  warning: 'oklch(0.84 0.16 84)',
  success: 'oklch(0.696 0.17 162.48)',
  border: 'oklch(1 0 0 / 10%)',
  input: 'oklch(1 0 0 / 15%)',
  ring: 'oklch(0.556 0 0)',
  chart1: 'oklch(0.488 0.243 264.376)',
  chart2: 'oklch(0.696 0.17 162.48)',
  chart3: 'oklch(0.769 0.188 70.08)',
  chart4: 'oklch(0.627 0.265 303.9)',
  chart5: 'oklch(0.645 0.246 16.439)',
};

export const slateDark: ThemeColors = {
  ...neutralDark,
  foreground: 'oklch(0.984 0.003 247.858)',
  cardForeground: 'oklch(0.984 0.003 247.858)',
  popoverForeground: 'oklch(0.984 0.003 247.858)',
  primary: 'oklch(0.929 0.013 255.508)',
  primaryForeground: 'oklch(0.208 0.042 265.755)',
  mutedForeground: 'oklch(0.704 0.04 256.788)',
};

export const grayDark: ThemeColors = {
  ...neutralDark,
  foreground: 'oklch(0.985 0.002 247.839)',
  cardForeground: 'oklch(0.985 0.002 247.839)',
  popoverForeground: 'oklch(0.985 0.002 247.839)',
  primary: 'oklch(0.928 0.006 264.531)',
  primaryForeground: 'oklch(0.21 0.034 264.665)',
  mutedForeground: 'oklch(0.707 0.022 261.325)',
};

export const zincDark: ThemeColors = {
  ...neutralDark,
  primary: 'oklch(0.92 0.004 286.32)',
  primaryForeground: 'oklch(0.21 0.006 285.885)',
  mutedForeground: 'oklch(0.705 0.015 286.067)',
};

export const stoneDark: ThemeColors = {
  ...neutralDark,
  foreground: 'oklch(0.985 0.001 106.423)',
  cardForeground: 'oklch(0.985 0.001 106.423)',
  popoverForeground: 'oklch(0.985 0.001 106.423)',
  primary: 'oklch(0.923 0.003 48.717)',
  primaryForeground: 'oklch(0.216 0.006 56.043)',
  mutedForeground: 'oklch(0.709 0.01 56.259)',
};

// ====================
// CUSTOM COLOR THEMES
// ====================

/**
 * Blue Theme
 * Corporate blue primary color
 * Best for: Tech companies, finance, professional services
 */
export const blueLight: ThemeColors = {
  ...neutralLight,
  primary: 'oklch(0.488 0.243 264.376)', // Blue
  warning: 'oklch(0.754 0.149 50)', // Orange (complementary)
  chart1: 'oklch(0.488 0.243 264.376)', // Blue
  chart2: 'oklch(0.696 0.17 162.48)', // Green
  chart3: 'oklch(0.627 0.265 303.9)', // Purple
  chart4: 'oklch(0.754 0.149 50)', // Orange
  chart5: 'oklch(0.6 0.118 184.704)', // Teal
};

export const blueDark: ThemeColors = {
  ...neutralDark,
  primary: 'oklch(0.7 0.2 264)', // Lighter blue for dark mode
  primaryForeground: 'oklch(0.145 0 0)',
};

/**
 * Purple Theme
 * Creative purple primary color
 * Best for: Creative agencies, design tools, entertainment
 */
export const purpleLight: ThemeColors = {
  ...neutralLight,
  primary: 'oklch(0.627 0.265 303.9)', // Purple
  chart1: 'oklch(0.627 0.265 303.9)', // Purple
  chart2: 'oklch(0.488 0.243 264.376)', // Blue
  chart3: 'oklch(0.754 0.149 50)', // Orange
  chart4: 'oklch(0.696 0.17 162.48)', // Green
  chart5: 'oklch(0.645 0.246 16.439)', // Red-orange
};

export const purpleDark: ThemeColors = {
  ...neutralDark,
  primary: 'oklch(0.75 0.23 303.9)', // Lighter purple for dark mode
  primaryForeground: 'oklch(0.145 0 0)',
};

/**
 * Teal Theme
 * Modern teal/cyan primary color
 * Best for: Healthcare, wellness, modern startups
 */
export const tealLight: ThemeColors = {
  ...neutralLight,
  primary: 'oklch(0.6 0.118 184.704)', // Teal
  chart1: 'oklch(0.6 0.118 184.704)', // Teal
  chart2: 'oklch(0.488 0.243 264.376)', // Blue
  chart3: 'oklch(0.696 0.17 162.48)', // Green
  chart4: 'oklch(0.627 0.265 303.9)', // Purple
  chart5: 'oklch(0.754 0.149 83.317)', // Yellow
};

export const tealDark: ThemeColors = {
  ...neutralDark,
  primary: 'oklch(0.7 0.15 184)', // Lighter teal for dark mode
  primaryForeground: 'oklch(0.145 0 0)',
};

// ====================
// THEME REGISTRY
// ====================

/**
 * Complete theme definitions with light and dark variants
 */
export const THEMES = {
  neutral: { light: neutralLight, dark: neutralDark },
  slate: { light: slateLight, dark: slateDark },
  gray: { light: grayLight, dark: grayDark },
  zinc: { light: zincLight, dark: zincDark },
  stone: { light: stoneLight, dark: stoneDark },
  blue: { light: blueLight, dark: blueDark },
  purple: { light: purpleLight, dark: purpleDark },
  teal: { light: tealLight, dark: tealDark },
} as const;

/**
 * Get theme by name and mode
 */
export function getTheme(name: ThemeName, mode: 'light' | 'dark' = 'light'): ThemeColors {
  return THEMES[name][mode];
}

// Legacy exports for backwards compatibility
export const lightTheme = neutralLight;
export const darkTheme = neutralDark;
