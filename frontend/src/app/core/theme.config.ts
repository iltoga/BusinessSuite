/**
 * BusinessSuite Theme Configuration
 *
 * Complete theme system based on Zard UI with support for multiple base themes
 * and custom color schemes.
 *
 * Colors are defined in OKLCH format for better perceptual uniformity.
 * Format: oklch(lightness chroma hue)
 *
 * Updated with distinct, professionally crafted palettes for each theme variant.
 */

export type ThemeName =
  | 'neutral'
  | 'slate'
  | 'spaceGray'
  | 'silver'
  | 'starlight'
  | 'zinc'
  | 'stone'
  | 'blue'
  | 'purple'
  | 'teal'
  | 'sakura'
  | 'legacy';

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
 * Neutral Theme
 * Pure monochrome. No hue shifts. Stark, high-contrast, professional.
 * Best for: Data-heavy apps, minimalistic portfolios.
 */
export const neutralLight: ThemeColors = {
  background: 'oklch(1 0 0)',
  foreground: 'oklch(0.1 0 0)', // Near black
  card: 'oklch(1 0 0)',
  cardForeground: 'oklch(0.1 0 0)',
  popover: 'oklch(1 0 0)',
  popoverForeground: 'oklch(0.1 0 0)',
  primary: 'oklch(0.12 0 0)', // Soft black
  primaryForeground: 'oklch(0.98 0 0)',
  secondary: 'oklch(0.96 0 0)', // Light gray
  secondaryForeground: 'oklch(0.12 0 0)',
  muted: 'oklch(0.96 0 0)',
  mutedForeground: 'oklch(0.45 0 0)',
  accent: 'oklch(0.96 0 0)',
  accentForeground: 'oklch(0.12 0 0)',
  destructive: 'oklch(0.577 0.245 27.325)',
  warning: 'oklch(0.754 0.149 83.317)',
  success: 'oklch(0.596 0.163 155.825)',
  border: 'oklch(0.92 0 0)',
  input: 'oklch(0.92 0 0)',
  ring: 'oklch(0.12 0 0)',
  chart1: 'oklch(0.12 0 0)',
  chart2: 'oklch(0.5 0 0)',
  chart3: 'oklch(0.3 0 0)',
  chart4: 'oklch(0.7 0 0)',
  chart5: 'oklch(0.9 0 0)',
};

export const neutralDark: ThemeColors = {
  background: 'oklch(0 0 0)', // Pure black
  foreground: 'oklch(0.98 0 0)',
  card: 'oklch(0.1 0 0)', // Deep gray card
  cardForeground: 'oklch(0.98 0 0)',
  popover: 'oklch(0.1 0 0)',
  popoverForeground: 'oklch(0.98 0 0)',
  primary: 'oklch(0.98 0 0)', // White
  primaryForeground: 'oklch(0 0 0)',
  secondary: 'oklch(0.2 0 0)',
  secondaryForeground: 'oklch(0.98 0 0)',
  muted: 'oklch(0.2 0 0)',
  mutedForeground: 'oklch(0.65 0 0)',
  accent: 'oklch(0.2 0 0)',
  accentForeground: 'oklch(0.98 0 0)',
  destructive: 'oklch(0.6 0.2 25)',
  warning: 'oklch(0.75 0.15 80)',
  success: 'oklch(0.6 0.16 155)',
  border: 'oklch(0.2 0 0)',
  input: 'oklch(0.2 0 0)',
  ring: 'oklch(0.8 0 0)',
  chart1: 'oklch(0.98 0 0)',
  chart2: 'oklch(0.7 0 0)',
  chart3: 'oklch(0.5 0 0)',
  chart4: 'oklch(0.3 0 0)',
  chart5: 'oklch(0.2 0 0)',
};

/**
 * Slate Theme
 * Cool, corporate, sophisticated. Distinct blue undertones.
 * Best for: SaaS, enterprise dashboards, developer tools.
 */
export const slateLight: ThemeColors = {
  background: 'oklch(0.99 0.01 250)', // Very slight cool tint
  foreground: 'oklch(0.15 0.06 255)', // Deep slate
  card: 'oklch(1 0 0)',
  cardForeground: 'oklch(0.15 0.06 255)',
  popover: 'oklch(1 0 0)',
  popoverForeground: 'oklch(0.15 0.06 255)',
  primary: 'oklch(0.3 0.1 255)', // Corporate slate blue
  primaryForeground: 'oklch(0.98 0.01 250)',
  secondary: 'oklch(0.95 0.03 255)', // Light blue-gray
  secondaryForeground: 'oklch(0.3 0.1 255)',
  muted: 'oklch(0.96 0.02 255)',
  mutedForeground: 'oklch(0.5 0.06 255)',
  accent: 'oklch(0.95 0.03 255)',
  accentForeground: 'oklch(0.3 0.1 255)',
  destructive: 'oklch(0.577 0.245 27.325)',
  warning: 'oklch(0.754 0.149 83.317)',
  success: 'oklch(0.596 0.163 155.825)',
  border: 'oklch(0.9 0.03 255)',
  input: 'oklch(0.9 0.03 255)',
  ring: 'oklch(0.3 0.1 255)',
  chart1: 'oklch(0.3 0.1 255)', // Slate Blue
  chart2: 'oklch(0.45 0.12 230)', // Cyan-Blue
  chart3: 'oklch(0.6 0.1 200)', // Teal
  chart4: 'oklch(0.5 0.15 280)', // Purple-Blue
  chart5: 'oklch(0.7 0.1 255)',
};

export const slateDark: ThemeColors = {
  background: 'oklch(0.1 0.04 255)', // Rich dark slate
  foreground: 'oklch(0.98 0.01 250)',
  card: 'oklch(0.14 0.04 255)', // Lighter slate card
  cardForeground: 'oklch(0.98 0.01 250)',
  popover: 'oklch(0.14 0.04 255)',
  popoverForeground: 'oklch(0.98 0.01 250)',
  primary: 'oklch(0.8 0.1 255)', // Bright slate
  primaryForeground: 'oklch(0.1 0.04 255)',
  secondary: 'oklch(0.25 0.05 255)',
  secondaryForeground: 'oklch(0.98 0.01 250)',
  muted: 'oklch(0.2 0.04 255)',
  mutedForeground: 'oklch(0.65 0.05 255)',
  accent: 'oklch(0.25 0.05 255)',
  accentForeground: 'oklch(0.98 0.01 250)',
  destructive: 'oklch(0.6 0.2 25)',
  warning: 'oklch(0.75 0.15 80)',
  success: 'oklch(0.6 0.16 155)',
  border: 'oklch(0.25 0.04 255)',
  input: 'oklch(0.25 0.04 255)',
  ring: 'oklch(0.8 0.1 255)',
  chart1: 'oklch(0.8 0.1 255)',
  chart2: 'oklch(0.6 0.1 230)',
  chart3: 'oklch(0.5 0.15 200)',
  chart4: 'oklch(0.7 0.12 280)',
  chart5: 'oklch(0.9 0.05 255)',
};

/**
 * Space Gray Theme (Formerly Gray)
 * Inspired by the MacBook Pro (2021) chassis.
 * A premium, industrial palette. Deep, cool grays with a metallic finish.
 * Best for: Professional tools, coding environments, high-end SaaS.
 */
export const spaceGrayLight: ThemeColors = {
  background: 'oklch(0.985 0.002 260)', // Aluminum finish (very slight cool tint)
  foreground: 'oklch(0.15 0.01 260)', // Dark gray text
  card: 'oklch(1 0 0)',
  cardForeground: 'oklch(0.15 0.01 260)',
  popover: 'oklch(1 0 0)',
  popoverForeground: 'oklch(0.15 0.01 260)',
  primary: 'oklch(0.28 0.02 260)', // Dark Anodized Gray (Apple Logo style)
  primaryForeground: 'oklch(0.98 0 0)',
  secondary: 'oklch(0.94 0.005 260)', // Light metal
  secondaryForeground: 'oklch(0.28 0.02 260)',
  muted: 'oklch(0.94 0.005 260)',
  mutedForeground: 'oklch(0.55 0.01 260)',
  accent: 'oklch(0.94 0.005 260)',
  accentForeground: 'oklch(0.28 0.02 260)',
  destructive: 'oklch(0.577 0.245 27.325)',
  warning: 'oklch(0.754 0.149 83.317)',
  success: 'oklch(0.596 0.163 155.825)',
  border: 'oklch(0.88 0.005 260)',
  input: 'oklch(0.88 0.005 260)',
  ring: 'oklch(0.28 0.02 260)',
  chart1: 'oklch(0.28 0.02 260)',
  chart2: 'oklch(0.45 0.02 260)',
  chart3: 'oklch(0.6 0.02 260)',
  chart4: 'oklch(0.2 0.02 260)',
  chart5: 'oklch(0.8 0.01 260)',
};

export const spaceGrayDark: ThemeColors = {
  background: 'oklch(0.11 0.01 260)', // Deep Space Gray (Chassis in shadow)
  foreground: 'oklch(0.98 0.002 260)',
  card: 'oklch(0.15 0.015 260)', // Slightly lighter metallic gray
  cardForeground: 'oklch(0.98 0.002 260)',
  popover: 'oklch(0.15 0.015 260)',
  popoverForeground: 'oklch(0.98 0.002 260)',
  primary: 'oklch(0.92 0.005 260)', // Bright Aluminum (Contrast against dark)
  primaryForeground: 'oklch(0.11 0.01 260)',
  secondary: 'oklch(0.22 0.015 260)',
  secondaryForeground: 'oklch(0.98 0.002 260)',
  muted: 'oklch(0.2 0.015 260)',
  mutedForeground: 'oklch(0.65 0.01 260)',
  accent: 'oklch(0.22 0.015 260)',
  accentForeground: 'oklch(0.98 0.002 260)',
  destructive: 'oklch(0.6 0.2 25)',
  warning: 'oklch(0.75 0.15 80)',
  success: 'oklch(0.6 0.16 155)',
  border: 'oklch(0.22 0.015 260)',
  input: 'oklch(0.22 0.015 260)',
  ring: 'oklch(0.8 0.01 260)',
  chart1: 'oklch(0.92 0.005 260)',
  chart2: 'oklch(0.7 0.02 260)',
  chart3: 'oklch(0.5 0.02 260)',
  chart4: 'oklch(0.3 0.02 260)',
  chart5: 'oklch(0.6 0.02 260)',
};

/**
 * Silver Theme (New!)
 * Inspired by the MacBook Pro (2021) Silver finish.
 * A classic, bright, and raw aluminum aesthetic. Lighter and crisper than Space Gray.
 * Best for: Clean, minimalistic interfaces, "Apple-native" feel.
 */
export const silverLight: ThemeColors = {
  background: 'oklch(0.99 0.001 240)', // Pure, bright silver-white
  foreground: 'oklch(0.12 0.01 240)', // High contrast black (Keys)
  card: 'oklch(1 0 0)',
  cardForeground: 'oklch(0.12 0.01 240)',
  popover: 'oklch(1 0 0)',
  popoverForeground: 'oklch(0.12 0.01 240)',
  primary: 'oklch(0.2 0.01 240)', // Deep black-gray (Keyboard well contrast)
  primaryForeground: 'oklch(1 0 0)',
  secondary: 'oklch(0.96 0.002 240)', // Very light aluminum
  secondaryForeground: 'oklch(0.2 0.01 240)',
  muted: 'oklch(0.96 0.002 240)',
  mutedForeground: 'oklch(0.5 0.01 240)',
  accent: 'oklch(0.95 0.005 240)', // Subtle metallic shimmer
  accentForeground: 'oklch(0.2 0.01 240)',
  destructive: 'oklch(0.577 0.245 27.325)',
  warning: 'oklch(0.754 0.149 83.317)',
  success: 'oklch(0.596 0.163 155.825)',
  border: 'oklch(0.92 0.002 240)', // Crisp border
  input: 'oklch(0.92 0.002 240)',
  ring: 'oklch(0.2 0.01 240)',
  chart1: 'oklch(0.2 0.01 240)',
  chart2: 'oklch(0.4 0.01 240)',
  chart3: 'oklch(0.6 0.01 240)',
  chart4: 'oklch(0.8 0.01 240)',
  chart5: 'oklch(0.5 0.01 240)',
};

export const silverDark: ThemeColors = {
  background: 'oklch(0.14 0.01 240)', // Cool, medium-dark gray (Silver in shadow)
  foreground: 'oklch(0.99 0.001 240)',
  card: 'oklch(0.18 0.015 240)', // Lighter cool gray
  cardForeground: 'oklch(0.99 0.001 240)',
  popover: 'oklch(0.18 0.015 240)',
  popoverForeground: 'oklch(0.99 0.001 240)',
  primary: 'oklch(0.98 0.002 240)', // Bright Silver (Contrast against dark)
  primaryForeground: 'oklch(0.14 0.01 240)',
  secondary: 'oklch(0.25 0.02 240)',
  secondaryForeground: 'oklch(0.99 0.001 240)',
  muted: 'oklch(0.22 0.02 240)',
  mutedForeground: 'oklch(0.65 0.01 240)',
  accent: 'oklch(0.25 0.02 240)',
  accentForeground: 'oklch(0.99 0.001 240)',
  destructive: 'oklch(0.6 0.2 25)',
  warning: 'oklch(0.75 0.15 80)',
  success: 'oklch(0.6 0.16 155)',
  border: 'oklch(0.25 0.02 240)',
  input: 'oklch(0.25 0.02 240)',
  ring: 'oklch(0.9 0.01 240)',
  chart1: 'oklch(0.98 0.002 240)',
  chart2: 'oklch(0.8 0.01 240)',
  chart3: 'oklch(0.6 0.01 240)',
  chart4: 'oklch(0.4 0.01 240)',
  chart5: 'oklch(0.7 0.01 240)',
};

/**
 * Starlight Theme (New!)
 * Inspired by the Apple Watch & MacBook Air "Starlight" finish.
 * A warm, champagne-silver aesthetic. Subtle luxury.
 * Best for: Lifestyle apps, high-end commerce, elegant dashboards.
 */
export const starlightLight: ThemeColors = {
  background: 'oklch(0.99 0.008 95)', // Warm, creamy white (Champagne tint)
  foreground: 'oklch(0.2 0.03 85)', // Warm dark bronze-gray
  card: 'oklch(1 0 0)', // Pure white to contrast with warm bg
  cardForeground: 'oklch(0.2 0.03 85)',
  popover: 'oklch(1 0 0)',
  popoverForeground: 'oklch(0.2 0.03 85)',
  primary: 'oklch(0.55 0.08 85)', // Antique Gold / Bronze (Readable on white)
  primaryForeground: 'oklch(0.99 0.008 95)',
  secondary: 'oklch(0.96 0.015 95)', // Pale warm beige
  secondaryForeground: 'oklch(0.55 0.08 85)',
  muted: 'oklch(0.96 0.015 95)',
  mutedForeground: 'oklch(0.5 0.04 85)',
  accent: 'oklch(0.95 0.02 95)', // Starlight shimmer
  accentForeground: 'oklch(0.55 0.08 85)',
  destructive: 'oklch(0.577 0.245 27.325)',
  warning: 'oklch(0.75 0.14 85)', // Gold warning
  success: 'oklch(0.6 0.14 145)', // Warm green
  border: 'oklch(0.9 0.02 95)', // Warm border
  input: 'oklch(0.9 0.02 95)',
  ring: 'oklch(0.55 0.08 85)',
  chart1: 'oklch(0.55 0.08 85)', // Bronze
  chart2: 'oklch(0.7 0.12 80)', // Gold
  chart3: 'oklch(0.6 0.06 50)', // Warm Stone
  chart4: 'oklch(0.8 0.1 90)', // Pale Gold
  chart5: 'oklch(0.4 0.05 85)', // Deep Bronze
};

export const starlightDark: ThemeColors = {
  background: 'oklch(0.12 0.02 90)', // Warm Black / Deep Espresso
  foreground: 'oklch(0.97 0.01 95)', // Warm white
  card: 'oklch(0.16 0.025 90)', // Lighter warm dark
  cardForeground: 'oklch(0.97 0.01 95)',
  popover: 'oklch(0.16 0.025 90)',
  popoverForeground: 'oklch(0.97 0.01 95)',
  primary: 'oklch(0.88 0.06 95)', // Starlight Metal (Pale Champagne)
  primaryForeground: 'oklch(0.12 0.02 90)', // Dark text on bright metal
  secondary: 'oklch(0.25 0.03 90)',
  secondaryForeground: 'oklch(0.97 0.01 95)',
  muted: 'oklch(0.22 0.03 90)',
  mutedForeground: 'oklch(0.65 0.03 90)',
  accent: 'oklch(0.25 0.03 90)',
  accentForeground: 'oklch(0.97 0.01 95)',
  destructive: 'oklch(0.6 0.2 25)',
  warning: 'oklch(0.75 0.15 80)',
  success: 'oklch(0.6 0.16 155)',
  border: 'oklch(0.25 0.03 90)',
  input: 'oklch(0.25 0.03 90)',
  ring: 'oklch(0.88 0.06 95)',
  chart1: 'oklch(0.88 0.06 95)',
  chart2: 'oklch(0.75 0.1 85)',
  chart3: 'oklch(0.6 0.08 50)',
  chart4: 'oklch(0.5 0.05 90)',
  chart5: 'oklch(0.9 0.04 95)',
};

/**
 * Zinc Theme
 * Industrial, metallic, clean. The standard "Vercel" aesthetic.
 * Best for: Modern web apps, technical content.
 */
export const zincLight: ThemeColors = {
  background: 'oklch(1 0 0)',
  foreground: 'oklch(0.09 0.01 240)', // Sharp black with tiny cool tint
  card: 'oklch(1 0 0)',
  cardForeground: 'oklch(0.09 0.01 240)',
  popover: 'oklch(1 0 0)',
  popoverForeground: 'oklch(0.09 0.01 240)',
  primary: 'oklch(0.13 0.02 240)', // Deep Zinc
  primaryForeground: 'oklch(0.98 0 0)',
  secondary: 'oklch(0.96 0.01 240)',
  secondaryForeground: 'oklch(0.13 0.02 240)',
  muted: 'oklch(0.96 0.01 240)',
  mutedForeground: 'oklch(0.5 0.03 240)',
  accent: 'oklch(0.96 0.01 240)',
  accentForeground: 'oklch(0.13 0.02 240)',
  destructive: 'oklch(0.577 0.245 27.325)',
  warning: 'oklch(0.754 0.149 83.317)',
  success: 'oklch(0.596 0.163 155.825)',
  border: 'oklch(0.9 0.01 240)',
  input: 'oklch(0.9 0.01 240)',
  ring: 'oklch(0.13 0.02 240)',
  chart1: 'oklch(0.13 0.02 240)',
  chart2: 'oklch(0.3 0.02 240)',
  chart3: 'oklch(0.5 0.02 240)',
  chart4: 'oklch(0.7 0.02 240)',
  chart5: 'oklch(0.9 0.02 240)',
};

export const zincDark: ThemeColors = {
  background: 'oklch(0.09 0.01 240)', // Deep metallic dark
  foreground: 'oklch(0.98 0.005 240)',
  card: 'oklch(0.12 0.01 240)',
  cardForeground: 'oklch(0.98 0.005 240)',
  popover: 'oklch(0.12 0.01 240)',
  popoverForeground: 'oklch(0.98 0.005 240)',
  primary: 'oklch(0.95 0.01 240)', // Bright Zinc
  primaryForeground: 'oklch(0.09 0.01 240)',
  secondary: 'oklch(0.2 0.02 240)',
  secondaryForeground: 'oklch(0.98 0 0)',
  muted: 'oklch(0.18 0.02 240)',
  mutedForeground: 'oklch(0.65 0.03 240)',
  accent: 'oklch(0.2 0.02 240)',
  accentForeground: 'oklch(0.98 0 0)',
  destructive: 'oklch(0.6 0.2 25)',
  warning: 'oklch(0.75 0.15 80)',
  success: 'oklch(0.6 0.16 155)',
  border: 'oklch(0.2 0.02 240)',
  input: 'oklch(0.2 0.02 240)',
  ring: 'oklch(0.8 0.02 240)',
  chart1: 'oklch(0.95 0.01 240)',
  chart2: 'oklch(0.75 0.02 240)',
  chart3: 'oklch(0.55 0.02 240)',
  chart4: 'oklch(0.35 0.02 240)',
  chart5: 'oklch(0.2 0.02 240)',
};

/**
 * Stone Theme
 * Warm, earthy, comforting. Distinct brown/sepia undertones.
 * Best for: Lifestyle, hospitality, writing apps.
 */
export const stoneLight: ThemeColors = {
  background: 'oklch(0.99 0.01 50)', // Warm linen
  foreground: 'oklch(0.15 0.03 50)', // Warm dark brown-gray
  card: 'oklch(1 0 0)', // Keep card white for contrast on linen bg
  cardForeground: 'oklch(0.15 0.03 50)',
  popover: 'oklch(1 0 0)',
  popoverForeground: 'oklch(0.15 0.03 50)',
  primary: 'oklch(0.35 0.04 50)', // Deep warm stone
  primaryForeground: 'oklch(0.98 0.01 50)',
  secondary: 'oklch(0.96 0.02 50)', // Beige
  secondaryForeground: 'oklch(0.35 0.04 50)',
  muted: 'oklch(0.96 0.02 50)',
  mutedForeground: 'oklch(0.5 0.04 50)',
  accent: 'oklch(0.96 0.02 50)',
  accentForeground: 'oklch(0.35 0.04 50)',
  destructive: 'oklch(0.577 0.245 27.325)',
  warning: 'oklch(0.754 0.149 83.317)',
  success: 'oklch(0.596 0.163 155.825)',
  border: 'oklch(0.9 0.02 50)',
  input: 'oklch(0.9 0.02 50)',
  ring: 'oklch(0.35 0.04 50)',
  chart1: 'oklch(0.35 0.04 50)', // Stone
  chart2: 'oklch(0.5 0.1 35)', // Rust
  chart3: 'oklch(0.6 0.1 70)', // Clay
  chart4: 'oklch(0.4 0.08 60)', // Earth
  chart5: 'oklch(0.7 0.05 50)', // Sand
};

export const stoneDark: ThemeColors = {
  background: 'oklch(0.11 0.03 50)', // Deep coffee/stone dark
  foreground: 'oklch(0.98 0.01 50)',
  card: 'oklch(0.14 0.03 50)', // Lighter brown-gray
  cardForeground: 'oklch(0.98 0.01 50)',
  popover: 'oklch(0.14 0.03 50)',
  popoverForeground: 'oklch(0.98 0.01 50)',
  primary: 'oklch(0.85 0.03 50)', // Pale Stone
  primaryForeground: 'oklch(0.11 0.03 50)',
  secondary: 'oklch(0.25 0.04 50)',
  secondaryForeground: 'oklch(0.98 0.01 50)',
  muted: 'oklch(0.22 0.04 50)',
  mutedForeground: 'oklch(0.65 0.05 50)',
  accent: 'oklch(0.25 0.04 50)',
  accentForeground: 'oklch(0.98 0.01 50)',
  destructive: 'oklch(0.6 0.2 25)',
  warning: 'oklch(0.75 0.15 80)',
  success: 'oklch(0.6 0.16 155)',
  border: 'oklch(0.25 0.03 50)',
  input: 'oklch(0.25 0.03 50)',
  ring: 'oklch(0.85 0.03 50)',
  chart1: 'oklch(0.85 0.03 50)',
  chart2: 'oklch(0.7 0.1 35)',
  chart3: 'oklch(0.8 0.1 70)',
  chart4: 'oklch(0.6 0.08 60)',
  chart5: 'oklch(0.5 0.05 50)',
};

// ====================
// CUSTOM COLOR THEMES
// ====================

/**
 * Blue Theme
 * Deep Corporate Blue / University Blue
 * Best for: Finance, Enterprise, Trust
 */
export const blueLight: ThemeColors = {
  background: 'oklch(1 0 0)',
  foreground: 'oklch(0.122 0.047 259.626)',
  card: 'oklch(1 0 0)',
  cardForeground: 'oklch(0.122 0.047 259.626)',
  popover: 'oklch(1 0 0)',
  popoverForeground: 'oklch(0.122 0.047 259.626)',
  primary: 'oklch(0.488 0.243 264.376)', // Strong Royal Blue
  primaryForeground: 'oklch(0.985 0 0)',
  secondary: 'oklch(0.965 0.015 264.376)', // Very light blue tint
  secondaryForeground: 'oklch(0.488 0.243 264.376)',
  muted: 'oklch(0.97 0.01 264.376)', // Cool gray
  mutedForeground: 'oklch(0.551 0.045 264.376)',
  accent: 'oklch(0.97 0.01 264.376)',
  accentForeground: 'oklch(0.488 0.243 264.376)',
  destructive: 'oklch(0.577 0.245 27.325)',
  warning: 'oklch(0.754 0.149 83.317)',
  success: 'oklch(0.596 0.163 155.825)',
  border: 'oklch(0.92 0.02 264.376)',
  input: 'oklch(0.92 0.02 264.376)',
  ring: 'oklch(0.488 0.243 264.376)',
  chart1: 'oklch(0.488 0.243 264.376)',
  chart2: 'oklch(0.6 0.118 184.704)',
  chart3: 'oklch(0.398 0.07 227.392)',
  chart4: 'oklch(0.828 0.189 84.429)',
  chart5: 'oklch(0.769 0.188 70.08)',
};

export const blueDark: ThemeColors = {
  background: 'oklch(0.1 0.03 264.376)', // Deep Navy (not black)
  foreground: 'oklch(0.985 0.01 264.376)',
  card: 'oklch(0.14 0.04 264.376)', // Slightly lighter navy
  cardForeground: 'oklch(0.985 0.01 264.376)',
  popover: 'oklch(0.14 0.04 264.376)',
  popoverForeground: 'oklch(0.985 0.01 264.376)',
  primary: 'oklch(0.6 0.2 264.376)', // Lighter, vibrant blue for dark mode
  primaryForeground: 'oklch(1 0 0)',
  secondary: 'oklch(0.25 0.05 264.376)',
  secondaryForeground: 'oklch(0.985 0 0)',
  muted: 'oklch(0.2 0.04 264.376)',
  mutedForeground: 'oklch(0.7 0.04 264.376)',
  accent: 'oklch(0.2 0.04 264.376)',
  accentForeground: 'oklch(0.985 0 0)',
  destructive: 'oklch(0.577 0.245 27.325)',
  warning: 'oklch(0.754 0.149 83.317)',
  success: 'oklch(0.596 0.163 155.825)',
  border: 'oklch(0.25 0.04 264.376)',
  input: 'oklch(0.25 0.04 264.376)',
  ring: 'oklch(0.5 0.2 264.376)',
  chart1: 'oklch(0.6 0.2 264.376)',
  chart2: 'oklch(0.6 0.118 184.704)',
  chart3: 'oklch(0.398 0.07 227.392)',
  chart4: 'oklch(0.828 0.189 84.429)',
  chart5: 'oklch(0.769 0.188 70.08)',
};

/**
 * Purple Theme
 * Vivid Violet / Digital Lavender
 * Best for: Creative, SaaS, AI Tools
 */
export const purpleLight: ThemeColors = {
  background: 'oklch(0.99 0.005 304)', // Very subtle lavender tint
  foreground: 'oklch(0.13 0.05 304)',
  card: 'oklch(1 0 0)',
  cardForeground: 'oklch(0.13 0.05 304)',
  popover: 'oklch(1 0 0)',
  popoverForeground: 'oklch(0.13 0.05 304)',
  primary: 'oklch(0.55 0.25 304)', // Vivid Purple
  primaryForeground: 'oklch(1 0 0)',
  secondary: 'oklch(0.96 0.02 304)',
  secondaryForeground: 'oklch(0.55 0.25 304)',
  muted: 'oklch(0.96 0.02 304)',
  mutedForeground: 'oklch(0.55 0.05 304)',
  accent: 'oklch(0.96 0.02 304)',
  accentForeground: 'oklch(0.55 0.25 304)',
  destructive: 'oklch(0.577 0.245 27.325)',
  warning: 'oklch(0.754 0.149 83.317)',
  success: 'oklch(0.596 0.163 155.825)',
  border: 'oklch(0.92 0.02 304)',
  input: 'oklch(0.92 0.02 304)',
  ring: 'oklch(0.55 0.25 304)',
  chart1: 'oklch(0.55 0.25 304)',
  chart2: 'oklch(0.627 0.265 303.9)',
  chart3: 'oklch(0.42 0.22 260)',
  chart4: 'oklch(0.696 0.17 162.48)',
  chart5: 'oklch(0.769 0.188 70.08)',
};

export const purpleDark: ThemeColors = {
  background: 'oklch(0.11 0.03 304)', // Deep Eggplant
  foreground: 'oklch(0.98 0.01 304)',
  card: 'oklch(0.15 0.04 304)',
  cardForeground: 'oklch(0.98 0.01 304)',
  popover: 'oklch(0.15 0.04 304)',
  popoverForeground: 'oklch(0.98 0.01 304)',
  primary: 'oklch(0.68 0.22 304)', // Bright Lavender
  primaryForeground: 'oklch(0.11 0.03 304)',
  secondary: 'oklch(0.25 0.06 304)',
  secondaryForeground: 'oklch(0.98 0.01 304)',
  muted: 'oklch(0.2 0.04 304)',
  mutedForeground: 'oklch(0.7 0.04 304)',
  accent: 'oklch(0.25 0.06 304)',
  accentForeground: 'oklch(0.98 0.01 304)',
  destructive: 'oklch(0.577 0.245 27.325)',
  warning: 'oklch(0.754 0.149 83.317)',
  success: 'oklch(0.596 0.163 155.825)',
  border: 'oklch(0.25 0.05 304)',
  input: 'oklch(0.25 0.05 304)',
  ring: 'oklch(0.6 0.2 304)',
  chart1: 'oklch(0.68 0.22 304)',
  chart2: 'oklch(0.627 0.265 303.9)',
  chart3: 'oklch(0.42 0.22 260)',
  chart4: 'oklch(0.696 0.17 162.48)',
  chart5: 'oklch(0.769 0.188 70.08)',
};

/**
 * Teal Theme
 * Tropical Ocean / Modern Green
 * Best for: Wellness, Healthcare, Environmental
 */
export const tealLight: ThemeColors = {
  background: 'oklch(0.99 0.005 175)', // Minty white
  foreground: 'oklch(0.13 0.04 175)',
  card: 'oklch(1 0 0)',
  cardForeground: 'oklch(0.13 0.04 175)',
  popover: 'oklch(1 0 0)',
  popoverForeground: 'oklch(0.13 0.04 175)',
  primary: 'oklch(0.53 0.18 175)', // Deep Teal
  primaryForeground: 'oklch(1 0 0)',
  secondary: 'oklch(0.95 0.02 175)',
  secondaryForeground: 'oklch(0.53 0.18 175)',
  muted: 'oklch(0.95 0.02 175)',
  mutedForeground: 'oklch(0.45 0.05 175)',
  accent: 'oklch(0.95 0.02 175)',
  accentForeground: 'oklch(0.53 0.18 175)',
  destructive: 'oklch(0.577 0.245 27.325)',
  warning: 'oklch(0.754 0.149 83.317)',
  success: 'oklch(0.596 0.163 155.825)',
  border: 'oklch(0.9 0.03 175)',
  input: 'oklch(0.9 0.03 175)',
  ring: 'oklch(0.53 0.18 175)',
  chart1: 'oklch(0.53 0.18 175)',
  chart2: 'oklch(0.6 0.118 184.704)',
  chart3: 'oklch(0.696 0.17 162.48)',
  chart4: 'oklch(0.769 0.188 70.08)',
  chart5: 'oklch(0.42 0.22 260)',
};

export const tealDark: ThemeColors = {
  background: 'oklch(0.1 0.03 175)', // Deep Rainforest Dark
  foreground: 'oklch(0.98 0.01 175)',
  card: 'oklch(0.13 0.04 175)',
  cardForeground: 'oklch(0.98 0.01 175)',
  popover: 'oklch(0.13 0.04 175)',
  popoverForeground: 'oklch(0.98 0.01 175)',
  primary: 'oklch(0.65 0.16 175)', // Seafoam
  primaryForeground: 'oklch(0.1 0.03 175)',
  secondary: 'oklch(0.2 0.05 175)',
  secondaryForeground: 'oklch(0.98 0.01 175)',
  muted: 'oklch(0.18 0.03 175)',
  mutedForeground: 'oklch(0.65 0.05 175)',
  accent: 'oklch(0.2 0.05 175)',
  accentForeground: 'oklch(0.98 0.01 175)',
  destructive: 'oklch(0.577 0.245 27.325)',
  warning: 'oklch(0.754 0.149 83.317)',
  success: 'oklch(0.596 0.163 155.825)',
  border: 'oklch(0.2 0.04 175)',
  input: 'oklch(0.2 0.04 175)',
  ring: 'oklch(0.53 0.18 175)',
  chart1: 'oklch(0.65 0.16 175)',
  chart2: 'oklch(0.6 0.118 184.704)',
  chart3: 'oklch(0.696 0.17 162.48)',
  chart4: 'oklch(0.769 0.188 70.08)',
  chart5: 'oklch(0.42 0.22 260)',
};

/**
 * Sakura Theme (New!)
 * Sophisticated "Coquette" & "Rose Gold" palette.
 * Light: Soft pinks, creamy whites, rose gold accents.
 * Dark: Deep plum, burgundy, and vibrant pink/gold highlights.
 * Best for: Lifestyle, Fashion, Beauty, Modern SaaS.
 */
export const sakuraLight: ThemeColors = {
  background: 'oklch(0.98 0.01 350)', // Soft Blush White
  foreground: 'oklch(0.25 0.04 350)', // Dark Berry Text
  card: 'oklch(1 0 0)', // Pure White
  cardForeground: 'oklch(0.25 0.04 350)',
  popover: 'oklch(1 0 0)',
  popoverForeground: 'oklch(0.25 0.04 350)',
  primary: 'oklch(0.65 0.18 350)', // Sophisticated Rose Pink (Sakura)
  primaryForeground: 'oklch(0.98 0 0)', // White text on pink
  secondary: 'oklch(0.96 0.02 350)', // Very Pale Pink (Button bg)
  secondaryForeground: 'oklch(0.65 0.18 350)',
  muted: 'oklch(0.96 0.02 350)',
  mutedForeground: 'oklch(0.55 0.08 350)', // Muted Mauve
  accent: 'oklch(0.95 0.03 350)',
  accentForeground: 'oklch(0.65 0.18 350)',
  destructive: 'oklch(0.577 0.245 27.325)',
  warning: 'oklch(0.8 0.12 60)', // Warm Gold/Peach for warning
  success: 'oklch(0.65 0.14 150)', // Soft Mint Green
  border: 'oklch(0.92 0.03 350)', // Pinkish border
  input: 'oklch(0.92 0.03 350)',
  ring: 'oklch(0.75 0.15 350)', // Soft pink ring
  chart1: 'oklch(0.65 0.18 350)', // Rose
  chart2: 'oklch(0.75 0.15 10)', // Coral
  chart3: 'oklch(0.7 0.12 300)', // Lavender
  chart4: 'oklch(0.8 0.1 60)', // Gold
  chart5: 'oklch(0.6 0.1 200)', // Teal
};

export const sakuraDark: ThemeColors = {
  background: 'oklch(0.15 0.04 340)', // Deep Plum/Burgundy Dark
  foreground: 'oklch(0.98 0.01 350)', // Pale Pink/White
  card: 'oklch(0.2 0.05 340)', // Lighter Plum
  cardForeground: 'oklch(0.98 0.01 350)',
  popover: 'oklch(0.2 0.05 340)',
  popoverForeground: 'oklch(0.98 0.01 350)',
  primary: 'oklch(0.75 0.16 350)', // Bright Sakura Pink
  primaryForeground: 'oklch(0.15 0.04 340)', // Dark text on bright pink
  secondary: 'oklch(0.3 0.08 340)', // Muted Burgundy
  secondaryForeground: 'oklch(0.98 0.01 350)',
  muted: 'oklch(0.25 0.06 340)',
  mutedForeground: 'oklch(0.7 0.08 350)', // Pinkish Gray
  accent: 'oklch(0.3 0.08 340)',
  accentForeground: 'oklch(0.98 0.01 350)',
  destructive: 'oklch(0.6 0.2 25)',
  warning: 'oklch(0.8 0.15 60)',
  success: 'oklch(0.65 0.14 150)',
  border: 'oklch(0.3 0.06 340)',
  input: 'oklch(0.3 0.06 340)',
  ring: 'oklch(0.75 0.16 350)',
  chart1: 'oklch(0.75 0.16 350)',
  chart2: 'oklch(0.8 0.15 10)',
  chart3: 'oklch(0.75 0.12 300)',
  chart4: 'oklch(0.85 0.1 60)',
  chart5: 'oklch(0.65 0.1 200)',
};

// ====================
// LEGACY THEME (Bootstrap-like) - UNTOUCHED
// ====================

export const legacyLight: ThemeColors = {
  background: 'oklch(1 0 0)',
  foreground: 'oklch(0.145 0.01 260)',
  card: 'oklch(1 0 0)',
  cardForeground: 'oklch(0.145 0.01 260)',
  popover: 'oklch(1 0 0)',
  popoverForeground: 'oklch(0.145 0.01 260)',
  primary: 'oklch(0.18 0.06 260)', // deep navy similar to #2C3E50
  primaryForeground: 'oklch(0.985 0 0)',
  secondary: 'oklch(0.35 0.02 240)', // muted gray-blue similar to #6c757d
  secondaryForeground: 'oklch(0.985 0 0)',
  muted: 'oklch(0.98 0 0)',
  mutedForeground: 'oklch(0.35 0.02 240)',
  accent: 'oklch(0.75 0.20 80)', // yellow (warning)
  accentForeground: 'oklch(0.145 0.01 260)',
  destructive: 'oklch(0.577 0.245 27.325)', // red
  destructiveForeground: 'oklch(0.985 0 0)',
  warning: 'oklch(0.75 0.20 80)',
  warningForeground: 'oklch(0.985 0 0)',
  success: 'oklch(0.595 0.165 155)',
  successForeground: 'oklch(0.985 0 0)',
  border: 'oklch(0.922 0 0)',
  input: 'oklch(1 0 0)',
  ring: 'oklch(0.18 0.06 260)',
  sidebarAccent: 'oklch(0.75 0.20 80)',
  sidebarAccentForeground: 'oklch(0.145 0 0)',
  chart1: 'oklch(0.18 0.06 260)',
  chart2: 'oklch(0.6 0.118 184.704)',
  chart3: 'oklch(0.595 0.165 155)',
  chart4: 'oklch(0.75 0.20 80)',
  chart5: 'oklch(0.35 0.02 240)',
  sidebar: 'oklch(0.18 0.06 260)',
  sidebarForeground: 'oklch(0.985 0 0)',
  sidebarPrimary: 'oklch(0.18 0.06 260)',
  sidebarPrimaryForeground: 'oklch(0.985 0 0)',
  sidebarBorder: 'oklch(0.94 0 0)',
  sidebarRing: 'oklch(0.12 0.03 260)',
};

export const legacyDark: ThemeColors = {
  background: 'oklch(0.145 0.01 260)',
  foreground: 'oklch(0.985 0 0)',
  card: 'oklch(0.13 0.02 260)',
  cardForeground: 'oklch(0.985 0 0)',
  popover: 'oklch(0.13 0.02 260)',
  popoverForeground: 'oklch(0.985 0 0)',
  primary: 'oklch(0.48 0.16 260)', // slightly lighter for contrast on dark
  primaryForeground: 'oklch(0.985 0 0)',
  secondary: 'oklch(0.35 0.02 240)',
  secondaryForeground: 'oklch(0.985 0 0)',
  muted: 'oklch(0.14 0.02 260)',
  mutedForeground: 'oklch(0.69 0.02 240)',
  accent: 'oklch(0.75 0.20 80)',
  accentForeground: 'oklch(0.12 0 0)',
  destructive: 'oklch(0.68 0.19 22.216)',
  destructiveForeground: 'oklch(0.985 0 0)',
  warning: 'oklch(0.75 0.20 80)',
  warningForeground: 'oklch(0.985 0 0)',
  success: 'oklch(0.595 0.165 155)',
  successForeground: 'oklch(0.985 0 0)',
  border: 'oklch(0.14 0.02 260)',
  input: 'oklch(0.13 0.02 260)',
  ring: 'oklch(0.12 0.03 260)',
  sidebarAccent: 'oklch(0.75 0.20 80)',
  sidebarAccentForeground: 'oklch(0.985 0 0)',
  chart1: 'oklch(0.18 0.06 260)',
  chart2: 'oklch(0.6 0.118 184.704)',
  chart3: 'oklch(0.595 0.165 155)',
  chart4: 'oklch(0.75 0.20 80)',
  chart5: 'oklch(0.35 0.02 240)',
  sidebar: 'oklch(0.11 0.02 260)',
  sidebarForeground: 'oklch(0.985 0 0)',
  sidebarPrimary: 'oklch(0.18 0.06 260)',
  sidebarPrimaryForeground: 'oklch(0.985 0 0)',
  sidebarBorder: 'oklch(0.09 0.01 260)',
  sidebarRing: 'oklch(0.12 0.03 260)',
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
  spaceGray: { light: spaceGrayLight, dark: spaceGrayDark },
  silver: { light: silverLight, dark: silverDark },
  starlight: { light: starlightLight, dark: starlightDark }, // Added
  zinc: { light: zincLight, dark: zincDark },
  stone: { light: stoneLight, dark: stoneDark },
  blue: { light: blueLight, dark: blueDark },
  purple: { light: purpleLight, dark: purpleDark },
  teal: { light: tealLight, dark: tealDark },
  sakura: { light: sakuraLight, dark: sakuraDark },
  legacy: { light: legacyLight, dark: legacyDark },
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
