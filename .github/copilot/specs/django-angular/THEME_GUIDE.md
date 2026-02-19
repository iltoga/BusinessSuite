# Zard UI Theme Customization Guide

> Complete guide to customizing colors and theming in your Angular application using Zard UI and TailwindCSS v4.

## Table of Contents

- [Quick Start](#quick-start-changing-button-colors)
- [Understanding OKLCH](#understanding-oklch-color-format)
- [Complete Theme Variables](#complete-list-of-theme-variables)
- [Pre-made Base Colors](#pre-made-base-color-themes)
- [Adding Custom Colors](#adding-custom-theme-colors)
- [Dark Mode](#dark-mode-system)
- [Examples](#practical-examples)
- [Troubleshooting](#troubleshooting)

---

## Quick Start: Changing Button Colors

### TL;DR - Change Primary Action Colors

Edit `/frontend/src/styles.css` and find these lines in the `:root` section:

```css
:root {
  /* CUSTOMIZE THESE FOR YOUR THEME */
  --primary: oklch(0.205 0 0); /* View button - default: dark gray */
  --warning: oklch(0.754 0.149 83.317); /* Edit button - default: yellow */
  --success: oklch(0.596 0.163 155.825); /* New Application - default: green */
  --destructive: oklch(0.577 0.245 27.325); /* Delete button - default: red */
}
```

### Quick Theme Presets

#### Blue Theme (Professional)

```css
--primary: oklch(0.42 0.22 260); /* Distinct Blue */
--warning: oklch(0.754 0.149 50); /* Orange */
--success: oklch(0.596 0.163 155.825); /* Green */
--destructive: oklch(0.577 0.245 27.325); /* Red */
```

#### Purple Theme (Creative)

```css
--primary: oklch(0.58 0.28 292); /* Magenta-Purple */
--warning: oklch(0.754 0.149 83.317); /* Yellow */
--success: oklch(0.596 0.163 155.825); /* Green */
--destructive: oklch(0.577 0.245 27.325); /* Red */
```

#### Teal Theme (Modern)

```css
--primary: oklch(0.58 0.2 190); /* Teal-Cyan */
--warning: oklch(0.754 0.149 83.317); /* Yellow */
--success: oklch(0.696 0.17 162.48); /* Light Green */
--destructive: oklch(0.577 0.245 27.325); /* Red */
```

#### Legacy Theme (Bootstrap-like)

A precise OKLCH conversion of the classic Bootstrap palette used by the legacy Django templates. Use this if you want the Angular frontend to visually match the legacy CMS UI.

```css
/* Legacy - Light */
--background: oklch(1 0 0);
--foreground: oklch(0.145 0.01 260);
--primary: oklch(0.18 0.06 260); /* deep navy */
--primary-foreground: oklch(0.985 0 0);
--secondary: oklch(0.35 0.02 240); /* muted gray-blue */
--muted: oklch(0.98 0 0);
--accent: oklch(0.75 0.2 80); /* yellow */
--destructive: oklch(0.577 0.245 27.325);
--warning: oklch(0.75 0.2 80);
--success: oklch(0.595 0.165 155);
--border: oklch(0.922 0 0);

/* Legacy - Dark */
--background: oklch(0.145 0.01 260);
--card: oklch(0.13 0.02 260);
--primary: oklch(0.48 0.16 260);
--muted: oklch(0.14 0.02 260);
--accent: oklch(0.75 0.2 80);
```

#### Customer List / Action Button Mapping

The following mapping is used across the app (Customer List, Application Detail, Invoices):

> Implementation notes:
>
> - The **Disable** action uses the `destructive` button variant when it represents a disabling action (white text on red background) — this improves parity with the legacy UI.
> - Active/selected sidebar items use `--sidebar-accent` and `--sidebar-accent-foreground` so you can replicate the legacy orange highlight on the active menu item.

| Action          | Button Variant | Color          | CSS Variable    |
| --------------- | -------------- | -------------- | --------------- |
| View            | `default`      | Primary (navy) | `--primary`     |
| Edit            | `warning`      | Yellow/Orange  | `--warning`     |
| Disable/Enable  | `ghost`        | Muted gray     | N/A             |
| Delete          | `destructive`  | Red            | `--destructive` |
| New Application | `success`      | Green          | `--success`     |

**Canonical note:** This `THEME_GUIDE.md` is the single source of truth for theming and styling in the Angular frontend. All docs, specs, and the `copilot` instructions must reference this file when making design and theme decisions.

### Test Your Changes

1. Save `/frontend/src/styles.css`
2. Hard refresh browser: **Cmd+Shift+R** (Mac) or **Ctrl+Shift+F5** (Windows/Linux)
3. Navigate to the customer list to see button colors change

---

## Application Integration (Angular) 🔧

This section covers how the theme system ties into the Angular frontend: configuration, the `ThemeService`, registering custom themes, persistence, and example components.

### Quick Start: Change Theme in Configuration

Edit the app config to set a global theme:

**File:** `/frontend/src/app/core/config/app.config.ts`

```typescript
export const APP_CONFIG = {
  theme: "blue", // <-- Change this to any theme name
} as const;
```

**Available themes:** `neutral`, `slate`, `gray`, `zinc`, `stone`, `blue`, `purple`, `teal` (you can add more — see Creating Custom Themes).

After changing the theme, restart the dev server:

```bash
cd frontend
bun run dev
```

---

### Using the `ThemeService`

Inject the service to switch themes programmatically, toggle dark mode, and read current state:

#### Basic Theme Switching

```typescript
import { Component, inject } from "@angular/core";
import { ThemeService } from "@/core/services/theme.service";

@Component({
  selector: "app-settings",
  template: `
    <select (change)="onThemeChange($event)">
      <option value="neutral">Neutral</option>
      <option value="blue">Blue</option>
      <option value="purple">Purple</option>
      <option value="teal">Teal</option>
    </select>
  `,
})
export class SettingsComponent {
  private themeService = inject(ThemeService);

  onThemeChange(event: Event) {
    const theme = (event.target as HTMLSelectElement).value;
    this.themeService.setTheme(theme as ThemeName);
  }
}
```

#### Dark Mode Toggle

```typescript
import { Component, inject } from "@angular/core";
import { ThemeService } from "@/core/services/theme.service";

@Component({
  selector: "app-header",
  template: `
    <button (click)="toggleDarkMode()">
      {{ isDarkMode() ? "🌙" : "☀️" }} Toggle Dark Mode
    </button>
  `,
})
export class HeaderComponent {
  private themeService = inject(ThemeService);

  isDarkMode = this.themeService.isDarkMode;

  toggleDarkMode() {
    this.themeService.toggleDarkMode();
  }
}
```

#### Get Current Theme

```typescript
import { Component, inject, effect } from "@angular/core";
import { ThemeService } from "@/core/services/theme.service";

@Component({
  selector: "app-example",
  template: `
    <div>
      Current theme: {{ currentTheme() }}
      <br />
      Dark mode: {{ isDarkMode() ? "Enabled" : "Disabled" }}
    </div>
  `,
})
export class ExampleComponent {
  private themeService = inject(ThemeService);

  currentTheme = this.themeService.currentTheme;
  isDarkMode = this.themeService.isDarkMode;

  constructor() {
    // React to theme changes
    effect(() => {
      console.log("Theme changed to:", this.currentTheme());
    });
  }
}
```

---

### Creating Custom Themes

1. **Define** your theme colors in `/frontend/src/app/core/theme.config.ts` (example: `orangeLight` / `orangeDark`).

```typescript
export const orangeLight: ThemeColors = {
  ...neutralLight,
  primary: "oklch(0.68 0.18 45)",
  chart1: "oklch(0.68 0.18 45)",
  /* ... */
};
```

1. **Register** the theme in the `THEMES` registry:

```typescript
export const THEMES = {
  neutral: { light: neutralLight, dark: neutralDark },
  slate: { light: slateLight, dark: slateDark },
  // ... existing themes ...
  orange: { light: orangeLight, dark: orangeDark },
} as const;
```

1. **Update types** (`ThemeName` union) to include your theme name.

2. **Use** the theme by setting `APP_CONFIG.theme` or via `ThemeService.setTheme()`.

---

### Theme Service API & Persistence

Key `ThemeService` methods and signals:

```typescript
class ThemeService {
  currentTheme: Signal<ThemeName>;
  isDarkMode: Signal<boolean>;
  setTheme(themeName: ThemeName): void;
  toggleDarkMode(): void;
  setDarkMode(isDark: boolean): void;
  initializeTheme(defaultTheme: ThemeName): void;
  getAvailableThemes(): ThemeName[];
  getThemeColors(themeName: ThemeName, mode: "light" | "dark"): ThemeColors;
}
```

The service persists choices to `localStorage`:

- `theme` (selected theme)
- `darkMode` (dark mode state)

---

### Advanced Usage

- **Theme Switcher Component** (example included in `theme.config.ts` docs) — use `ThemeService.getAvailableThemes()` and signals for reactive UI.
- **System Preference Detection** — the service detects system dark mode on first load and listens for preference changes; it only overrides system preferences when the user sets a preference explicitly.

---

## Understanding OKLCH Color Format

Zard UI uses **OKLCH** (Oklch Color Space) for better perceptual uniformity and color accuracy compared to HSL or RGB.

### Format Syntax

```css
oklch(lightness chroma hue)
```

### Parameters Explained

| Parameter     | Range         | Description                    | Examples                                                     |
| ------------- | ------------- | ------------------------------ | ------------------------------------------------------------ |
| **Lightness** | `0` to `1`    | Perceived brightness           | `0` = black, `0.5` = medium, `1` = white                     |
| **Chroma**    | `0` to `~0.4` | Color saturation/vibrancy      | `0` = grayscale, `0.2` = saturated, `0.4` = highly saturated |
| **Hue**       | `0` to `360`  | Color wheel position (degrees) | See table below                                              |

### Hue Color Wheel Reference

| Hue Range  | Color              | Example Values                                |
| ---------- | ------------------ | --------------------------------------------- |
| `0-30°`    | **Red**            | `oklch(0.577 0.245 27.325)` - Destructive red |
| `40-90°`   | **Orange/Yellow**  | `oklch(0.754 0.149 83.317)` - Warning yellow  |
| `120-180°` | **Green**          | `oklch(0.596 0.163 155.825)` - Success green  |
| `180-210°` | **Cyan/Teal**      | `oklch(0.6 0.118 184.704)` - Teal accent      |
| `240-280°` | **Blue**           | `oklch(0.488 0.243 264.376)` - Primary blue   |
| `290-330°` | **Purple/Magenta** | `oklch(0.627 0.265 303.9)` - Purple accent    |

### Practical Color Examples

```css
/* Bright, vibrant blue */
--vibrant-blue: oklch(0.6 0.25 265);

/* Dark, muted red */
--dark-red: oklch(0.4 0.2 30);

/* Pastel green */
--pastel-green: oklch(0.8 0.1 155);

/* Warm orange */
--warm-orange: oklch(0.7 0.18 50);

/* Cool gray (low chroma = desaturated) */
--cool-gray: oklch(0.5 0.02 265);
```

### Why OKLCH?

✅ **Perceptually uniform** - Equal numeric changes = equal visual changes
✅ **Predictable lightness** - `0.5` looks medium-bright regardless of hue
✅ **Wider color gamut** - Access to more vivid colors than sRGB
✅ **Better for dark mode** - Easier to maintain contrast ratios

---

## Complete List of Theme Variables

Zard UI implements a comprehensive theming system with **background/foreground** convention. Each color has a corresponding `-foreground` variant for text color.

### Variable Categories

#### 🎨 Core Theme Colors

| Variable                 | Purpose                 | Components Using It           |
| ------------------------ | ----------------------- | ----------------------------- |
| `--background`           | Main app background     | Body, pages                   |
| `--foreground`           | Main text color         | All text content              |
| `--primary`              | Primary actions         | **View buttons**, main CTAs   |
| `--primary-foreground`   | Text on primary buttons | Button labels                 |
| `--secondary`            | Secondary actions       | Alternative buttons           |
| `--secondary-foreground` | Text on secondary       | Button labels                 |
| `--muted`                | Subtle backgrounds      | Disabled states, subtle areas |
| `--muted-foreground`     | Muted text              | Placeholders, hints           |
| `--accent`               | Accent highlights       | Hover states, highlights      |
| `--accent-foreground`    | Text on accents         | Highlighted text              |

#### ⚠️ Action Colors (Key for Your App)

| Variable                   | Purpose             | Where Used in App                |
| -------------------------- | ------------------- | -------------------------------- |
| `--destructive`            | Destructive actions | **Delete buttons**, error states |
| `--destructive-foreground` | Text on destructive | Delete button labels             |
| `--warning`                | Warning/caution     | **Edit buttons**, warnings       |
| `--warning-foreground`     | Text on warnings    | Edit button labels               |
| `--success`                | Success/create      | **New Application button**       |
| `--success-foreground`     | Text on success     | Create button labels             |

> **Note**: `warning` and `success` are **custom colors** added to the base Zard UI theme (see [Adding Custom Colors](#adding-custom-theme-colors)).

#### 🃏 Surface Colors

| Variable                             | Purpose                       |
| ------------------------------------ | ----------------------------- |
| `--card` / `--card-foreground`       | Card backgrounds              |
| `--popover` / `--popover-foreground` | Popover, dropdown backgrounds |

#### 🎯 Interactive Elements

| Variable   | Purpose                      |
| ---------- | ---------------------------- |
| `--input`  | Input field borders          |
| `--border` | Border colors throughout app |
| `--ring`   | Focus ring color             |

#### 📊 Chart Colors (Optional)

| Variable                        | Purpose                   |
| ------------------------------- | ------------------------- |
| `--chart-1` through `--chart-5` | Data visualization colors |

#### 📂 Sidebar Colors (If Using Sidebar)

| Variable               | Purpose             |
| ---------------------- | ------------------- |
| `--sidebar`            | Sidebar background  |
| `--sidebar-foreground` | Sidebar text        |
| `--sidebar-primary`    | Sidebar active item |
| `--sidebar-accent`     | Sidebar hover state |
| `--sidebar-border`     | Sidebar borders     |
| `--sidebar-ring`       | Sidebar focus ring  |

### Complete Theme Template

Here's the complete structure from official Zard UI docs (Neutral theme):

```css
:root {
  /* Border radius for rounded corners */
  --radius: 0.625rem;

  /* Core colors */
  --background: oklch(1 0 0);
  --foreground: oklch(0.145 0 0);

  /* Surface colors */
  --card: oklch(1 0 0);
  --card-foreground: oklch(0.145 0 0);
  --popover: oklch(1 0 0);
  --popover-foreground: oklch(0.145 0 0);

  /* Action colors */
  --primary: oklch(0.205 0 0);
  --primary-foreground: oklch(0.985 0 0);
  --secondary: oklch(0.97 0 0);
  --secondary-foreground: oklch(0.205 0 0);
  --muted: oklch(0.97 0 0);
  --muted-foreground: oklch(0.556 0 0);
  --accent: oklch(0.97 0 0);
  --accent-foreground: oklch(0.205 0 0);
  --destructive: oklch(0.577 0.245 27.325);

  /* Interactive elements */
  --border: oklch(0.922 0 0);
  --input: oklch(0.922 0 0);
  --ring: oklch(0.708 0 0);

  /* Chart colors */
  --chart-1: oklch(0.646 0.222 41.116);
  --chart-2: oklch(0.6 0.118 184.704);
  --chart-3: oklch(0.398 0.07 227.392);
  --chart-4: oklch(0.828 0.189 84.429);
  --chart-5: oklch(0.769 0.188 70.08);

  /* Sidebar (if using) */
  --sidebar: oklch(0.985 0 0);
  --sidebar-foreground: oklch(0.145 0 0);
  --sidebar-primary: oklch(0.205 0 0);
  --sidebar-primary-foreground: oklch(0.985 0 0);
  --sidebar-accent: oklch(0.97 0 0);
  --sidebar-accent-foreground: oklch(0.205 0 0);
  --sidebar-border: oklch(0.922 0 0);
  --sidebar-ring: oklch(0.708 0 0);
}

/* Dark mode variants */
.dark {
  --background: oklch(0.145 0 0);
  --foreground: oklch(0.985 0 0);
  --card: oklch(0.205 0 0);
  --card-foreground: oklch(0.985 0 0);
  --popover: oklch(0.205 0 0);
  --popover-foreground: oklch(0.985 0 0);
  --primary: oklch(0.922 0 0);
  --primary-foreground: oklch(0.205 0 0);
  --secondary: oklch(0.269 0 0);
  --secondary-foreground: oklch(0.985 0 0);
  --muted: oklch(0.269 0 0);
  --muted-foreground: oklch(0.708 0 0);
  --accent: oklch(0.269 0 0);
  --accent-foreground: oklch(0.985 0 0);
  --destructive: oklch(0.704 0.191 22.216);
  --border: oklch(1 0 0 / 10%);
  --input: oklch(1 0 0 / 15%);
  --ring: oklch(0.556 0 0);
  --chart-1: oklch(0.488 0.243 264.376);
  --chart-2: oklch(0.696 0.17 162.48);
  --chart-3: oklch(0.769 0.188 70.08);
  --chart-4: oklch(0.627 0.265 303.9);
  --chart-5: oklch(0.645 0.246 16.439);
  --sidebar: oklch(0.205 0 0);
  --sidebar-foreground: oklch(0.985 0 0);
  --sidebar-primary: oklch(0.488 0.243 264.376);
  --sidebar-primary-foreground: oklch(0.985 0 0);
  --sidebar-accent: oklch(0.269 0 0);
  --sidebar-accent-foreground: oklch(0.985 0 0);
  --sidebar-border: oklch(1 0 0 / 10%);
  --sidebar-ring: oklch(0.556 0 0);
}
```

---

## Pre-made Base Color Themes

Zard UI provides several professionally-designed base color palettes. Each uses subtle hue/chroma variations for a cohesive look.

### 1. Neutral (Default)

**Pure grayscale** - No hue shift, completely neutral

```css
:root {
  --primary: oklch(0.205 0 0);
  --foreground: oklch(0.145 0 0);
  --muted-foreground: oklch(0.556 0 0);
}
```

✅ **Best for:** Professional apps, data-heavy interfaces, when color carries specific meaning
**Character:** Clean, unbiased, business-focused

---

### 2. Slate

**Cool blue-gray** - Slight blue undertone (hue ~255-265°)

```css
:root {
  --primary: oklch(0.208 0.042 265.755);
  --foreground: oklch(0.129 0.042 264.695);
  --muted-foreground: oklch(0.554 0.046 257.417);
}

.dark {
  --primary: oklch(0.929 0.013 255.508);
  --chart-1: oklch(0.488 0.243 264.376); /* Blue charts */
}
```

✅ **Best for:** Tech products, developer tools, modern SaaS
**Character:** Cool, technical, digital-first

---

### 3. Gray

**Neutral gray** - Balanced with minimal saturation (hue ~260°)

```css
:root {
  --primary: oklch(0.21 0.034 264.665);
  --foreground: oklch(0.13 0.028 261.692);
  --muted-foreground: oklch(0.551 0.027 264.364);
}
```

✅ **Best for:** Enterprise apps, dashboards, CRM systems
**Character:** Balanced, professional, versatile

---

### 4. Zinc

**Slightly cool gray** - Subtle blue-gray (hue ~285°)

```css
:root {
  --primary: oklch(0.21 0.006 285.885);
  --foreground: oklch(0.141 0.005 285.823);
  --muted-foreground: oklch(0.552 0.016 285.938);
}
```

✅ **Best for:** Modern web apps, content platforms
**Character:** Contemporary, refined, subtle

---

### 5. Stone

**Warm gray** - Slight warm undertone (hue ~50°)

```css
:root {
  --primary: oklch(0.216 0.006 56.043);
  --foreground: oklch(0.147 0.004 49.25);
  --muted-foreground: oklch(0.553 0.013 58.071);
}
```

✅ **Best for:** E-commerce, lifestyle apps, hospitality
**Character:** Warm, inviting, organic

---

### How to Apply a Base Theme

**Option 1:** Copy the entire theme from [Zard UI Theming Docs](https://zardui.com/docs/theming)

**Option 2:** Mix and match - use a base theme but customize action colors:

```css
/* Start with Slate base */
:root {
  --primary: oklch(0.208 0.042 265.755); /* From Slate */
  --foreground: oklch(0.129 0.042 264.695); /* From Slate */

  /* Add your custom action colors */
  --warning: oklch(0.754 0.149 83.317); /* Keep yellow warning */
  --success: oklch(0.596 0.163 155.825); /* Keep green success */
  --destructive: oklch(0.577 0.245 27.325); /* Keep red destructive */
}
```

---

## Adding Custom Theme Colors

### Why Add Custom Colors?

The app uses `--warning` and `--success` which are **not** part of the base Zard UI theme. You need to add these custom semantic colors for your business logic.

### Method: Using `@theme` Directive

TailwindCSS v4 uses the `@theme` directive to extend the color system.

#### Step 1: Add CSS Variables

In `/frontend/src/styles.css`, add your custom colors to `:root` and `.dark`:

```css
:root {
  /* ... existing variables ... */

  /* Custom action colors for your app */
  --warning: oklch(0.754 0.149 83.317);
  --warning-foreground: oklch(0.145 0 0);
  --success: oklch(0.596 0.163 155.825);
  --success-foreground: oklch(1 0 0);
}

.dark {
  /* ... existing dark variables ... */

  /* Dark mode versions */
  --warning: oklch(0.84 0.16 84);
  --warning-foreground: oklch(0.28 0.07 46);
  --success: oklch(0.696 0.17 162.48);
  --success-foreground: oklch(0.99 0.02 95);
}
```

#### Step 2: Register with Tailwind

Add to the `@theme inline` block in `/frontend/src/styles.css`:

```css
@theme inline {
  --color-background: var(--background);
  --color-foreground: var(--foreground);
  /* ... other existing mappings ... */

  /* Add your custom colors */
  --color-warning: var(--warning);
  --color-warning-foreground: var(--warning-foreground);
  --color-success: var(--success);
  --color-success-foreground: var(--success-foreground);
}
```

#### Step 3: Use in Components

Now you can use your custom colors with Tailwind utilities:

```html
<!-- In templates -->
<button class="bg-warning text-warning-foreground">Edit</button>
<button class="bg-success text-success-foreground">Create</button>

<!-- Or with Zard UI button variants -->
<button z-button zVariant="warning">Edit Customer</button>
<button z-button zVariant="success">New Application</button>
```

### Alternative Color Formats

While OKLCH is recommended, you can also use other formats:

```css
@theme {
  /* OKLCH (recommended) */
  --color-primary: oklch(0.64 0.22 260);

  /* RGB */
  --color-secondary: rgb(59 130 246);

  /* HSL */
  --color-accent: hsl(210 100% 50%);

  /* HEX */
  --color-muted: #6b7280;
}
```

**Note:** OKLCH provides better perceptual uniformity and wider color gamut. See [TailwindCSS Colors Docs](https://tailwindcss.com/docs/colors) for more details.

---

## Dark Mode System

Zard UI includes a robust dark mode system with automatic persistence and smooth transitions.

### How It Works

1. **CSS Variables:** Both `:root` (light) and `.dark` (dark) define color values
2. **Class Toggle:** The `.dark` class on `<html>` activates dark theme
3. **Service Management:** `ZardDarkMode` service handles state and persistence

### Dark Mode Service

The service is already configured in your app. It provides:

- ✅ **Auto-detection** of system preference
- ✅ **LocalStorage persistence** across sessions
- ✅ **Reactive state** using Angular signals
- ✅ **Three modes:** light, dark, system

### Installing Dark Mode Toggle

If not already installed, add the dark mode component:

```bash
cd frontend
npx @ngzard/ui add dark-mode
```

This installs:

- `ZardDarkMode` service
- Updates `index.html` to prevent flash of wrong theme
- Example header component with toggle button

### Using in Your Components

```typescript
// header.component.ts
import { Component, inject } from "@angular/core";
import { ZardDarkMode } from "@zard/services/dark-mode";

@Component({
  selector: "app-header",
  template: `
    <button z-button zVariant="ghost" (click)="toggleTheme()">
      <z-icon zType="dark-mode" />
      <span class="sr-only">Toggle theme</span>
    </button>
  `,
})
export class HeaderComponent {
  private darkMode = inject(ZardDarkMode);

  toggleTheme() {
    this.darkMode.toggleTheme();
  }

  // Or access current theme
  currentTheme = this.darkMode.currentTheme; // Signal: 'light' | 'dark' | 'system'
}
```

### Dark Mode Color Guidelines

When customizing dark mode colors:

1. **Reduce lightness** - Dark mode colors should be dimmer
2. **Lower chroma** - Slightly desaturate colors for comfort
3. **Maintain contrast** - Ensure text remains readable (WCAG AA: 4.5:1 minimum)
4. **Use opacity** - Borders/inputs often use semi-transparent whites

**Example:**

```css
:root {
  --primary: oklch(0.205 0 0); /* Very dark */
  --border: oklch(0.922 0 0); /* Light gray */
}

.dark {
  --primary: oklch(0.922 0 0); /* Very light (inverted) */
  --border: oklch(1 0 0 / 10%); /* 10% white overlay */
}
```

---

## Practical Examples

### Example 1: Corporate Brand Theme

**Scenario:** Your company brand uses **blue (#2563eb)** as primary color.

#### Step 1: Convert HEX to OKLCH

Use [OKLCH Color Picker](https://oklch.com/) to convert `#2563eb` → `oklch(0.553 0.232 264.052)`

#### Step 2: Apply to Theme

```css
:root {
  /* Corporate blue */
  --primary: oklch(0.553 0.232 264.052);
  --primary-foreground: oklch(1 0 0); /* White text */

  /* Keep action colors semantic */
  --destructive: oklch(0.577 0.245 27.325); /* Red */
  --warning: oklch(0.754 0.149 50); /* Orange */
  --success: oklch(0.596 0.163 155.825); /* Green */
}

.dark {
  /* Lighter blue for dark mode */
  --primary: oklch(0.7 0.2 264);
  --primary-foreground: oklch(0.145 0 0); /* Dark text */
}
```

#### Step 3: Test Buttons

```html
<!-- View button will now be corporate blue -->
<button z-button variant="default">View Customer</button>

<!-- Action buttons keep semantic colors -->
<button z-button variant="warning">Edit</button>
<button z-button variant="destructive">Delete</button>
```

---

### Example 2: Green "Approve" + Red "Reject" Workflow

**Scenario:** Invoice approval interface needs clear approve/reject actions.

```typescript
// invoice-approval.component.ts
@Component({
  template: `
    <div class="flex gap-2">
      <button z-button zVariant="success" (click)="approve()">
        <z-icon name="check" />
        Approve Invoice
      </button>

      <button z-button zVariant="destructive" (click)="reject()">
        <z-icon name="x" />
        Reject Invoice
      </button>
    </div>
  `,
})
export class InvoiceApprovalComponent {
  approve() {
    /* ... */
  }
  reject() {
    /* ... */
  }
}
```

Ensure CSS defines both:

```css
:root {
  --success: oklch(0.596 0.163 155.825); /* Green */
  --success-foreground: oklch(1 0 0);
  --destructive: oklch(0.577 0.245 27.325); /* Red */
  --destructive-foreground: oklch(1 0 0);
}
```

---

### Example 3: Colorful Dashboard with Chart Harmony

**Scenario:** Dashboard with data visualizations needs cohesive color palette.

#### Choose Harmonious Chart Colors

```css
:root {
  /* Primary brand color */
  --primary: oklch(0.488 0.243 264.376); /* Blue */

  /* Harmonious chart colors (analogous + complementary) */
  --chart-1: oklch(0.488 0.243 264.376); /* Blue (primary) */
  --chart-2: oklch(0.696 0.17 162.48); /* Green (complementary) */
  --chart-3: oklch(0.627 0.265 303.9); /* Purple (analogous) */
  --chart-4: oklch(0.754 0.149 50); /* Orange (triadic) */
  --chart-5: oklch(0.6 0.118 184.704); /* Teal (accent) */
}
```

#### Use in Chart Components

```typescript
// chart.component.ts
chartColors = [
  "rgb(var(--chart-1))",
  "rgb(var(--chart-2))",
  "rgb(var(--chart-3))",
  "rgb(var(--chart-4))",
  "rgb(var(--chart-5))",
];
```

---

### Example 4: Accessibility-First Theme

**Scenario:** Ensure WCAG AA contrast ratios (4.5:1 for normal text).

#### Test Contrast

Use [WebAIM Contrast Checker](https://webaim.org/resources/contrastchecker/):

- Background: `oklch(0.205 0 0)` (dark gray)
- Foreground: `oklch(0.985 0 0)` (near white)
- **Contrast ratio: 18.2:1** ✅ (exceeds AAA)

#### Adjust Colors if Needed

```css
:root {
  /* If contrast is low, increase lightness difference */
  --primary: oklch(0.3 0.1 264); /* Darker background */
  --primary-foreground: oklch(1 0 0); /* Pure white text */

  /* Or use APCA (Advanced Perceptual Contrast Algorithm) */
  /* Aim for Lc 60+ for body text, Lc 75+ for small text */
}
```

---

### Example 5: Seasonal Theme Switcher

**Scenario:** Change theme colors seasonally (winter/summer).

#### Create Theme Variants

```typescript
// themes.config.ts
export const winterTheme = {
  primary: "oklch(0.488 0.243 264.376)", // Cool blue
  accent: "oklch(0.6 0.118 184.704)", // Icy teal
  chart1: "oklch(0.7 0.2 240)", // Winter blue
};

export const summerTheme = {
  primary: "oklch(0.754 0.149 50)", // Warm orange
  accent: "oklch(0.769 0.188 70.08)", // Sunny yellow
  chart1: "oklch(0.8 0.15 60)", // Summer gold
};
```

#### Apply Dynamically

```typescript
// theme.service.ts
export class ThemeService {
  applySeason(season: "winter" | "summer") {
    const theme = season === "winter" ? winterTheme : summerTheme;
    const root = document.documentElement;

    root.style.setProperty("--primary", theme.primary);
    root.style.setProperty("--accent", theme.accent);
    root.style.setProperty("--chart-1", theme.chart1);
  }
}
```

---

## Troubleshooting

### ❌ Colors Not Updating After CSS Change

**Symptoms:** Changed CSS variables but browser still shows old colors.

**Solutions:**

1. **Hard refresh:** Cmd+Shift+R (Mac) or Ctrl+Shift+F5 (Windows)
2. **Clear cache:** Browser DevTools → Network → Disable cache
3. **Check CSS file loaded:** DevTools → Sources → verify `/styles.css` is latest
4. **Verify no inline styles:** Search codebase for `style="--primary:"`

---

### ❌ Dark Mode Not Working

**Symptoms:** `.dark` class on `<html>` but colors don't change.

**Solutions:**

1. **Check `.dark` specificity:**

   ```css
   /* ❌ Wrong: .dark will be overridden */
   :root {
     --primary: blue;
   }

   /* ✅ Correct: .dark has higher specificity */
   :root {
     --primary: oklch(0.2 0 0);
   }
   .dark {
     --primary: oklch(0.9 0 0);
   }
   ```

2. **Verify `@custom-variant` directive:**

   ```css
   @custom-variant dark (&:is(.dark *));
   ```

3. **Check ZardDarkMode service initialization** in `app.config.ts`:

   ```typescript
   providers: [
     provideZard(), // Includes dark mode
   ];
   ```

---

### ❌ Foreground Text Not Readable

**Symptoms:** Text is hard to read against button backgrounds.

**Solutions:**

1. **Increase lightness contrast:**

   ```css
   /* ❌ Low contrast: 0.5 vs 0.6 */
   --primary: oklch(0.5 0.2 264);
   --primary-foreground: oklch(0.6 0 0);

   /* ✅ High contrast: 0.3 vs 1.0 */
   --primary: oklch(0.3 0.2 264);
   --primary-foreground: oklch(1 0 0);
   ```

2. **Use contrast checker:** Test at [WebAIM](https://webaim.org/resources/contrastchecker/)

3. **Desaturate backgrounds:** Lower chroma for better text readability:

   ```css
   --primary: oklch(0.4 0.05 264); /* Low chroma = less vibrant */
   ```

---

### ❌ Custom Colors Not Recognized by Tailwind

**Symptoms:** `class="bg-warning"` doesn't apply color.

**Solutions:**

1. **Register in `@theme inline` block:**

   ```css
   @theme inline {
     --color-warning: var(--warning);
   }
   ```

2. **Restart dev server:**

   ```bash
   cd frontend
   bun run dev
   ```

3. **Check TailwindCSS v4 syntax:** Ensure using `@theme`, not old `theme.extend` in `tailwind.config.js`.

---

### ❌ OKLCH Colors Look Different Than Expected

**Symptoms:** `oklch(0.5 0.2 264)` doesn't look "medium blue".

**Explanation:**

- OKLCH is **device-dependent** and requires **wide-gamut displays** for full range
- On sRGB displays, colors are automatically clamped to displayable range
- Perceived lightness varies by hue (blue looks darker than yellow at same L value)

**Solutions:**

1. **Test on target devices:** View on actual hardware your users have
2. **Use OKLCH Color Picker:** [oklch.com](https://oklch.com/) shows clamping warnings
3. **Stick to safe chroma values:** Keep C under 0.25 for sRGB compatibility

---

## Tips for Choosing Colors

### ✅ Do's

1. **Maintain contrast ratios:**
   - WCAG AA: 4.5:1 for normal text
   - WCAG AAA: 7:1 for normal text
   - Large text (18pt+): 3:1 minimum

2. **Keep consistent chroma:**
   - Use similar saturation levels across theme
   - Example: All action colors at C=0.15-0.25

3. **Test in both modes:**
   - Always define both `:root` and `.dark`
   - Verify dark mode readability

4. **Use semantic color names:**
   - `--destructive` not `--red`
   - `--success` not `--green`

5. **Align with brand:**
   - Match company brand guidelines
   - Use brand colors for primary actions

### ❌ Don'ts

1. **Don't rely on color alone:**
   - Use icons + text labels
   - Support colorblind users

2. **Don't over-saturate:**
   - High chroma (>0.3) is hard on eyes
   - Causes visual fatigue in long-use apps

3. **Don't mix color systems:**
   - Stick to OKLCH throughout
   - Avoid mixing HSL/RGB unless necessary

4. **Don't forget dark mode:**
   - If light theme exists, dark theme should too
   - Dark mode is not just "inverted colors"

5. **Don't hardcode colors:**
   - Always use CSS variables
   - Never: `style="color: blue"`

---

## Useful Resources

### Color Tools

- **[OKLCH Color Picker](https://oklch.com/)** - Visual OKLCH picker with sRGB gamut warnings
- **[Coolors](https://coolors.co/)** - Palette generator (export to OKLCH)
- **[Adobe Color](https://color.adobe.com/)** - Color wheel and harmony rules
- **[Palettte App](https://palettte.app/)** - Build palettes with contrast checker

### Contrast & Accessibility

- **[WebAIM Contrast Checker](https://webaim.org/resources/contrastchecker/)** - WCAG compliance testing
- **[Accessible Colors](https://accessible-colors.com/)** - Auto-adjust colors for accessibility
- **[Who Can Use](https://whocanuse.com/)** - Test colors for various vision types

### Documentation

- **[Zard UI Theming](https://zardui.com/docs/theming)** - Official Zard UI theme docs
- **[Zard UI Dark Mode](https://zardui.com/docs/dark-mode)** - Dark mode implementation guide
- **[TailwindCSS Colors](https://tailwindcss.com/docs/colors)** - TailwindCSS v4 color system
- **[OKLCH in CSS](https://evilmartians.com/chronicles/oklch-in-css-why-quit-rgb-hsl)** - Deep dive into OKLCH

---

## Quick Reference Card

### Color Cheat Sheet

| Action                 | Variable        | Light Value              | Dark Value              |
| ---------------------- | --------------- | ------------------------ | ----------------------- |
| **View/Primary**       | `--primary`     | `oklch(0.205 0 0)`       | `oklch(0.922 0 0)`      |
| **Edit/Warning**       | `--warning`     | `oklch(0.754 0.149 83)`  | `oklch(0.84 0.16 84)`   |
| **Delete/Destructive** | `--destructive` | `oklch(0.577 0.245 27)`  | `oklch(0.704 0.191 22)` |
| **Create/Success**     | `--success`     | `oklch(0.596 0.163 155)` | `oklch(0.696 0.17 162)` |

### OKLCH Quick Values

```css
/* Lightness scale */
0.145 = Very dark (foreground)
0.205 = Dark (primary buttons)
0.5   = Medium (mid-tones)
0.922 = Light (borders)
0.985 = Very light (backgrounds)
1.0   = Pure white

/* Chroma scale */
0     = Grayscale (neutral grays)
0.1   = Subtle tint (muted)
0.2   = Moderate saturation (most UI)
0.3   = High saturation (accents)
0.4   = Max saturation (rare)

/* Hue wheel */
0-30°   = Red
50-90°  = Orange/Yellow
120-180° = Green
180-210° = Cyan/Teal
240-280° = Blue
290-330° = Purple/Magenta
```

---

**Happy theming! 🎨**

For questions or issues, refer to:

- [Zard UI Documentation](https://zardui.com/docs)
- [Project Issue Tracker](https://github.com/zard-ui/zardui/issues)
- [Zard UI Discord Community](https://discord.com/invite/yP8Uj9rAX9)
