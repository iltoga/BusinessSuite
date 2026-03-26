import { describe, expect, it, vi } from 'vitest';

import { openPdfPrintPreview } from './pdf-print-preview';

describe('openPdfPrintPreview', () => {
  it('navigates an existing popup to the blob URL and schedules printing', async () => {
    const blobUrl = 'blob:invoice-preview';
    const createObjectURLSpy = vi.spyOn(URL, 'createObjectURL').mockReturnValue(blobUrl);
    const revokeObjectURLSpy = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
    const addEventListener = vi.fn();
    const focus = vi.fn();
    const print = vi.fn();
    const popup = {
      closed: false,
      focus,
      print,
      addEventListener,
      location: {
        href: '',
        replace: vi.fn(),
      },
    } as unknown as Window;

    await openPdfPrintPreview(new Blob(['pdf'], { type: 'application/pdf' }), popup);

    expect(createObjectURLSpy).toHaveBeenCalledTimes(1);
    expect((popup as any).location.href).toBe(blobUrl);
    expect(addEventListener).not.toHaveBeenCalled();
    expect(focus).not.toHaveBeenCalled();
    expect(print).not.toHaveBeenCalled();

    revokeObjectURLSpy.mockRestore();
    createObjectURLSpy.mockRestore();
  });
});
