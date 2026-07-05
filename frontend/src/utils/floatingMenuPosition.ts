/** Keep a fixed floating menu fully visible in the viewport. */

export interface ViewportPoint {
  top: number;
  left: number;
}

const VIEWPORT_PADDING = 16;

export function computeFloatingMenuPosition(
  anchorX: number,
  anchorY: number,
  menuWidth: number,
  menuHeight: number
): ViewportPoint {
  const viewportWidth = window.innerWidth;
  const viewportHeight = window.innerHeight;
  const maxWidth = Math.max(0, viewportWidth - VIEWPORT_PADDING * 2);
  const maxHeight = Math.max(0, viewportHeight - VIEWPORT_PADDING * 2);
  const width = Math.min(menuWidth, maxWidth);
  const height = Math.min(menuHeight, maxHeight);

  const spaceBelow = viewportHeight - anchorY - VIEWPORT_PADDING;
  const spaceAbove = anchorY - VIEWPORT_PADDING;
  const anchorInLowerHalf = anchorY > viewportHeight * 0.45;
  const overflowsBelow = height > spaceBelow;
  const overflowsAbove = height > spaceAbove;

  let top: number;
  if (anchorInLowerHalf || (overflowsBelow && !overflowsAbove)) {
    top = anchorY - height - 8;
  } else if (overflowsBelow) {
    top = Math.max(VIEWPORT_PADDING, (viewportHeight - height) / 2);
  } else {
    top = anchorY;
  }

  if (top + height > viewportHeight - VIEWPORT_PADDING) {
    top = viewportHeight - height - VIEWPORT_PADDING;
  }
  if (top < VIEWPORT_PADDING || (anchorInLowerHalf && overflowsBelow)) {
    top = Math.max(VIEWPORT_PADDING, (viewportHeight - height) / 2);
  }

  let left = anchorX;
  if (left + width > viewportWidth - VIEWPORT_PADDING) {
    left = viewportWidth - width - VIEWPORT_PADDING;
  }
  if (left < VIEWPORT_PADDING) {
    left = VIEWPORT_PADDING;
  }

  if (anchorInLowerHalf && height > viewportHeight * 0.35) {
    left = Math.max(VIEWPORT_PADDING, (viewportWidth - width) / 2);
    top = Math.max(VIEWPORT_PADDING, (viewportHeight - height) / 2);
  }

  return { top, left };
}
