type NavigatorWithUserAgentData = Navigator & {
  userAgentData?: {
    platform?: string;
  };
};

function getDefaultDocument(): Document | null {
  return typeof document !== 'undefined' ? document : null;
}

function getDefaultNavigator(): Navigator | null {
  return typeof navigator !== 'undefined' ? navigator : null;
}

function normalizeScaleFactor(value: number): number {
  return Number.isFinite(value) && value > 0 ? value : 1;
}

function readNavigatorPlatform(navigatorLike?: Navigator | null): string {
  const safeNavigator = navigatorLike ?? getDefaultNavigator();
  if (!safeNavigator) {
    return '';
  }

  const navigatorWithUserAgentData = safeNavigator as NavigatorWithUserAgentData;
  return String(
    navigatorWithUserAgentData.userAgentData?.platform ||
      safeNavigator.platform ||
      safeNavigator.userAgent ||
      '',
  ).toLowerCase();
}

export function isWindowsPlatform(navigatorLike?: Navigator | null): boolean {
  return readNavigatorPlatform(navigatorLike).includes('win');
}

export function readCurrentUiScaleFactor(doc?: Document | null): number {
  const safeDocument = doc ?? getDefaultDocument();
  if (!safeDocument) {
    return 1;
  }

  const rootElement = safeDocument.documentElement;
  const rootStyle = getComputedStyle(rootElement);
  const cssVarScale = Number.parseFloat(rootStyle.getPropertyValue('--app-ui-scale').trim());

  if (Number.isFinite(cssVarScale) && cssVarScale > 0) {
    return cssVarScale;
  }

  const inlineZoom = Number.parseFloat(rootElement.style.zoom || '');
  if (Number.isFinite(inlineZoom) && inlineZoom > 0) {
    return inlineZoom;
  }

  return 1;
}

export function shouldCompensateWindowsUiScale(
  doc?: Document | null,
  navigatorLike?: Navigator | null,
): boolean {
  return isWindowsPlatform(navigatorLike) && Math.abs(readCurrentUiScaleFactor(doc) - 1) > 0.001;
}

export function readOverlayTriggerWidthPx(
  element: Element | null | undefined,
  navigatorLike?: Navigator | null,
): number | null {
  if (!(element instanceof HTMLElement)) {
    return null;
  }

  const ownerDocument = element.ownerDocument ?? getDefaultDocument();
  const visualWidth = element.getBoundingClientRect().width;

  if (!shouldCompensateWindowsUiScale(ownerDocument, navigatorLike)) {
    if (Number.isFinite(visualWidth) && visualWidth > 0) {
      return visualWidth;
    }

    return Number.isFinite(element.offsetWidth) && element.offsetWidth > 0
      ? element.offsetWidth
      : null;
  }

  if (Number.isFinite(element.offsetWidth) && element.offsetWidth > 0) {
    return element.offsetWidth;
  }

  if (Number.isFinite(visualWidth) && visualWidth > 0) {
    return visualWidth / normalizeScaleFactor(readCurrentUiScaleFactor(ownerDocument));
  }

  return null;
}

export function scaleOverlayMaxHeightPx(
  basePx: number,
  doc?: Document | null,
  navigatorLike?: Navigator | null,
): number {
  const safeBasePx = Number.isFinite(basePx) && basePx > 0 ? basePx : 0;

  if (!shouldCompensateWindowsUiScale(doc, navigatorLike)) {
    return Math.round(safeBasePx);
  }

  const scaleFactor = normalizeScaleFactor(readCurrentUiScaleFactor(doc));
  return Math.max(Math.round(safeBasePx / scaleFactor), Math.round(safeBasePx));
}
