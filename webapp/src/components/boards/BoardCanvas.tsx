// Full-screen Excalidraw canvas for a single named board — Miro-style UX.
//
// Layout:
//   • Fixed-position fullscreen overlay (above tab stack).
//   • Sticky header: back arrow ← + editable board name (PATCH on blur)
//     + save-status hint + bg-pattern toggle.
//   • Lazy-loaded <Excalidraw> filling the remaining height.
//   • LEFT TOOLBAR: vertical pill — Select/Pen/Rect/Ellipse/Arrow/Text/Eraser/Hand.
//   • BOTTOM BAR: color pills + stroke-width selector (visible when draw tool active).
//   • BOTTOM-RIGHT: zoom in/out/reset + undo.
//
// Bugs fixed vs v1:
//   1. Dot pattern now follows pan/zoom via CSS vars updated via RAF.
//   2. Two-finger touch switches to "hand" tool to enable native pinch/pan.
//
// Persistence:
//   • On mount: GET /api/boards/:id → restore(scene_json) → initialData.
//   • On change: debounced 1500ms → serializeAsJSON → PATCH scene_json.
//   • On unmount / header back: flush pending save immediately.
//
// Telegram integration:
//   • Container height from viewportStableHeight (NOT 100dvh).
//   • theme from colorScheme.
//   • autoFocus=false, handleKeyboardGlobally=false.
//   • UIOptions phone form-factor, stripped-down canvas actions.
//   • paddingBottom: env(safe-area-inset-bottom).

import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ComponentType,
} from "react";
import {
  ChevronLeft,
  Grid2x2,
  Grid3x3,
  Square,
  MousePointer2,
  Pencil,
  RectangleHorizontal,
  Circle,
  ArrowRight,
  Type,
  Eraser,
  Hand,
  ZoomIn,
  ZoomOut,
  Maximize,
  type LucideIcon,
} from "lucide-react";
import { apiClient } from "../../api/client";
import { haptic, getWebApp } from "../../lib/telegram";
import { navigate } from "../../lib/router";
import type { BoardDetail } from "../../types";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type ExcalidrawElement = any;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AppState = any;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type BinaryFiles = any;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type ExcalidrawImperativeAPI = any;

// Lazy-load the entire Excalidraw bundle (own chunk: ~900KB gzipped).
// Cast to a loosely-typed component: Excalidraw's prop types are strict
// and don't unify with the local `any` scene-shape aliases above.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const ExcalidrawComponent = lazy(() => import("./ExcalidrawLazy")) as unknown as ComponentType<any>;

// Dynamic import helpers for serialise/restore — they land in the same
// excalidraw chunk, so this import is essentially free after the chunk loads.
async function getExcalidrawApi() {
  return import("./ExcalidrawLazy");
}

const DEBOUNCE_MS = 1500;

interface Props {
  boardId: number;
}

type SaveStatus = "idle" | "saving" | "saved" | "error";

// Background pattern for the canvas.
// "blank" = stock Excalidraw background
// "dots" = CSS polka pattern (follows pan/zoom via CSS vars)
// "grid" = Excalidraw native gridModeEnabled
type BgPattern = "blank" | "dots" | "grid";
const BG_STORAGE_KEY = "boards:bg-pattern";

const BG_LABEL: Record<BgPattern, string> = {
  blank: "Без фона",
  dots: "Точки",
  grid: "Клетка",
};
const BG_NEXT: Record<BgPattern, BgPattern> = {
  blank: "dots",
  dots: "grid",
  grid: "blank",
};

// Tools exposed in our custom Miro-style toolbar
type ToolType =
  | "selection"
  | "freedraw"
  | "rectangle"
  | "ellipse"
  | "arrow"
  | "text"
  | "eraser"
  | "hand";

interface ToolDef {
  type: ToolType;
  label: string;
  Icon: LucideIcon;
}

const TOOLS: ToolDef[] = [
  { type: "selection", label: "Выбор", Icon: MousePointer2 },
  { type: "freedraw", label: "Рисовать", Icon: Pencil },
  { type: "rectangle", label: "Прямоугольник", Icon: RectangleHorizontal },
  { type: "ellipse", label: "Эллипс", Icon: Circle },
  { type: "arrow", label: "Стрелка", Icon: ArrowRight },
  { type: "text", label: "Текст", Icon: Type },
  { type: "eraser", label: "Ластик", Icon: Eraser },
  { type: "hand", label: "Рука", Icon: Hand },
];

// Draw tools: those that benefit from the bottom colour+stroke-width bar
const DRAW_TOOLS = new Set<ToolType>([
  "freedraw",
  "rectangle",
  "ellipse",
  "arrow",
  "text",
]);

// Miro-style colour palette (12 colours)
const PALETTE = [
  "#1f2937",
  "#ffffff",
  "#22c55e",
  "#3b82f6",
  "#ef4444",
  "#f97316",
  "#eab308",
  "#a855f7",
  "#ec4899",
  "#06b6d4",
  "#6b7280",
  "#92400e",
];

interface StrokeWidthDef {
  value: number;
  label: string;
  thick: number; // visual bar height
}

const STROKE_WIDTHS: StrokeWidthDef[] = [
  { value: 1, label: "Тонкая", thick: 1 },
  { value: 2, label: "Обычная", thick: 2 },
  { value: 4, label: "Жирная", thick: 4 },
  { value: 6, label: "Очень жирная", thick: 6 },
];

export function BoardCanvas({ boardId }: Props) {
  const [board, setBoard] = useState<BoardDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [nameDraft, setNameDraft] = useState("");
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("idle");

  // Background pattern — persisted globally via localStorage
  const [bgPattern, setBgPattern] = useState<BgPattern>(() => {
    if (typeof window === "undefined") return "dots";
    const stored = window.localStorage.getItem(BG_STORAGE_KEY);
    if (stored === "blank" || stored === "dots" || stored === "grid") return stored;
    return "dots";
  });

  // Active tool mirrored from Excalidraw for our toolbar
  const [activeTool, setActiveTool] = useState<ToolType>("selection");
  // Colour + stroke-width mirrored from Excalidraw appState
  const [activeColor, setActiveColor] = useState<string>("#1f2937");
  const [activeStrokeWidth, setActiveStrokeWidth] = useState<number>(2);

  const debounceTimerRef = useRef<number | undefined>(undefined);
  const pendingSceneRef = useRef<Record<string, unknown> | null>(null);
  const excalidrawApiRef = useRef<ExcalidrawImperativeAPI | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  // Two-finger gesture tool-switching
  const prevToolRef = useRef<ToolType>("selection");
  const isMultiTouchRef = useRef(false);

  // RAF-throttled CSS-var updates for dot-pattern pan/zoom tracking
  const rafPendingRef = useRef(false);
  const scrollStateRef = useRef({ scrollX: 0, scrollY: 0, zoom: 1 });

  const wa = getWebApp();
  const tgTheme = wa?.colorScheme ?? "light";

  const containerHeight = useMemo(() => {
    const stable = wa?.viewportStableHeight;
    if (stable && stable > 0) return stable;
    return window.innerHeight;
  }, [wa]);

  // --------------------------------------------------------------------------
  // Board load
  // --------------------------------------------------------------------------
  const loadBoard = useCallback(async () => {
    setLoadError(null);
    try {
      const detail = await apiClient.board(boardId);
      setBoard(detail);
      setNameDraft(detail.name);
    } catch {
      setLoadError("Не удалось загрузить доску. Попробуй ещё раз.");
    }
  }, [boardId]);

  useEffect(() => {
    void loadBoard();
  }, [loadBoard]);

  // Register Telegram BackButton while this overlay is mounted.
  useEffect(() => {
    const bb = wa?.BackButton;
    if (!bb) return;
    const handler = () => {
      flushSave();
      navigate("/boards");
    };
    bb.show();
    bb.onClick(handler);
    return () => {
      bb.offClick(handler);
      bb.hide();
    };
  }, [wa]);

  // --------------------------------------------------------------------------
  // Save logic
  // --------------------------------------------------------------------------
  const flushSave = useCallback(() => {
    if (debounceTimerRef.current !== undefined) {
      window.clearTimeout(debounceTimerRef.current);
      debounceTimerRef.current = undefined;
    }
    const scene = pendingSceneRef.current;
    if (scene === null) return;
    pendingSceneRef.current = null;
    // Best-effort fire-and-forget on unmount/back.
    void apiClient.patchBoard(boardId, { scene_json: scene });
  }, [boardId]);

  useEffect(() => {
    return () => {
      flushSave();
    };
  }, [flushSave]);

  // --------------------------------------------------------------------------
  // Background pattern → Excalidraw state sync
  // --------------------------------------------------------------------------
  useEffect(() => {
    const api = excalidrawApiRef.current;
    if (!api) return;
    const isGrid = bgPattern === "grid";
    const bg = bgPattern === "blank" ? "#ffffff" : "transparent";
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (api as any).updateScene({
        appState: {
          gridModeEnabled: isGrid,
          viewBackgroundColor: bg,
        },
        captureUpdate: "NEVER",
      });
    } catch {
      // Best-effort — no-op on failure
    }
  }, [bgPattern]);

  // --------------------------------------------------------------------------
  // Bug #1 fix: dot pattern follows pan/zoom via CSS vars (RAF-throttled)
  // --------------------------------------------------------------------------
  const scheduleCssVarUpdate = useCallback(() => {
    if (rafPendingRef.current) return;
    rafPendingRef.current = true;
    requestAnimationFrame(() => {
      rafPendingRef.current = false;
      const el = containerRef.current;
      if (!el) return;
      const { scrollX, scrollY, zoom } = scrollStateRef.current;
      el.style.setProperty("--bg-pan-x", `${scrollX * zoom}px`);
      el.style.setProperty("--bg-pan-y", `${scrollY * zoom}px`);
      el.style.setProperty("--bg-size", `${22 * zoom}px`);
    });
  }, []);

  // --------------------------------------------------------------------------
  // onChange: debounce save + track pan/zoom + mirror tool state
  // --------------------------------------------------------------------------
  const handleChange = useCallback(
    (
      elements: readonly ExcalidrawElement[],
      appState: AppState,
      files: BinaryFiles,
    ) => {
      // Mirror active tool from Excalidraw's internal appState
      if (appState?.activeTool?.type) {
        const t = appState.activeTool.type as ToolType;
        if (TOOLS.some((tool) => tool.type === t)) {
          setActiveTool(t);
        }
      }

      // Mirror stroke colour + width
      if (appState?.currentItemStrokeColor) {
        setActiveColor(appState.currentItemStrokeColor as string);
      }
      if (appState?.currentItemStrokeWidth !== undefined) {
        setActiveStrokeWidth(appState.currentItemStrokeWidth as number);
      }

      // Bug #1: update CSS vars for dot pattern pan/zoom (RAF-throttled)
      if (appState?.scrollX !== undefined) {
        scrollStateRef.current = {
          scrollX: (appState.scrollX as number) ?? 0,
          scrollY: (appState.scrollY as number) ?? 0,
          zoom: (appState.zoom?.value as number) ?? 1,
        };
        scheduleCssVarUpdate();
      }

      // Debounce the server save
      if (debounceTimerRef.current !== undefined) {
        window.clearTimeout(debounceTimerRef.current);
      }

      debounceTimerRef.current = window.setTimeout(() => {
        debounceTimerRef.current = undefined;
        setSaveStatus("saving");
        void (async () => {
          try {
            const api = await getExcalidrawApi();
            const raw = api.serializeAsJSON(elements, appState, files, "database");
            const json = JSON.parse(raw) as Record<string, unknown>;
            pendingSceneRef.current = null;
            await apiClient.patchBoard(boardId, { scene_json: json });
            setSaveStatus("saved");
            window.setTimeout(() => setSaveStatus("idle"), 2000);
          } catch {
            setSaveStatus("error");
          }
        })();
      }, DEBOUNCE_MS);

      // Keep latest scene buffered in case unmount fires before debounce.
      void (async () => {
        const api = await getExcalidrawApi();
        const raw = api.serializeAsJSON(elements, appState, files, "database");
        pendingSceneRef.current = JSON.parse(raw) as Record<string, unknown>;
      })();
    },
    [boardId, scheduleCssVarUpdate],
  );

  // --------------------------------------------------------------------------
  // Bug #2 fix: two-finger touch → switch to hand tool for pinch/pan
  // --------------------------------------------------------------------------
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const handleTouchStart = (e: TouchEvent) => {
      if (e.touches.length >= 2 && !isMultiTouchRef.current) {
        isMultiTouchRef.current = true;
        const api = excalidrawApiRef.current;
        if (!api) return;
        // Remember the current active tool to restore after gesture
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const curState = (api as any).getAppState?.() as AppState;
        if (curState?.activeTool?.type) {
          prevToolRef.current = curState.activeTool.type as ToolType;
        }
        try {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          (api as any).setActiveTool({ type: "hand" });
        } catch {
          // best-effort
        }
      }
    };

    const handleTouchEnd = (e: TouchEvent) => {
      if (e.touches.length < 2 && isMultiTouchRef.current) {
        isMultiTouchRef.current = false;
        const api = excalidrawApiRef.current;
        if (!api) return;
        try {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          (api as any).setActiveTool({ type: prevToolRef.current });
        } catch {
          // best-effort
        }
      }
    };

    el.addEventListener("touchstart", handleTouchStart, { passive: true, capture: true });
    el.addEventListener("touchend", handleTouchEnd, { passive: true, capture: true });
    el.addEventListener("touchcancel", handleTouchEnd, { passive: true, capture: true });

    return () => {
      el.removeEventListener("touchstart", handleTouchStart, true);
      el.removeEventListener("touchend", handleTouchEnd, true);
      el.removeEventListener("touchcancel", handleTouchEnd, true);
    };
  }, [board]); // re-attach when board loads (containerRef is stable)

  // --------------------------------------------------------------------------
  // Header actions
  // --------------------------------------------------------------------------
  const handleCycleBg = useCallback(() => {
    haptic("select");
    setBgPattern((prev) => {
      const next = BG_NEXT[prev];
      try {
        window.localStorage.setItem(BG_STORAGE_KEY, next);
      } catch {
        // localStorage may throw in private browsing — non-fatal.
      }
      return next;
    });
  }, []);

  const handleBack = useCallback(() => {
    haptic("select");
    flushSave();
    navigate("/boards");
  }, [flushSave]);

  const handleNameBlur = useCallback(async () => {
    if (!board || nameDraft.trim() === board.name) return;
    const trimmed = nameDraft.trim() || "Без названия";
    setNameDraft(trimmed);
    try {
      const updated = await apiClient.patchBoard(boardId, { name: trimmed });
      setBoard(updated);
    } catch {
      setNameDraft(board.name);
    }
  }, [board, nameDraft, boardId]);

  // --------------------------------------------------------------------------
  // Toolbar actions
  // --------------------------------------------------------------------------

  // Tool picker: imperative call + mirror local state immediately
  const handleSelectTool = useCallback((type: ToolType) => {
    haptic("select");
    setActiveTool(type);
    const api = excalidrawApiRef.current;
    if (!api) return;
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (api as any).setActiveTool({ type });
    } catch {
      // best-effort
    }
  }, []);

  // Colour picker
  const handleSelectColor = useCallback((hex: string) => {
    haptic("select");
    setActiveColor(hex);
    const api = excalidrawApiRef.current;
    if (!api) return;
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (api as any).updateScene({
        appState: {
          currentItemStrokeColor: hex,
          currentItemBackgroundColor: hex + "20",
        },
        captureUpdate: "NEVER",
      });
    } catch {
      // best-effort
    }
  }, []);

  // Stroke width picker
  const handleSelectStrokeWidth = useCallback((w: number) => {
    haptic("select");
    setActiveStrokeWidth(w);
    const api = excalidrawApiRef.current;
    if (!api) return;
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (api as any).updateScene({
        appState: {
          currentItemStrokeWidth: w,
          currentItemRoughness: 0,
        },
        captureUpdate: "NEVER",
      });
    } catch {
      // best-effort
    }
  }, []);

  // Zoom controls
  const handleZoom = useCallback((delta: number) => {
    const api = excalidrawApiRef.current;
    if (!api) return;
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const state = (api as any).getAppState?.() as AppState;
      const current = (state?.zoom?.value as number) ?? 1;
      const next = Math.min(Math.max(current + delta, 0.1), 5);
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (api as any).updateScene({
        appState: { zoom: { value: next } },
        captureUpdate: "NEVER",
      });
    } catch {
      // best-effort
    }
  }, []);

  const handleZoomReset = useCallback(() => {
    const api = excalidrawApiRef.current;
    if (!api) return;
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (api as any).updateScene({
        appState: { zoom: { value: 1 } },
        captureUpdate: "NEVER",
      });
    } catch {
      // best-effort
    }
  }, []);

  // Undo — Excalidraw 0.18 exposes history.clear() but not undoOnce().
  // We dispatch a synthetic Ctrl+Z keyboard event to the canvas container.
  const handleUndo = useCallback(() => {
    haptic("select");
    try {
      const el = containerRef.current;
      if (!el) return;
      const event = new KeyboardEvent("keydown", {
        key: "z",
        code: "KeyZ",
        ctrlKey: true,
        metaKey: false,
        bubbles: true,
        cancelable: true,
      });
      el.dispatchEvent(event);
    } catch {
      // best-effort
    }
  }, []);

  // --------------------------------------------------------------------------
  // initialData from scene_json
  // --------------------------------------------------------------------------
  const [initialData, setInitialData] = useState<
    | {
        elements: readonly ExcalidrawElement[];
        appState: Partial<AppState>;
        files: BinaryFiles;
        scrollToContent: boolean;
      }
    | undefined
  >(undefined);
  const [initialDataReady, setInitialDataReady] = useState(false);

  useEffect(() => {
    if (!board) return;
    if (initialDataReady) return;

    void (async () => {
      const isGrid = bgPattern === "grid";
      const seedAppState = {
        gridModeEnabled: isGrid,
        viewBackgroundColor: bgPattern === "blank" ? "#ffffff" : "transparent",
      };
      if (!board.scene_json) {
        setInitialData({
          elements: [],
          appState: seedAppState as Partial<AppState>,
          files: {} as BinaryFiles,
          scrollToContent: false,
        });
        setInitialDataReady(true);
        return;
      }
      try {
        const api = await getExcalidrawApi();
        const scene = api.restore(board.scene_json, null, null);
        setInitialData({
          elements: scene.elements,
          appState: { ...scene.appState, ...seedAppState } as Partial<AppState>,
          files: scene.files,
          scrollToContent: true,
        });
      } catch {
        // Corrupted scene — start fresh rather than crashing.
        setInitialData(undefined);
      } finally {
        setInitialDataReady(true);
      }
    })();
  }, [board, initialDataReady]);

  // --------------------------------------------------------------------------
  // Derived UI state
  // --------------------------------------------------------------------------
  const saveHint =
    saveStatus === "saving"
      ? "сохраняю…"
      : saveStatus === "saved"
        ? "сохранено ✓"
        : saveStatus === "error"
          ? "ошибка сохранения"
          : "";

  const showBottomBar = DRAW_TOOLS.has(activeTool);

  // --------------------------------------------------------------------------
  // Error state
  // --------------------------------------------------------------------------
  if (loadError) {
    return (
      <div
        className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-tg-bg"
        style={{ height: containerHeight }}
      >
        <p className="text-sm text-tg-hint">{loadError}</p>
        <button
          type="button"
          onClick={() => void loadBoard()}
          className="ease-apple mt-4 rounded-2xl bg-tg-button px-4 py-2 text-sm font-medium text-tg-button-text transition-all active:scale-95"
        >
          Повторить
        </button>
      </div>
    );
  }

  // --------------------------------------------------------------------------
  // Render
  // --------------------------------------------------------------------------
  return (
    <div
      className="fixed inset-0 z-50 flex flex-col bg-tg-bg"
      style={{ height: containerHeight }}
    >
      {/* ── Header ── */}
      <header className="flex shrink-0 items-center gap-2 border-b border-black/[0.06] bg-tg-bg px-2 py-2 dark:border-white/[0.06]">
        <button
          type="button"
          onClick={handleBack}
          aria-label="Назад к доскам"
          className="ease-apple inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-tg-text/70 transition-all duration-150 hover:bg-bento active:scale-90"
        >
          <ChevronLeft size={20} strokeWidth={2.5} aria-hidden />
        </button>
        <input
          type="text"
          value={nameDraft}
          onChange={(e) => setNameDraft(e.target.value)}
          onBlur={() => void handleNameBlur()}
          aria-label="Название доски"
          className="font-display min-w-0 flex-1 truncate bg-transparent text-[17px] font-semibold tracking-tight text-tg-text focus:outline-none"
          maxLength={128}
        />
        {saveHint && (
          <span
            className={
              "shrink-0 text-[12px] " +
              (saveStatus === "error" ? "text-red-500" : "text-tg-hint")
            }
          >
            {saveHint}
          </span>
        )}
        <button
          type="button"
          onClick={handleCycleBg}
          aria-label={`Фон: ${BG_LABEL[bgPattern]} (нажми для смены)`}
          title={BG_LABEL[bgPattern]}
          className="ease-apple inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-tg-text/70 transition-all duration-150 hover:bg-bento active:scale-90"
        >
          {bgPattern === "blank" ? (
            <Square size={18} strokeWidth={2} aria-hidden />
          ) : bgPattern === "dots" ? (
            <Grid2x2 size={18} strokeWidth={2} aria-hidden />
          ) : (
            <Grid3x3 size={18} strokeWidth={2} aria-hidden />
          )}
        </button>
      </header>

      {/* ── Canvas area ── */}
      <div
        ref={containerRef}
        className={
          "relative min-h-0 flex-1 " +
          (bgPattern === "dots" ? "board-bg-dots" : "")
        }
        style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
      >
        {board && initialDataReady ? (
          <Suspense
            fallback={
              <div className="flex h-full items-center justify-center text-sm text-tg-hint">
                Загружаем холст…
              </div>
            }
          >
            <ExcalidrawComponent
              key={boardId}
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              excalidrawAPI={(api: any) => {
                excalidrawApiRef.current = api;
              }}
              initialData={initialData}
              onChange={handleChange}
              theme={tgTheme}
              autoFocus={false}
              handleKeyboardGlobally={false}
              UIOptions={{
                getFormFactor: () => "phone",
                tools: { image: false },
                canvasActions: {
                  saveAsImage: false,
                  loadScene: false,
                  export: false,
                  toggleTheme: false,
                  clearCanvas: true,
                  changeViewBackgroundColor: false,
                },
              }}
            />
          </Suspense>
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-tg-hint">
            {loadError ? null : "Загружаем…"}
          </div>
        )}

        {/* ── Left toolbar (tool picker pill) ── */}
        <div
          className="pointer-events-auto absolute left-3 top-1/2 z-10 -translate-y-1/2"
          aria-label="Инструменты"
        >
          <div className="flex flex-col gap-1 rounded-2xl bg-tg-bg/90 p-[6px] shadow-island backdrop-blur-md">
            {TOOLS.map(({ type, label, Icon }) => {
              const isActive = activeTool === type;
              return (
                <button
                  key={type}
                  type="button"
                  aria-label={label}
                  title={label}
                  onClick={() => handleSelectTool(type)}
                  className={
                    "ease-apple inline-flex h-9 w-9 items-center justify-center rounded-xl transition-all duration-150 active:scale-90 " +
                    (isActive
                      ? "bg-tg-button text-tg-button-text shadow-sm"
                      : "text-tg-text/70 hover:bg-bento")
                  }
                >
                  <Icon size={18} strokeWidth={2} aria-hidden />
                </button>
              );
            })}
          </div>
        </div>

        {/* ── Bottom colour + stroke-width bar (draw tools only) ── */}
        {showBottomBar && (
          <div className="pointer-events-auto absolute bottom-[calc(env(safe-area-inset-bottom,0px)+12px)] left-1/2 z-10 -translate-x-1/2">
            <div className="flex flex-col gap-2 rounded-2xl bg-tg-bg/90 px-3 py-2.5 shadow-island backdrop-blur-md">
              {/* Row 1: colour pills */}
              <div className="flex items-center gap-1.5">
                {PALETTE.map((hex) => {
                  const isActive =
                    activeColor === hex ||
                    activeColor.toLowerCase() === hex.toLowerCase();
                  return (
                    <button
                      key={hex}
                      type="button"
                      aria-label={hex}
                      title={hex}
                      onClick={() => handleSelectColor(hex)}
                      className={
                        "ease-apple inline-flex h-7 w-7 items-center justify-center rounded-full transition-all duration-150 active:scale-90 " +
                        (isActive
                          ? "ring-2 ring-tg-button ring-offset-1 ring-offset-tg-bg"
                          : "hover:scale-110")
                      }
                      style={{
                        backgroundColor: hex,
                        border:
                          hex === "#ffffff"
                            ? "1px solid rgba(0,0,0,0.12)"
                            : undefined,
                      }}
                    />
                  );
                })}
              </div>
              {/* Row 2: stroke-width buttons */}
              <div className="flex items-center justify-center gap-2">
                {STROKE_WIDTHS.map(({ value, label, thick }) => {
                  const isActive = activeStrokeWidth === value;
                  return (
                    <button
                      key={value}
                      type="button"
                      aria-label={label}
                      title={label}
                      onClick={() => handleSelectStrokeWidth(value)}
                      className={
                        "ease-apple inline-flex h-9 min-w-[36px] items-center justify-center rounded-xl px-2 transition-all duration-150 active:scale-90 " +
                        (isActive
                          ? "bg-tg-button/15 ring-2 ring-tg-button"
                          : "hover:bg-bento")
                      }
                    >
                      <span
                        className="block rounded-full bg-tg-text"
                        style={{ width: 20, height: thick }}
                        aria-hidden
                      />
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        {/* ── Bottom-right: undo + zoom controls ── */}
        <div className="pointer-events-auto absolute bottom-[calc(env(safe-area-inset-bottom,0px)+12px)] right-3 z-10 flex flex-col gap-1.5">
          {/* Undo */}
          <div className="flex flex-col gap-1 rounded-2xl bg-tg-bg/90 p-[6px] shadow-island backdrop-blur-md">
            <button
              type="button"
              aria-label="Отменить"
              title="Отменить (Ctrl+Z)"
              onClick={handleUndo}
              className="ease-apple inline-flex h-9 w-9 items-center justify-center rounded-xl text-tg-text/70 transition-all duration-150 hover:bg-bento active:scale-90"
            >
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden>
                <path
                  d="M3.5 7.5H10a4.5 4.5 0 0 1 0 9H6"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <path
                  d="M3.5 7.5L6 5m-2.5 2.5L6 10"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </button>
          </div>
          {/* Zoom */}
          <div className="flex flex-col gap-1 rounded-2xl bg-tg-bg/90 p-[6px] shadow-island backdrop-blur-md">
            <button
              type="button"
              aria-label="Приблизить"
              title="Приблизить"
              onClick={() => handleZoom(0.2)}
              className="ease-apple inline-flex h-9 w-9 items-center justify-center rounded-xl text-tg-text/70 transition-all duration-150 hover:bg-bento active:scale-90"
            >
              <ZoomIn size={18} strokeWidth={2} aria-hidden />
            </button>
            <button
              type="button"
              aria-label="Сбросить масштаб"
              title="Сбросить масштаб"
              onClick={handleZoomReset}
              className="ease-apple inline-flex h-9 w-9 items-center justify-center rounded-xl text-tg-text/70 transition-all duration-150 hover:bg-bento active:scale-90"
            >
              <Maximize size={16} strokeWidth={2} aria-hidden />
            </button>
            <button
              type="button"
              aria-label="Отдалить"
              title="Отдалить"
              onClick={() => handleZoom(-0.2)}
              className="ease-apple inline-flex h-9 w-9 items-center justify-center rounded-xl text-tg-text/70 transition-all duration-150 hover:bg-bento active:scale-90"
            >
              <ZoomOut size={18} strokeWidth={2} aria-hidden />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
