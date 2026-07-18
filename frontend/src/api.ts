const DEFAULT_BACKEND_URL = import.meta.env.DEV
  ? "http://127.0.0.1:62018"
  : window.location.origin;
const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || DEFAULT_BACKEND_URL;
let activeProjectId: string | null = null; // Default to null so Landing Page shows

export const api = {
  setActiveProject(id: string) {
    activeProjectId = id;
  },

  getActiveProject(): string | null {
    return activeProjectId;
  },

  hasActiveProject(): boolean {
    return activeProjectId !== null;
  },
  
  // --- Projects API ---
  async getProjects() {
    const res = await fetch(`${BACKEND_URL}/api/projects`, { headers: { "Authorization": "Bearer TEST_TOKEN" } });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
  async listBoards() {
    const res = await fetch(`${BACKEND_URL}/api/boards`, { headers: { "Authorization": "Bearer TEST_TOKEN" } });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
  async refreshBoards(query: string = "STM32") {
    const res = await fetch(`${BACKEND_URL}/api/boards/refresh?query=${encodeURIComponent(query)}`, {
      method: "POST",
      headers: { "Authorization": "Bearer TEST_TOKEN" }
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
  async refreshAllBoards() {
    // Pulls STM32 + Arduino + ESP32 + ESP8266 + MKR + Zero from PlatformIO
    // in one call (backend: registry.refresh_all()). Previously the only
    // reachable refresh route defaulted to STM32 alone, so the Arduino/
    // ESP/SAMD side of the catalog could never grow past the hand-seeded
    // boards from the UI.
    const res = await fetch(`${BACKEND_URL}/api/boards/refresh-all`, {
      method: "POST",
      headers: { "Authorization": "Bearer TEST_TOKEN" }
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
  async addCustomBoard(payload: { id: string; mcu: string; label?: string; arch?: string }) {
    const res = await fetch(`${BACKEND_URL}/api/boards/custom`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Authorization": "Bearer TEST_TOKEN" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
  async importStm32Metadata() {
    const res = await fetch(`${BACKEND_URL}/api/boards/stm32-data/import`, {
      method: "POST",
      headers: { "Authorization": "Bearer TEST_TOKEN" },
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
  async getStm32MetadataStatus() {
    const res = await fetch(`${BACKEND_URL}/api/boards/stm32-data/status`, {
      headers: { "Authorization": "Bearer TEST_TOKEN" },
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
  async getBoard(boardId: string) {
    const res = await fetch(`${BACKEND_URL}/api/boards/${boardId}`, { headers: { "Authorization": "Bearer TEST_TOKEN" } });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
  async setProjectBoard(projectId: string, boardId: string) {
    const res = await fetch(`${BACKEND_URL}/api/boards/projects/${projectId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", "Authorization": "Bearer TEST_TOKEN" },
      body: JSON.stringify({ board_id: boardId })
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
  async pickFolder(): Promise<string | null> {
  const res = await fetch(`${BACKEND_URL}/api/pick-folder`, {
    method: "POST",
    headers: { "Authorization": "Bearer TEST_TOKEN" }
  });
  if (!res.ok) throw new Error(await res.text());
  const data = await res.json();
  return data.path;
},

async createProject(name: string, description: string = "", path: string | null = null) {
  const res = await fetch(`${BACKEND_URL}/api/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "Authorization": "Bearer TEST_TOKEN" },
    body: JSON.stringify({ name, description, path })
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
},

  async deleteProject(id: string) {
    const res = await fetch(`${BACKEND_URL}/api/projects/${id}`, {
      method: "DELETE",
      headers: { "Authorization": "Bearer TEST_TOKEN" }
    });
    if (!res.ok) throw new Error(await res.text());
    return true;
  },

  async renameProject(id: string, name: string) {
    try {
      const res = await fetch(`${BACKEND_URL}/api/projects/${id}/rename`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Authorization": "Bearer TEST_TOKEN" },
        body: JSON.stringify({ name })
      });
      if (res.ok) return await res.json();
    } catch (e) {
      console.warn("Failed to rename project on backend, falling back to local rename", e);
    }
    return { id, name };
  },

  async getConversationHistory(projectId: string) {
    try {
      const res = await fetch(`${BACKEND_URL}/api/projects/${projectId}/conversations`, {
        headers: { "Authorization": "Bearer TEST_TOKEN" }
      });
      if (res.ok) return await res.json();
    } catch (e) {
      console.warn("Failed to fetch conversation history, falling back to localStorage", e);
    }
    const local = localStorage.getItem(`chat_history_${projectId}`);
    return local ? JSON.parse(local) : [];
  },

  async saveConversationHistory(projectId: string, history: any[]) {
    try {
      const res = await fetch(`${BACKEND_URL}/api/projects/${projectId}/conversations`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Authorization": "Bearer TEST_TOKEN" },
        body: JSON.stringify({ history })
      });
      if (res.ok) return await res.json();
    } catch (e) {
      console.warn("Failed to save conversation history, saving to localStorage", e);
    }
    localStorage.setItem(`chat_history_${projectId}`, JSON.stringify(history));
    return history;
  },

  async deleteConversationHistory(projectId: string) {
    try {
      const res = await fetch(`${BACKEND_URL}/api/projects/${projectId}/conversations`, {
        method: "DELETE",
        headers: { "Authorization": "Bearer TEST_TOKEN" }
      });
      if (res.ok) return true;
    } catch (e) {
      console.warn("Failed to delete conversation history, clearing localStorage", e);
    }
    localStorage.removeItem(`chat_history_${projectId}`);
    return true;
  },

  async getProjectFiles(id: string) {
    const res = await fetch(`${BACKEND_URL}/api/projects/${id}/files`, { headers: { "Authorization": "Bearer TEST_TOKEN" } });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  // Real working-directory tree (includes .pio, untracked files, binaries).
  async getProjectTree(id: string) {
    const res = await fetch(`${BACKEND_URL}/api/projects/${id}/tree`, { headers: { "Authorization": "Bearer TEST_TOKEN" } });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  // Read a single working-dir file's content on demand (for untracked/.pio files).
  async getDiskFile(id: string, path: string) {
    const res = await fetch(`${BACKEND_URL}/api/projects/${id}/disk-file?path=${encodeURIComponent(path)}`, {
      headers: { "Authorization": "Bearer TEST_TOKEN" }
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async upsertFile(id: string, path: string, content: string, language: string = "c") {
    // The backend path is a path param, needs URL encoding if it has slashes, though FastAPI path:path handles it
    const res = await fetch(`${BACKEND_URL}/api/projects/${id}/files/${path}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", "Authorization": "Bearer TEST_TOKEN" },
      body: JSON.stringify({ content, language })
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async deleteFile(id: string, path: string) {
    const res = await fetch(`${BACKEND_URL}/api/projects/${id}/files/${path}`, {
      method: "DELETE",
      headers: { "Authorization": "Bearer TEST_TOKEN" }
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  // --- Backend (Python FastAPI) ---
  
  async uploadRagDocument(file: File) {
    const formData = new FormData();
    formData.append("documents", file);
    const res = await fetch(`${BACKEND_URL}/api/projects/${activeProjectId}/rag/upload`, {
      method: "POST",
      body: formData,
      headers: {
        "Authorization": "Bearer TEST_TOKEN"
      }
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async listRagDocuments() {
    const res = await fetch(`${BACKEND_URL}/api/projects/${activeProjectId}/rag/documents`, {
      method: "GET",
      headers: { "Authorization": "Bearer TEST_TOKEN" }
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async deleteRagDocument(filename: string) {
    const res = await fetch(`${BACKEND_URL}/api/projects/${activeProjectId}/rag/documents/${encodeURIComponent(filename)}`, {
      method: "DELETE",
      headers: { "Authorization": "Bearer TEST_TOKEN" }
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async searchRag(query: string) {
    const res = await fetch(`${BACKEND_URL}/api/projects/${activeProjectId}/rag/search`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": "Bearer TEST_TOKEN"
      },
      body: JSON.stringify({ query })
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async scrapeUrl(url: string) {
    const res = await fetch(`${BACKEND_URL}/api/projects/${activeProjectId}/rag/scrape-url`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": "Bearer TEST_TOKEN"
      },
      body: JSON.stringify({ url })
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async scrapeSearch(query: string, numResults: number = 3) {
    const res = await fetch(`${BACKEND_URL}/api/projects/${activeProjectId}/rag/scrape-search`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": "Bearer TEST_TOKEN"
      },
      body: JSON.stringify({ query, num_results: numResults })
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async askAgent(query: string, conversationHistory?: any[], phase?: string, provider: string = "openrouter", buildOutput: string = "", autoApprove: boolean = false) {
    const res = await fetch(`${BACKEND_URL}/api/projects/${activeProjectId}/agent/solve`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": "Bearer TEST_TOKEN"
      },
      body: JSON.stringify({
        provider,
        problem: query,
        conversation_history: conversationHistory,
        phase: phase,
        build_output: buildOutput,
        auto_approve: autoApprove
      })
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async getAgentProviders() {
    const res = await fetch(`${BACKEND_URL}/api/agent/providers`, {
      headers: { "Authorization": "Bearer TEST_TOKEN" }
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async getGitInfo() {
    const res = await fetch(`${BACKEND_URL}/api/projects/${activeProjectId}/git/info`, {
      headers: { "Authorization": "Bearer TEST_TOKEN" }
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async getGitStatus() {
    const res = await fetch(`${BACKEND_URL}/api/projects/${activeProjectId}/git/status`, {
      headers: {
        "Authorization": "Bearer TEST_TOKEN"
      }
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async getGitLog(n: number = 50) {
    const res = await fetch(`${BACKEND_URL}/api/projects/${activeProjectId}/git/log?n=${n}`, {
      headers: { "Authorization": "Bearer TEST_TOKEN" }
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async commitChanges(message: string) {
    const res = await fetch(`${BACKEND_URL}/api/projects/${activeProjectId}/git/commit`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": "Bearer TEST_TOKEN"
      },
      body: JSON.stringify({ message })
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async checkoutCommit(ref: string) {
    const res = await fetch(`${BACKEND_URL}/api/projects/${activeProjectId}/git/checkout`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Authorization": "Bearer TEST_TOKEN" },
      body: JSON.stringify({ ref })
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async checkoutHead() {
    const res = await fetch(`${BACKEND_URL}/api/projects/${activeProjectId}/git/checkout-head`, {
      method: "POST",
      headers: { "Authorization": "Bearer TEST_TOKEN" }
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async getGitBranches() {
    const res = await fetch(`${BACKEND_URL}/api/projects/${activeProjectId}/git/branches`, {
      headers: { "Authorization": "Bearer TEST_TOKEN" }
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async createGitBranch(name: string) {
    const res = await fetch(`${BACKEND_URL}/api/projects/${activeProjectId}/git/branches`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Authorization": "Bearer TEST_TOKEN" },
      body: JSON.stringify({ name })
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  // --- Hardware: build / flash / device detection ---

  async getDeviceStatus(projectId?: string) {
    const url = projectId
      ? `${BACKEND_URL}/api/device/status?project_id=${projectId}`
      : `${BACKEND_URL}/api/device/status`;
    const res = await fetch(url, {
      headers: { "Authorization": "Bearer TEST_TOKEN" }
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  // Generic chip-ID probe: ignores any selected board, reads the connected
  // chip's DBGMCU DEV_ID, and returns { detected_family, suggested_boards }.
  async detectConnectedBoard(projectId?: string) {
    const url = projectId
      ? `${BACKEND_URL}/api/device/detect?project_id=${projectId}`
      : `${BACKEND_URL}/api/device/detect`;
    const res = await fetch(url, {
      headers: { "Authorization": "Bearer TEST_TOKEN" }
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async buildProject() {
    const res = await fetch(`${BACKEND_URL}/api/projects/${activeProjectId}/build`, {
      method: "POST",
      headers: { "Authorization": "Bearer TEST_TOKEN" }
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  /**
   * Stream a real PlatformIO build over SSE. Calls onEvent for each frame:
   *   {type:"status"|"line", text} during the build, then
   *   {type:"done", success, returncode, firmware_path, duration_s, output}.
   * Resolves when the stream closes.
   */
  async streamBuild(onEvent: (event: any) => void, signal?: AbortSignal) {
    const res = await fetch(`${BACKEND_URL}/api/projects/${activeProjectId}/build/stream`, {
      method: "POST",
      headers: { "Authorization": "Bearer TEST_TOKEN" },
      signal
    });
    if (!res.ok || !res.body) throw new Error(await res.text());

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let sep: number;
      while ((sep = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        const line = frame.split("\n").find(l => l.startsWith("data:"));
        if (!line) continue;
        const json = line.slice(5).trim();
        if (!json) continue;
        try {
          onEvent(JSON.parse(json));
        } catch (e) {
          console.warn("Failed to parse build SSE frame", json, e);
        }
      }
    }
  },

  async flashProject() {
    const res = await fetch(`${BACKEND_URL}/api/projects/${activeProjectId}/flash`, {
      method: "POST",
      headers: { "Authorization": "Bearer TEST_TOKEN" }
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  /**
   * Stream the agent run over SSE. Calls onEvent for each parsed event
   * ({type: "think"|"call"|"code"|"result"|"question"|"plan"|"note"|"final"|"done"|"error", ...}).
   * Uses fetch + a ReadableStream reader (not EventSource) so we can POST the
   * conversation payload. Returns when the stream closes.
   */
  async streamAgent(
    query: string,
    onEvent: (event: any) => void,
    conversationHistory?: any[],
    phase?: string,
    provider: string = "openrouter",
    buildOutput: string = "",
    signal?: AbortSignal,
    autoApprove: boolean = false
  ) {
    const res = await fetch(`${BACKEND_URL}/api/projects/${activeProjectId}/agent/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": "Bearer TEST_TOKEN"
      },
      body: JSON.stringify({
        provider,
        problem: query,
        conversation_history: conversationHistory,
        phase: phase,
        build_output: buildOutput,
        auto_approve: autoApprove
      }),
      signal
    });
    if (!res.ok || !res.body) throw new Error(await res.text());

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // SSE frames are separated by a blank line; each frame has "data: <json>".
      let sep: number;
      while ((sep = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        const line = frame.split("\n").find(l => l.startsWith("data:"));
        if (!line) continue;
        const json = line.slice(5).trim();
        if (!json) continue;
        try {
          onEvent(JSON.parse(json));
        } catch (e) {
          console.warn("Failed to parse SSE frame", json, e);
        }
      }
    }
  },

  // --- Library Manager ---

  async getAvailableLibraries(search: string = "", category: string = "") {
    const params = new URLSearchParams();
    if (search) params.set("search", search);
    if (category) params.set("category", category);
    const res = await fetch(`${BACKEND_URL}/api/libraries?${params}`, {
      headers: { "Authorization": "Bearer TEST_TOKEN" }
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async getLibraryCategories() {
    const res = await fetch(`${BACKEND_URL}/api/libraries/categories`, {
      headers: { "Authorization": "Bearer TEST_TOKEN" }
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async getInstalledLibraries(projectId: string) {
    const res = await fetch(`${BACKEND_URL}/api/projects/${projectId}/libraries`, {
      headers: { "Authorization": "Bearer TEST_TOKEN" }
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async installLibrary(projectId: string, libraryId?: string, gitUrl?: string) {
    const res = await fetch(`${BACKEND_URL}/api/projects/${projectId}/libraries/install`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Authorization": "Bearer TEST_TOKEN" },
      body: JSON.stringify({ library_id: libraryId ?? null, git_url: gitUrl ?? null })
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async uninstallLibrary(projectId: string, libraryId: string) {
    const res = await fetch(`${BACKEND_URL}/api/projects/${projectId}/libraries/${encodeURIComponent(libraryId)}`, {
      method: "DELETE",
      headers: { "Authorization": "Bearer TEST_TOKEN" }
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  // --- Component research / resolution ---

  async getComponentSchema() {
    const res = await fetch(`${BACKEND_URL}/api/components/schema`, {
      headers: { "Authorization": "Bearer TEST_TOKEN" }
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async getComponentContext(projectId: string) {
    const res = await fetch(`${BACKEND_URL}/api/projects/${projectId}/components/context`, {
      headers: { "Authorization": "Bearer TEST_TOKEN" }
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async resolveComponentContext(projectId: string, installLibraries = false) {
    const params = new URLSearchParams();
    if (installLibraries) params.set("install_libraries", "true");
    const query = params.toString();
    const res = await fetch(
      `${BACKEND_URL}/api/projects/${projectId}/components/resolve${query ? `?${query}` : ""}`,
      {
        method: "POST",
        headers: { "Authorization": "Bearer TEST_TOKEN" }
      }
    );
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  // --- Research / ideation flow ---

  async getResearchState(projectId: string) {
    const res = await fetch(`${BACKEND_URL}/api/projects/${projectId}/research`, {
      headers: { "Authorization": "Bearer TEST_TOKEN" }
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async ideateResearch(projectId: string, idea: string, provider: string = "deepseek") {
    const res = await fetch(`${BACKEND_URL}/api/projects/${projectId}/research/ideate`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Authorization": "Bearer TEST_TOKEN" },
      body: JSON.stringify({ idea, provider })
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async selectResearchComponents(projectId: string, selectedComponentIds: string[], notes = "", installLibraries = false) {
    const res = await fetch(`${BACKEND_URL}/api/projects/${projectId}/research/select`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Authorization": "Bearer TEST_TOKEN" },
      body: JSON.stringify({ selected_component_ids: selectedComponentIds, notes, install_libraries: installLibraries })
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async prepareResearchPhase3(projectId: string, installLibraries = true) {
    const params = new URLSearchParams();
    params.set("install_libraries", installLibraries ? "true" : "false");
    const res = await fetch(`${BACKEND_URL}/api/projects/${projectId}/research/phase3?${params}`, {
      method: "POST",
      headers: { "Authorization": "Bearer TEST_TOKEN" }
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async generateResearchReadme(projectId: string) {
    const res = await fetch(`${BACKEND_URL}/api/projects/${projectId}/research/readme`, {
      method: "POST",
      headers: { "Authorization": "Bearer TEST_TOKEN" }
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  // ── Debug API ──────────────────────────────────────────────────────────────

  async startDebug(projectId: string, board: string) {
  if (!board) {
    throw new Error("No STM32 board selected");
  }

  const res = await fetch(
    `${BACKEND_URL}/api/projects/${projectId}/debug/start`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": "Bearer TEST_TOKEN",
      },
      body: JSON.stringify({ board }),
    }
  );

  if (!res.ok) {
    throw new Error(await res.text());
  }

  return res.json();
},

  async stopDebug(projectId: string) {
    const res = await fetch(`${BACKEND_URL}/api/projects/${projectId}/debug/stop`, {
      method: "POST",
      headers: { "Authorization": "Bearer TEST_TOKEN" },
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  /** Open an SSE stream of debug events. Call `controller.abort()` to close. */
  streamDebug(
    projectId: string,
    onEvent: (event: Record<string, unknown>) => void,
    signal: AbortSignal,
  ): EventSource | null {
    // Use EventSource for SSE; it auto-reconnects on network drops
    const url = `${BACKEND_URL}/api/projects/${projectId}/debug/stream`;
    try {
      // EventSource does not support custom headers, so we embed the token
      // via a query param that the backend accepts in dev mode.
      const es = new EventSource(url);
      es.onmessage = (e) => {
        try {
          onEvent(JSON.parse(e.data));
        } catch {
          // ignore parse errors
        }
      };
      es.onerror = () => es.close();
      signal.addEventListener("abort", () => es.close());
      return es;
    } catch {
      return null;
    }
  },

  async setBreakpoint(projectId: string, file: string, line: number) {
    const res = await fetch(`${BACKEND_URL}/api/projects/${projectId}/debug/breakpoint`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Authorization": "Bearer TEST_TOKEN" },
      body: JSON.stringify({ file, line }),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json() as Promise<{ id: number; file: string; line: number; enabled: boolean }>;
  },

  async removeBreakpoint(projectId: string, bpId: number) {
    const res = await fetch(`${BACKEND_URL}/api/projects/${projectId}/debug/breakpoint/${bpId}`, {
      method: "DELETE",
      headers: { "Authorization": "Bearer TEST_TOKEN" },
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async debugContinue(projectId: string) {
    const res = await fetch(`${BACKEND_URL}/api/projects/${projectId}/debug/continue`, {
      method: "POST",
      headers: { "Authorization": "Bearer TEST_TOKEN" },
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async debugStepOver(projectId: string) {
    const res = await fetch(`${BACKEND_URL}/api/projects/${projectId}/debug/step-over`, {
      method: "POST",
      headers: { "Authorization": "Bearer TEST_TOKEN" },
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async debugStepInto(projectId: string) {
    const res = await fetch(`${BACKEND_URL}/api/projects/${projectId}/debug/step-into`, {
      method: "POST",
      headers: { "Authorization": "Bearer TEST_TOKEN" },
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async debugStepOut(projectId: string) {
    const res = await fetch(`${BACKEND_URL}/api/projects/${projectId}/debug/step-out`, {
      method: "POST",
      headers: { "Authorization": "Bearer TEST_TOKEN" },
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async getDebugSnapshot(projectId: string) {
    const res = await fetch(`${BACKEND_URL}/api/projects/${projectId}/debug/snapshot`, {
      headers: { "Authorization": "Bearer TEST_TOKEN" },
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
};

