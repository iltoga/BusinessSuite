import { bootstrapApplication } from '@angular/platform-browser';
import { App } from './app/app';
import { appConfig } from './app/app.config';

bootstrapApplication(App, appConfig).catch((err) => console.error(err));

// Global capture for Shift+N to open "new" routes in list views
if (typeof window !== 'undefined') {
  window.addEventListener(
    'keydown',
    (ev: KeyboardEvent) => {
      try {
        if (ev.key === 'N' && ev.shiftKey && !ev.ctrlKey && !ev.altKey && !ev.metaKey) {
          const active = document.activeElement as HTMLElement | null;
          const tag = active?.tagName ?? '';
          const isEditable =
            tag === 'INPUT' || tag === 'TEXTAREA' || (active && active.isContentEditable);
          if (isEditable) return;

          const path = window.location.pathname || '';
          const mapping = ['/customers', '/applications', '/invoices', '/products'];
          for (const base of mapping) {
            if (path.startsWith(base)) {
              ev.preventDefault();
              ev.stopPropagation();
              // Try to use history API so SPA can pick up the navigation without reloading
              try {
                history.pushState(null, '', `${base}/new`);
                window.dispatchEvent(new PopStateEvent('popstate'));
              } catch {
                // Fallback to full navigation
                window.location.href = `${base}/new`;
              }
              return;
            }
          }
        }
      } catch {}
    },
    true,
  );
}
