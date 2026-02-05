# BusinessSuiteFrontend

This project was generated using [Angular CLI](https://github.com/angular/angular-cli) version 21.1.1.

## Development server

To start a local development server, run:

```bash
ng serve
```

Once the server is running, open your browser and navigate to `http://localhost:4200/`. The application will automatically reload whenever you modify any of the source files.

---

## Runtime branding / logo via environment variables ✅

When deployed in Docker the frontend server reads the `LOGO_FILENAME` and `LOGO_INVERTED_FILENAME` environment variables at runtime. These values are:

- Injected into server-rendered HTML as `window.APP_BRAND` (SSR)
- Served at `/assets/config.json` (overrides `assets/config.json` values)

Set the variables in your `.env` and ensure `docker-compose.yml` passes them to the `bs-frontend` service. After changing the variables, restart the `bs-frontend` container so values take effect.

Examples (docker-compose):

```yaml
services:
  bs-frontend:
    environment:
      - LOGO_FILENAME=${LOGO_FILENAME}
      - LOGO_INVERTED_FILENAME=${LOGO_INVERTED_FILENAME}
```

## Code scaffolding

Angular CLI includes powerful code scaffolding tools. To generate a new component, run:

```bash
ng generate component component-name
```

For a complete list of available schematics (such as `components`, `directives`, or `pipes`), run:

```bash
ng generate --help
```

## Building

To build the project run:

```bash
ng build
```

This will compile your project and store the build artifacts in the `dist/` directory. By default, the production build optimizes your application for performance and speed.

## Running unit tests

To execute unit tests with the [Vitest](https://vitest.dev/) test runner, use the following command:

```bash
ng test
```

## Running end-to-end tests

We use Playwright for e2e tests. Playwright will automatically start the dev server defined in `playwright.config.ts` (so you don't need to run `ng serve` manually).

Run tests locally:

```bash
# Run the Playwright test runner (starts the dev server automatically)
npm run test:e2e
```

Useful options:

- Run a single test file: `npx playwright test e2e/theme.spec.ts`
- Run headed (non-headless) for debugging: `npx playwright test --headed`

CI integration: a GitHub Actions workflow is provided at `.github/workflows/playwright.yml` which installs dependencies, installs Playwright browsers, and runs `npm run test:e2e` (Playwright will bring up the dev server).

If you prefer Playwright to _not_ start the dev server, set `reuseExistingServer=true` in `playwright.config.ts` and start the app manually before running tests.

## Mocked authentication for local development ✅

You can enable a mocked authentication mode so you don't have to login repeatedly during local development. Steps:

1. Open `src/app/core/config/app.config.ts` and set `mockAuthEnabled: true`:

```ts
export const APP_CONFIG = {
  mockAuthEnabled: true, // <-- Set to true
} as const;
```

2. Restart the Angular dev server (`bun run start`).

When enabled, `AuthService.login()` will immediately return a fake token (`mock-token`) and the app will auto-set a token on startup if none exists.

3. Switch it back to `false` before testing real authentication flows or when running integration tests.

---

## Theming System 🎨

The application uses a comprehensive theming system based on Zard UI with support for multiple pre-made themes and dark mode.

### Quick Start: Change Theme

1. Open `src/app/core/config/app.config.ts`
2. Change the `theme` property:

```typescript
export const APP_CONFIG = {
  mockAuthEnabled: true,
  theme: 'blue', // <-- Change to: 'neutral', 'slate', 'gray', 'zinc', 'stone', 'blue', 'purple', or 'teal'
} as const;
```

3. Restart the dev server to see changes

### Available Themes

- **`neutral`** (default) - Pure grayscale, professional
- **`slate`** - Cool blue-gray, tech/SaaS
- **`gray`** - Balanced gray, enterprise apps
- **`zinc`** - Slightly cool gray, modern apps
- **`stone`** - Warm gray, e-commerce/lifestyle
- **`blue`** - Corporate blue primary
- **`purple`** - Creative purple primary
- **`teal`** - Modern teal/cyan primary

### Dark Mode

The theme system includes automatic dark mode support:

- Detects system preference automatically
- Persists user choice to localStorage
- Smooth transitions between modes

### Dynamic Theme Switching

Add the theme switcher component anywhere in your app:

```typescript
import { ThemeSwitcherComponent } from '@/shared/components/theme-switcher/theme-switcher.component';

@Component({
  imports: [ThemeSwitcherComponent],
  template: `<app-theme-switcher />`
})
```

### Creating Custom Themes

See [THEMING_GUIDE.md](./THEMING_GUIDE.md) for:

- Complete theme customization guide
- OKLCH color format explanation
- Creating custom themes
- Theme service API reference
- Dark mode implementation
- Best practices and troubleshooting

Also see [QUICK_THEME_GUIDE.md](../.github/copilot/specs/django-angular/QUICK_THEME_GUIDE.md) for additional examples and color theory.

---

## Additional Resources

For more information on using the Angular CLI, including detailed command references, visit the [Angular CLI Overview and Command Reference](https://angular.dev/tools/cli) page.
