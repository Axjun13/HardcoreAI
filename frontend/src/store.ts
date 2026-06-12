import { writable } from "svelte/store";
import { api } from "./api";

export interface FileItem {
  name: string;
  path: string;
  isFolder: boolean;
  children?: FileItem[];
}

export interface RegisterItem {
  name: string;
  value: string;
  description: string;
  bits?: { name: string; value: number; range: string; description: string }[];
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
}


// Pin configuration data
const stm32F401Pins = [
  "VBAT", "PC13", "PC14", "PC15", "PH0", "PH1", "NRST", "PC0",
  "PC1", "PC2", "PC3", "VSSA", "VDDA", "PA0", "PA1", "PA2",
  "PA3", "VSS", "VDD", "PA4", "PA5", "PA6", "PA7", "PC4",
  "PC5", "PB0", "PB1", "PB2", "PB10", "PB11", "VSS", "VDD",
  "PB12", "PB13", "PB14", "PB15", "PC6", "PC7", "PC8", "PC9",
  "PA8", "PA9", "PA10", "PA11", "PA12", "PA13", "VCAP", "VSS",
  "VDD", "PA14", "PA15", "PC10", "PC11", "PC12", "PD2", "PB3",
  "PB4", "PB5", "PB6", "PB7", "BOOT0", "PB8", "PB9", "VSS",
];

const initialPins: PinConfig[] = stm32F401Pins.map((pin, index) => {
  const defaults: Partial<PinConfig> = {};
  if (pin === "PA5") Object.assign(defaults, { signal: "GPIO_Output", mode: "Output Push Pull", label: "LED", enabled: true });
  if (pin === "PA2") Object.assign(defaults, { signal: "USART2_TX", mode: "Alternate Function", label: "UART TX", af: "AF7", enabled: true });
  if (pin === "PA3") Object.assign(defaults, { signal: "USART2_RX", mode: "Alternate Function", label: "UART RX", af: "AF7", enabled: true });
  if (pin === "PB6") Object.assign(defaults, { signal: "I2C1_SCL", mode: "Alternate Function", label: "I2C SCL", af: "AF4", enabled: true });
  if (pin === "PB7") Object.assign(defaults, { signal: "I2C1_SDA", mode: "Alternate Function", label: "I2C SDA", af: "AF4", enabled: true });

  const isPower = ["VSS", "VDD", "VBAT", "VDDA", "VSSA", "VCAP"].includes(pin);
  const isSystem = ["NRST", "BOOT0", "PH0", "PH1"].includes(pin);

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
  if (!isBrowser) return "STM32F401";
  try {
    const val = localStorage.getItem("selectedBoard");
    return val ? JSON.parse(val) : "STM32F401";
  } catch {
    return "STM32F401";
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
  gitChanges: [] as { path: string; status: string }[],
  fileContents: {} as Record<string, string>,
  fileTree: [] as FileItem[],

  // Compilation & Flashing
  isCompiling: false,
  isFlashing: false,
  buildLogs: [] as string[],
  // Live hardware connection status (polled from the backend)
  deviceStatus: { connected: false, probe: null as string | null, target: null as string | null, detail: "" },

  // GDB Debugging
  isDebugging: false,
  debuggerActive: false,
  currentLine: null as number | null,
  breakpoints: [] as number[],
  callStack: [] as string[],
  registers: [] as RegisterItem[],
  crashed: false,
  crashReason: null as string | null,

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
  selectedProvider: "openrouter",

  // UI Tabs
  activeBottomTab: getInitialActiveBottomTab() as "terminal" | "registers" | "memory",
  terminalOpen: getInitialTerminalOpen(),  // whether the bottom drawer (serial/build/etc.) is expanded
  showWelcomeScreen: getInitialShowWelcomeScreen(),
  activeSidebarTab: getInitialActiveSidebarTab() as "explorer" | "search" | "git" | "debug" | "extensions" | "boards" | "rag" | "libraries",
  selectedBoard: getInitialSelectedBoard() as "STM32F401" | "ESP32-S3" | "RP2040",
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
export const actions = {
  loadProjects: async () => {
    try {
      const projects = await api.getProjects();
      workspaceStore.update(s => ({ ...s, projectsList: projects }));
    } catch (e) {
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
              text: "Hello! I am your HARDCOREAI Copilot. I have loaded context for the **STM32F401RET6** target, SVD registers, and your current `CMake` configuration. \n\nHow can I help you write or debug firmware today?",
              timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
            }
          ];
        }
      } catch (err) {
        console.error("Failed to load chat history", err);
      }

      workspaceStore.update(s => {
        const filePaths = files.map(f => "/" + String(f.path || "").replace(/^\/+/, ""));
        
        let activeFile = s.activeFile;
        let openFiles = s.openFiles;
        
        if (!activeFile || !filePaths.includes(activeFile)) {
          activeFile = files.length > 0 ? "/" + files[0].path : null;
        }
        
        openFiles = openFiles.filter(f => filePaths.includes(f));
        if (openFiles.length === 0 && activeFile) {
          openFiles = [activeFile];
        }

        const savedPins = getSavedPins(id) || initialPins;

        return {
          ...s,
          activeProjectId: id,
          fileTree,
          fileContents,
          activeFile,
          openFiles,
          aiMessages: history,
          pins: savedPins,
          // Clear all session-specific state so previous project data doesn't bleed over
          buildLogs: [],
          serialLogs: [],
          isDebugging: false,
          debuggerActive: false,
          currentLine: null,
          crashed: false,
          crashReason: null,
        };
      });
      
      // Also fetch RAG documents for this project
      await actions.fetchRagDocuments();
      // Load git status
      await actions.loadGitStatus();
    } catch (e) {
      console.error("Failed to load project files", e);
    }
  },

  setActiveFile: (path: string | null) => {
    workspaceStore.update(s => {
      if (!path) return { ...s, activeFile: null };
      const openFiles = s.openFiles.includes(path) ? s.openFiles : [...s.openFiles, path];
      return { ...s, openFiles, activeFile: path };
    });
  },

  closeFileTab: (path: string) => {
    workspaceStore.update(s => {
      const openFiles = s.openFiles.filter(f => f !== path);
      let activeFile = s.activeFile;
      if (activeFile === path) {
        activeFile = openFiles.length > 0 ? openFiles[openFiles.length - 1] : null;
      }
      return { ...s, openFiles, activeFile };
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
    workspaceStore.update(s => {
      projectId = s.activeProjectId;
      return {
        ...s,
        fileContents: { ...s.fileContents, [path]: content }
      };
    });
    
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

  // Real PlatformIO build — streams the compiler output live into the Build Output
  // tab (auto-opening it), then feeds the result to the agent.
  runBuild: async () => {
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
      actions.notifyAgentOfBuild(done);
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
  pollDeviceStatus: async () => {
    try {
      const res = await api.getDeviceStatus();
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

  toggleBreakpoint: (line: number) => {
    workspaceStore.update(s => ({
      ...s,
      breakpoints: s.breakpoints.includes(line)
        ? s.breakpoints.filter(l => l !== line)
        : [...s.breakpoints, line]
    }));
  },
  startDebugging: async () => {
    workspaceStore.update(s => ({
      ...s,
      isDebugging: true,
      debuggerActive: true,
      currentLine: 20,
      activeBottomTab: "registers"
    }));
    actions.addBuildLog('[GDB] Debugger UI requires backend GDB integration.');
  },
  stopDebugging: () => {
    workspaceStore.update(s => ({
      ...s,
      isDebugging: false,
      debuggerActive: false,
      currentLine: null,
      crashed: false,
      crashReason: null
    }));
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
  triggerCrash: () => {
    actions.addBuildLog('Crash UI requires backend GDB integration to trigger manually.');
  },
  resolveCrash: () => {
    actions.addBuildLog('Crash UI requires backend GDB integration to resolve manually.');
  },
  stepOver: () => {
    actions.addBuildLog('[GDB] Step requires backend GDB integration.');
  },
  continueExecution: () => {
    workspaceStore.update(s => ({ ...s, currentLine: null }));
  },
  setShowWelcomeScreen: (val: boolean) => {
    workspaceStore.update(s => ({ ...s, showWelcomeScreen: val }));
  },
  setActiveSidebarTab: (tab: "explorer" | "search" | "git" | "debug" | "extensions" | "boards" | "rag" | "libraries") => {
    workspaceStore.update(s => ({ ...s, activeSidebarTab: tab }));
    if (tab === "git") {
      actions.loadGitStatus();
    }
    if (tab === "libraries") {
      actions.fetchAvailableLibraries();
      actions.fetchLibraryCategories();
      let pid: string | null = null;
      workspaceStore.subscribe(s => { pid = s.activeProjectId; })();
      if (pid) actions.fetchInstalledLibraries(pid);
    }
  },
  setSelectedBoard: (board: "STM32F401" | "ESP32-S3" | "RP2040") => {
    workspaceStore.update(s => ({ ...s, selectedBoard: board }));
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
            tokens: 0
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
      return { ...s, aiMessages };
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

      let selectedProvider = "openrouter";
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
        selectedProvider = (s as any).selectedProvider || "openrouter";
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
            }
            break;
        }
      }, history, currentPhase, selectedProvider, buildOutput, agentAbortController.signal);

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
            text: "Hello! I am your HARDCOREAI Copilot. I have loaded context for the **STM32F401RET6** target, SVD registers, and your current `CMake` configuration. \n\nHow can I help you write or debug firmware today?",
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
