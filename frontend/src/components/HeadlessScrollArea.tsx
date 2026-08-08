import React, {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from 'react';

export interface HeadlessScrollAreaHandle {
  scrollToBottom: (behavior?: ScrollBehavior) => void;
  scrollToSelector: (selector: string, behavior?: ScrollBehavior) => void;
  getViewport: () => HTMLDivElement | null;
}

interface HeadlessScrollAreaProps {
  children: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
  viewportClassName?: string;
  viewportStyle?: React.CSSProperties;
  /** Scroll axes to enable. Default vertical only. */
  axes?: 'y' | 'x' | 'both';
}

const HeadlessScrollArea = forwardRef<HeadlessScrollAreaHandle, HeadlessScrollAreaProps>(
  ({ children, className = '', style, viewportClassName = '', viewportStyle, axes = 'y' }, ref) => {
    const viewportRef = useRef<HTMLDivElement>(null);
    const [vThumb, setVThumb] = useState({ height: 0, top: 0, visible: false });
    const [hThumb, setHThumb] = useState({ width: 0, left: 0, visible: false });

    const enableY = axes === 'y' || axes === 'both';
    const enableX = axes === 'x' || axes === 'both';

    const getViewport = useCallback(() => viewportRef.current, []);

    const scrollToBottom = useCallback((behavior: ScrollBehavior = 'auto') => {
      const el = viewportRef.current;
      if (!el) return;
      const top = el.scrollHeight;
      if (behavior === 'smooth') {
        el.scrollTo({ top, behavior: 'smooth' });
        return;
      }
      el.scrollTop = top;
    }, []);

    useImperativeHandle(
      ref,
      () => ({
        scrollToBottom,
        getViewport,
        scrollToSelector: (selector: string, behavior: ScrollBehavior = 'smooth') => {
          const el = viewportRef.current;
          if (!el) return;
          const target = el.querySelector(selector);
          if (target instanceof HTMLElement) {
            target.scrollIntoView({ behavior, block: 'nearest', inline: 'nearest' });
          }
        },
      }),
      [scrollToBottom, getViewport]
    );

    const updateThumbs = useCallback(() => {
      const el = viewportRef.current;
      if (!el) return;
      const { scrollTop, scrollLeft, scrollHeight, scrollWidth, clientHeight, clientWidth } = el;

      if (enableY && scrollHeight > clientHeight + 1) {
        const ratio = clientHeight / scrollHeight;
        const height = Math.max(28, clientHeight * ratio);
        const maxTop = clientHeight - height;
        const scrollRange = scrollHeight - clientHeight;
        const top = scrollRange > 0 ? maxTop * (scrollTop / scrollRange) : 0;
        setVThumb({ height, top, visible: true });
      } else {
        setVThumb({ height: 0, top: 0, visible: false });
      }

      if (enableX && scrollWidth > clientWidth + 1) {
        const ratio = clientWidth / scrollWidth;
        const width = Math.max(28, clientWidth * ratio);
        const maxLeft = clientWidth - width;
        const scrollRange = scrollWidth - clientWidth;
        const left = scrollRange > 0 ? maxLeft * (scrollLeft / scrollRange) : 0;
        setHThumb({ width, left, visible: true });
      } else {
        setHThumb({ width: 0, left: 0, visible: false });
      }
    }, [enableX, enableY]);

    useEffect(() => {
      const el = viewportRef.current;
      if (!el) return;
      updateThumbs();
      el.addEventListener('scroll', updateThumbs, { passive: true });
      const resizeObserver = new ResizeObserver(updateThumbs);
      resizeObserver.observe(el);
      // Watch the viewport node only — do not rebind when `children` identity
      // changes (e.g. every drag highlight), or MutationObserver thrash freezes UI.
      const mutationObserver = new MutationObserver(updateThumbs);
      mutationObserver.observe(el, { childList: true, subtree: true, characterData: true });
      return () => {
        el.removeEventListener('scroll', updateThumbs);
        resizeObserver.disconnect();
        mutationObserver.disconnect();
      };
    }, [updateThumbs]);

    const overflowClass = enableX && enableY
      ? 'overflow-auto'
      : enableX
        ? 'overflow-x-auto overflow-y-hidden'
        : 'overflow-y-auto overflow-x-hidden';

    return (
      <div
        className={`headless-scroll-area relative flex min-h-0 flex-col overflow-hidden ${className}`}
        style={style}
      >
        <div
          ref={viewportRef}
          className={`headless-scroll-viewport min-h-0 flex-1 ${overflowClass} ${viewportClassName}`}
          style={viewportStyle}
        >
          {children}
        </div>
        {vThumb.visible && (
          <div aria-hidden className="pointer-events-none absolute inset-y-2 right-1 z-10 w-1.5">
            <div
              className="absolute right-0 w-1 rounded-full bg-[#59a5d8]/80"
              style={{ height: vThumb.height, top: vThumb.top }}
            />
          </div>
        )}
        {hThumb.visible && (
          <div aria-hidden className="pointer-events-none absolute inset-x-2 bottom-1 z-10 h-1.5">
            <div
              className="absolute bottom-0 h-1 rounded-full bg-[#59a5d8]/80"
              style={{ width: hThumb.width, left: hThumb.left }}
            />
          </div>
        )}
      </div>
    );
  }
);

HeadlessScrollArea.displayName = 'HeadlessScrollArea';

export default HeadlessScrollArea;
