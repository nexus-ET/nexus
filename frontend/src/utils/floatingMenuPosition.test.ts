import { computeFloatingMenuPosition } from './floatingMenuPosition';

describe('computeFloatingMenuPosition', () => {
  const originalInnerWidth = window.innerWidth;
  const originalInnerHeight = window.innerHeight;

  afterEach(() => {
    Object.defineProperty(window, 'innerWidth', {
      configurable: true,
      value: originalInnerWidth,
    });
    Object.defineProperty(window, 'innerHeight', {
      configurable: true,
      value: originalInnerHeight,
    });
  });

  it('opens upward when the anchor is in the lower half of the viewport', () => {
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1200 });
    Object.defineProperty(window, 'innerHeight', { configurable: true, value: 800 });

    const position = computeFloatingMenuPosition(400, 700, 280, 320);

    expect(position.top).toBeLessThan(700);
    expect(position.top).toBeGreaterThanOrEqual(16);
    expect(position.top + 320).toBeLessThanOrEqual(800);
  });

  it('centers a tall menu when opened from the bottom rows', () => {
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1200 });
    Object.defineProperty(window, 'innerHeight', { configurable: true, value: 800 });

    const position = computeFloatingMenuPosition(900, 760, 280, 420);

    expect(position.top).toBeGreaterThanOrEqual(16);
    expect(position.top + 420).toBeLessThanOrEqual(800);
    expect(position.left).toBeGreaterThanOrEqual(16);
    expect(position.left + 280).toBeLessThanOrEqual(1200);
  });
});
