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
}

interface HeadlessScrollAreaProps {
  children: React.ReactNode;
  className?: string;
}

const HeadlessScrollArea = forwardRef<HeadlessScrollAreaHandle, HeadlessScrollAreaProps>(
  ({ children, className = '' }, ref) => {
    const viewportRef = useRef<HTMLDivElement>(null);
    const [thumb, setThumb] = useState({ height: 0, top: 0, visible: false });

    const scrollToBottom = useCallback((behavior: ScrollBehavior = 'auto') => {
      const el = viewportRef.current;
      if (!el) return;
      if (behavior === 'smooth') {
        el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
        return;
      }
      el.scrollTop = el.scrollHeight;
    }, []);

    useImperativeHandle(
      ref,
      () => ({
        scrollToBottom,
        scrollToSelector: (selector: string, behavior: ScrollBehavior = 'smooth') => {
          const el = viewportRef.current;
          if (!el) return;
          const target = el.querySelector(selector);
          if (target instanceof HTMLElement) {
            target.scrollIntoView({ behavior, block: 'center' });
          }
        },
      }),
      [scrollToBottom]
    );

    const updateThumb = useCallback(() => {
      const el = viewportRef.current;
      if (!el) return;
      const { scrollTop, scrollHeight, clientHeight } = el;
      if (scrollHeight <= clientHeight + 1) {
        setThumb({ height: 0, top: 0, visible: false });
        return;
      }
      const ratio = clientHeight / scrollHeight;
      const height = Math.max(28, clientHeight * ratio);
      const maxTop = clientHeight - height;
      const scrollRange = scrollHeight - clientHeight;
      const top = scrollRange > 0 ? maxTop * (scrollTop / scrollRange) : 0;
      setThumb({ height, top, visible: true });
    }, []);

    useEffect(() => {
      const el = viewportRef.current;
      if (!el) return;
      updateThumb();
      el.addEventListener('scroll', updateThumb, { passive: true });
      const observer = new ResizeObserver(updateThumb);
      observer.observe(el);
      return () => {
        el.removeEventListener('scroll', updateThumb);
        observer.disconnect();
      };
    }, [updateThumb, children]);

    return (
      <div className={`headless-scroll-area relative min-h-0 ${className}`}>
        <div ref={viewportRef} className="headless-scroll-viewport h-full min-h-0 overflow-y-auto overflow-x-hidden">
          {children}
        </div>
        {thumb.visible && (
          <div
            aria-hidden
            className="pointer-events-none absolute inset-y-2 right-1 w-1.5"
          >
            <div
              className="absolute right-0 w-1 rounded-full bg-[#59a5d8]/80"
              style={{ height: thumb.height, top: thumb.top }}
            />
          </div>
        )}
      </div>
    );
  }
);

HeadlessScrollArea.displayName = 'HeadlessScrollArea';

export default HeadlessScrollArea;
