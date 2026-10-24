import { useCallback, useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type PointerEvent as ReactPointerEvent, type RefObject } from "react";

export interface View {
  x: number;
  y: number;
  k: number;
}

const MIN_K = 0.1;
const MAX_K = 8;
const clamp = (k: number) => Math.min(MAX_K, Math.max(MIN_K, k));

/**
 * Pan/zoom for an SVG whose content is drawn inside `<g transform=...>`.
 * Wheel zooms around the cursor, drag pans, and `fit` frames a content box.
 */
export function usePanZoom(containerRef: RefObject<HTMLElement>, content: { width: number; height: number } | null) {
  const [view, setView] = useState<View>({ x: 0, y: 0, k: 1 });
  const drag = useRef<{ id: number; x: number; y: number; moved: boolean } | null>(null);
  const lastGestureDragged = useRef(false);

  const fit = useCallback(() => {
    const el = containerRef.current;
    if (!el || !content || content.width === 0) return;
    const { clientWidth: w, clientHeight: h } = el;
    const k = clamp(Math.min(w / content.width, h / content.height, 2) * 0.95);
    setView({ k, x: (w - content.width * k) / 2, y: (h - content.height * k) / 2 });
  }, [containerRef, content]);

  // Re-fit whenever the content changes or the container is resized.
  useEffect(() => {
    fit();
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver(() => fit());
    observer.observe(el);
    return () => observer.disconnect();
  }, [fit, containerRef]);

  const zoomAt = useCallback((factor: number, cx?: number, cy?: number) => {
    const el = containerRef.current;
    setView((v) => {
      const px = cx ?? (el ? el.clientWidth / 2 : 0);
      const py = cy ?? (el ? el.clientHeight / 2 : 0);
      const k = clamp(v.k * factor);
      const ratio = k / v.k;
      return { k, x: px - (px - v.x) * ratio, y: py - (py - v.y) * ratio };
    });
  }, [containerRef]);

  // Wheel must be a non-passive native listener so we can prevent page scrolling.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const rect = el.getBoundingClientRect();
      zoomAt(Math.exp(-event.deltaY * 0.0015), event.clientX - rect.left, event.clientY - rect.top);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [containerRef, zoomAt]);

  const onPointerDown = (event: ReactPointerEvent) => {
    if (event.button !== 0) return;
    // Capture only once the pointer really moves, so a plain click still reaches wires.
    drag.current = { id: event.pointerId, x: event.clientX, y: event.clientY, moved: false };
    lastGestureDragged.current = false;
  };
  const onPointerMove = (event: ReactPointerEvent) => {
    const d = drag.current;
    if (!d || d.id !== event.pointerId) return;
    const dx = event.clientX - d.x;
    const dy = event.clientY - d.y;
    if (!d.moved) {
      if (Math.abs(dx) + Math.abs(dy) < 4) return;
      (event.currentTarget as Element).setPointerCapture(event.pointerId);
      lastGestureDragged.current = true;
    }
    drag.current = { ...d, x: event.clientX, y: event.clientY, moved: true };
    setView((v) => ({ ...v, x: v.x + dx, y: v.y + dy }));
  };
  const onPointerUp = (event: ReactPointerEvent) => {
    if (drag.current?.id === event.pointerId) drag.current = null;
  };

  const onKeyDown = (event: ReactKeyboardEvent) => {
    const step = 40;
    const actions: Record<string, () => void> = {
      "+": () => zoomAt(1.25),
      "=": () => zoomAt(1.25),
      "-": () => zoomAt(0.8),
      "0": fit,
      ArrowLeft: () => setView((v) => ({ ...v, x: v.x + step })),
      ArrowRight: () => setView((v) => ({ ...v, x: v.x - step })),
      ArrowUp: () => setView((v) => ({ ...v, y: v.y + step })),
      ArrowDown: () => setView((v) => ({ ...v, y: v.y - step })),
    };
    const action = actions[event.key];
    if (action) {
      event.preventDefault();
      action();
    }
  };

  return {
    view,
    fit,
    zoomIn: () => zoomAt(1.25),
    zoomOut: () => zoomAt(0.8),
    /** True if the gesture that just ended was a pan (so its click should be ignored). */
    didDrag: () => lastGestureDragged.current,
    handlers: { onPointerDown, onPointerMove, onPointerUp, onPointerCancel: onPointerUp, onKeyDown },
  };
}
