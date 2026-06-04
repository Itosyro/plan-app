// The ONLY file that imports @excalidraw/excalidraw and its CSS.
// It is imported exclusively via React.lazy() from BoardCanvas so
// the entire Excalidraw bundle stays in its own chunk and never
// inflates the main bundle on cold load.
//
// Re-exports: serializeAsJSON and restore are also re-exported here
// so sibling board components can import them from this module via
// dynamic import and land in the same excalidraw chunk (not a separate
// one). This keeps the chunk boundary clean.

import { Excalidraw, serializeAsJSON, restore } from "@excalidraw/excalidraw";
import "@excalidraw/excalidraw/index.css";

export default Excalidraw;
export { serializeAsJSON, restore };
