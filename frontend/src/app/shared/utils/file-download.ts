/**
 * Utility to trigger a file download from a Blob.
 *
 * @param blob The blob content to download
 * @param filename The name of the file
 */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;

  // Append to body, click, and remove
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);

  // Clean up the URL
  window.URL.revokeObjectURL(url);
}
