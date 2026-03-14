function writePreviewShell(targetWindow: Window, bodyMarkup: string): void {
  const doc = targetWindow.document;
  const html = doc.documentElement;

  let head = doc.head;
  if (!head) {
    head = doc.createElement('head');
    html.insertBefore(head, doc.body ?? null);
  }

  let body = doc.body;
  if (!body) {
    body = doc.createElement('body');
    html.appendChild(body);
  }

  head.replaceChildren();

  const charset = doc.createElement('meta');
  charset.setAttribute('charset', 'utf-8');

  const title = doc.createElement('title');
  title.textContent = 'Print Preview';

  const style = doc.createElement('style');
  style.textContent = `
    html, body {
      margin: 0;
      height: 100%;
      background: #111;
      color: #f5f5f5;
      font-family: Inter, system-ui, sans-serif;
    }
    .preview-loading {
      display: grid;
      place-items: center;
      height: 100%;
      text-align: center;
      padding: 2rem;
    }
    .preview-loading p {
      opacity: 0.8;
      margin: 0;
    }
    embed {
      width: 100%;
      height: 100%;
      border: 0;
    }
  `;

  head.append(charset, title, style);

  body.replaceChildren();
  body.innerHTML = bodyMarkup;
}

export function openPendingPdfPrintPreviewWindow(): Window {
  const popup = window.open('', '_blank');
  if (!popup) {
    throw new Error('Popup blocked. Allow popups to open the print preview.');
  }

  writePreviewShell(
    popup,
    `
      <div class="preview-loading">
        <div>
          <h1>Preparing print preview…</h1>
          <p>Your PDF is being generated. This window will update automatically.</p>
        </div>
      </div>
    `,
  );

  return popup;
}

export async function openPdfPrintPreview(
  src: Blob | string | null,
  targetWindow?: Window | null,
): Promise<void> {
  if (typeof window === 'undefined') {
    return;
  }

  if (!src) {
    window.print();
    return;
  }

  let blob: Blob | null = null;
  if (src instanceof Blob) {
    blob = src;
  } else {
    try {
      const response = await fetch(src, { credentials: 'same-origin' });
      if (response.ok) {
        blob = await response.blob();
      }
    } catch {
      window.open(src, '_blank', 'noopener');
      return;
    }
  }

  if (!blob) {
    if (typeof src === 'string') {
      window.open(src, '_blank', 'noopener');
      return;
    }
    throw new Error('Unable to open print preview.');
  }

  const blobUrl = URL.createObjectURL(blob);
  const popup = targetWindow && !targetWindow.closed ? targetWindow : window.open('', '_blank');
  if (!popup) {
    URL.revokeObjectURL(blobUrl);
    throw new Error('Popup blocked. Allow popups to open the print preview.');
  }

  writePreviewShell(
    popup,
    `
      <embed src="${blobUrl}" type="application/pdf" />
    `,
  );

  let didPrint = false;
  const triggerPrint = () => {
    if (didPrint) {
      return;
    }
    didPrint = true;
    try {
      popup.focus();
      popup.print();
    } catch (error) {
      console.error(error);
    }
  };

  const embed = popup.document.querySelector('embed');
  if (embed) {
    embed.addEventListener(
      'load',
      () => {
        window.setTimeout(triggerPrint, 200);
      },
      { once: true },
    );
  }

  window.setTimeout(triggerPrint, 700);

  const cleanup = () => {
    try {
      URL.revokeObjectURL(blobUrl);
    } catch {
      // Ignore cleanup failures.
    }
  };

  popup.addEventListener('afterprint', cleanup, { once: true });
  window.setTimeout(cleanup, 60_000);
}
