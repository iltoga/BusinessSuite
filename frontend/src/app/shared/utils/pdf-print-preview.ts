function writePreviewShell(targetWindow: Window, bodyMarkup: string): void {
  targetWindow.document.write(`
    <!doctype html>
    <html>
      <head>
        <meta charset="utf-8" />
        <title>Print Preview</title>
        <style>
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
        </style>
      </head>
      <body>
        ${bodyMarkup}
      </body>
    </html>
  `);
  targetWindow.document.close();
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
      <script>
        window.addEventListener('load', () => {
          setTimeout(() => {
            try {
              window.focus();
              window.print();
            } catch (error) {
              console.error(error);
            }
          }, 700);
        });
      </script>
    `,
  );

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
