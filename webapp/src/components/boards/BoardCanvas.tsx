// Full-screen Excalidraw canvas for a single named board — bottom-toolbar UX.
//
// Layout:
//   • Fixed-position fullscreen overlay (above tab stack).
//   • Sticky header: back arrow ← + editable board name (PATCH on blur)
//     + save-status hint + bg-pattern toggle.
//   • Lazy-loaded <Excalidraw> filling the remaining height.
//   • BOTTOM TOOLBAR (v2): horizontal pill at the bottom — all 8 tools.
//   • CONTEXTUAL SETTINGS PANEL: slides up above tool row when draw tool active.
//     Per-tool: colour swatch row + thickness slider + opacity slider +
//     fill toggle (shapes) / font size (text).
//   • TOP-RIGHT: undo/redo + zoom in/out/reset (glass pills, no collision).
//
// Bugs fixed:
//   1. Dot pattern follows pan/zoom via CSS vars updated via RAF.
//   2. Two-finger touch switches to "hand" tool to enable native pinch/pan.
//   3. ALL stock Excalidraw chrome hidden — our controls are sole source of truth.
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
  memo,
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
  Undo2,
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

// Tools that show the contextual settings panel
const DRAW_TOOLS = new Set<ToolType>([
  "freedraw",
  "rectangle",
  "ellipse",
  "arrow",
  "text",
]);

// Tools that show stroke colour + thickness
const STROKE_TOOLS = new Set<ToolType>([
  "freedraw",
  "rectangle",
  "ellipse",
  "arrow",
  "text",
]);

// Tools that show fill controls (shapes only)
const FILL_TOOLS = new Set<ToolType>(["rectangle", "ellipse"]);

// 12-colour Miro-style palette
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
] as const;

// Font size options for the text tool
const FONT_SIZES = [
  { label: "S", value: 16 },
  { label: "M", value: 20 },
  { label: "L", value: 28 },
  { label: "XL", value: 36 },
] as const;

// ─────────────────────────────────────────────────────────────────────────────
// Sub-components (memoised so canvas onChange doesn't re-render them)
// ─────────────────────────────────────────────────────────────────────────────

interface ToolRowProps {
  tools: ToolDef[];
  activeTool: ToolType;
  onSelect: (type: ToolType) => void;
}

const ToolRow = memo(function ToolRow({ tools, activeTool, onSelect }: ToolRowProps) {
  return (
    <div
      className="flex items-center gap-0.5 rounded-2xl bg-tg-bg/95 px-1.5 py-1.5 shadow-island backdrop-blur-xl ring-1 ring-black/[0.06] dark:ring-white/[0.06]"
      role="toolbar"
      aria-label="Инструменты рисования"
    >
      {tools.map(({ type, label, Icon }) => {
        const isActive = activeTool === type;
        return (
          <button
            key={type}
            type="button"
            aria-label={label}
            title={label}
            aria-pressed={isActive}
            onClick={() => onSelect(type)}
            className={
              "ease-apple inline-flex h-10 w-10 items-center justify-center rounded-xl transition-all duration-150 active:scale-90 " +
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
  );
});

interface SettingsPanelProps {
  activeTool: ToolType;
  activeColor: string;
  activeStrokeWidth: number;
  activeOpacity: number;
  activeFillColor: string;
  activeFontSize: number;
  onColorChange: (hex: string) => void;
  onStrokeWidthChange: (w: number) => void;
  onOpacityChange: (v: number) => void;
  onFillColorChange: (hex: string | "transparent") => void;
  onFontSizeChange: (size: number) => void;
}

const SettingsPanel = memo(function SettingsPanel({
  activeTool,
  activeColor,
  activeStrokeWidth,
  activeOpacity,
  activeFillColor,
  activeFontSize,
  onColorChange,
  onStrokeWidthChange,
  onOpacityChange,
  onFillColorChange,
  onFontSizeChange,
}: SettingsPanelProps) {
  const showStroke = STROKE_TOOLS.has(activeTool);
  const showFill = FILL_TOOLS.has(activeTool);
  const showFontSize = activeTool === "text";

  return (
    <div className="w-full rounded-2xl bg-tg-bg/95 px-3 py-3 shadow-island backdrop-blur-xl ring-1 ring-black/[0.06] dark:ring-white/[0.06]">
      {/* Colour row */}
      {showStroke && (
        <div className="mb-3">
          <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-tg-hint">
            Цвет
          </p>
          <div className="flex items-center gap-1.5 overflow-x-auto pb-0.5">
            {PALETTE.map((hex) => {
              const isActive =
                activeColor === hex ||
                activeColor.toLowerCase() === hex.toLowerCase();
              return (
                <button
                  key={hex}
                  type="button"
                  aria-label={hex}
                  aria-pressed={isActive}
                  onClick={() => onColorChange(hex)}
                  className={
                    "ease-apple inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full transition-all duration-150 active:scale-90 " +
                    (isActive
                      ? "ring-2 ring-tg-button ring-offset-2 ring-offset-tg-bg scale-110"
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
        </div>
      )}

      {/* Fill toggle (shapes only) */}
      {showFill && (
        <div className="mb-3">
          <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-tg-hint">
            Заливка
          </p>
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              aria-label="Без заливки"
              aria-pressed={activeFillColor === "transparent"}
              onClick={() => onFillColorChange("transparent")}
              className={
                "ease-apple inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border transition-all duration-150 active:scale-90 " +
                (activeFillColor === "transparent"
                  ? "border-tg-button ring-2 ring-tg-button ring-offset-2 ring-offset-tg-bg scale-110"
                  : "border-black/20 hover:scale-110 dark:border-white/20")
              }
              style={{ backgroundImage: "repeating-linear-gradient(45deg, transparent, transparent 3px, rgba(0,0,0,0.1) 3px, rgba(0,0,0,0.1) 4px)" }}
            />
            {PALETTE.filter((c) => c !== "#ffffff").slice(0, 8).map((hex) => {
              const fillHex = hex + "33";
              const isActive = activeFillColor === fillHex;
              return (
                <button
                  key={hex}
                  type="button"
                  aria-label={`Заливка ${hex}`}
                  aria-pressed={isActive}
                  onClick={() => onFillColorChange(fillHex)}
                  className={
                    "ease-apple inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full transition-all duration-150 active:scale-90 " +
                    (isActive
                      ? "ring-2 ring-tg-button ring-offset-2 ring-offset-tg-bg scale-110"
                      : "hover:scale-110")
                  }
                  style={{ backgroundColor: hex + "33", border: `2px solid ${hex}` }}
                />
              );
            })}
          </div>
        </div>
      )}

      {/* Font size (text tool only) */}
      {showFontSize && (
        <div className="mb-3">
          <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-tg-hint">
            Размер шрифта
          </p>
          <div className="flex items-center gap-1.5">
            {FONT_SIZES.map(({ label, value }) => {
              const isActive = activeFontSize === value;
              return (
                <button
                  key={value}
                  type="button"
                  aria-label={`Размер ${label}`}
                  aria-pressed={isActive}
                  onClick={() => onFontSizeChange(value)}
                  className={
                    "ease-apple inline-flex h-9 min-w-[44px] items-center justify-center rounded-xl px-2 text-sm font-semibold transition-all duration-150 active:scale-90 " +
                    (isActive
                      ? "bg-tg-button text-tg-button-text"
                      : "bg-bento text-tg-text/70 hover:bg-bento/80")
                  }
                >
                  {label}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Thickness slider */}
      {showStroke && activeTool !== "text" && (
        <div className="mb-3">
          <div className="mb-1.5 flex items-center justify-between">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-tg-hint">
              Толщина
            </p>
            <span className="text-[11px] font-semibold tabular-nums text-tg-button">
              {activeStrokeWidth}
            </span>
          </div>
          <input
            type="range"
            min={1}
            max={8}
            step={1}
            value={activeStrokeWidth}
            onChange={(e) => onStrokeWidthChange(Number(e.target.value))}
            className="board-slider w-full"
            aria-label="Толщина линии"
          />
        </div>
      )}

      {/* Opacity slider */}
      <div>
        <div className="mb-1.5 flex items-center justify-between">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-tg-hint">
            Прозрачность
          </p>
          <span className="text-[11px] font-semibold tabular-nums text-tg-button">
            {activeOpacity}%
          </span>
        </div>
        <input
          type="range"
          min={0}
          max={100}
          step={5}
          value={activeOpacity}
          onChange={(e) => onOpacityChange(Number(e.target.value))}
          className="board-slider w-full"
          aria-label="Прозрачность"
        />
      </div>
    </div>
  );
});

// ─────────────────────────────────────────────────────────────────────────────
// Main component
// ─────────────────────────────────────────────────────────────────────────────

export function BoardCanvas({ boardId }: Props) {
  const [board, setBoard] = useState<BoardDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [nameDraft, setNameDraft] = useState("");
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("idle");

  const [bgPattern, setBgPattern] = useState<BgPattern>(() => {
    if (typeof window === "undefined") return "dots";
    const stored = window.localStorage.getItem(BG_STORAGE_KEY);
    if (stored === "blank" || stored === "dots" || stored === "grid") return stored;
    return "dots";
  });

  // Active tool mirrored from Excalidraw
  const [activeTool, setActiveTool] = useState<ToolType>("selection");
  // Drawing state mirrored from Excalidraw appState
  const [activeColor, setActiveColor] = useState<string>("#1f2937");
  const [activeStrokeWidth, setActiveStrokeWidth] = useState<number>(2);
  const [activeOpacity, setActiveOpacity] = useState<number>(100);
  const [activeFillColor, setActiveFillColor] = useState<string>("transparent");
  const [activeFontSize, setActiveFontSize] = useState<number>(20);

  const debounceTimerRef = useRef<number | undefined>(undefined);
  const pendingSceneRef = useRef<Record<string, unknown> | null>(null);
  const excalidrawApiRef = useRef<ExcalidrawImperativeAPI | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  const prevToolRef = useRef<ToolType>("selection");
  const isMultiTouchRef = useRef(false);

  // RAF-throttled CSS-var updates
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

  // Register Telegram BackButton
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
        appState: { gridModeEnabled: isGrid, viewBackgroundColor: bg },
        captureUpdate: "NEVER",
      });
    } catch {
      // best-effort
    }
  }, [bgPattern]);

  // --------------------------------------------------------------------------
  // Bug #1: dot pattern follows pan/zoom via CSS vars (RAF-throttled)
  // This writes CSS vars directly — NO React setState so no re-render.
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
      // Mirror active tool
      if (appState?.activeTool?.type) {
        const t = appState.activeTool.type as ToolType;
        if (TOOLS.some((tool) => tool.type === t)) {
          setActiveTool(t);
        }
      }

      // Mirror drawing state (batched into a single setStates call via flushSync
      // is not needed — React batches these automatically in React 18)
      if (appState?.currentItemStrokeColor) {
        setActiveColor(appState.currentItemStrokeColor as string);
      }
      if (appState?.currentItemStrokeWidth !== undefined) {
        setActiveStrokeWidth(appState.currentItemStrokeWidth as number);
      }
      if (appState?.currentItemOpacity !== undefined) {
        setActiveOpacity(appState.currentItemOpacity as number);
      }
      if (appState?.currentItemBackgroundColor !== undefined) {
        setActiveFillColor((appState.currentItemBackgroundColor as string) || "transparent");
      }
      if (appState?.currentItemFontSize !== undefined) {
        setActiveFontSize(appState.currentItemFontSize as number);
      }

      // CSS var update for dot-pattern — no setState, pure DOM write
      if (appState?.scrollX !== undefined) {
        scrollStateRef.current = {
          scrollX: (appState.scrollX as number) ?? 0,
          scrollY: (appState.scrollY as number) ?? 0,
          zoom: (appState.zoom?.value as number) ?? 1,
        };
        scheduleCssVarUpdate();
      }

      // Debounce save
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

      // Buffer for flush-on-unmount
      void (async () => {
        const api = await getExcalidrawApi();
        const raw = api.serializeAsJSON(elements, appState, files, "database");
        pendingSceneRef.current = JSON.parse(raw) as Record<string, unknown>;
      })();
    },
    [boardId, scheduleCssVarUpdate],
  );

  // --------------------------------------------------------------------------
  // Bug #2: two-finger touch → hand tool for pinch/pan
  // --------------------------------------------------------------------------
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const handleTouchStart = (e: TouchEvent) => {
      if (e.touches.length >= 2 && !isMultiTouchRef.current) {
        isMultiTouchRef.current = true;
        const api = excalidrawApiRef.current;
        if (!api) return;
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
  }, [board]);

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
        // non-fatal
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
  // Toolbar actions (all memoised)
  // --------------------------------------------------------------------------

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

  const handleSelectColor = useCallback((hex: string) => {
    haptic("select");
    setActiveColor(hex);
    const api = excalidrawApiRef.current;
    if (!api) return;
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (api as any).updateScene({
        appState: { currentItemStrokeColor: hex },
        captureUpdate: "NEVER",
      });
    } catch {
      // best-effort
    }
  }, []);

  const handleStrokeWidthChange = useCallback((w: number) => {
    haptic("select");
    setActiveStrokeWidth(w);
    const api = excalidrawApiRef.current;
    if (!api) return;
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (api as any).updateScene({
        appState: { currentItemStrokeWidth: w, currentItemRoughness: 0 },
        captureUpdate: "NEVER",
      });
    } catch {
      // best-effort
    }
  }, []);

  const handleOpacityChange = useCallback((v: number) => {
    setActiveOpacity(v);
    const api = excalidrawApiRef.current;
    if (!api) return;
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (api as any).updateScene({
        appState: { currentItemOpacity: v },
        captureUpdate: "NEVER",
      });
    } catch {
      // best-effort
    }
  }, []);

  const handleFillColorChange = useCallback((hex: string | "transparent") => {
    haptic("select");
    setActiveFillColor(hex);
    const api = excalidrawApiRef.current;
    if (!api) return;
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (api as any).updateScene({
        appState: { currentItemBackgroundColor: hex === "transparent" ? "transparent" : hex },
        captureUpdate: "NEVER",
      });
    } catch {
      // best-effort
    }
  }, []);

  const handleFontSizeChange = useCallback((size: number) => {
    haptic("select");
    setActiveFontSize(size);
    const api = excalidrawApiRef.current;
    if (!api) return;
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (api as any).updateScene({
        appState: { currentItemFontSize: size },
        captureUpdate: "NEVER",
      });
    } catch {
      // best-effort
    }
  }, []);

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

  const showSettingsPanel = DRAW_TOOLS.has(activeTool);

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

        {/* ── Top-right: undo + zoom (float, no collision with bottom bar) ── */}
        <div className="pointer-events-auto absolute right-3 top-3 z-10 flex flex-col gap-1.5">
          {/* Undo */}
          <div className="flex flex-col gap-1 rounded-2xl bg-tg-bg/95 p-[5px] shadow-island backdrop-blur-xl ring-1 ring-black/[0.06] dark:ring-white/[0.06]">
            <button
              type="button"
              aria-label="Отменить"
              title="Отменить (Ctrl+Z)"
              onClick={handleUndo}
              className="ease-apple inline-flex h-9 w-9 items-center justify-center rounded-xl text-tg-text/70 transition-all duration-150 hover:bg-bento active:scale-90"
            >
              <Undo2 size={17} strokeWidth={2} aria-hidden />
            </button>
          </div>
          {/* Zoom */}
          <div className="flex flex-col gap-0.5 rounded-2xl bg-tg-bg/95 p-[5px] shadow-island backdrop-blur-xl ring-1 ring-black/[0.06] dark:ring-white/[0.06]">
            <button
              type="button"
              aria-label="Приблизить"
              title="Приблизить"
              onClick={() => handleZoom(0.2)}
              className="ease-apple inline-flex h-9 w-9 items-center justify-center rounded-xl text-tg-text/70 transition-all duration-150 hover:bg-bento active:scale-90"
            >
              <ZoomIn size={17} strokeWidth={2} aria-hidden />
            </button>
            <button
              type="button"
              aria-label="Сбросить масштаб"
              title="Сбросить масштаб"
              onClick={handleZoomReset}
              className="ease-apple inline-flex h-9 w-9 items-center justify-center rounded-xl text-tg-text/70 transition-all duration-150 hover:bg-bento active:scale-90"
            >
              <Maximize size={15} strokeWidth={2} aria-hidden />
            </button>
            <button
              type="button"
              aria-label="Отдалить"
              title="Отдалить"
              onClick={() => handleZoom(-0.2)}
              className="ease-apple inline-flex h-9 w-9 items-center justify-center rounded-xl text-tg-text/70 transition-all duration-150 hover:bg-bento active:scale-90"
            >
              <ZoomOut size={17} strokeWidth={2} aria-hidden />
            </button>
          </div>
        </div>

        {/* ── Bottom toolbar stack ── */}
        <div
          className="pointer-events-auto absolute bottom-0 left-0 right-0 z-10 flex flex-col items-center gap-2 px-3 pb-[calc(env(safe-area-inset-bottom,0px)+10px)] pt-2"
          aria-label="Панель инструментов"
        >
          {/* Settings panel — slides up when draw tool active */}
          <div
            className={
              "w-full max-w-[520px] transition-all duration-[200ms] " +
              (showSettingsPanel
                ? "translate-y-0 opacity-100 ease-[cubic-bezier(0.16,1,0.3,1)]"
                : "pointer-events-none translate-y-3 opacity-0 ease-[cubic-bezier(0.16,1,0.3,1)]")
            }
            style={{ willChange: "transform, opacity" }}
            aria-hidden={!showSettingsPanel}
          >
            {showSettingsPanel && (
              <SettingsPanel
                activeTool={activeTool}
                activeColor={activeColor}
                activeStrokeWidth={activeStrokeWidth}
                activeOpacity={activeOpacity}
                activeFillColor={activeFillColor}
                activeFontSize={activeFontSize}
                onColorChange={handleSelectColor}
                onStrokeWidthChange={handleStrokeWidthChange}
                onOpacityChange={handleOpacityChange}
                onFillColorChange={handleFillColorChange}
                onFontSizeChange={handleFontSizeChange}
              />
            )}
          </div>

          {/* Tool row — always visible */}
          <ToolRow
            tools={TOOLS}
            activeTool={activeTool}
            onSelect={handleSelectTool}
          />
        </div>
      </div>
    </div>
  );
}
