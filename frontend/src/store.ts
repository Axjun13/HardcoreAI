import { writable } from "svelte/store";
import { api } from "./api";
import type { GraphNode } from "./gitGraph";

export interface FileItem {
  name: string;
  path: string;
  isFolder: boolean;
  isBinary?: boolean;
  children?: FileItem[];
}

export interface RegisterItem {
  name: string;
  value: string;
  description: string;
  bits?: { name: string; value: number; range: string; description: string }[];
}

// ── Debug interfaces ──────────────────────────────────────────────────────────
export interface DebugBreakpointItem {
  id: number | null;
  file: string;
  line: number;
}

export interface DebugRegisterItem {
  name: string;
  number: number;
  value: string;
}

export interface DebugFrameItem {
  level: number;
  function: string;
  file: string | null;
  line: number | null;
  address?: string | null;
}

export interface DebugLocalItem {
  name: string;
  value: string;
  type: string;
}


export interface AgentStep {
  kind: "think" | "call" | "code" | "result" | "note" | "error" | "proposal";
  text?: string;            // think / note / error text
  name?: string;            // tool name for call / result
  args?: Record<string, any>; // call args
  path?: string;            // code card / proposal target file
  code?: string;            // code card body / proposed new content
  result?: string;          // tool result text
  old?: string;             // proposal: previous file content (for diff)
  deleted?: boolean;        // proposal: file was deleted
  decision?: "pending" | "allowed" | "rejected"; // proposal approval state
}

// Synthetic tab-id prefix for proposal diff tabs. A tab whose id starts with
// this is rendered as a Monaco diff editor (original vs proposed) rather than a
// normal file editor. The real file path follows the prefix.
export const DIFF_PREFIX = "diff://";

// A staged file change awaiting the user's Allow/Reject in the chat.
export interface FileProposal {
  path: string;
  language: string;
  old: string;              // baseline content ("" if newly created)
  code: string;             // proposed new content ("" if deleted)
  deleted?: boolean;
  created?: boolean;
  decision: "pending" | "allowed" | "rejected";
}

export interface ChatMessage {
  id: string;
  sender: "user" | "ai";
  text: string;
  timestamp: string;
  status?: string;
  plan?: string;
  options?: string[];
  phase?: string;
  inputType?: "radio" | "checkbox" | "select" | "buttons" | "text";
  selectedValue?: string | string[];
  submitted?: boolean;
  // --- streaming agent panel ---
  steps?: AgentStep[];       // ordered live events (think/call/code/result/...)
  thinking?: string;         // current/last think text (streamed live)
  thinkingDone?: boolean;    // true once the run produced a non-think event
  thinkingCollapsed?: boolean; // user/auto collapse state for the think block
  streaming?: boolean;       // true while the SSE run is in flight
  proposals?: FileProposal[]; // staged file changes awaiting Allow/Reject
}

export interface PlotDataPoint {
  time: string;
  temp: number;
  voltage: number;
  current: number;
}

export interface PinConfig {
  pin: string;
  signal: string;
  mode: string;
  speed: string;
  pull: string;
  label: string;
  af: string;
  enabled: boolean;
}

export interface RagDocument {
  id: string;
  name: string;
  size: string;
  chunks: number;
  status: "Uploading..." | "Chunking..." | "Embedding..." | "Ready in Database";
  tokens: number;
  /** "pdf" for uploaded files, "web" for URL-scraped pages */
  source?: "pdf" | "web";
  /** Original URL for web-scraped documents, empty string otherwise */
  url?: string;
}

export interface GitCommit {
  hash: string;
  short_hash: string;
  subject: string;
  author_name: string;
  author_email: string;
  date_iso: string;
  date_relative: string;
  refs: string[];
  parents: string[];
}

export interface GitInfo {
  is_repo: boolean;
  branch: string | null;
  detached: boolean;
  head_hash: string | null;
  short_hash: string | null;
}

export interface BoardMeta {
  id: string;
  label: string;
  vendor?: string;
  mcu?: string;
  family?: string;
  core?: string;
  arch?: string;
  pio_platform?: string | null;
  flash_bytes?: number;
  ram_bytes?: number;
  f_cpu_hz?: number;
  hal_header?: string;
  upload_protocol?: string;
  debug_tool?: string;
  avrdude_programmer?: string | null;
  openocd_target?: string;
  openocd_interface?: string;
  frameworks?: string[];
  full_pinout?: string[] | null;
  package_pins?: number | null;
  pinout_status?: "verified" | "package_count_only" | "unavailable" | string;
  pin_metadata?: {
    name: string;
    raw_name?: string;
    position?: number;
    type?: string;
    signals?: { name: string; af?: string | null; io_modes?: string }[];
  }[] | null;
}

// Pin configuration data — STM32F103C8T6 Blue Pill (LQFP48) pinout.
const bluePillPins = [
  "VBAT", "PC13", "PC14", "PC15", "PD0", "PD1", "NRST", "VSSA",
  "VDDA", "PA0", "PA1", "PA2", "PA3", "PA4", "PA5", "PA6",
  "PA7", "PB0", "PB1", "PB2", "PB10", "PB11", "VSS", "VDD",
  "PB12", "PB13", "PB14", "PB15", "PA8", "PA9", "PA10", "PA11",
  "PA12", "PA13", "VSS", "VDD", "PA14", "PA15", "PB3", "PB4",
  "PB5", "PB6", "PB7", "BOOT0", "PB8", "PB9", "VSS", "VDD",
];

const initialPins: PinConfig[] = bluePillPins.map((pin, index) => {
  const defaults: Partial<PinConfig> = {};
  // Blue Pill onboard LED is PC13 (active LOW).
  if (pin === "PC13") Object.assign(defaults, { signal: "GPIO_Output", mode: "Output Push Pull", label: "LED (PC13)", enabled: true });
  if (pin === "PA9") Object.assign(defaults, { signal: "USART1_TX", mode: "Alternate Function", label: "UART TX", af: "AF", enabled: true });
  if (pin === "PA10") Object.assign(defaults, { signal: "USART1_RX", mode: "Alternate Function", label: "UART RX", af: "AF", enabled: true });
  if (pin === "PB6") Object.assign(defaults, { signal: "I2C1_SCL", mode: "Alternate Function", label: "I2C SCL", af: "AF", enabled: true });
  if (pin === "PB7") Object.assign(defaults, { signal: "I2C1_SDA", mode: "Alternate Function", label: "I2C SDA", af: "AF", enabled: true });

  const isPower = ["VSS", "VDD", "VBAT", "VDDA", "VSSA", "VCAP"].includes(pin);
  const isSystem = ["NRST", "BOOT0", "PD0", "PD1"].includes(pin);

  return {
    pin,
    signal: defaults.signal ?? (isPower ? pin : isSystem ? "System" : "Unassigned"),
    mode: defaults.mode ?? (isPower ? "Power" : isSystem ? "System" : "Input Floating"),
    speed: defaults.speed ?? "Low",
    pull: defaults.pull ?? "No pull-up/down",
    label: defaults.label ?? `Pin ${index + 1}`,
    af: defaults.af ?? "-",
    enabled: defaults.enabled ?? (isPower || isSystem),
  };
});
function buildPinsFromDevice(device: any): PinConfig[] {
  // No verified pinout for this board (device.full_pinout is null/empty from
  // boards/pinout.py) — return [] rather than silently substituting the Blue
  // Pill's 48-pin layout under a different board's name. Callers (the
  // Pinout tab) show an explicit "not verified" state when pins is empty.
  const metadata: BoardMeta["pin_metadata"] = device?.pin_metadata ?? null;
  if (metadata?.length) {
    return metadata.map((pin, index) => {
      const signalNames = pin.signals?.map(s => s.name).filter(Boolean) ?? [];
      const firstPeripheral = signalNames.find(name => name !== "GPIO");
      const firstAf = pin.signals?.find(s => s.name === firstPeripheral)?.af;
      const isPower = String(pin.type || "").toLowerCase().includes("power");
      const isSystem = ["Reset", "Boot", "MonoIO"].some(t => String(pin.type || "").includes(t));
      return {
        pin: pin.name,
        signal: firstPeripheral ?? (isPower ? pin.name : isSystem ? "System" : "Unassigned"),
        mode: isPower ? "Power" : firstPeripheral ? "Alternate Function" : isSystem ? "System" : "Input Floating",
        speed: "Low",
        pull: "No pull-up/down",
        label: `Pin ${pin.position ?? index + 1}`,
        af: firstAf ?? "-",
        enabled: isPower || isSystem || !!firstPeripheral,
      };
    });
  }

  const pinList: string[] = device?.full_pinout ?? [];
  if (pinList.length === 0 && Number.isFinite(device?.package_pins) && device.package_pins > 0) {
    return Array.from({ length: device.package_pins }, (_, index) => ({
      pin: `P${index + 1}`,
      signal: "Unverified package pad",
      mode: "Input Floating",
      speed: "Low",
      pull: "No pull-up/down",
      label: `Pad ${index + 1}`,
      af: "-",
      enabled: false,
    }));
  }
  return pinList.map((pin, index) => {
    const defaults: Partial<PinConfig> = {};
    const isPower = ["VSS", "VDD", "VBAT", "VDDA", "VSSA", "VCAP"].includes(pin);
    const isSystem = ["NRST", "BOOT0", "PD0", "PD1", "PH0", "PH1", "PD2"].includes(pin);
    return {
      pin,
      signal: defaults.signal ?? (isPower ? pin : isSystem ? "System" : "Unassigned"),
      mode: defaults.mode ?? (isPower ? "Power" : isSystem ? "System" : "Input Floating"),
      speed: defaults.speed ?? "Low",
      pull: defaults.pull ?? "No pull-up/down",
      label: defaults.label ?? `Pin ${index + 1}`,
      af: defaults.af ?? "-",
      enabled: defaults.enabled ?? (isPower || isSystem),
    };
  });
}
// RAG Documents initial mock list
const initialRagDocs: RagDocument[] = [];

function buildProjectFileState(files: any[]): { fileContents: Record<string, string>; fileTree: FileItem[] } {
  const fileContents: Record<string, string> = {};
  const fileTree: FileItem[] = [];

  files.forEach((f: any) => {
    const relativePath = String(f.path || "").replace(/^\/+/, "");
    const fullPath = "/" + relativePath;
    fileContents[fullPath] = f.content || "";

    const parts = fullPath.split("/").filter(Boolean);
    let currentLevel = fileTree;
    let builtPath = "";

    parts.forEach((part, i) => {
      builtPath += "/" + part;
      const isFolder = i < parts.length - 1;
      let existing = currentLevel.find(item => item.name === part);

      if (!existing) {
        existing = { name: part, path: builtPath, isFolder, ...(isFolder ? { children: [] } : {}) };
        currentLevel.push(existing);
      }

      if (isFolder && existing.children) {
        currentLevel = existing.children;
      }
    });
  });

  return { fileContents, fileTree };
}

// Normalize a backend disk-tree node into a FileItem. Disk paths already carry a
// leading slash (e.g. "/src/main.c"), matching the editor's path convention.
function normalizeDiskNode(node: any): FileItem {
  const item: FileItem = {
    name: node.name,
    path: node.path,
    isFolder: !!node.isFolder,
  };
  if (node.isBinary) item.isBinary = true;
  if (node.isFolder && Array.isArray(node.children)) {
    item.children = node.children.map(normalizeDiskNode);
  }
  return item;
}

const isBrowser = typeof window !== 'undefined';

const getInitialActiveProjectId = () => {
  if (!isBrowser) return null;
  try {
    const val = localStorage.getItem("activeProjectId");
    return val ? JSON.parse(val) : null;
  } catch {
    return null;
  }
};

const getInitialActiveFile = () => {
  if (!isBrowser) return null;
  try {
    const val = localStorage.getItem("activeFile");
    return val ? JSON.parse(val) : null;
  } catch {
    return null;
  }
};

const getInitialOpenFiles = () => {
  if (!isBrowser) return [];
  try {
    const val = localStorage.getItem("openFiles");
    return val ? JSON.parse(val) : [];
  } catch {
    return [];
  }
};

const getInitialShowWelcomeScreen = () => {
  if (!isBrowser) return true;
  try {
    const val = localStorage.getItem("showWelcomeScreen");
    return val ? JSON.parse(val) : true;
  } catch {
    return true;
  }
};

const getInitialSelectedBoard = () => {
  if (!isBrowser) return "bluepill_f103c8";
  try {
    const val = localStorage.getItem("selectedBoard");
    return val ? JSON.parse(val) : "bluepill_f103c8";
  } catch {
    return "bluepill_f103c8";
  }
};

const getInitialSelectedProbe = () => {
  if (!isBrowser) return "ST-Link V2";
  try {
    const val = localStorage.getItem("selectedProbe");
    return val ? JSON.parse(val) : "ST-Link V2";
  } catch {
    return "ST-Link V2";
  }
};

const getInitialToolchainPath = () => {
  if (!isBrowser) return "/usr/bin/arm-none-eabi-gcc";
  try {
    const val = localStorage.getItem("toolchainPath");
    return val ? JSON.parse(val) : "/usr/bin/arm-none-eabi-gcc";
  } catch {
    return "/usr/bin/arm-none-eabi-gcc";
  }
};

const getInitialActiveSidebarTab = () => {
  if (!isBrowser) return "explorer";
  try {
    const val = localStorage.getItem("activeSidebarTab");
    return val ? JSON.parse(val) : "explorer";
  } catch {
    return "explorer";
  }
};

const getInitialActiveBottomTab = () => {
  if (!isBrowser) return "terminal";
  try {
    const val = localStorage.getItem("activeBottomTab");
    return val ? JSON.parse(val) : "terminal";
  } catch {
    return "terminal";
  }
};

const getInitialTerminalOpen = () => {
  if (!isBrowser) return true;
  try {
    const val = localStorage.getItem("terminalOpen");
    return val ? JSON.parse(val) : true;
  } catch {
    return true;
  }
};

const getInitialSelectedProvider = () => {
  if (!isBrowser) return "deepseek";
  try {
    const provider = localStorage.getItem("selectedProvider");
    return provider && ["gemini", "deepseek", "sarvam"].includes(provider)
      ? provider
      : "deepseek";
  } catch {
    return "deepseek";
  }
};

const getInitialPins = (initialProjId: string | null) => {
  if (!isBrowser || !initialProjId) return initialPins;
  try {
    const val = localStorage.getItem(`pins_${initialProjId}`);
    return val ? JSON.parse(val) : initialPins;
  } catch {
    return initialPins;
  }
};

const getSavedPins = (projectId: string) => {
  if (!isBrowser) return null;
  try {
    const val = localStorage.getItem(`pins_${projectId}`);
    return val ? JSON.parse(val) : null;
  } catch {
    return null;
  }
};

export const workspaceStore = writable({
  // Project & Files
  activeProjectId: getInitialActiveProjectId(),
  projectsList: [] as any[],
  activeFile: getInitialActiveFile(),
  openFiles: getInitialOpenFiles(),
  // Proposal diff tabs opened in the editor area. Keyed by the synthetic tab id
  // `diff://<path>` (which also lives in openFiles so the tab bar renders it);
  // the value carries which chat message the proposal belongs to so Allow/Reject
  // routes back to the shared proposal state and reflects in the chat panel.
  diffTabs: {} as Record<string, { path: string; msgId: string }>,
  gitChanges: [] as { path: string; status: string }[],
  gitInfo: { is_repo: false, branch: null, detached: false, head_hash: null, short_hash: null } as GitInfo,
  gitBranches: [] as string[],
  gitLog: [] as GraphNode[],
  gitLogLoading: false,
  gitExpandedCommit: null as string | null, // hash of expanded commit row
  fileContents: {} as Record<string, string>,
  fileTree: [] as FileItem[],
  // Paths present on disk but NOT tracked in the DB (e.g. .pio build artifacts).
  // These are viewable but read-only — edits are never persisted to the DB.
  untrackedPaths: {} as Record<string, boolean>,
  // Folder paths the user has expanded in the explorer. Folders default to
  // collapsed; a path appears here only after the user opens it.
  expandedFolders: {} as Record<string, boolean>,
  // When false, dotfiles (.gitignore, .pio, etc.) are hidden in the explorer.
  // Toggled by the eye button in the explorer header.
  showHiddenFiles: false,

  // Compilation & Flashing
  isCompiling: false,
  isFlashing: false,
  buildLogs: [] as string[],
  // Live hardware connection status (polled from the backend)
  deviceStatus: { connected: false, probe: null as string | null, target: null as string | null, detail: "" },



  // Peripheral registers (shown in the bottom "registers" tab)
  registers: [] as RegisterItem[],

  // ── GDB Debug Session ─────────────────────────────────────────────────────
  isDebugging: false,
  debuggerActive: false,
  debugHalted: false,
  debugCurrentFile: null as string | null,
  debugCurrentLine: null as number | null,
  debugStopReason: null as string | null,
  debugBreakpoints: [] as DebugBreakpointItem[],
  debugRegisters: [] as DebugRegisterItem[],
  debugCallStack: [] as DebugFrameItem[],
  debugLocals: [] as DebugLocalItem[],
  debugLog: [] as string[],


  // Telemetry & Serial
  serialLogs: [] as string[],
  serialConnected: false,
  activePort: "COM4 (ST-Link Virtual Port)",
  baudRate: 115200,
  plotData: [] as PlotDataPoint[],

  // AI Panel
  aiMessages: [] as ChatMessage[],
  aiWaiting: false,
  queuedAiFollowup: null as string | null,
  selectedProvider: getInitialSelectedProvider(),
  // When true, the agent runs build/flash without pausing for a Yes/No prompt
  // and auto-allows file diffs. Per-session toggle in the chat UI.
  autoApproveAgent: false,

  // UI Tabs
  activeBottomTab: getInitialActiveBottomTab() as "terminal" | "plotter" | "registers" | "memory",
  terminalOpen: getInitialTerminalOpen(),  // whether the bottom drawer (serial/build/etc.) is expanded
  showWelcomeScreen: getInitialShowWelcomeScreen(),
  activeSidebarTab: getInitialActiveSidebarTab() as "explorer" | "search" | "git" | "debug" | "extensions" | "boards" | "rag" | "research" | "libraries",
  selectedBoard: getInitialSelectedBoard() as string,
  selectedBoardInfo: null as BoardMeta | null,
  boardCatalog: [] as BoardMeta[],
  selectedProbe: getInitialSelectedProbe() as "ST-Link V2" | "J-Link" | "CMSIS-DAP",
  toolchainPath: getInitialToolchainPath(),

  // ── NEW FEATURE STATE ──
  // Interactive Pin Configuration
  pins: getInitialPins(getInitialActiveProjectId()) as PinConfig[],
  
  analogSensors: {
    temp: 24.5,
    voltage: 3.3,
    current: 42.1
  },

  // RAG Document State
  ragDocuments: initialRagDocs as RagDocument[],
  ragUploadProgress: null as string | null,
  semanticQuery: "",
  semanticResults: [] as { file: string; match: string; score: number }[],

  // Library Manager State
  libraryManagerTab: "discover" as "discover" | "installed" | "updates",
  availableLibraries: [] as any[],
  installedLibraries: [] as any[],
  libraryCategories: [] as string[],
  librarySearchQuery: "",
  librarySelectedCategory: "",
  libraryInstallStatus: {} as Record<string, "idle" | "confirming" | "installing" | "installed" | "error">,
  libraryInstallError: {} as Record<string, string>,
  librariesLoading: false,
});

let agentAbortController: AbortController | null = null;

// Helper Actions for Store
const _INTERFACE_CFG_TO_PROBE: Record<string, "ST-Link V2" | "J-Link" | "CMSIS-DAP"> = {
  "interface/stlink.cfg": "ST-Link V2",
  "interface/jlink.cfg": "J-Link",
  "interface/cmsis-dap.cfg": "CMSIS-DAP",
};

export const actions = {
  loadBoardCatalog: async () => {
    try {
      const boards = await api.listBoards();
      workspaceStore.update(s => ({
        ...s,
        boardCatalog: boards,
        selectedBoardInfo: boards.find((b: BoardMeta) => b.id === s.selectedBoard) || s.selectedBoardInfo || boards[0] || null,
      }));
    } catch (e) {
      console.warn("Failed to load board catalog", e);
    }
  },
  refreshBoardCatalog: async () => {
    const result = await api.refreshAllBoards();
    await actions.loadBoardCatalog();
    return result;
  },
  addCustomBoard: async (payload: { id: string; mcu: string; label?: string; arch?: string }) => {
    const board = await api.addCustomBoard(payload);
    await actions.loadBoardCatalog();
    await actions.setSelectedBoard(board.id);
    return board;
  },
  importStm32Metadata: async () => {
    const result = await api.importStm32Metadata();
    let selectedBoard: string | null = null;
    workspaceStore.subscribe(s => { selectedBoard = s.selectedBoard; })();
    if (selectedBoard) await actions.setSelectedBoard(selectedBoard);
    return result;
  },
  loadProjects: async () => {
    try {
      const projects = await api.getProjects();
      workspaceStore.update(s => ({ ...s, projectsList: projects }));
      
    } 
    catch (e) {
      console.error("Failed to load projects", e);
    }
    
  },

  deleteProject: async (id: string) => {
    try {
      await api.deleteProject(id);
      await actions.loadProjects();
    } catch (e) {
      console.error("Failed to delete project", e);
      alert("Failed to delete project");
    }
  },

  // Fetch the real working-directory tree (incl. .pio, untracked, binaries) and
  // replace fileTree with it. Falls back silently to the DB-derived tree on error.
  loadDiskTree: async (id: string) => {
    try {
      const res = await api.getProjectTree(id);
      if (res.source === "disk" && Array.isArray(res.tree)) {
        const fileTree = res.tree.map(normalizeDiskNode);
        workspaceStore.update(s =>
          s.activeProjectId === id ? { ...s, fileTree } : s
        );
      }
    } catch (e) {
      console.warn("Failed to load disk tree, keeping DB-derived tree", e);
    }
  },

  // Refresh only the file tree/contents without clearing chat or logs.
  // Used after an agent response so the editor shows new code without losing the conversation.
  refreshProjectFiles: async (id: string) => {
    try {
      const files = await api.getProjectFiles(id);
      const { fileContents, fileTree } = buildProjectFileState(files);

      workspaceStore.update(s => ({
        ...s,
        fileTree,
        fileContents,
        // Intentionally do NOT touch aiMessages, buildLogs, serialLogs
      }));
      // Overlay the real working-dir tree (shows .pio/untracked files).
      actions.loadDiskTree(id);
    } catch (e) {
      console.error("Failed to refresh project files", e);
    }
  },

  loadProject: async (id: string) => {
    try {
      api.setActiveProject(id);
      const files = await api.getProjectFiles(id);
      const { fileContents, fileTree } = buildProjectFileState(files);

      let history: ChatMessage[] = [];
      try {
        history = await api.getConversationHistory(id);
        if (history.length === 0) {
          history = [
            {
              id: "default-greeting",
              sender: "ai",
              text: "Hello! I am your HARDCOREAI Copilot. I have loaded context for your board target, SVD registers, and your current PlatformIO configuration. \n\nHow can I help you write or debug firmware today?",
              timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
            }
          ];
        }
      } catch (err) {
        console.error("Failed to load chat history", err);
      }

      workspaceStore.update(s => {
        const filePaths = files.map((f: any) => "/" + String(f.path || "").replace(/^\/+/, ""));

        let activeFile = s.activeFile;
        let openFiles = s.openFiles;

        if (!activeFile || !filePaths.includes(activeFile)) {
          activeFile = files.length > 0 ? "/" + files[0].path : null;
        }

        openFiles = openFiles.filter((f: string) => filePaths.includes(f));
        if (openFiles.length === 0 && activeFile) {
          openFiles = [activeFile];
        }

        const project = s.projectsList.find((p: any) => String(p.id) === String(id));
        const boardId = project?.board_id || "bluepill_f103c8";
        const savedPins = getSavedPins(id);

        return {
          ...s,
          activeProjectId: id,
          fileTree,
          fileContents,
          activeFile,
          openFiles,
          aiMessages: history,
          selectedBoard: boardId,
          pins: savedPins || initialPins, // real board pins loaded async below
          // Clear all session-specific state so previous project data doesn't bleed over
          buildLogs: [],
          serialLogs: [],
          isDebugging: false,
          debuggerActive: false,
          currentLine: null,
          crashed: false,
          crashReason: null,
          // Clear debug session state on project switch
          debugHalted: false,
          debugCurrentFile: null,
          debugCurrentLine: null,
          debugStopReason: null,
          debugBreakpoints: [],
          debugRegisters: [],
          debugCallStack: [],
          debugLocals: [],
          debugLog: [],

        };
      });

      // If no cached pins existed for this project, fetch the real board's
      // pinout and populate pins from it instead of leaving the stale/default set.
      if (!getSavedPins(id)) {
        try {
          const project = (() => { let p: any; workspaceStore.subscribe(s => { p = s.projectsList.find((x: any) => String(x.id) === String(id)); })(); return p; })();
          const boardId = project?.board_id || "bluepill_f103c8";
          const board = await api.getBoard(boardId);
          workspaceStore.update(s => (s.activeProjectId === id ? { ...s, selectedBoardInfo: board, pins: buildPinsFromDevice(board) } : s));
        } catch (e) {
          console.warn("Failed to load board pinout, keeping default pins", e);
        }
      }

      // Overlay the real working-dir tree (shows .pio/untracked files).
      actions.loadDiskTree(id);
      // Also fetch RAG documents for this project
      await actions.fetchRagDocuments();
      // Load git status and info
      await actions.loadGitInfo();
      await actions.loadGitStatus();
    } catch (e) {
      console.error("Failed to load project files", e);
    }
  },

  setActiveFile: (path: string | null) => {
    let needsDiskLoad = false;
    let projectId: string | null = null;
    workspaceStore.update(s => {
      if (!path) return { ...s, activeFile: null };
      const openFiles = s.openFiles.includes(path) ? s.openFiles : [...s.openFiles, path];
      // Tracked files have content from the DB; untracked/.pio files don't —
      // fetch their content from disk on demand.
      
      if (s.fileContents[path] === undefined) {
        needsDiskLoad = true;
        projectId = s.activeProjectId;
      }
      return { ...s, openFiles, activeFile: path };
    });
    const pid: string | null = projectId;
    if (needsDiskLoad && pid && path) actions.loadDiskFileContent(pid, path);
  },

  // Lazily fetch a working-dir file's content (untracked/.pio) and cache it in
  // fileContents so the editor renders it. Binary files get a short placeholder.
  loadDiskFileContent: async (projectId: string, path: string) => {
    try {
      const rel = path.replace(/^\/+/, "");
      const res = await api.getDiskFile(projectId, rel);
      const content = res.binary
        ? `// Binary file (${rel}) — not shown.`
        : (res.content || "");
      workspaceStore.update(s => ({
        ...s,
        fileContents: { ...s.fileContents, [path]: content },
        // Mark read-only: this file lives on disk only, not in the DB.
        untrackedPaths: { ...s.untrackedPaths, [path]: true },
      }));
    } catch (e) {
      console.warn("Failed to load disk file content", path, e);
      workspaceStore.update(s => ({
        ...s,
        fileContents: { ...s.fileContents, [path]: "" },
      }));
    }
  },

  closeFileTab: (path: string) => {
    workspaceStore.update(s => {
      const openFiles = s.openFiles.filter((f: string) => f !== path);
      let activeFile = s.activeFile;
      if (activeFile === path) {
        activeFile = openFiles.length > 0 ? openFiles[openFiles.length - 1] : null;
      }
      // Drop any diff-tab bookkeeping for this tab id.
      let diffTabs = s.diffTabs;
      if (diffTabs[path]) {
        diffTabs = { ...diffTabs };
        delete diffTabs[path];
      }
      return { ...s, openFiles, activeFile, diffTabs };
    });
  },

  loadGitStatus: async () => {
    let projectId: string | null = null;
    workspaceStore.subscribe(s => { projectId = s.activeProjectId; })();
    if (!projectId) return;

    try {
      const status = await api.getGitStatus();
      workspaceStore.update(s => ({ ...s, gitChanges: status }));
    } catch (e) {
      console.error("Failed to load git status:", e);
    }
  },

  loadGitInfo: async () => {
    let projectId: string | null = null;
    workspaceStore.subscribe(s => { projectId = s.activeProjectId; })();
    if (!projectId) return;

    try {
      const info = await api.getGitInfo();
      workspaceStore.update(s => ({ ...s, gitInfo: info }));
      if (info.is_repo) {
        await actions.loadGitBranches();
      }
    } catch (e) {
      console.error("Failed to load git info:", e);
    }
  },

  loadGitBranches: async () => {
    try {
      const branches = await api.getGitBranches();
      workspaceStore.update(s => ({ ...s, gitBranches: branches }));
    } catch (e) {
      console.error("Failed to load git branches:", e);
    }
  },

  createGitBranch: async (name: string) => {
    try {
      await api.createGitBranch(name);
      await actions.loadGitInfo();
      await actions.loadGitLog();
      await actions.loadGitStatus();
    } catch (e) {
      console.error("Failed to create git branch:", e);
      throw e;
    }
  },

  loadGitLog: async () => {
    let projectId: string | null = null;
    workspaceStore.subscribe(s => { projectId = s.activeProjectId; })();
    if (!projectId) return;

    workspaceStore.update(s => ({ ...s, gitLogLoading: true }));
    try {
      const log = await api.getGitLog(50);
      const { computeGitGraph } = await import("./gitGraph");
      const graphNodes = computeGitGraph(log);
      workspaceStore.update(s => ({ ...s, gitLog: graphNodes as any, gitLogLoading: false }));
    } catch (e) {
      console.error("Failed to load git log:", e);
      workspaceStore.update(s => ({ ...s, gitLogLoading: false }));
    }
  },

  checkoutCommit: async (ref: string) => {
    try {
      await api.checkoutCommit(ref);
      // Reload git state after checkout
      await actions.loadGitInfo();
      await actions.loadGitLog();
      await actions.loadGitStatus();
      let projectId: string | null = null;
      workspaceStore.subscribe(s => { projectId = s.activeProjectId; })();
      if (projectId) {
        await actions.refreshProjectFiles(projectId);
      }
    } catch (e) {
      console.error("Checkout failed:", e);
      throw e;
    }
  },

  checkoutHead: async () => {
    try {
      await api.checkoutHead();
      await actions.loadGitInfo();
      await actions.loadGitLog();
      await actions.loadGitStatus();
      let projectId: string | null = null;
      workspaceStore.subscribe(s => { projectId = s.activeProjectId; })();
      if (projectId) {
        await actions.refreshProjectFiles(projectId);
      }
    } catch (e) {
      console.error("Checkout HEAD failed:", e);
      throw e;
    }
  },

  setGitExpandedCommit: (hash: string | null) => {
    workspaceStore.update(s => ({ ...s, gitExpandedCommit: s.gitExpandedCommit === hash ? null : hash }));
  },

  commitChanges: async (message: string) => {
    let projectId: string | null = null;
    workspaceStore.subscribe(s => { projectId = s.activeProjectId; })();
    if (!projectId) return;

    try {
      await api.commitChanges(message);
      await actions.loadGitStatus();
    } catch (e) {
      console.error("Failed to commit changes:", e);
      alert("Failed to commit changes: " + (e instanceof Error ? e.message : String(e)));
    }
  },
  
  updateFileContent: (path: string, content: string) => {
    let projectId: string | null = null;
    let untracked = false;
    workspaceStore.update(s => {
      projectId = s.activeProjectId;
      untracked = !!s.untrackedPaths[path];
      return {
        ...s,
        fileContents: { ...s.fileContents, [path]: content }
      };
    });

    // Disk-only files (e.g. .pio build artifacts) are read-only: view but never
    // persist back to the DB.
    if (untracked) return;

    if (projectId) {
      // @ts-ignore - store timeout on the window to survive store updates
      clearTimeout(window.__saveTimeout);
      // @ts-ignore
      window.__saveTimeout = setTimeout(async () => {
        try {
          // Remove leading slash if present
          const relPath = path.startsWith('/') ? path.substring(1) : path;
          await api.upsertFile(projectId!, relPath, content);
          await actions.loadGitStatus();
        } catch (e) {
          console.error("Failed to save file to backend:", e);
        }
      }, 800);
    }
  },
  createFile: async (name: string, folderPath: string = "") => {
    const fullPath = folderPath ? `/${folderPath}/${name}` : `/${name}`;
    let projectId: string | null = null;
    workspaceStore.update(s => {
      projectId = s.activeProjectId;
      if (s.fileContents[fullPath] !== undefined) return s; // already exists
      const openFiles = s.openFiles.includes(fullPath) ? s.openFiles : [...s.openFiles, fullPath];
      return {
        ...s,
        fileContents: { ...s.fileContents, [fullPath]: "" },
        openFiles,
        activeFile: fullPath
      };
    });
    if (projectId) {
      try {
        const relPath = fullPath.startsWith('/') ? fullPath.substring(1) : fullPath;
        await api.upsertFile(projectId, relPath, "");
        // Refresh the file tree
        await actions.refreshProjectFiles(projectId);
      } catch (e) {
        console.error("Failed to create file on backend", e);
      }
    }
  },
  
  createFolder: async (name: string, folderPath: string = "") => {
    // We don't have empty folders in this backend structure, 
    // but we can create a dummy file to represent the folder, 
    // e.g., folderName/.gitkeep
    const dummyFile = folderPath ? `/${folderPath}/${name}/.gitkeep` : `/${name}/.gitkeep`;
    let projectId: string | null = null;
    workspaceStore.update(s => { projectId = s.activeProjectId; return s; });
    if (projectId) {
      try {
        const relPath = dummyFile.startsWith('/') ? dummyFile.substring(1) : dummyFile;
        await api.upsertFile(projectId, relPath, "");
        await actions.refreshProjectFiles(projectId);
      } catch(e) {
        console.error("Failed to create folder on backend", e);
      }
    }
  },

  deleteFile: async (path: string) => {
    let projectId: string | null = null;
    workspaceStore.update(s => {
      projectId = s.activeProjectId;
      const fileContents = { ...s.fileContents };
      delete fileContents[path];
      const openFiles = s.openFiles.filter((f: string) => f !== path);
      let activeFile = s.activeFile;
      if (activeFile === path) {
        activeFile = openFiles.length > 0 ? openFiles[openFiles.length - 1] : null;
      }
      return {
        ...s,
        fileContents,
        openFiles,
        activeFile
      };
    });
    if (projectId) {
      try {
        const relPath = path.startsWith('/') ? path.substring(1) : path;
        await api.deleteFile(projectId, relPath);
        await actions.refreshProjectFiles(projectId);
        await actions.loadGitStatus();
      } catch (e) {
        console.error("Failed to delete file on backend", e);
        alert("Failed to delete file: " + (e instanceof Error ? e.message : String(e)));
      }
    }
  },

  deleteFolder: async (folderPath: string) => {
    let projectId: string | null = null;
    let filesToDelete: string[] = [];
    workspaceStore.update(s => {
      projectId = s.activeProjectId;
      const folderPathWithSlash = folderPath.endsWith('/') ? folderPath : folderPath + '/';
      
      // Find all file paths starting with the folder path
      filesToDelete = Object.keys(s.fileContents).filter(path => 
        path.startsWith(folderPathWithSlash) || path === folderPath
      );

      const fileContents = { ...s.fileContents };
      filesToDelete.forEach(path => delete fileContents[path]);

      const openFiles = s.openFiles.filter((f: string) => !filesToDelete.includes(f));
      let activeFile = s.activeFile;
      if (activeFile && filesToDelete.includes(activeFile)) {
        activeFile = openFiles.length > 0 ? openFiles[openFiles.length - 1] : null;
      }

      return {
        ...s,
        fileContents,
        openFiles,
        activeFile
      };
    });

    if (projectId && filesToDelete.length > 0) {
      try {
        for (const file of filesToDelete) {
          const relPath = file.startsWith('/') ? file.substring(1) : file;
          await api.deleteFile(projectId, relPath);
        }
        await actions.refreshProjectFiles(projectId);
        await actions.loadGitStatus();
      } catch (e) {
        console.error("Failed to delete folder files on backend", e);
        alert("Failed to delete folder content completely: " + (e instanceof Error ? e.message : String(e)));
      }
    }
  },

  setCompiling: (val: boolean) => {
    workspaceStore.update(s => ({ ...s, isCompiling: val }));
  },
  setFlashing: (val: boolean) => {
    workspaceStore.update(s => ({ ...s, isFlashing: val }));
  },
  addBuildLog: (log: string) => {
    workspaceStore.update(s => ({ ...s, buildLogs: [...s.buildLogs, log] }));
  },
  clearBuildLogs: () => {
    workspaceStore.update(s => ({ ...s, buildLogs: [] }));
  },

  // Per-session "auto-approve everything" toggle for the agent. When on, the
  // agent runs build/flash without a Yes/No prompt and auto-allows file diffs.
  setAutoApproveAgent: (on: boolean) => {
    workspaceStore.update(s => ({ ...s, autoApproveAgent: on }));
  },
  toggleAutoApproveAgent: () => {
    workspaceStore.update(s => ({ ...s, autoApproveAgent: !s.autoApproveAgent }));
  },

  // Explorer folder expand/collapse. Folders are collapsed by default.
  toggleFolder: (path: string) => {
    workspaceStore.update(s => {
      const expandedFolders = { ...s.expandedFolders };
      if (expandedFolders[path]) delete expandedFolders[path];
      else expandedFolders[path] = true;
      return { ...s, expandedFolders };
    });
  },

  // Show/hide dotfiles (.gitignore, .pio, etc.) in the explorer.
  toggleHiddenFiles: () => {
    workspaceStore.update(s => ({ ...s, showHiddenFiles: !s.showHiddenFiles }));
  },

  // Real PlatformIO build — streams the compiler output live into the Build Output
  // tab (auto-opening it), then feeds the result to the agent.
  // notifyAgent: when true (default), the build outcome is posted into the agent
  // chat so it reacts (Build & Check). When false, it's a plain build only.
  runBuild: async (notifyAgent: boolean = true) => {
    let projectId: string | null = null;
    let busy = false;
    workspaceStore.subscribe(s => { projectId = s.activeProjectId; busy = s.isCompiling; })();
    if (!projectId) { actions.addBuildLog("No active project to build."); return; }
    if (busy) return;

    // Auto-open the bottom drawer on the BUILD OUTPUT tab so the user watches it run.
    workspaceStore.update(s => ({ ...s, terminalOpen: true, activeBottomTab: "memory" }));
    actions.setCompiling(true);
    actions.clearBuildLogs();
    actions.addBuildLog("Building firmware (PlatformIO)...");

    let done: any = null;
    try {
      await api.streamBuild((event) => {
        if (event.type === "status" || event.type === "line") {
          actions.addBuildLog(event.text ?? "");
        } else if (event.type === "done") {
          done = event;
        }
      });
    } catch (e) {
      actions.addBuildLog("Build error: " + (e instanceof Error ? e.message : String(e)));
    } finally {
      actions.setCompiling(false);
    }

    if (done) {
      actions.addBuildLog(
        done.success
          ? `Build successful in ${done.duration_s}s.${done.firmware_path ? " -> " + done.firmware_path : ""}`
          : `Build FAILED (exit ${done.returncode}).`
      );
      if (notifyAgent) actions.notifyAgentOfBuild(done);
    }
  },

  // After a build finishes, post a short outcome into the agent chat so it reacts
  // (e.g. offers to fix on failure). The full build log flows to the agent via
  // buildOutput on this message. sendAiMessage itself queues if an agent run is
  // already in progress, so this never interrupts one.
  notifyAgentOfBuild: (result: any) => {
    const msg = result.success
      ? "The firmware just built successfully. Briefly confirm and note anything worth checking."
      : `The firmware build just FAILED (exit ${result.returncode}). Diagnose the error from the build output and propose a fix.`;
    actions.sendAiMessage(msg);
  },

  // Flash the built firmware to a connected board — gated server-side on detection.
  runFlash: async () => {
    let projectId: string | null = null;
    let busy = false;
    workspaceStore.subscribe(s => { projectId = s.activeProjectId; busy = s.isFlashing; })();
    if (!projectId) { actions.addBuildLog("No active project to flash."); return; }
    if (busy) return;

    actions.setFlashing(true);
    actions.addBuildLog("Flashing firmware to target...");
    try {
      const res = await api.flashProject();
      (res.output || "").split("\n").forEach((line: string) => { if (line.trim()) actions.addBuildLog(line); });
      if (res.flashed) {
        actions.addBuildLog("Flash successful. Target reset.");
        actions.addSerialLog("[SYSTEM] Board reset. Flashed firmware execution initialized.");
      } else if (res.reason === "no_device") {
        actions.addBuildLog("No device connected — nothing was flashed.");
      } else {
        actions.addBuildLog(`Flash FAILED (${res.reason}, exit ${res.returncode}).`);
      }
    } catch (e) {
      actions.addBuildLog("Flash error: " + (e instanceof Error ? e.message : String(e)));
    } finally {
      actions.setFlashing(false);
    }
  },

  // Poll whether an ST-Link + board is connected; drives the UI status chip.
  // Poll whether an ST-Link + board is connected; drives the UI status chip.
  // Passes the active project so we probe the project's real target board
  // instead of always assuming Blue Pill.
  pollDeviceStatus: async () => {
    let projectId: string | null = null;
    workspaceStore.subscribe(s => { projectId = s.activeProjectId; })();
    try {
      const res = await api.getDeviceStatus(projectId ?? undefined);
      workspaceStore.update(s => ({
        ...s,
        deviceStatus: {
          connected: !!res.connected,
          probe: res.probe ?? null,
          target: res.target ?? null,
          detail: res.detail ?? ""
        }
      }));
    } catch (e) {
      workspaceStore.update(s => ({ ...s, deviceStatus: { ...s.deviceStatus, connected: false } }));
    }
  },

  // Generic auto-detect: reads whatever chip is actually connected and
  // suggests a matching board. Never auto-applies — caller/UI presents the
  // suggestion and the user confirms via setSelectedBoard.
  detectBoard: async (): Promise<{
    family: string | null;
    suggestions: string[];
    detail: string;
    candidates: { board: BoardMeta; confidence: number; source: string; reason: string }[];
  }> => {
    let projectId: string | null = null;
    workspaceStore.subscribe(s => { projectId = s.activeProjectId; })();
    try {
      const res = await api.detectConnectedBoard(projectId ?? undefined);
      return {
        family: res.detected_family ?? null,
        suggestions: res.suggested_boards ?? [],
        detail: res.detail ?? "",
        candidates: res.candidates ?? [],
      };
    } catch (e) {
      return {
        family: null,
        suggestions: [],
        detail: e instanceof Error ? e.message : "Detection failed.",
        candidates: [],
      };
    }
  },


  toggleSerialConnection: () => {
    workspaceStore.update(s => ({ ...s, serialConnected: !s.serialConnected }));
  },
  setBaudRate: (baud: number) => {
    workspaceStore.update(s => ({ ...s, baudRate: baud }));
    actions.addSerialLog(`[SYSTEM] Baud rate changed to ${baud} bps.`);
  },
  addSerialLog: (log: string) => {
    workspaceStore.update(s => ({ ...s, serialLogs: [...s.serialLogs, log] }));
  },
  addPlotPoint: (pt: PlotDataPoint) => {
    workspaceStore.update(s => ({ ...s, plotData: [...s.plotData, pt] }));
  },
  setBottomTab: (tab: "terminal" | "registers" | "memory") => {
    workspaceStore.update(s => ({ ...s, activeBottomTab: tab }));
  },
  setTerminalOpen: (open: boolean) => {
    workspaceStore.update(s => ({ ...s, terminalOpen: open }));
  },

  setShowWelcomeScreen: (val: boolean) => {
    workspaceStore.update(s => ({ ...s, showWelcomeScreen: val }));
  },
  setActiveSidebarTab: (tab: "explorer" | "search" | "git" | "debug" | "extensions" | "boards" | "rag" | "libraries") => {
    workspaceStore.update(s => ({ ...s, activeSidebarTab: tab }));
    if (tab === "git") {
      actions.loadGitInfo();
      actions.loadGitStatus();
      actions.loadGitLog();
    }
    if (tab === "libraries") {
      actions.fetchAvailableLibraries();
      actions.fetchLibraryCategories();
      let pid: string | null = null;
      workspaceStore.subscribe(s => { pid = s.activeProjectId; })();
      if (pid) actions.fetchInstalledLibraries(pid);
    }
  },
  setSelectedBoard: async (board: string) => {
    let pid: string | null = null;
    workspaceStore.subscribe(s => { pid = s.activeProjectId; })();
    workspaceStore.update(s => ({ ...s, selectedBoard: board }));
    try {
      const deviceInfo = await api.getBoard(board);
      // Auto-default the debug probe to whatever this specific board
      // actually uses (e.g. Arduino Zero's onboard EDBG -> CMSIS-DAP)
      // instead of leaving whatever probe was selected for the
      // previously-selected board — that's how a SAMD board silently
      // inherited "ST-Link V2" and failed to debug even after
      // supports_live_debug was turned on for it. The dropdown still
      // lets the user override afterward, e.g. for an external J-Link
      // instead of a board's onboard debugger.
      const impliedProbe = deviceInfo.openocd_interface
        ? _INTERFACE_CFG_TO_PROBE[deviceInfo.openocd_interface]
        : undefined;
      workspaceStore.update(s => ({
        ...s,
        selectedBoardInfo: deviceInfo,
        pins: buildPinsFromDevice(deviceInfo),
        selectedProbe: impliedProbe ?? s.selectedProbe,
      }));
      if (pid) await api.setProjectBoard(pid, board);
    } catch (e) {
      console.error("Failed to switch board", e);
      workspaceStore.update(s => ({ ...s, selectedBoardInfo: s.selectedBoardInfo || { id: board, label: board } }));
    }
  },
  setSelectedProbe: (probe: "ST-Link V2" | "J-Link" | "CMSIS-DAP") => {
    workspaceStore.update(s => ({ ...s, selectedProbe: probe }));
  },
  setToolchainPath: (path: string) => {
    workspaceStore.update(s => ({ ...s, toolchainPath: path }));
  },

  // ── NEW FEATURE ACTIONS ──
  // Interactive Pin Configuration
  updatePinConfig: (pinName: string, updates: Partial<PinConfig>) => {
    workspaceStore.update(s => {
      const updatedPins = s.pins.map(p => {
        if (p.pin === pinName) {
          return { ...p, ...updates };
        }
        return p;
      });

      return {
        ...s,
        pins: updatedPins
      };
    });
  },
  
  updateAnalogSensor: (sensor: "temp" | "voltage" | "current", val: number) => {
    workspaceStore.update(s => ({
      ...s,
      analogSensors: {
        ...s.analogSensors,
        [sensor]: val
      }
    }));
  },
  // RAG Document Actions
  fetchRagDocuments: async () => {
    try {
      const res = await api.listRagDocuments();
      workspaceStore.update(s => ({
        ...s,
        ragDocuments: res.documents.map((doc: any) => {
          const name = typeof doc === "string" ? doc : doc.name;
          const sizeBytes = typeof doc === "string" ? 0 : (doc.size || 0);
          const sizeKb = sizeBytes > 0 ? (sizeBytes / 1024).toFixed(1) + " KB" : "Unknown";
          return {
            id: name,
            name: name,
            size: sizeKb,
            chunks: 0,
            status: "Ready in Database",
            tokens: 0,
            source: (doc.source as "pdf" | "web") ?? "pdf",
            url: doc.url ?? "",
          };
        })
      }));
    } catch (e) {
      console.error("Failed to fetch RAG docs", e);
    }
  },

  uploadDocument: async (file: File) => {
    const sizeStr = (file.size / (1024 * 1024)).toFixed(2) + " MB";
    const id = file.name;

    workspaceStore.update(s => ({
      ...s,
      ragUploadProgress: "Uploading file to RAG database...",
      ragDocuments: [
        { id, name: file.name, size: sizeStr, chunks: 0, status: "Uploading...", tokens: 0 },
        ...s.ragDocuments.filter(d => d.id !== id)
      ]
    }));

    try {
      await api.uploadRagDocument(file);
      
      // Poll until the file appears in the data_dir (backend stages it before ingesting).
      // Large PDFs (20-40 MB) take much longer than 30s to ingest — poll up to 2 minutes.
      let found = false;
      for (let i = 0; i < 120; i++) {
        await new Promise(r => setTimeout(r, 1000));
        const res = await api.listRagDocuments();
        // API returns {documents: [{name, size}, ...]} — must compare .name, not the object itself
        if (res.documents.some((d: any) => (typeof d === "string" ? d : d.name) === file.name)) {
          found = true;
          break;
        }
      }

      if (found) {
        // Refresh from the backend so UI shows the real, up-to-date file list
        await actions.fetchRagDocuments();
        workspaceStore.update(s => ({ ...s, ragUploadProgress: null }));
      } else {
        throw new Error("Timeout waiting for file to be ingested.");
      }
    } catch (e: any) {
      workspaceStore.update(s => ({
        ...s,
        ragUploadProgress: null,
        ragDocuments: s.ragDocuments.filter(d => d.id !== id)
      }));
      alert(`Failed to upload document: ${e.message}`);
    }
  },

  deleteRagDocument: async (filename: string) => {
    try {
      await api.deleteRagDocument(filename);
      workspaceStore.update(s => ({
        ...s,
        ragDocuments: s.ragDocuments.filter(d => d.name !== filename)
      }));
    } catch (e) {
      console.error("Failed to delete doc", e);
    }
  },

  ingestUrl: async (url: string) => {
    const displayName = (() => {
      try { return new URL(url).hostname; } catch { return url; }
    })();
    const tempId = `web__${displayName}`;

    workspaceStore.update(s => ({
      ...s,
      ragUploadProgress: `Fetching & ingesting ${displayName}...`,
      ragDocuments: [
        { id: tempId, name: displayName, size: "...", chunks: 0, status: "Uploading...", tokens: 0, source: "web", url },
        ...s.ragDocuments.filter(d => d.id !== tempId)
      ]
    }));

    try {
      const result = await api.scrapeUrl(url);
      const filename: string = result.filename;

      if (result.skipped) {
        // Already ingested — just refresh the doc list.
        workspaceStore.update(s => ({ ...s, ragUploadProgress: null }));
        await actions.fetchRagDocuments();
        return;
      }

      // Poll until the new file appears in the list (same pattern as uploadDocument).
      let found = false;
      for (let i = 0; i < 30; i++) {
        await new Promise(r => setTimeout(r, 1000));
        const res = await api.listRagDocuments();
        if (res.documents.some((d: any) => (typeof d === "string" ? d : d.name) === filename)) {
          found = true;
          break;
        }
      }

      await actions.fetchRagDocuments();
      workspaceStore.update(s => ({ ...s, ragUploadProgress: null }));

      if (!found) {
        console.warn("ingestUrl: file did not appear in list within timeout, refreshed anyway.");
      }
    } catch (e: any) {
      workspaceStore.update(s => ({
        ...s,
        ragUploadProgress: null,
        ragDocuments: s.ragDocuments.filter(d => d.id !== tempId)
      }));
      alert(`Failed to ingest URL: ${e.message}`);
    }
  },

  searchRag: async (query: string) => {
    workspaceStore.update(s => ({ ...s, semanticQuery: query }));
    if (!query.trim()) {
      workspaceStore.update(s => ({ ...s, semanticResults: [] }));
      return;
    }
    try {
      const res = await api.searchRag(query);
      let results: any[] = [];
      if (Array.isArray(res.context)) {
        results = res.context.map((match: any) => ({
          file: match.source || "Knowledge Base",
          match: match.text || match.content || (typeof match === 'string' ? match : JSON.stringify(match)),
          score: match.score || 1.0
        }));
      } else if (typeof res.context === 'string') {
        results = [{
          file: "Rag Query Result",
          match: res.context,
          score: 1.0
        }];
      }
      workspaceStore.update(s => ({ ...s, semanticResults: results }));
    } catch (e) {
      console.error("Failed to search RAG", e);
      workspaceStore.update(s => ({ ...s, semanticResults: [] }));
    }
  },
  applyAgentFiles: (files: any[]) => {
    if (!Array.isArray(files) || files.length === 0) return;
    // Prevent a pending editor debounce from writing stale pre-agent content over
    // the just-persisted files when the stream closes.
    // @ts-ignore - save debounce is stored on window by updateFileContent
    clearTimeout(window.__saveTimeout);
    const { fileContents, fileTree } = buildProjectFileState(files);
    workspaceStore.update(s => {
      const activeFile = s.activeFile && fileContents[s.activeFile] !== undefined
        ? s.activeFile
        : (fileContents["/src/main.c"] !== undefined ? "/src/main.c" : Object.keys(fileContents)[0] || s.activeFile);
      const openFiles = activeFile && !s.openFiles.includes(activeFile) ? [...s.openFiles, activeFile] : s.openFiles;
      return {
        ...s,
        fileContents,
        fileTree,
        activeFile,
        openFiles
      };
    });
    // Overlay the real working-dir tree (shows .pio/untracked files).
    let pid: string | null = null;
    workspaceStore.subscribe(s => { pid = s.activeProjectId; })();
    if (pid) actions.loadDiskTree(pid);
    // Load git status
    actions.loadGitStatus();
  },

  // --- Agent file proposals: stage-then-approve -----------------------------
  // The agent's writes/edits arrive as proposals (diff cards). Nothing touches
  // the editor or DB until the user clicks Allow here.

  _setProposalDecision: (msgId: string, path: string, decision: "allowed" | "rejected") => {
    workspaceStore.update(s => {
      const aiMessages = s.aiMessages.map(m => {
        if (m.id !== msgId) return m;
        const proposals = (m.proposals || []).map(p =>
          p.path === path ? { ...p, decision } : p
        );
        const steps = (m.steps || []).map(st =>
          st.kind === "proposal" && st.path === path ? { ...st, decision } : st
        );
        return { ...m, proposals, steps };
      });
      const pid = s.activeProjectId;
      if (pid) api.saveConversationHistory(pid, aiMessages).catch(console.error);

      // Once decided, close the proposal's diff tab if one is open.
      const tabId = DIFF_PREFIX + path;
      let { openFiles, activeFile, diffTabs } = s;
      if (diffTabs[tabId]) {
        diffTabs = { ...diffTabs };
        delete diffTabs[tabId];
        openFiles = openFiles.filter((f: string) => f !== tabId);
        if (activeFile === tabId) {
          activeFile = openFiles.length > 0 ? openFiles[openFiles.length - 1] : null;
        }
      }
      return { ...s, aiMessages, openFiles, activeFile, diffTabs };
    });
  },

  approveProposal: async (msgId: string, path: string) => {
    let proposal: FileProposal | undefined;
    let projectId: string | null = null;
    workspaceStore.update(s => {
      projectId = s.activeProjectId;
      const m = s.aiMessages.find(x => x.id === msgId);
      proposal = m?.proposals?.find(p => p.path === path);
      return s;
    });
    if (!proposal || !projectId) return;
    try {
      // Cancel any pending editor-save debounce so it can't write stale,
      // pre-approval content back over the file we just persisted.
      // @ts-ignore - debounce handle is parked on window by updateFileContent
      clearTimeout(window.__saveTimeout);
      if (proposal.deleted) {
        await api.deleteFile(projectId, proposal.path);
      } else {
        await api.upsertFile(projectId, proposal.path, proposal.code, proposal.language || "c");
      }
      actions._setProposalDecision(msgId, path, "allowed");
      // Reflect the approved change in the editor immediately.
      await actions.refreshProjectFiles(projectId);
      const key = "/" + proposal.path;
      if (!proposal.deleted) {
        workspaceStore.update(s => ({
          ...s,
          activeFile: key,
          openFiles: s.openFiles.includes(key) ? s.openFiles : [...s.openFiles, key],
        }));
      }
      actions.loadGitStatus();
    } catch (e) {
      console.error("Failed to apply proposal", e);
    }
  },

  rejectProposal: (msgId: string, path: string) => {
    actions._setProposalDecision(msgId, path, "rejected");
  },

  approveAllProposals: async (msgId: string) => {
    let pending: string[] = [];
    workspaceStore.update(s => {
      const m = s.aiMessages.find(x => x.id === msgId);
      pending = (m?.proposals || []).filter(p => p.decision === "pending").map(p => p.path);
      return s;
    });
    for (const path of pending) {
      await actions.approveProposal(msgId, path);
    }
  },

  // --- Proposal diff tabs (open a proposed change as an editor diff tab) ------
  // Opens the proposed file as a side-by-side diff tab (original vs modified).
  // Allow/Reject from the tab call the same approveProposal/rejectProposal, so
  // the chat panel's proposal card stays in sync automatically.
  openDiffProposal: (msgId: string, path: string) => {
    const tabId = DIFF_PREFIX + path;
    workspaceStore.update(s => {
      const openFiles = s.openFiles.includes(tabId) ? s.openFiles : [...s.openFiles, tabId];
      return {
        ...s,
        openFiles,
        activeFile: tabId,
        diffTabs: { ...s.diffTabs, [tabId]: { path, msgId } },
      };
    });
  },

  // Open every still-pending proposal from a message as diff tabs at once, and
  // focus the first. Used when the agent finishes proposing changes.
  openAllDiffProposals: (msgId: string) => {
    let pending: string[] = [];
    workspaceStore.update(s => {
      const m = s.aiMessages.find(x => x.id === msgId);
      pending = (m?.proposals || []).filter(p => p.decision === "pending").map(p => p.path);
      if (pending.length === 0) return s;
      const newTabs = { ...s.diffTabs };
      let openFiles = [...s.openFiles];
      for (const path of pending) {
        const tabId = DIFF_PREFIX + path;
        newTabs[tabId] = { path, msgId };
        if (!openFiles.includes(tabId)) openFiles.push(tabId);
      }
      return { ...s, openFiles, diffTabs: newTabs, activeFile: DIFF_PREFIX + pending[0] };
    });
  },

  clearQueuedAiFollowup: () => {
    workspaceStore.update(s => ({ ...s, queuedAiFollowup: null }));
  },

  cancelAiMessage: () => {
    if (agentAbortController) {
      agentAbortController.abort();
      agentAbortController = null;
    }
    workspaceStore.update(s => {
      const msgs = s.aiMessages.map(m => {
        if (m.streaming) {
          return { ...m, streaming: false, text: m.text || "Generation cancelled by user." };
        }
        return m;
      });
      return { ...s, aiMessages: msgs, aiWaiting: false };
    });
  },

  sendAiMessage: async (text: string) => {
    const cleanText = text.trim();
    if (!cleanText) return;

    let projectId: string | null = null;
    let queuedForActiveRun = false;
    workspaceStore.update(state => {
      const activeRun = state.aiMessages.some(m => m.sender === "ai" && m.streaming);
      if (activeRun) {
        queuedForActiveRun = true;
        return { ...state, queuedAiFollowup: cleanText };
      }

      projectId = state.activeProjectId;
      
      // Mark previous AI message as submitted when user submits an answer
      const updatedMessages = [...state.aiMessages];
      const lastAiIndex = updatedMessages.map(m => m.sender === 'ai').lastIndexOf(true);
      if (lastAiIndex !== -1) {
        updatedMessages[lastAiIndex] = {
          ...updatedMessages[lastAiIndex],
          submitted: true
        };
      }

      return {
        ...state,
        aiMessages: [
          ...updatedMessages,
          {
            id: Math.random().toString(),
            sender: "user",
            text: cleanText,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
          }
        ],
        aiWaiting: true
      };
    });

    if (queuedForActiveRun) return;

    if (projectId) {
      let currentMsgs: ChatMessage[] = [];
      workspaceStore.subscribe(s => { currentMsgs = s.aiMessages; })();
      api.saveConversationHistory(projectId, currentMsgs).catch(console.error);
    }
      
    try {
      let history: any[] = [];
      let currentPhase: string | undefined = undefined;
      let buildOutput = "";

      let selectedProvider = "deepseek";
      let autoApprove = false;
      workspaceStore.update(s => {
        history = s.aiMessages.map(m => ({
          role: m.sender === "ai" ? "assistant" : "user",
          content: m.text
        }));

        const lastAiMsg = [...s.aiMessages].reverse().find(m => m.sender === "ai" && m.phase);
        if (lastAiMsg) {
          currentPhase = lastAiMsg.phase;
        }

        // Read the currently selected LLM provider
        selectedProvider = (s as any).selectedProvider || "deepseek";
        autoApprove = (s as any).autoApproveAgent || false;
        buildOutput = s.buildLogs.join("\n").slice(-20000);

        return s;
      });

      // Simulation command interceptor (for UI testing) — kept on the old
      // non-streaming path so the canned questionnaire demos still work.
      const simCmd = text.toLowerCase().startsWith("simulate ")
        ? text.toLowerCase().substring(9).trim()
        : null;
      const simResponses: Record<string, any> = {
        radio: { wiring: { status: "waiting_for_user", question: "Please select the target SPI clock polarity (CPOL):", options: ["CPOL = 0 (Clock active high, idle low)", "CPOL = 1 (Clock active low, idle high)"], inputType: "radio", phase: "spi_setup" } },
        checkbox: { wiring: { status: "waiting_for_user", question: "Select the GPIO peripherals you want to enable:", options: ["GPIOA (pins PA0-PA15)", "GPIOB (pins PB0-PB15)", "GPIOC (pins PC0-PC15)", "GPIOD (pins PD0-PD15)"], inputType: "checkbox", phase: "gpio_setup" } },
        select: { wiring: { status: "waiting_for_user", question: "Choose a prescaler value for the timer clock division:", options: ["Prescaler = 1", "Prescaler = 2", "Prescaler = 4", "Prescaler = 8", "Prescaler = 16"], inputType: "select", phase: "timer_setup" } },
        approval: { wiring: { status: "waiting_for_approval", question: "Do you approve this configuration plan?", final: "1. Enable RCC clock for GPIOA.\n2. Configure PA5 mode register (MODER) as output.\n3. Configure speed register (OSPEEDR) as Medium speed.\n4. Initialize state register (ODR) as low.", phase: "approval_phase" } },
      };

      // Maps a final response/done payload onto the user-facing fields of an AI message.
      const finalizeFields = (status: string, finalText: string, question: string, options?: string[], phase?: string) => {
        let aiText = (finalText || "").trim() || "I successfully completed your request.";
        let plan: string | undefined = undefined;
        let inputType: any = "buttons";
        if (status === "waiting_for_user") {
          aiText = question || "I need more information.";
        } else if (status === "waiting_for_approval") {
          plan = finalText;
          aiText = "Do you approve this plan?";
        }
        return { text: aiText, status: status || "completed", plan, options, phase, inputType };
      };

      if (simCmd && simResponses[simCmd]) {
        // Old canned demo path.
        const response = simResponses[simCmd];
        const r = response.wiring;
        const f = finalizeFields(r.status, r.final, r.question, r.options, r.phase);
        workspaceStore.update(s => {
          const newMsg: ChatMessage = {
            id: Math.random().toString(), sender: "ai", timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            ...f, inputType: r.inputType || "buttons", submitted: false,
          };
          const updatedMsgs = [...s.aiMessages, newMsg];
          if (projectId) api.saveConversationHistory(projectId, updatedMsgs).catch(console.error);
          return { ...s, aiMessages: updatedMsgs, aiWaiting: false };
        });
        return;
      }

      // --- Real agent run over SSE ---
      // Insert a live placeholder AI message that we mutate as events arrive.
      const aiMsgId = Math.random().toString();
      workspaceStore.update(s => ({
        ...s,
        aiWaiting: false,            // dots handled by the streaming placeholder now
        aiMessages: [...s.aiMessages, {
          id: aiMsgId, sender: "ai", text: "",
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          steps: [], thinking: "", thinkingDone: false, thinkingCollapsed: false,
          streaming: true, submitted: false,
        } as ChatMessage],
      }));

      // Mutate the placeholder message in place by id.
      const patchAiMsg = (fn: (m: ChatMessage) => void) => {
        workspaceStore.update(s => {
          const msgs = s.aiMessages.map(m => {
            if (m.id !== aiMsgId) return m;
            const copy: ChatMessage = { ...m, steps: [...(m.steps || [])] };
            fn(copy);
            return copy;
          });
          return { ...s, aiMessages: msgs };
        });
      };

      let sawAnyEvent = false;
      agentAbortController = new AbortController();
      await api.streamAgent(cleanText, (ev: any) => {
        sawAnyEvent = true;
        switch (ev.type) {
          case "think":
            patchAiMsg(m => {
              m.thinking = ev.text;
              m.thinkingDone = false;
              (m.steps as AgentStep[]).push({ kind: "think", text: ev.text });
            });
            break;
          case "call":
            patchAiMsg(m => {
              m.thinkingDone = true;       // thinking is over once a call lands
              m.thinkingCollapsed = true;  // auto-collapse the think block
              (m.steps as AgentStep[]).push({ kind: "call", name: ev.name, args: ev.args });
            });
            // When the agent runs a build/flash, surface it in the BUILD OUTPUT
            // panel just like the manual button does.
            if (ev.name === "build" || ev.name === "flash") {
              workspaceStore.update(s => ({ ...s, terminalOpen: true, activeBottomTab: "memory" }));
              actions.clearBuildLogs();
              actions.addBuildLog(ev.name === "build"
                ? "Agent is building firmware (PlatformIO)..."
                : "Agent is flashing firmware to target...");
            }
            break;
          case "code":
            // Legacy event kept for back-compat; treated as an informational card.
            patchAiMsg(m => {
              (m.steps as AgentStep[]).push({ kind: "code", path: ev.path, code: ev.code });
            });
            break;
          case "proposal":
            // A staged file change. Render a diff card with Allow/Reject; do NOT
            // touch the editor/DB until the user approves.
            patchAiMsg(m => {
              (m.steps as AgentStep[]).push({
                kind: "proposal", path: ev.path, code: ev.code, old: ev.old,
                deleted: ev.deleted, decision: "pending",
              });
              const list = (m.proposals ||= []);
              const existing = list.find(p => p.path === ev.path);
              const prop: FileProposal = {
                path: ev.path, language: ev.deleted ? "c" : "c",
                old: ev.old || "", code: ev.code || "",
                deleted: ev.deleted, created: !ev.old,
                decision: "pending",
              };
              if (existing) Object.assign(existing, prop);
              else list.push(prop);
            });
            break;
          case "result":
            patchAiMsg(m => {
              (m.steps as AgentStep[]).push({ kind: "result", name: ev.name, result: ev.result });
            });
            // Mirror the agent's build/flash output into the BUILD OUTPUT panel.
            if (ev.name === "build" || ev.name === "flash") {
              (ev.result || "").split("\n").forEach((line: string) => actions.addBuildLog(line));
            }
            break;
          case "note":
            patchAiMsg(m => {
              (m.steps as AgentStep[]).push({ kind: "note", text: ev.message || ev.text });
            });
            break;
          case "error":
            patchAiMsg(m => {
              (m.steps as AgentStep[]).push({ kind: "error", text: ev.message });
            });
            break;
          case "question":
            patchAiMsg(m => {
              m.status = "waiting_for_user";
              m.text = ev.question || "I need more information.";
              m.options = ev.options;
              m.inputType = "buttons";
            });
            break;
          case "plan":
            patchAiMsg(m => {
              m.status = "waiting_for_approval";
              m.plan = ev.plan;
              m.text = "Do you approve this plan?";
            });
            break;
          case "final":
            patchAiMsg(m => {
              // Only overwrite text if we are not in an interactive wait state.
              if (m.status !== "waiting_for_user" && m.status !== "waiting_for_approval") {
                m.text = (ev.text || "").trim();
              }
            });
            break;
          case "done":
            patchAiMsg(m => {
              m.streaming = false;
              m.thinkingDone = true;
              m.thinkingCollapsed = true;
              if (m.status !== "waiting_for_user" && m.status !== "waiting_for_approval") {
                const f = finalizeFields(ev.status, ev.final, ev.question, ev.options);
                m.text = m.text?.trim() || f.text;
                m.status = f.status;
                if (ev.status === "waiting_for_user") { m.text = ev.question || m.text; m.options = ev.options; }
                if (ev.status === "waiting_for_approval") { m.plan = ev.final; m.text = "Do you approve this plan?"; }
              }
            });
            // `proposals` is the authoritative final diff set computed on the
            // backend. Reconcile against the live-streamed proposals so the
            // message ends with exactly the changes the user can approve.
            if (Array.isArray(ev.proposals)) {
              patchAiMsg(m => {
                const list = (m.proposals ||= []);
                for (const p of ev.proposals) {
                  const existing = list.find(x => x.path === p.path);
                  const merged: FileProposal = {
                    path: p.path, language: p.language || "c",
                    old: p.old || "", code: p.code || "",
                    deleted: p.deleted, created: p.created,
                    decision: existing?.decision || "pending",
                  };
                  if (existing) Object.assign(existing, merged);
                  else list.push(merged);
                }
              });
              // With auto-approve on, apply every proposed file change without
              // asking. Otherwise open them as diff tabs in the editor so the
              // user can review original-vs-proposed and Allow/Reject there.
              if (ev.proposals.length > 0) {
                if (autoApprove) {
                  actions.approveAllProposals(aiMsgId);
                } else {
                  actions.openAllDiffProposals(aiMsgId);
                }
              }
            }
            break;
        }
      }, history, currentPhase, selectedProvider, buildOutput, agentAbortController.signal, autoApprove);

      // Stream closed. Nothing is auto-applied: the agent's file changes are
      // staged as proposals and only persisted when the user clicks Allow.

      // Finalize: ensure streaming flag is cleared and persist history.
      let queuedFollowup: string | null = null;
      agentAbortController = null;
      workspaceStore.update(s => {
        const msgs = s.aiMessages.map(m => {
          if (m.id !== aiMsgId) return m;
          const copy = { ...m, streaming: false };
          if (!copy.text?.trim() && (!copy.status || copy.status === "completed")) {
            copy.text = sawAnyEvent ? "Done." : "I successfully completed your request.";
          }
          return copy;
        });
        queuedFollowup = s.queuedAiFollowup?.trim() || null;
        if (projectId) api.saveConversationHistory(projectId, msgs).catch(console.error);
        return { ...s, aiMessages: msgs, aiWaiting: false, queuedAiFollowup: null };
      });
      if (queuedFollowup) {
        window.setTimeout(() => actions.sendAiMessage(queuedFollowup!), 0);
      }
    } catch (e: any) {
      if (e.name === 'AbortError') {
        return;
      }
      workspaceStore.update(s => {
        const errorMsg: ChatMessage = {
          id: Math.random().toString(),
          sender: "ai",
          text: `❌ **Error connecting to agent:** ${e.message}`,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        };
        const updatedMsgs = [...s.aiMessages, errorMsg];
        if (projectId) {
          api.saveConversationHistory(projectId, updatedMsgs).catch(console.error);
        }
        return {
          ...s,
          aiMessages: updatedMsgs,
          aiWaiting: false
        };
      });
    }
  },

  clearChat: async (projectId: string) => {
    try {
      await api.deleteConversationHistory(projectId);
      workspaceStore.update(s => ({
        ...s,
        aiMessages: [
          {
            id: "default-greeting",
            sender: "ai",
            text: "Hello! I am your HARDCOREAI Copilot. I have loaded context for your selected target, SVD registers, and your current PlatformIO configuration. \n\nHow can I help you write or debug firmware today?",
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
          }
        ]
      }));
    } catch (e) {
      console.error("Failed to clear chat history", e);
    }
  },

  renameProject: async (id: string, name: string) => {
    try {
      await api.renameProject(id, name);
      await actions.loadProjects();
    } catch (e) {
      console.error("Failed to rename project", e);
      alert("Failed to rename project");
    }
  },

  deleteActiveProject: async (id: string) => {
    try {
      await api.deleteProject(id);
      await actions.loadProjects();
      workspaceStore.update(s => ({
        ...s,
        activeProjectId: null,
        showWelcomeScreen: true
      }));
    } catch (e) {
      console.error("Failed to delete project", e);
      alert("Failed to delete project");
    }
  },

  // ── Library Manager Actions ──

  fetchAvailableLibraries: async () => {
    let query = "";
    let category = "";
    workspaceStore.subscribe(s => {
      query = s.librarySearchQuery;
      category = s.librarySelectedCategory;
    })();
    workspaceStore.update(s => ({ ...s, librariesLoading: true }));
    try {
      const libs = await api.getAvailableLibraries(query, category);
      workspaceStore.update(s => ({ ...s, availableLibraries: libs, librariesLoading: false }));
    } catch (e) {
      console.error("Failed to fetch libraries", e);
      workspaceStore.update(s => ({ ...s, librariesLoading: false }));
    }
  },

  fetchLibraryCategories: async () => {
    try {
      const cats = await api.getLibraryCategories();
      workspaceStore.update(s => ({ ...s, libraryCategories: cats }));
    } catch (e) {
      console.error("Failed to fetch library categories", e);
    }
  },

  fetchInstalledLibraries: async (projectId: string) => {
    try {
      const libs = await api.getInstalledLibraries(projectId);
      workspaceStore.update(s => ({ ...s, installedLibraries: libs }));
    } catch (e) {
      console.error("Failed to fetch installed libraries", e);
    }
  },

  setLibraryManagerTab: (tab: "discover" | "installed" | "updates") => {
    workspaceStore.update(s => ({ ...s, libraryManagerTab: tab }));
    if (tab === "installed") {
      let pid: string | null = null;
      workspaceStore.subscribe(s => { pid = s.activeProjectId; })();
      if (pid) actions.fetchInstalledLibraries(pid);
    }
  },

  setLibrarySearch: (query: string) => {
    workspaceStore.update(s => ({ ...s, librarySearchQuery: query }));
  },

  setLibraryCategory: (category: string) => {
    workspaceStore.update(s => ({ ...s, librarySelectedCategory: category }));
  },

  confirmInstallLibrary: (libraryId: string) => {
    workspaceStore.update(s => ({
      ...s,
      libraryInstallStatus: { ...s.libraryInstallStatus, [libraryId]: "confirming" }
    }));
  },

  cancelInstallLibrary: (libraryId: string) => {
    workspaceStore.update(s => ({
      ...s,
      libraryInstallStatus: { ...s.libraryInstallStatus, [libraryId]: "idle" }
    }));
  },

  installLibrary: async (libraryId: string) => {
    let projectId: string | null = null;
    workspaceStore.subscribe(s => { projectId = s.activeProjectId; })();
    if (!projectId) {
      alert("No active project. Open a project first.");
      return;
    }
    workspaceStore.update(s => ({
      ...s,
      libraryInstallStatus: { ...s.libraryInstallStatus, [libraryId]: "installing" }
    }));
    try {
      await api.installLibrary(projectId, libraryId);
      workspaceStore.update(s => ({
        ...s,
        libraryInstallStatus: { ...s.libraryInstallStatus, [libraryId]: "installed" }
      }));
      // Refresh installed list
      await actions.fetchInstalledLibraries(projectId);
    } catch (e: any) {
      workspaceStore.update(s => ({
        ...s,
        libraryInstallStatus: { ...s.libraryInstallStatus, [libraryId]: "error" },
        libraryInstallError: { ...s.libraryInstallError, [libraryId]: e.message || "Install failed" }
      }));
    }
  },

  uninstallLibrary: async (libraryId: string) => {
    let projectId: string | null = null;
    workspaceStore.subscribe(s => { projectId = s.activeProjectId; })();
    if (!projectId) return;
    try {
      await api.uninstallLibrary(projectId, libraryId);
      workspaceStore.update(s => ({
        ...s,
        libraryInstallStatus: { ...s.libraryInstallStatus, [libraryId]: "idle" },
        installedLibraries: s.installedLibraries.filter((l: any) => l.id !== libraryId)
      }));
    } catch (e: any) {
      alert("Failed to uninstall: " + e.message);
    }
  },

  // ── Debug Actions ──────────────────────────────────────────────────────────

  startDebugging: async () => {
    let pid: string | null = null;
    let board: string = "bluepill_f103c8";
    workspaceStore.subscribe(s => {
      pid = s.activeProjectId;
      board = s.selectedBoard || "bluepill_f103c8";
    })();
    if (!pid) return;

    // Reset debug state
    workspaceStore.update(s => ({
      ...s,
      isDebugging: true,
      debugLog: ["Starting debug session..."],
      debugHalted: false,
      debugCurrentFile: null,
      debugCurrentLine: null,
      debugStopReason: null,
      debugRegisters: [],
      debugCallStack: [],
      debugLocals: [],
    }));

    try {
      const snapshot = await api.startDebug(pid, board);
      actions.handleDebugEvent({ type: "stopped", snapshot });
      
      // Open stream
      const controller = new AbortController();
      // Store the controller somewhere if we need to abort it later, or just let stopDebugging kill the backend which will close the stream.
      api.streamDebug(pid, (event) => actions.handleDebugEvent(event), controller.signal);
      
      workspaceStore.update(s => ({
        ...s,
        debuggerActive: true,
        activeSidebarTab: "debug",
        terminalOpen: true,
      }));
    } catch (e: any) {
      workspaceStore.update(s => ({
        ...s,
        isDebugging: false,
        debuggerActive: false,
        debugLog: [...s.debugLog, `[Error] ${e.message}`]
      }));
    }
  },

  stopDebugging: async () => {
    let pid: string | null = null;
    workspaceStore.subscribe(s => { pid = s.activeProjectId; })();
    if (!pid) return;

    try {
      await api.stopDebug(pid);
    } catch (e) {
      // Ignore
    }
    
    workspaceStore.update(s => ({
      ...s,
      isDebugging: false,
      debuggerActive: false,
      debugHalted: false,
      debugCurrentFile: null,
      debugCurrentLine: null,
      debugStopReason: null,
      debugRegisters: [],
      debugCallStack: [],
      debugLocals: [],
      debugLog: [...s.debugLog, "Debug session stopped."]
    }));
  },

  toggleBreakpoint: async (file: string, line: number) => {
    let pid: string | null = null;
    let bps: any[] = [];
    workspaceStore.subscribe(s => { 
      pid = s.activeProjectId; 
      bps = s.debugBreakpoints;
    })();
    if (!pid) return;

    const existing = bps.find(b => b.file === file && b.line === line);
    if (existing) {
      // Optimistic remove
      workspaceStore.update(s => ({
        ...s,
        debugBreakpoints: s.debugBreakpoints.filter(b => b !== existing)
      }));
      if (existing.id !== null) {
        try {
          await api.removeBreakpoint(pid, existing.id);
        } catch {
          // Revert if failed
          workspaceStore.update(s => ({ ...s, debugBreakpoints: [...s.debugBreakpoints, existing] }));
        }
      }
    } else {
      // Optimistic add (without ID)
      const optimistic = { id: null, file, line };
      workspaceStore.update(s => ({
        ...s,
        debugBreakpoints: [...s.debugBreakpoints, optimistic]
      }));
      try {
        const bp = await api.setBreakpoint(pid, file, line);
        workspaceStore.update(s => ({
          ...s,
          debugBreakpoints: s.debugBreakpoints.map(b => (b.file === file && b.line === line) ? { ...b, id: bp.id } : b)
        }));
      } catch (e) {
        // Revert
        workspaceStore.update(s => ({
          ...s,
          debugBreakpoints: s.debugBreakpoints.filter(b => b !== optimistic)
        }));
      }
    }
  },

  continueExecution: async () => {
    let pid: string | null = null;
    workspaceStore.subscribe(s => { pid = s.activeProjectId; })();
    if (!pid) return;
    workspaceStore.update(s => ({ ...s, debugHalted: false, debugCurrentLine: null }));
    try { await api.debugContinue(pid); } catch (e) { /* handle */ }
  },

  stepOver: async () => {
    let pid: string | null = null;
    workspaceStore.subscribe(s => { pid = s.activeProjectId; })();
    if (!pid) return;
    workspaceStore.update(s => ({ ...s, debugHalted: false, debugCurrentLine: null }));
    try { await api.debugStepOver(pid); } catch (e) { /* handle */ }
  },

  stepInto: async () => {
    let pid: string | null = null;
    workspaceStore.subscribe(s => { pid = s.activeProjectId; })();
    if (!pid) return;
    workspaceStore.update(s => ({ ...s, debugHalted: false, debugCurrentLine: null }));
    try { await api.debugStepInto(pid); } catch (e) { /* handle */ }
  },

  stepOut: async () => {
    let pid: string | null = null;
    workspaceStore.subscribe(s => { pid = s.activeProjectId; })();
    if (!pid) return;
    workspaceStore.update(s => ({ ...s, debugHalted: false, debugCurrentLine: null }));
    try { await api.debugStepOut(pid); } catch (e) { /* handle */ }
  },

  handleDebugEvent: (event: any) => {
    workspaceStore.update(s => {
      const state = { ...s };
      if (event.type === "log" && event.text) {
        state.debugLog = [...state.debugLog, event.text.trim()];
      } else if (event.type === "running") {
        state.debugHalted = false;
        state.debugCurrentLine = null;
      } else if (event.type === "stopped" && event.snapshot) {
        const snap = event.snapshot;
        state.debugHalted = snap.state.halted;
        state.debugCurrentFile = snap.state.file;
        state.debugCurrentLine = snap.state.line;
        state.debugStopReason = snap.state.reason;
        
        if (snap.error) {
          state.debugLog = [...state.debugLog, `[Error] ${snap.error}`];
          state.debuggerActive = false;
          state.isDebugging = false;
        } else {
          state.debuggerActive = true;
          if (snap.registers) state.debugRegisters = snap.registers;
          if (snap.call_stack) state.debugCallStack = snap.call_stack;
          if (snap.locals) state.debugLocals = snap.locals;
          if (snap.breakpoints && snap.breakpoints.length > 0) {
            // Update known IDs
            const bps = [...state.debugBreakpoints];
            snap.breakpoints.forEach((b: any) => {
              const match = bps.find(x => x.file === b.file && x.line === b.line);
              if (match) match.id = b.id;
              else bps.push({ id: b.id, file: b.file, line: b.line });
            });
            state.debugBreakpoints = bps;
          }
          
          if (state.debugHalted && state.debugCurrentFile) {
            state.debugLog = [...state.debugLog, `[Halted] ${state.debugCurrentFile}:${state.debugCurrentLine} (${state.debugStopReason || 'unknown'})`];
            
            // Auto-switch to file
            const fileName = state.debugCurrentFile.split('/').pop();
            // find path in open files if possible
            const matchingFile = state.fileTree.find(f => f.path.endsWith(fileName!));
            if (matchingFile) {
              state.activeFile = matchingFile.path;
              if (!state.openFiles.includes(matchingFile.path)) {
                state.openFiles = [...state.openFiles, matchingFile.path];
              }
            }
          }
        }
      }
      return state;
    });
  }
};

// Subscribe to workspaceStore and persist state to localStorage
if (typeof window !== "undefined") {
  workspaceStore.subscribe(s => {
    try {
      if (s.activeProjectId) {
        localStorage.setItem("activeProjectId", JSON.stringify(s.activeProjectId));
        // Save project-specific pins
        localStorage.setItem(`pins_${s.activeProjectId}`, JSON.stringify(s.pins));
      } else {
        localStorage.removeItem("activeProjectId");
      }
      if (s.activeFile) {
        localStorage.setItem("activeFile", JSON.stringify(s.activeFile));
      } else {
        localStorage.removeItem("activeFile");
      }
      localStorage.setItem("openFiles", JSON.stringify(s.openFiles));
      localStorage.setItem("showWelcomeScreen", JSON.stringify(s.showWelcomeScreen));

      // Global UI configurations
      localStorage.setItem("selectedBoard", JSON.stringify(s.selectedBoard));
      localStorage.setItem("selectedProbe", JSON.stringify(s.selectedProbe));
      localStorage.setItem("toolchainPath", JSON.stringify(s.toolchainPath));
      localStorage.setItem("activeSidebarTab", JSON.stringify(s.activeSidebarTab));
      localStorage.setItem("activeBottomTab", JSON.stringify(s.activeBottomTab));
      localStorage.setItem("terminalOpen", JSON.stringify(s.terminalOpen));
    } catch (e) {
      console.error("Failed to sync store to localStorage:", e);
    }
  });
}
