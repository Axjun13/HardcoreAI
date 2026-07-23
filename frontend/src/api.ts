import { authenticatedFetch, supabase } from "./auth";

const DEFAULT_BACKEND_URL = import.meta.env.DEV
  ? "http://127.0.0.1:62018"
  : window.location.origin;
const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || DEFAULT_BACKEND_URL;
let activeProjectId: string | null = null; // Default to null so Landing Page shows

async function responseError(res: Response): Promise<string> {
  const text = await res.text();
  try {
    const parsed = JSON.parse(text);
    return parsed.detail || parsed.message || text || `Request failed (${res.status})`;
  } catch {
    return text || `Request failed (${res.status})`;
  }
}

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
    if (!supabase) throw new Error("Supabase is not configured.");
    const { data, error } = await supabase
      .from("projects")
      .select("id,name,description,path,board_id,created_at,updated_at")
      .order("updated_at", { ascending: false });
    if (error) throw error;
    return (data ?? []).map((project) => ({
      ...project,
      id: String(project.id),
    }));
  },
  async listBoards() {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/boards`, { headers: {} });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
  async refreshBoards(query: string = "STM32") {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/boards/refresh?query=${encodeURIComponent(query)}`, {
      method: "POST",
      headers: {}
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
    const res = await authenticatedFetch(`${BACKEND_URL}/api/boards/refresh-all`, {
      method: "POST",
      headers: {}
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
  async addCustomBoard(payload: { id: string; mcu: string; label?: string; arch?: string }) {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/boards/custom`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload) });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
  async importStm32Metadata() {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/boards/stm32-data/import`, {
      method: "POST",
      headers: {} });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
  async getStm32MetadataStatus() {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/boards/stm32-data/status`, {
      headers: {} });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
  async getBoard(boardId: string) {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/boards/${boardId}`, { headers: {} });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
  async setProjectBoard(projectId: string, boardId: string) {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/boards/projects/${projectId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ board_id: boardId })
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
  async pickFolder(): Promise<string | null> {
  const res = await authenticatedFetch(`${BACKEND_URL}/api/pick-folder`, {
    method: "POST",
    headers: {}
  });
  if (!res.ok) throw new Error(await res.text());
  const data = await res.json();
  return data.path;
},

async createProject(
  name: string,
  description: string = "",
  path: string | null = null,
  boardId: string | null = null,
) {
  const res = await authenticatedFetch(`${BACKEND_URL}/api/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, description, path, board_id: boardId })
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
},

  async deleteProject(id: string) {
    if (!supabase) throw new Error("Supabase is not configured.");
    const { error } = await supabase
      .from("projects")
      .delete()
      .eq("id", Number(id));
    if (error) throw error;
    return true;
  },

  async renameProject(id: string, name: string) {
    if (!supabase) throw new Error("Supabase is not configured.");
    const { data, error } = await supabase
      .from("projects")
      .update({ name: name.trim(), updated_at: new Date().toISOString() })
      .eq("id", Number(id))
      .select("id,name,description,path,board_id,created_at,updated_at")
      .single();
    if (error) throw error;
    return { ...data, id: String(data.id) };
  },

  async getConversationHistory(projectId: string) {
    try {
      if (!supabase) throw new Error("Supabase is not configured.");
      const { data, error } = await supabase
        .from("conversations")
        .select("history")
        .eq("project_id", Number(projectId))
        .maybeSingle();
      if (error) throw error;
      return Array.isArray(data?.history) ? data.history : [];
    } catch (e) {
      console.warn("Failed to fetch conversation history, falling back to localStorage", e);
    }
    const local = localStorage.getItem(`chat_history_${projectId}`);
    return local ? JSON.parse(local) : [];
  },

  async saveConversationHistory(projectId: string, history: any[]) {
    try {
      if (!supabase) throw new Error("Supabase is not configured.");
      const { error } = await supabase.from("conversations").upsert({
        project_id: Number(projectId),
        history,
        updated_at: new Date().toISOString(),
      }, {
        onConflict: "project_id",
      });
      if (error) throw error;
      return history;
    } catch (e) {
      console.warn("Failed to save conversation history, saving to localStorage", e);
    }
    localStorage.setItem(`chat_history_${projectId}`, JSON.stringify(history));
    return history;
  },

  async deleteConversationHistory(projectId: string) {
    try {
      if (!supabase) throw new Error("Supabase is not configured.");
      const { error } = await supabase
        .from("conversations")
        .delete()
        .eq("project_id", Number(projectId));
      if (error) throw error;
      return true;
    } catch (e) {
      console.warn("Failed to delete conversation history, clearing localStorage", e);
    }
    localStorage.removeItem(`chat_history_${projectId}`);
    return true;
  },

  async getProjectFiles(id: string) {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${id}/files`, { headers: {} });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  // Real working-directory tree (includes .pio, untracked files, binaries).
  async getProjectTree(id: string) {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${id}/tree`, { headers: {} });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  // Read a single working-dir file's content on demand (for untracked/.pio files).
  async getDiskFile(id: string, path: string) {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${id}/disk-file?path=${encodeURIComponent(path)}`, {
      headers: {}
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async upsertFile(id: string, path: string, content: string, language: string = "c") {
    // The backend path is a path param, needs URL encoding if it has slashes, though FastAPI path:path handles it
    const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${id}/files/${path}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content, language })
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async deleteFile(id: string, path: string) {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${id}/files/${path}`, {
      method: "DELETE",
      headers: {}
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async searchWorkspace(projectId: string, query: string, include: string) {
    const response = await authenticatedFetch(
      `${BACKEND_URL}/api/projects/${projectId}/search`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, include }),
      },
    );
    if (!response.ok) throw new Error(await responseError(response));
    return response.json();
  },

  // --- Backend (Python FastAPI) ---

  async uploadRagDocument(file: File) {
    const formData = new FormData();
    formData.append("documents", file);
    const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${activeProjectId}/rag/upload`, {
      method: "POST",
      body: formData,
      headers: {}
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async listRagDocuments() {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${activeProjectId}/rag/documents`, {
      method: "GET",
      headers: {}
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async deleteRagDocument(filename: string) {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${activeProjectId}/rag/documents/${encodeURIComponent(filename)}`, {
      method: "DELETE",
      headers: {}
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async searchRag(query: string) {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${activeProjectId}/rag/search`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json" },
      body: JSON.stringify({ query })
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async scrapeUrl(url: string) {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${activeProjectId}/rag/scrape-url`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json" },
      body: JSON.stringify({ url })
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async scrapeSearch(query: string, numResults: number = 3) {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${activeProjectId}/rag/scrape-search`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json" },
      body: JSON.stringify({ query, num_results: numResults })
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async askAgent(query: string, conversationHistory?: any[], phase?: string, provider: string = "cloud", buildOutput: string = "", autoApprove: boolean = false, agentRunId: string = crypto.randomUUID()) {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${activeProjectId}/agent/solve`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json" },
      body: JSON.stringify({
        provider,
        problem: query,
        conversation_history: conversationHistory,
        phase: phase,
        build_output: buildOutput,
        auto_approve: autoApprove,
        agent_run_id: agentRunId })
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async getAgentProviders() {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/agent/providers`, {
      headers: {}
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async getGitInfo() {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${activeProjectId}/git/info`, {
      headers: {}
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async getGitStatus() {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${activeProjectId}/git/status`, {
      headers: {}
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async getGitLog(n: number = 50) {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${activeProjectId}/git/log?n=${n}`, {
      headers: {}
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async commitChanges(message: string) {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${activeProjectId}/git/commit`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json" },
      body: JSON.stringify({ message })
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async checkoutCommit(ref: string) {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${activeProjectId}/git/checkout`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ref })
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async checkoutHead() {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${activeProjectId}/git/checkout-head`, {
      method: "POST",
      headers: {}
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async getGitBranches() {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${activeProjectId}/git/branches`, {
      headers: {}
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async createGitBranch(name: string) {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${activeProjectId}/git/branches`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
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
    const res = await authenticatedFetch(url, {
      headers: {}
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
    const res = await authenticatedFetch(url, {
      headers: {}
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async buildProject() {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${activeProjectId}/build`, {
      method: "POST",
      headers: {}
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
    const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${activeProjectId}/build/stream`, {
      method: "POST",
      headers: {},
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
    const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${activeProjectId}/flash`, {
      method: "POST",
      headers: {}
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
    provider: string = "cloud",
    buildOutput: string = "",
    signal?: AbortSignal,
    autoApprove: boolean = false,
    agentRunId: string = crypto.randomUUID(),
  ) {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${activeProjectId}/agent/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json" },
      body: JSON.stringify({
        provider,
        problem: query,
        conversation_history: conversationHistory,
        phase: phase,
        build_output: buildOutput,
        auto_approve: autoApprove,
        agent_run_id: agentRunId }),
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
    const res = await authenticatedFetch(`${BACKEND_URL}/api/libraries?${params}`, {
      headers: {}
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async getLibraryCategories() {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/libraries/categories`, {
      headers: {}
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async getInstalledLibraries(projectId: string) {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${projectId}/libraries`, {
      headers: {}
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async installLibrary(projectId: string, libraryId?: string, gitUrl?: string) {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${projectId}/libraries/install`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ library_id: libraryId ?? null, git_url: gitUrl ?? null })
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async uninstallLibrary(projectId: string, libraryId: string) {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${projectId}/libraries/${encodeURIComponent(libraryId)}`, {
      method: "DELETE",
      headers: {}
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  // --- Component research / resolution ---

  async getComponentSchema() {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/components/schema`, {
      headers: {}
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async getComponentContext(projectId: string) {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${projectId}/components/context`, {
      headers: {}
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async resolveComponentContext(projectId: string, installLibraries = false) {
    const params = new URLSearchParams();
    if (installLibraries) params.set("install_libraries", "true");
    const query = params.toString();
    const res = await authenticatedFetch(
      `${BACKEND_URL}/api/projects/${projectId}/components/resolve${query ? `?${query}` : ""}`,
      {
        method: "POST",
        headers: {}
      }
    );
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  // --- Research / ideation flow ---

  async getResearchState(projectId: string) {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${projectId}/research`, {
      headers: {}
    });
    if (!res.ok) throw new Error(await responseError(res));
    return res.json();
  },

  async createResearchContext(projectId: string, title = "") {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${projectId}/research/contexts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title })
    });
    if (!res.ok) throw new Error(await responseError(res));
    return res.json();
  },

  async activateResearchContext(projectId: string, contextId: string) {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${projectId}/research/contexts/${contextId}/activate`, {
      method: "POST",
      headers: {}
    });
    if (!res.ok) throw new Error(await responseError(res));
    return res.json();
  },

  async deleteResearchContext(projectId: string, contextId: string) {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${projectId}/research/contexts/${contextId}`, {
      method: "DELETE",
      headers: {}
    });
    if (!res.ok) throw new Error(await responseError(res));
    return res.json();
  },

  async ideateResearch(projectId: string, idea: string, provider: string = "cloud", contextId?: string) {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${projectId}/research/ideate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ idea, provider, context_id: contextId })
    });
    if (!res.ok) throw new Error(await responseError(res));
    return res.json();
  },

  /** Stream a Research reply as provider text deltas over POSTed SSE. */
  async streamResearch(
    projectId: string,
    idea: string,
    provider: string,
    contextId: string | undefined,
    onEvent: (event: any) => void,
    signal?: AbortSignal
  ) {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${projectId}/research/ideate/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ idea, provider, context_id: contextId }),
      signal
    });
    if (!res.ok || !res.body) throw new Error(await responseError(res));

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let separator: number;
      while ((separator = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, separator);
        buffer = buffer.slice(separator + 2);
        const line = frame.split("\n").find(item => item.startsWith("data:"));
        if (!line) continue;
        try {
          onEvent(JSON.parse(line.slice(5).trim()));
        } catch (error) {
          console.warn("Failed to parse Research SSE frame", line, error);
        }
      }
    }
  },

  async selectResearchComponents(projectId: string, selectedComponentIds: string[], notes = "", installLibraries = false, contextId?: string) {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${projectId}/research/select`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ selected_component_ids: selectedComponentIds, notes, install_libraries: installLibraries, context_id: contextId })
    });
    if (!res.ok) throw new Error(await responseError(res));
    return res.json();
  },

  async advanceResearch(projectId: string, action = "confirm", selectedComponentIds: string[] = [], notes = "", message = "", provider = "deepseek", expectedStage = "") {
    const controller = new AbortController();
    // 45s was tuned for the quick stage transitions (ideation/component_selection/
    // revise). final_review's confirm additionally runs install_component_libraries()
    // synchronously server-side — a real PlatformIO package/toolchain install that
    // can take several minutes on first run — so it needs real headroom too.
    const timeoutMs = expectedStage === "final_review" ? 300_000 : 45_000;
    const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
    try {
      const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${projectId}/research/advance`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, selected_component_ids: selectedComponentIds, notes, message, provider, expected_stage: expectedStage }),
        signal: controller.signal
      });
      if (!res.ok) throw new Error(await responseError(res));
      return res.json();
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        throw new Error(
          `Confirmation timed out after ${Math.round(timeoutMs / 1000)}s — this step installs PlatformIO ` +
          "libraries and can be slow on first run. The latest workflow state has been reloaded; check " +
          "whether it already advanced before retrying."
        );
      }
      throw error;
    } finally {
      window.clearTimeout(timeout);
    }
  },

  /** Run sequential Phase-3 verification while receiving persisted TODO updates. */
  async streamResearchVerification(
    projectId: string,
    selectedComponentIds: string[],
    notes: string,
    provider: string,
    expectedStage: string,
    onEvent: (event: any) => void,
    signal?: AbortSignal
  ) {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${projectId}/research/verify/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: "confirm",
        selected_component_ids: selectedComponentIds,
        notes,
        provider,
        expected_stage: expectedStage }),
      signal });
    if (!res.ok || !res.body) throw new Error(await responseError(res));
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let separator: number;
      while ((separator = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, separator);
        buffer = buffer.slice(separator + 2);
        const line = frame.split("\n").find(item => item.startsWith("data:"));
        if (!line) continue;
        try {
          onEvent(JSON.parse(line.slice(5).trim()));
        } catch (error) {
          console.warn("Failed to parse Phase-3 SSE frame", line, error);
        }
      }
    }
  },

  async prepareResearchPhase3(projectId: string, installLibraries = true) {
    const params = new URLSearchParams();
    params.set("install_libraries", installLibraries ? "true" : "false");
    const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${projectId}/research/phase3?${params}`, {
      method: "POST",
      headers: {}
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async condenseResearch(projectId: string) {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${projectId}/research/condense`, {
      method: "POST",
      headers: {}
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async generateResearchReadme(projectId: string) {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${projectId}/research/readme`, {
      method: "POST",
      headers: {}
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  // ── Debug API ──────────────────────────────────────────────────────────────

  async startDebug(projectId: string, board: string) {
  if (!board) {
    throw new Error("No STM32 board selected");
  }

  const res = await authenticatedFetch(
    `${BACKEND_URL}/api/projects/${projectId}/debug/start`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json" },
      body: JSON.stringify({ board }) }
  );

  if (!res.ok) {
    throw new Error(await res.text());
  }

  return res.json();
},

  async stopDebug(projectId: string) {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${projectId}/debug/stop`, {
      method: "POST",
      headers: {} });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  /** Open an SSE stream of debug events. Call `controller.abort()` to close. */
  async streamDebug(
    projectId: string,
    onEvent: (event: Record<string, unknown>) => void,
    signal: AbortSignal,
  ): Promise<void> {
    const url = `${BACKEND_URL}/api/projects/${projectId}/debug/stream`;
    const response = await authenticatedFetch(url, { signal });
    if (!response.ok || !response.body) {
      throw new Error(await responseError(response));
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (!signal.aborted) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let separator: number;
      while ((separator = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, separator);
        buffer = buffer.slice(separator + 2);
        const dataLine = frame.split("\n").find((line) => line.startsWith("data:"));
        if (!dataLine) continue;
        try {
          onEvent(JSON.parse(dataLine.slice(5).trim()));
        } catch {
          // Ignore malformed diagnostic events and continue the stream.
        }
      }
    }
  },

  async setBreakpoint(projectId: string, file: string, line: number) {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${projectId}/debug/breakpoint`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file, line }) });
    if (!res.ok) throw new Error(await res.text());
    return res.json() as Promise<{ id: number; file: string; line: number; enabled: boolean }>;
  },

  async removeBreakpoint(projectId: string, bpId: number) {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${projectId}/debug/breakpoint/${bpId}`, {
      method: "DELETE",
      headers: {} });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async debugContinue(projectId: string) {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${projectId}/debug/continue`, {
      method: "POST",
      headers: {} });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async debugStepOver(projectId: string) {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${projectId}/debug/step-over`, {
      method: "POST",
      headers: {} });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async debugStepInto(projectId: string) {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${projectId}/debug/step-into`, {
      method: "POST",
      headers: {} });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async debugStepOut(projectId: string) {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${projectId}/debug/step-out`, {
      method: "POST",
      headers: {} });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async getDebugSnapshot(projectId: string) {
    const res = await authenticatedFetch(`${BACKEND_URL}/api/projects/${projectId}/debug/snapshot`, {
      headers: {} });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  } };
