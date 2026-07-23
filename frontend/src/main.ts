import { mount } from "svelte";
import App from "./App.svelte";
import "./App.css";
import { initializeAuth } from "./auth";

// Wire up Monaco's web workers for Vite. Without this, monaco-editor can't
// spawn its workers and falls back to running worker code on the main thread
// (the "Could not create web worker(s)" warning + UI freezes).
import editorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker";
import jsonWorker from "monaco-editor/esm/vs/language/json/json.worker?worker";
import cssWorker from "monaco-editor/esm/vs/language/css/css.worker?worker";
import htmlWorker from "monaco-editor/esm/vs/language/html/html.worker?worker";
import tsWorker from "monaco-editor/esm/vs/language/typescript/ts.worker?worker";

self.MonacoEnvironment = {
  getWorker(_workerId: string, label: string) {
    if (label === "json") return new jsonWorker();
    if (label === "css" || label === "scss" || label === "less") return new cssWorker();
    if (label === "html" || label === "handlebars" || label === "razor") return new htmlWorker();
    if (label === "typescript" || label === "javascript") return new tsWorker();
    return new editorWorker();
  },
};

await initializeAuth();

mount(App, {
  target: document.getElementById("root")!   // <-- the exclamation ensures a non‑null target
});
