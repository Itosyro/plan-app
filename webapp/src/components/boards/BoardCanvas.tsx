// Full-screen Excalidraw canvas for a single named board.
//
// Layout:
//   • Fixed-position fullscreen overlay (above tab stack).
//   • Sticky header: back arrow ← + editable board name (PATCH on blur)
//     + save-status hint.
//   • Lazy-loaded <Excalidraw> filling the remaining height.
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
import { ChevronLeft } from "lucide-react";
import { apiClient } from "../../api/client";
import { haptic, getWebApp } from "../../lib/telegram";
import { navigate } from "../../lib/router";
import type { BoardDetail } from "../../types";
// Excalidraw's granular types are not re-exported from the main package entry.
// We import them from the internal types module. The package.json exports map
// exposes "./*" → "./dist/types/excalidraw/*.d.ts" for TypeScript resolution.
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
// and don't unify with the local `any` scene-shape aliases above. We
// don't need full prop type-checking on a third-party canvas embed —
// the runtime contract is what matters, and it's verified in the browser.
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

export function BoardCanvas({ boardId }: Props) {
  const [board, setBoard] = useState<BoardDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [nameDraft, setNameDraft] = useState("");
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("idle");

  // Pending debounced scene save — cleared on flush or unmount.
  const debounceTimerRef = useRef<number | undefined>(undefined);
  // The latest scene payload to be sent on flush.
  const pendingSceneRef = useRef<Record<string, unknown> | null>(null);
  // Excalidraw imperative API handle (not needed for controlled onChange flow,
  // but useful for optional future imperative calls).
  const excalidrawApiRef = useRef<ExcalidrawImperativeAPI | null>(null);

  const wa = getWebApp();
  const tgTheme = wa?.colorScheme ?? "light";

  // Container height: use Telegram's stable viewport height to avoid the
  // iOS address-bar / keyboard resizing the canvas unexpectedly.
  const containerHeight = useMemo(() => {
    const stable = wa?.viewportStableHeight;
    if (stable && stable > 0) return stable;
    return window.innerHeight;
  }, [wa]);

  // Load the board on mount.
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

  // Flush any pending debounced save to the server synchronously.
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

  // Flush on unmount.
  useEffect(() => {
    return () => {
      flushSave();
    };
  }, [flushSave]);

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
      // Revert to server name on failure.
      setNameDraft(board.name);
    }
  }, [board, nameDraft, boardId]);

  // Called by Excalidraw on every change; we debounce and serialize.
  const handleChange = useCallback(
    (
      elements: readonly ExcalidrawElement[],
      appState: AppState,
      files: BinaryFiles,
    ) => {
      if (debounceTimerRef.current !== undefined) {
        window.clearTimeout(debounceTimerRef.current);
      }

      debounceTimerRef.current = window.setTimeout(() => {
        debounceTimerRef.current = undefined;
        setSaveStatus("saving");
        void (async () => {
          try {
            const api = await getExcalidrawApi();
            const raw = api.serializeAsJSON(
              elements,
              appState,
              files,
              "database",
            );
            const json = JSON.parse(raw) as Record<string, unknown>;
            pendingSceneRef.current = null;
            await apiClient.patchBoard(boardId, { scene_json: json });
            setSaveStatus("saved");
            // Clear the "saved" hint after 2s.
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
    [boardId],
  );

  // Build initialData from the stored scene_json using restore().
  // This is computed once from the loaded board; after that Excalidraw
  // is uncontrolled.
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
      if (!board.scene_json) {
        setInitialData(undefined);
        setInitialDataReady(true);
        return;
      }
      try {
        const api = await getExcalidrawApi();
        const scene = api.restore(board.scene_json, null, null);
        setInitialData({
          elements: scene.elements,
          appState: scene.appState,
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

  const saveHint =
    saveStatus === "saving"
      ? "сохраняю…"
      : saveStatus === "saved"
        ? "сохранено ✓"
        : saveStatus === "error"
          ? "ошибка сохранения"
          : "";

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

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col bg-tg-bg"
      style={{ height: containerHeight }}
    >
      {/* Header */}
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
      </header>

      {/* Canvas area */}
      <div
        className="relative min-h-0 flex-1"
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
      </div>
    </div>
  );
}
