# Theme Customization Guide

## Quick Start: Changing Theme Colors

### TL;DR - Change Button Colors

Edit `/src/styles.css` and find these lines in the `:root` section:

```css
:root {
  /* ... other variables ... */

  /* CUSTOMIZE THESE FOR YOUR THEME */
  --primary: oklch(0.205 0 0); /* View button - default: dark gray */
  --warning: oklch(0.754 0.149 83.317); /* Edit button - default: yellow */
  --success: oklch(0.596 0.163 155.825); /* New Application - default: green */
  --destructive: oklch(0.577 0.245 27.325); /* Delete button - default: red */
}
```

### Example: Blue Theme

Replace with:

```css
--primary: oklch(0.488 0.243 264.376); /* Blue */
--warning: oklch(0.754 0.149 50); /* Orange */
--success: oklch(0.596 0.163 155.825); /* Green */
--destructive: oklch(0.577 0.245 27.325); /* Red */
```

### Example: Purple Theme

Replace with:

```css
--primary: oklch(0.627 0.265 303.9); /* Purple */
--warning: oklch(0.754 0.149 83.317); /* Yellow */
--success: oklch(0.596 0.163 155.825); /* Green */
--destructive: oklch(0.577 0.245 27.325); /* Red */
```

### Example: Green Theme

Replace with:

```css
--primary: oklch(0.596 0.163 155.825); /* Green */
--warning: oklch(0.754 0.149 83.317); /* Yellow */
--success: oklch(0.488 0.243 264.376); /* Blue */
--destructive: oklch(0.577 0.245 27.325); /* Red */
```

### How OKLCH Works

`oklch(lightness chroma hue)`

- **Lightness**: 0-1 (0=black, 1=white)
- **Chroma**: 0-0.4 (0=gray, 0.4=vibrant)
- **Hue**: 0-360 degrees
  - 30° = Red
  - 83° = Yellow
  - 155° = Green
  - 200° = Cyan
  - 265° = Blue
  - 304° = Purple

### Test Your Changes

1. Save `/src/styles.css`
2. Refresh browser (Cmd+R or F5)
3. Check the customer list page

### Need More Help?

See the complete guide below.

## Overview

The application uses a CSS variable-based theming system that allows you to easily customize colors throughout the entire application. All UI components (buttons, cards, tables, etc.) use these theme colors automatically.

## Method 1: Simple Color Changes (Recommended)

Edit the color values in `/src/app/core/theme.config.ts`:

```typescript
export const lightTheme: ThemeColors = {
  // ... other colors ...

  primary: "oklch(0.488 0.243 264.376)", // Blue primary
  destructive: "oklch(0.577 0.245 27.325)", // Red
  warning: "oklch(0.754 0.149 83.317)", // Yellow
  success: "oklch(0.596 0.163 155.825)", // Green
};
```

Then update `/src/styles.css` with your new colors from `theme.config.ts`.

## Method 2: Direct CSS Variable Editing

Edit `/src/styles.css` directly and modify the color values:

```css
:root {
  /* Change these values to customize your theme */
  --primary: oklch(0.488 0.243 264.376); /* Blue */
  --destructive: oklch(0.577 0.245 27.325); /* Red */
  --warning: oklch(0.754 0.149 83.317); /* Yellow */
  --success: oklch(0.596 0.163 155.825); /* Green */
}
```

## Understanding OKLCH Color Format

The theme uses OKLCH color format for better perceptual uniformity:

**Format:** `oklch(lightness chroma hue)`

- **Lightness (L):** `0` (black) to `1` (white)
  - Example: `0.5` = medium brightness
- **Chroma (C):** `0` (gray) to `~0.4` (saturated)
  - Example: `0.2` = moderately saturated color
- **Hue (H):** `0-360` degrees (color wheel position)
  - Red: ~30°
  - Yellow/Orange: ~83°
  - Green: ~155°
  - Cyan: ~200°
  - Blue: ~265°
  - Magenta: ~330°

### Examples

```css
/* Bright blue */
oklch(0.6 0.25 265)

/* Dark red */
oklch(0.4 0.2 30)

/* Pastel green */
oklch(0.8 0.1 155)

/* Vibrant yellow */
oklch(0.75 0.15 83)
```

## Theme Colors Reference

### Semantic Colors (Used by buttons and components)

These are the main colors you'll want to customize:

| Color           | Usage                   | Default Light Theme |
| --------------- | ----------------------- | ------------------- |
| `--primary`     | Primary buttons (View)  | Dark gray/black     |
| `--destructive` | Delete, error actions   | Red                 |
| `--warning`     | Edit, caution actions   | Yellow/Orange       |
| `--success`     | Create, success actions | Green               |

### Button Color Mapping

In the customer list (and throughout the app):

- **View button:** Uses `--primary`
- **Edit button:** Uses `--warning`
- **Disable button:** Uses ghost variant (muted)
- **Delete button:** Uses `--destructive`
- **New Application button:** Uses `--success`

## Pre-made Theme Examples

The `theme.config.ts` file includes several pre-made themes you can use:

### 1. Default Theme (Gray/Black)

Current default - professional and neutral

### 2. Blue Theme

```typescript
export const blueTheme: Partial<ThemeColors> = {
  primary: "oklch(0.488 0.243 264.376)", // Blue
  warning: "oklch(0.754 0.149 50)", // Orange
};
```

### 3. Purple Theme

```typescript
export const purpleTheme: Partial<ThemeColors> = {
  primary: "oklch(0.627 0.265 303.9)", // Purple
};
```

### 4. Green Theme

```typescript
export const greenTheme: Partial<ThemeColors> = {
  primary: "oklch(0.596 0.163 155.825)", // Green
};
```

## Applying a Pre-made Theme

1. Open `/src/styles.css`
2. Find the `:root` section
3. Replace the color values with values from one of the pre-made themes in `theme.config.ts`

Example - applying the blue theme:

```css
:root {
  /* ... other variables ... */
  --primary: oklch(0.488 0.243 264.376); /* Blue from blueTheme */
  --primary-foreground: oklch(0.985 0 0);
  --warning: oklch(0.754 0.149 50); /* Orange from blueTheme */
  --warning-foreground: oklch(0.145 0 0);
  --success: oklch(0.596 0.163 155.825); /* Keep green */
  --success-foreground: oklch(1 0 0);
  --destructive: oklch(0.577 0.245 27.325); /* Keep red */
}
```

## Dark Mode

The application also supports dark mode. To customize dark mode colors:

```css
.dark {
  /* Dark mode color overrides */
  --primary: oklch(0.922 0 0);
  --destructive: oklch(0.704 0.191 22.216);
  /* ... etc ... */
}
```

Note: Usually you'll want darker/desaturated versions of your light theme colors in dark mode.

## Testing Your Theme

1. Start the development server: `bun run start`
2. Open the customer list page: `http://localhost:4200/customers`
3. You should see your new colors applied to all buttons and components
4. Test both light and dark modes (if your OS/browser supports it)

## Tips for Choosing Colors

1. **Maintain contrast:** Ensure text is readable against button backgrounds
2. **Keep consistency:** Use similar chroma/saturation levels across colors
3. **Test accessibility:** Use tools like WebAIM's contrast checker
4. **Brand alignment:** Match with your company's brand colors
5. **Semantic meaning:** Keep destructive=red, success=green for familiarity

## Color Tool Recommendations

- [OKLCH Color Picker](https://oklch.com/) - Visual OKLCH color picker
- [Coolors](https://coolors.co/) - Color palette generator
- [Adobe Color](https://color.adobe.com/) - Color wheel and harmony tools

## Troubleshooting

### Colors not updating?

- Clear browser cache or hard refresh (Cmd+Shift+R / Ctrl+Shift+F5)
- Check that CSS variable names match exactly (case-sensitive)
- Verify OKLCH format is correct

### Foreground text not readable?

- Adjust the corresponding `-foreground` color
- Increase contrast between background and foreground

### Need more help?

- Refer to the Tailwind CSS documentation for utility classes
- Check the ZardUI button component variants in `/src/app/shared/components/button/`

---

**Happy theming! 🎨**
