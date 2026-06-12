<script lang="ts">
  import { tick, onMount } from "svelte";
  import { api } from "./api";
  import { workspaceStore, actions, type FileItem } from "./store";
  import * as monaco from "monaco-editor";
  import EmbeddedConfigurator from "./components/EmbeddedConfigurator.svelte";
  import RagUploadPanel from "./components/RagUploadPanel.svelte";
  import LibraryManager from "./components/LibraryManager.svelte";

  import {
    Play,
    Zap,
    Bug,
    FolderOpen,
    FileCode,
    File,
    Send,
    AlertTriangle,
    Sparkles,
    ArrowRight,
    Search,
    GitBranch,
    Blocks,
    Folder,
    Settings,
    X,
    Plus,
    Moon,
    Sun,
    Cpu,
    Database,
    Sliders,
    Trash2,
    MonitorPlay,
    Copy,
    Check,
    Package,
    Camera,
    ArrowDown,
  } from "lucide-svelte";

  let aiInput = "";
  let serialInput = "";
  let selectedPeripheral = "Core Registers";
  let aiOpen = true;

  let showConfigurator = true;
  let showCopilot = true;

  let rightPaneSplit = 55;

  let buildOutputCopied = false;
  const agentWorkingPhrases = [
    "Thinking through firmware state",
    "Checking registers and files",
    "Preparing the next tool call",
    "Waiting for the next milestone",
  ];
  let agentWorkingPhraseIndex = 0;
  $: agentWorkingPhrase = agentWorkingPhrases[agentWorkingPhraseIndex];
  $: activeAgentStreaming = $workspaceStore.aiMessages.some(
    (m) => m.sender === "ai" && m.streaming,
  );
  $: queuedAiFollowup = $workspaceStore.queuedAiFollowup;

  // Delete confirmation modal state
  let deleteConfirmModal = {
    show: false,
    projectId: "",
    projectName: "",
    isActiveProject: false,
  };

  // Delete file/folder confirmation modal state
  let fileDeleteConfirmModal = {
    show: false,
    path: "",
    isFolder: false,
  };

  // Chat scrolling state and handlers
  let chatContentEl: HTMLDivElement | null = null;
  let showScrollToBottom = false;

  function handleChatScroll() {
    if (!chatContentEl) return;
    const { scrollTop, scrollHeight, clientHeight } = chatContentEl;
    showScrollToBottom = scrollHeight - scrollTop - clientHeight > 150;
  }

  function scrollToBottom() {
    if (chatContentEl) {
      chatContentEl.scrollTo({
        top: chatContentEl.scrollHeight,
        behavior: "smooth"
      });
    }
  }

  // Auto-scroll to bottom when messages change
  $: if ($workspaceStore.aiMessages && chatContentEl) {
    tick().then(() => {
      if (!chatContentEl) return;
      const { scrollTop, scrollHeight, clientHeight } = chatContentEl;
      if (scrollHeight - scrollTop - clientHeight < 300) {
        chatContentEl.scrollTo({
          top: chatContentEl.scrollHeight,
          behavior: "smooth"
        });
      }
    });
  }

  // Decoupled panel states
  let showSidebar = true;
  let showViewDropdown = false;
  let html2canvas: any = null;

  // Input prompt modal state (New File/Folder)
  let inputPromptModal = {
    show: false,
    title: "",
    placeholder: "",
    value: "",
    actionType: "file" as "file" | "folder" | "project",
    folderPath: "",
  };

  // Autocomplete @tag states
  let fileTagInputRef: HTMLInputElement;
  let showFileTagDropdown = false;
  let fileTagFilter = "";
  let fileTagIndex = 0;
  let fileTagTriggerPos = -1;

  let gitCommitMessage = "";
  let gitCommitting = false;
  let gitCommitFeedback = "";

  // Panel sizing
  let sidebarWidth = 260;
  let rightSidebarWidth = 420;
  let bottomDrawerHeight = 220;

  let isDraggingLeft = false;
  let isDraggingRight = false;
  let isDraggingBottom = false;

  let recentProjectsExpanded = false;
  let isLightTheme =
    typeof localStorage !== "undefined" &&
    localStorage.getItem("theme") === "light";
  let currentLine = 12;
  let currentColumn = 25;

  function startRightResize(e: MouseEvent) {
    e.preventDefault();

    const startY = e.clientY;
    const startSplit = rightPaneSplit;

    function move(ev: MouseEvent) {
      const container = document.querySelector(".split-sidebar-right");

      if (!container) return;

      const delta = ev.clientY - startY;

      rightPaneSplit = Math.max(
        20,
        Math.min(80, startSplit + (delta / container.clientHeight) * 100),
      );
    }

    function up() {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    }

    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  }

  function toggleTheme() {
    isLightTheme = !isLightTheme;
    if (typeof localStorage !== "undefined") {
      localStorage.setItem("theme", isLightTheme ? "light" : "dark");
    }
    if (isLightTheme) {
      document.body.classList.add("light-theme");
    } else {
      document.body.classList.remove("light-theme");
    }
    if (monacoEditor) {
      monaco.editor.setTheme(isLightTheme ? "vs" : "vs-dark");
    }
  }

  function handleKeyDown(e: KeyboardEvent) {
    if (e.ctrlKey && e.key === "o") {
      e.preventDefault();
      actions.setShowWelcomeScreen(true);
    }
  }

  onMount(() => {
    if (isLightTheme) {
      document.body.classList.add("light-theme");
    }
  });

  // DOM Elements
  let canvasEl: HTMLCanvasElement;
  let terminalEndRef: HTMLDivElement;
  let buildOutputEndRef: HTMLDivElement;
  let monacoEditor: monaco.editor.IStandaloneCodeEditor | null = null;

  async function handleMouseMove(e: MouseEvent) {
    if (isDraggingLeft) {
      sidebarWidth = Math.max(180, Math.min(450, e.clientX - 52));
      await tick();
      window.requestAnimationFrame(() => {
        if (monacoEditor) monacoEditor.layout();
        resetEditorScroll();
      });
    }
    if (isDraggingRight) {
      rightSidebarWidth = Math.max(
        360,
        Math.min(680, window.innerWidth - e.clientX),
      );
      await tick();
      window.requestAnimationFrame(() => {
        if (monacoEditor) monacoEditor.layout();
        resetEditorScroll();
      });
    }
    if (isDraggingBottom) {
      bottomDrawerHeight = Math.max(
        120,
        Math.min(500, window.innerHeight - e.clientY),
      );
      await tick();
      window.requestAnimationFrame(() => {
        if (monacoEditor) monacoEditor.layout();
        resetEditorScroll();
      });
    }
  }

  function resetEditorScroll() {
    const frame = document.querySelector(".monaco-editor-frame");
    const wrapper = document.querySelector(".monaco-editor-wrapper");
    const container = document.querySelector(".editor-container");
    if (frame) frame.scrollTop = 0;
    if (wrapper) wrapper.scrollTop = 0;
    if (container) container.scrollTop = 0;
  }

  function handleMouseUp() {
    isDraggingLeft = false;
    isDraggingRight = false;
    isDraggingBottom = false;
    document.body.classList.remove("dragging-row", "dragging-col");
    resetEditorScroll();
  }

  // Draw plot canvas reactively
  $: plotData = $workspaceStore.plotData;
  $: activeBottomTab = $workspaceStore.activeBottomTab;
  $: if (canvasEl && plotData && activeBottomTab === "plotter") {
    setTimeout(drawCanvas, 0);
  }

  onMount(async () => {
    await actions.loadProjects();
    if (typeof window !== "undefined") {
      const script = document.createElement("script");
      script.src = "https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js";
      script.onload = () => {
        html2canvas = (window as any).html2canvas;
      };
      document.head.appendChild(script);

      // Auto-load project files if there is a saved activeProjectId
      let savedProjId: string | null = null;
      workspaceStore.subscribe(s => { savedProjId = s.activeProjectId; })();
      if (savedProjId) {
        await actions.loadProject(savedProjId);
      }
    }
  });

  onMount(() => {
    const phraseTimer = window.setInterval(() => {
      agentWorkingPhraseIndex =
        (agentWorkingPhraseIndex + 1) % agentWorkingPhrases.length;
    }, 2200);

    return () => window.clearInterval(phraseTimer);
  });

  // Poll whether an ST-Link + STM32 board is connected, for the status chip.
  onMount(() => {
    actions.pollDeviceStatus();
    const deviceTimer = window.setInterval(
      () => actions.pollDeviceStatus(),
      5000,
    );
    return () => window.clearInterval(deviceTimer);
  });

  // Synchronize Monaco editor contents with active file changes
  $: activeFile = $workspaceStore.activeFile;
  $: if (monacoEditor && activeFile) {
    const content = $workspaceStore.fileContents[activeFile] || "";
    if (monacoEditor.getValue() !== content) {
      monacoEditor.setValue(content);
      const isC = activeFile.endsWith(".c") || activeFile.endsWith(".h");
      monaco.editor.setModelLanguage(
        monacoEditor.getModel()!,
        isC ? "c" : "javascript",
      );
    }
  }

  // Auto-scroll terminal output
  $: if ($workspaceStore.serialLogs && terminalEndRef) {
    setTimeout(() => {
      terminalEndRef.scrollIntoView({ behavior: "smooth" });
    }, 50);
  }

  $: if ($workspaceStore.buildLogs && buildOutputEndRef) {
    setTimeout(() => {
      buildOutputEndRef.scrollIntoView({ behavior: "smooth" });
    }, 50);
  }

  async function copyBuildOutput() {
    const output = $workspaceStore.buildLogs.join("\n");
    if (!output.trim()) return;

    try {
      await navigator.clipboard.writeText(output);
    } catch {
      const textarea = document.createElement("textarea");
      textarea.value = output;
      textarea.style.position = "fixed";
      textarea.style.left = "-9999px";
      document.body.appendChild(textarea);
      textarea.focus();
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
    }

    buildOutputCopied = true;
    window.setTimeout(() => {
      buildOutputCopied = false;
    }, 1400);
  }

  function initMonaco(node: HTMLElement) {
    monacoEditor = monaco.editor.create(node, {
      value:
        $workspaceStore.fileContents[$workspaceStore.activeFile || ""] || "",
      language: "c",
      theme: isLightTheme ? "vs" : "vs-dark",
      automaticLayout: true,
      fontFamily: "JetBrains Mono",
      fontSize: 13,
      minimap: { enabled: false },
    });

    const disposable = monacoEditor.onDidChangeModelContent(() => {
      if ($workspaceStore.activeFile && monacoEditor) {
        actions.updateFileContent(
          $workspaceStore.activeFile,
          monacoEditor.getValue(),
        );
      }
    });

    const cursorDisposable = monacoEditor.onDidChangeCursorPosition((e) => {
      currentLine = e.position.lineNumber;
      currentColumn = e.position.column;
    });

    return {
      destroy() {
        disposable.dispose();
        cursorDisposable.dispose();
        if (monacoEditor) {
          monacoEditor.dispose();
          monacoEditor = null;
        }
      },
    };
  }

  function drawCanvas() {
    if (!canvasEl) return;
    const ctx = canvasEl.getContext("2d");
    if (!ctx) return;

    const width = canvasEl.clientWidth;
    const height = canvasEl.clientHeight;
    canvasEl.width = width;
    canvasEl.height = height;

    ctx.clearRect(0, 0, width, height);

    // Background Grid
    ctx.strokeStyle = "#12121A";
    ctx.lineWidth = 1;
    for (let i = 40; i < width; i += 60) {
      ctx.beginPath();
      ctx.moveTo(i, 0);
      ctx.lineTo(i, height - 20);
      ctx.stroke();
    }
    for (let i = 20; i < height - 20; i += 30) {
      ctx.beginPath();
      ctx.moveTo(40, i);
      ctx.lineTo(width, i);
      ctx.stroke();
    }

    if ($workspaceStore.plotData.length < 2) {
      ctx.fillStyle = "#64748B";
      ctx.font = "11px Outfit";
      ctx.fillText(
        "Waiting for serial stream telemetry...",
        width / 2 - 100,
        height / 2,
      );
      return;
    }

    const paddingLeft = 40;
    const paddingBottom = 20;
    const graphWidth = width - paddingLeft - 20;
    const graphHeight = height - paddingBottom - 10;

    const temps = $workspaceStore.plotData.map((d) => d.temp);
    const minTemp = Math.min(...temps) - 1;
    const maxTemp = Math.max(...temps) + 1;
    const tempRange = maxTemp - minTemp || 1;

    // Drawing Gradient Line
    ctx.strokeStyle = "#8B5CF6";
    ctx.lineWidth = 2;
    ctx.beginPath();

    $workspaceStore.plotData.forEach((pt, index) => {
      const x =
        paddingLeft +
        (index / ($workspaceStore.plotData.length - 1)) * graphWidth;
      const y =
        height -
        paddingBottom -
        ((pt.temp - minTemp) / tempRange) * graphHeight;
      if (index === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    });
    ctx.stroke();

    // Axis
    ctx.strokeStyle = "#334155";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(paddingLeft, 5);
    ctx.lineTo(paddingLeft, height - paddingBottom);
    ctx.lineTo(width - 10, height - paddingBottom);
    ctx.stroke();

    // Ticks text
    ctx.fillStyle = "#94A3B8";
    ctx.font = "9px JetBrains Mono";
    ctx.fillText(`${maxTemp.toFixed(1)}°C`, 5, 12);
    ctx.fillText(`${minTemp.toFixed(1)}°C`, 5, height - paddingBottom - 4);
  }

  // Compiler / Flash handlers — real PlatformIO build + ST-Link flash via backend.
  function handleBuild() {
    actions.runBuild();
  }

  function handleFlash() {
    actions.runFlash();
  }


  function handleAiSend(e: Event) {
    e.preventDefault();
    if (!aiInput.trim()) return;
    actions.sendAiMessage(aiInput);
    aiInput = "";
  }

  function handleSerialSend(e: Event) {
    e.preventDefault();
    if (!serialInput.trim()) return;
    actions.addSerialLog(`[TX] ${serialInput}`);
    serialInput = "";
  }

  function escapeHtml(value: string) {
    return value
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function renderInlineMarkdown(value: string) {
    return escapeHtml(value)
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/__([^_]+)__/g, "<strong>$1</strong>")
      .replace(/\*([^*\n]+)\*/g, "<em>$1</em>")
      .replace(/_([^_\n]+)_/g, "<em>$1</em>");
  }

  function parseDiff(
    resultText: string,
  ): Array<{ text: string; type: string }> {
    const idx = resultText.indexOf("=== Unified Diff ===");
    if (idx === -1) return [];

    let diffContent = resultText
      .substring(idx + "=== Unified Diff ===".length)
      .trim();
    if (diffContent.endsWith("============")) {
      diffContent = diffContent
        .substring(0, diffContent.length - "============".length)
        .trim();
    }

    return diffContent.split("\n").map((line) => {
      let type = "normal";
      if (line.startsWith("+") && !line.startsWith("+++")) {
        type = "add";
      } else if (line.startsWith("-") && !line.startsWith("---")) {
        type = "del";
      } else if (line.startsWith("@@")) {
        type = "meta";
      } else if (line.startsWith("+++") || line.startsWith("---")) {
        type = "file";
      }
      return { text: line, type };
    });
  }

  // Line-level diff for proposal cards (old vs proposed content). A small LCS
  // so unchanged lines are shown as context and only real changes are +/-.
  function computeProposalDiff(
    oldText: string,
    newText: string,
  ): Array<{ text: string; type: string }> {
    const a = (oldText || "").split("\n");
    const b = (newText || "").split("\n");
    const n = a.length,
      m = b.length;
    const lcs: number[][] = Array.from({ length: n + 1 }, () =>
      new Array(m + 1).fill(0),
    );
    for (let i = n - 1; i >= 0; i--)
      for (let j = m - 1; j >= 0; j--)
        lcs[i][j] =
          a[i] === b[j]
            ? lcs[i + 1][j + 1] + 1
            : Math.max(lcs[i + 1][j], lcs[i][j + 1]);
    const out: Array<{ text: string; type: string }> = [];
    let i = 0,
      j = 0;
    while (i < n && j < m) {
      if (a[i] === b[j]) {
        out.push({ text: "  " + a[i], type: "normal" });
        i++;
        j++;
      } else if (lcs[i + 1][j] >= lcs[i][j + 1]) {
        out.push({ text: "- " + a[i], type: "del" });
        i++;
      } else {
        out.push({ text: "+ " + b[j], type: "add" });
        j++;
      }
    }
    while (i < n) {
      out.push({ text: "- " + a[i], type: "del" });
      i++;
    }
    while (j < m) {
      out.push({ text: "+ " + b[j], type: "add" });
      j++;
    }
    return out;
  }

  function renderMarkdown(markdown: string) {
    const lines = markdown.replace(/\r\n/g, "\n").split("\n");
    const html: string[] = [];
    let paragraph: string[] = [];
    let listType: "ul" | "ol" | null = null;
    let inCode = false;
    let codeLang = "";
    let codeLines: string[] = [];

    const closeParagraph = () => {
      if (paragraph.length === 0) return;
      html.push(`<p>${paragraph.map(renderInlineMarkdown).join("<br>")}</p>`);
      paragraph = [];
    };

    const closeList = () => {
      if (!listType) return;
      html.push(`</${listType}>`);
      listType = null;
    };

    const openList = (type: "ul" | "ol") => {
      if (listType === type) return;
      closeParagraph();
      closeList();
      html.push(`<${type}>`);
      listType = type;
    };

    for (const line of lines) {
      const fence = line.match(/^```(\w+)?\s*$/);
      if (fence) {
        if (inCode) {
          const lang = codeLang ? `<span>${escapeHtml(codeLang)}</span>` : "";
          html.push(
            `<pre class="chat-code-block markdown-code">${lang}<code>${escapeHtml(codeLines.join("\n"))}</code></pre>`,
          );
          inCode = false;
          codeLang = "";
          codeLines = [];
        } else {
          closeParagraph();
          closeList();
          inCode = true;
          codeLang = fence[1] || "";
        }
        continue;
      }

      if (inCode) {
        codeLines.push(line);
        continue;
      }

      if (!line.trim()) {
        closeParagraph();
        closeList();
        continue;
      }

      const heading = line.match(/^(#{1,3})\s+(.+)$/);
      if (heading) {
        closeParagraph();
        closeList();
        const level = heading[1].length + 2;
        html.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`);
        continue;
      }

      const bullet = line.match(/^\s*[-*]\s+(.+)$/);
      if (bullet) {
        openList("ul");
        html.push(`<li>${renderInlineMarkdown(bullet[1])}</li>`);
        continue;
      }

      const numbered = line.match(/^\s*\d+\.\s+(.+)$/);
      if (numbered) {
        openList("ol");
        html.push(`<li>${renderInlineMarkdown(numbered[1])}</li>`);
        continue;
      }

      closeList();
      paragraph.push(line);
    }

    if (inCode) {
      const lang = codeLang ? `<span>${escapeHtml(codeLang)}</span>` : "";
      html.push(
        `<pre class="chat-code-block markdown-code">${lang}<code>${escapeHtml(codeLines.join("\n"))}</code></pre>`,
      );
    }
    closeParagraph();
    closeList();
    return html.join("");
  }

  function renderFileNode(item: FileItem) {
    const isFolder = item.isFolder;
    const isActive = $workspaceStore.activeFile === item.path;

    if (isFolder) {
      return {
        isFolder: true,
        item,
        children: item.children || [],
      };
    } else {
      return {
        isFolder: false,
        item,
        isActive,
      };
    }
  }

  // Local state for tracking selections in chat dialogues
  let chatRadioSelections: Record<string, string> = {};
  let chatCheckboxSelections: Record<string, string[]> = {};
  let chatDropdownSelections: Record<string, string> = {};
  let chatOtherText: Record<string, string> = {};
  let chatOtherOpen: Record<string, boolean> = {};

  // Project Renaming State
  let editingProjectNameId: string | null = null;
  let renamingName = "";

  function focusElement(node: HTMLInputElement) {
    node.focus();
    node.select();
  }

  $: activeProject = $workspaceStore.projectsList.find(
    (p) => p.id === $workspaceStore.activeProjectId,
  );

  // Resize and Layout management
  async function triggerEditorLayout() {
    await tick();
    window.requestAnimationFrame(() => {
      if (monacoEditor) monacoEditor.layout();
    });
  }

  $: {
    showConfigurator;
    showCopilot;
    showSidebar;
    $workspaceStore.terminalOpen;
    triggerEditorLayout();
  }

  // Handle left activity tab click (VS Code style toggle sidebar)
  function handleActivityTabClick(tab: any) {
    if (showSidebar && $workspaceStore.activeSidebarTab === tab) {
      showSidebar = false;
    } else {
      showSidebar = true;
      actions.setActiveSidebarTab(tab);
    }
  }

  // Project files flat list for tagging autocomplete
  $: projectFilesList = Object.keys($workspaceStore.fileContents).map(p => p.startsWith('/') ? p.substring(1) : p);

  function handleChatInput(e: Event) {
    const input = e.target as HTMLInputElement;
    const value = input.value;
    const cursor = input.selectionStart || 0;

    // Find the last '@' before the cursor
    const lastAtPos = value.lastIndexOf("@", cursor - 1);
    if (lastAtPos !== -1) {
      // Check if there is no space between '@' and cursor
      const substring = value.substring(lastAtPos + 1, cursor);
      if (!substring.includes(" ") && !substring.includes("\n")) {
        showFileTagDropdown = true;
        fileTagFilter = substring.toLowerCase();
        fileTagTriggerPos = lastAtPos;
        fileTagIndex = 0;
        return;
      }
    }
    showFileTagDropdown = false;
    fileTagTriggerPos = -1;
  }

  function handleChatInputKeyDown(e: KeyboardEvent) {
    if (!showFileTagDropdown) return;

    const filteredFiles = projectFilesList.filter(f => 
      f.toLowerCase().includes(fileTagFilter)
    );

    if (filteredFiles.length === 0) return;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      fileTagIndex = (fileTagIndex + 1) % filteredFiles.length;
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      fileTagIndex = (fileTagIndex - 1 + filteredFiles.length) % filteredFiles.length;
    } else if (e.key === "Enter" || e.key === "Tab") {
      e.preventDefault();
      insertFileTag(filteredFiles[fileTagIndex]);
    } else if (e.key === "Escape") {
      e.preventDefault();
      showFileTagDropdown = false;
    }
  }

  function insertFileTag(filePath: string) {
    if (fileTagTriggerPos === -1 || !fileTagInputRef) return;
    const value = fileTagInputRef.value;
    const cursor = fileTagInputRef.selectionStart || 0;
    
    const before = value.substring(0, fileTagTriggerPos);
    const after = value.substring(cursor);
    
    aiInput = before + "@" + filePath + " " + after;
    showFileTagDropdown = false;
    fileTagTriggerPos = -1;

    tick().then(() => {
      if (fileTagInputRef) {
        fileTagInputRef.focus();
        const newCursorPos = fileTagTriggerPos + filePath.length + 2; // +1 for @, +1 for space
        fileTagInputRef.setSelectionRange(newCursorPos, newCursorPos);
      }
    });
  }

  // Screenshot capture functionality
  async function takeScreenshot() {
    if (!html2canvas) {
      alert("Screenshot library is loading, please try again in a moment.");
      return;
    }
    try {
      const appEl = document.querySelector(".helix-app") as HTMLElement;
      if (!appEl) return;
      const canvas = await html2canvas(appEl, {
        backgroundColor: null,
        useCORS: true,
        logging: false,
      });
      const url = canvas.toDataURL("image/png");
      const a = document.createElement("a");
      a.href = url;
      a.download = `hardcoreai-screenshot-${Date.now()}.png`;
      a.click();
    } catch (err) {
      console.error("Failed to capture screenshot:", err);
      alert("Failed to capture screenshot: " + err);
    }
  }
</script>

<svelte:window
  onmousemove={handleMouseMove}
  onmouseup={handleMouseUp}
  onkeydown={handleKeyDown}
  onclick={(e) => {
    const target = e.target as HTMLElement;
    if (showViewDropdown && !target.closest('.view-menu-container')) {
      showViewDropdown = false;
    }
  }}
/>
<div class="helix-app {isLightTheme ? 'light-theme' : ''}">
  <!-- 1. Header Command Bar -->
  <header class="helix-header">
    <div class="logo-section">
      <div class="logo-text">HARDCORE<span>AI</span></div>
      <div class="target-tag-pill">
        <span>Target: {$workspaceStore.selectedBoard}RETx</span>
      </div>
    </div>

    <!-- Center Actions Capsule -->
    <div class="command-capsule">
      <button
        class="capsule-btn build"
        onclick={handleBuild}
        disabled={$workspaceStore.isCompiling || $workspaceStore.isFlashing}
        title="Compile Project"
      >
        <Play size={12} class="play-triangle-fill" />
        <span>{$workspaceStore.isCompiling ? "Compiling..." : "Build"}</span>
      </button>

      <div class="divider-line"></div>

      <button
        class="capsule-btn flash"
        onclick={handleFlash}
        disabled={$workspaceStore.isCompiling || $workspaceStore.isFlashing}
        title="Flash to Device"
      >
        <Zap size={12} />
        <span>{$workspaceStore.isFlashing ? "Flashing..." : "Flash"}</span>
      </button>


    </div>

    <!-- Connectivity Status & Controls -->
    <div class="connection-status-group">
      <div class="connection-status">


        <button
          class="status-pill"
          onclick={() => actions.setActiveSidebarTab("rag")}
          style="cursor: pointer;"
          title="Active Vector Database Files"
        >
          <span class="status-dot ai-active"></span>
          <span>RAG Active: {$workspaceStore.ragDocuments.length} Docs</span>
        </button>
      </div>

      <!-- Quick Access Right -->
      <div class="tauri-controls-group" style="display: flex; align-items: center; gap: 8px;">
        <!-- Take SS Button -->
        <button
          type="button"
          class="control-icon-btn"
          onclick={takeScreenshot}
          title="Take Screenshot (PNG)"
          style="display: flex; align-items: center; gap: 4px; padding: 4px 8px; border: 1px solid var(--border-color); border-radius: 4px; background: transparent; color: var(--text-muted); cursor: pointer;"
        >
          <Camera size={13} />
          <span style="font-size: 0.72rem; font-weight: 500;">Take SS</span>
        </button>

        <!-- View Panels Toggle Dropdown -->
        <div class="view-menu-container" style="position: relative;">
          <button
            type="button"
            class="control-icon-btn view-toggle-btn"
            style="display: flex; align-items: center; gap: 4px; padding: 4px 8px; border: 1px solid var(--border-color); border-radius: 4px; background: transparent; color: var(--text-muted); cursor: pointer;"
            onclick={() => (showViewDropdown = !showViewDropdown)}
            title="Toggle Panels Layout"
          >
            <Sliders size={13} />
            <span style="font-size: 0.72rem; font-weight: 500;">View</span>
          </button>

          {#if showViewDropdown}
            <!-- svelte-ignore a11y-click-events-have-key-events -->
            <!-- svelte-ignore a11y-no-static-element-interactions -->
            <div
              class="view-dropdown-menu"
              onclick={() => (showViewDropdown = false)}
            >
              <div class="dropdown-header">Toggle Panels</div>
              
              <button
                type="button"
                class="dropdown-item"
                onclick={(e) => {
                  e.stopPropagation();
                  showSidebar = !showSidebar;
                }}
              >
                <span>Left Sidebar</span>
                <span class="check-icon" style="color: {showSidebar ? 'var(--accent-violet)' : 'var(--text-dark)'}">{showSidebar ? "✓" : "○"}</span>
              </button>

              <button
                type="button"
                class="dropdown-item"
                onclick={(e) => {
                  e.stopPropagation();
                  actions.setTerminalOpen(!$workspaceStore.terminalOpen);
                }}
              >
                <span>Bottom Terminal</span>
                <span class="check-icon" style="color: {$workspaceStore.terminalOpen ? 'var(--accent-violet)' : 'var(--text-dark)'}">{$workspaceStore.terminalOpen ? "✓" : "○"}</span>
              </button>

              <button
                type="button"
                class="dropdown-item"
                onclick={(e) => {
                  e.stopPropagation();
                  showConfigurator = !showConfigurator;
                }}
              >
                <span>Embedded Configurator</span>
                <span class="check-icon" style="color: {showConfigurator ? 'var(--accent-violet)' : 'var(--text-dark)'}">{showConfigurator ? "✓" : "○"}</span>
              </button>

              <button
                type="button"
                class="dropdown-item"
                onclick={(e) => {
                  e.stopPropagation();
                  showCopilot = !showCopilot;
                }}
              >
                <span>AI Copilot Chat</span>
                <span class="check-icon" style="color: {showCopilot ? 'var(--accent-violet)' : 'var(--text-dark)'}">{showCopilot ? "✓" : "○"}</span>
              </button>
            </div>
          {/if}
        </div>

        <Search
          size={14}
          class="control-icon-btn"
          onclick={() => actions.setActiveSidebarTab("search")}
        />
        <Settings
          size={14}
          class="control-icon-btn"
          onclick={() => {
            showConfigurator = true;
            showCopilot = true;
          }}
        />
        <!-- svelte-ignore a11y-click-events-have-key-events -->
        <!-- svelte-ignore a11y-no-static-element-interactions -->
        <div
          class="control-icon-btn"
          onclick={toggleTheme}
          title="Toggle light/dark theme"
        >
          {#if isLightTheme}
            <Sun size={14} />
          {:else}
            <Moon size={14} />
          {/if}
        </div>
        <!-- svelte-ignore a11y-click-events-have-key-events -->
        <!-- svelte-ignore a11y-no-static-element-interactions -->
        <div
          class="control-icon-btn close-btn-highlight"
          onclick={() => actions.setShowWelcomeScreen(true)}
        >
          <X size={14} />
        </div>
      </div>
    </div>
  </header>

  {#if $workspaceStore.showWelcomeScreen}
    <div class="welcome-screen">
      <div class="welcome-container">
        <div class="welcome-header">
          <h1 class="welcome-title">HARDCORE<span>AI</span></h1>
          <p class="welcome-subtitle">
            A premium, modern embedded developer workspace. Optimize your
            compilation, flashing, and debug loops directly on target
            microcontrollers with zero unnecessary visual noise.
          </p>
        </div>

        <div class="welcome-grid">
          <div class="welcome-column">
            <h3 class="welcome-section-title">Start</h3>
            <div class="welcome-action-list">
              {#if $workspaceStore.activeProjectId}
                <button
                  class="welcome-action-btn"
                  style="border-color: rgba(6, 182, 212, 0.5); background: rgba(6, 182, 212, 0.05);"
                  onclick={() => actions.setShowWelcomeScreen(false)}
                >
                  <MonitorPlay
                    size={16}
                    class="welcome-action-icon"
                    style="color: var(--accent-cyan);"
                  />
                  <span style="color: var(--accent-cyan); font-weight: 500;"
                    >Return to Active Workspace &rarr;</span
                  >
                </button>
              {/if}
              <button
                class="welcome-action-btn"
                onclick={async () => {
                  if ($workspaceStore.projectsList.length > 0) {
                    await actions.loadProject(
                      $workspaceStore.projectsList[0].id,
                    );
                    actions.setShowWelcomeScreen(false);
                    actions.setActiveSidebarTab("explorer");
                  } else {
                    alert("No recent projects found. Please create one.");
                  }
                }}
              >
                <FolderOpen size={16} class="welcome-action-icon" />
                <span>Open Project Folder...</span>
              </button>
              <button
                class="welcome-action-btn"
                onclick={async () => {
                  if ($workspaceStore.projectsList.length > 0) {
                    await actions.loadProject(
                      $workspaceStore.projectsList[0].id,
                    );
                    actions.setShowWelcomeScreen(false);
                    actions.setActiveSidebarTab("boards");
                  } else {
                    alert("No recent projects found. Please create one.");
                  }
                }}
              >
                <Settings size={16} class="welcome-action-icon" />
                <span>Configure Target Hardware...</span>
              </button>
              <div
                class="create-project-row"
                style="display: flex; gap: 8px; margin-top: 8px;"
              >
                <input
                  type="text"
                  id="newProjectName"
                  placeholder="New Project Name..."
                  class="welcome-input"
                  style="flex: 1; padding: 12px; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.1); border-radius: 6px; color: white; font-family: inherit;"
                />
                <button
                  class="welcome-action-btn"
                  style="width: auto; padding: 0 20px; margin: 0;"
                  onclick={async () => {
                    const inputEl = document.getElementById(
                      "newProjectName",
                    ) as HTMLInputElement;
                    const projectName =
                      inputEl?.value?.trim() || "My Embedded Project";
                    try {
                      const folderPath = await api.pickFolder();
                      if (!folderPath) return; // user cancelled
                      const project = await api.createProject(
                        projectName,
                        "Created from IDE",
                        folderPath,
                      );
                      await actions.loadProject(project.id);
                      await actions.loadProjects(); // Refresh the list
                      actions.setActiveSidebarTab("explorer");
                      actions.setShowWelcomeScreen(false);
                      actions.addBuildLog(
                        "Created new embedded project template successfully.",
                      );
                    } catch (e: any) {
                      actions.addBuildLog(
                        "Failed to create project: " + e.message,
                      );
                    }
                  }}
                >
                  <Plus size={16} class="welcome-action-icon" />
                  <span>Create</span>
                </button>
              </div>
            </div>
          </div>

          <div class="welcome-column">
            <h3 class="welcome-section-title">Recent Workspaces</h3>
            <div class="recent-list">
              {#each $workspaceStore.projectsList as project}
                <div
                  style="display: flex; align-items: center; justify-content: space-between; padding-right: 12px; gap: 8px; border: 1px solid rgba(255,255,255,0.05); border-radius: 6px; margin-bottom: 8px; background: rgba(0,0,0,0.2);"
                >
                  <button
                    type="button"
                    class="recent-item"
                    style="flex: 1; border: none; margin-bottom: 0; background: transparent; text-align: left; cursor: pointer;"
                    onclick={async () => {
                      await actions.loadProject(project.id);
                      actions.setSelectedBoard("STM32F401");
                      actions.setSelectedProbe("ST-Link V2");
                      actions.setShowWelcomeScreen(false);
                    }}
                  >
                    <div class="recent-name">{project.name}</div>
                    <div class="recent-path">
                      Project ID: {project.id} | {new Date(
                        project.created_at,
                      ).toLocaleDateString()}
                    </div>
                  </button>
                  <button
                    class="control-icon-btn close-btn-highlight"
                    title="Delete Project"
                    style="padding: 6px; border-radius: 4px;"
                    onclick={(e) => {
                      e.stopPropagation();
                      deleteConfirmModal = {
                        show: true,
                        projectId: project.id,
                        projectName: project.name,
                        isActiveProject: false,
                      };
                    }}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              {/each}
              {#if $workspaceStore.projectsList.length === 0}
                <div class="recent-item" style="opacity: 0.5;">
                  <div class="recent-name">No projects found</div>
                  <div class="recent-path">
                    Create a new template to get started
                  </div>
                </div>
              {/if}
            </div>
          </div>
        </div>

        <div class="welcome-footer">
          <div class="welcome-footer-logo">
            HARDCOREAI v1.0.0 (Renderer: Svelte 5)
          </div>
          <button
            class="welcome-enter-btn"
            onclick={async () => {
              if (!$workspaceStore.activeProjectId) {
                await actions.loadProjects();
                if ($workspaceStore.projectsList.length > 0) {
                  await actions.loadProject($workspaceStore.projectsList[0].id);
                } else {
                  await api.createProject(
                    "My Embedded Project",
                    "Created from IDE",
                  );
                  await actions.loadProjects();
                  const newProj = $workspaceStore.projectsList[0];
                  if (newProj) await actions.loadProject(newProj.id);
                }
              }
              actions.setShowWelcomeScreen(false);
            }}
          >
            <span
              >{$workspaceStore.activeProjectId
                ? "Return to Workspace"
                : "Open Workspace"}</span
            >
            <ArrowRight size={14} />
          </button>
        </div>
      </div>
    </div>
  {:else}
    <!-- 2. Main Workspace Layout -->
    <div
      class="helix-main-workspace {(showConfigurator || showCopilot) ? 'ai-open' : ''}"
    >
      <!-- Leftmost Activity Bar -->
      <nav class="activity-bar">
        <!-- svelte-ignore a11y-click-events-have-key-events -->
        <!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
        <button
          class="activity-item {$workspaceStore.activeSidebarTab === 'explorer' && showSidebar
            ? 'active'
            : ''}"
          onclick={() => handleActivityTabClick("explorer")}
          title="Explorer"
        >
          <Folder size={18} />
        </button>
        <!-- svelte-ignore a11y-click-events-have-key-events -->
        <!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
        <button
          class="activity-item {$workspaceStore.activeSidebarTab === 'search' && showSidebar
            ? 'active'
            : ''}"
          onclick={() => handleActivityTabClick("search")}
          title="Search"
        >
          <Search size={18} />
        </button>
        <!-- svelte-ignore a11y-click-events-have-key-events -->
        <!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
        <button
          class="activity-item {$workspaceStore.activeSidebarTab === 'git' && showSidebar
            ? 'active'
            : ''}"
          onclick={() => handleActivityTabClick("git")}
          title="Source Control"
        >
          <GitBranch size={18} />
        </button>

        <!-- svelte-ignore a11y-click-events-have-key-events -->
        <!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
        <button
          class="activity-item {$workspaceStore.activeSidebarTab === 'rag' && showSidebar
            ? 'active'
            : ''}"
          onclick={() => handleActivityTabClick("rag")}
          title="RAG Knowledge Docs"
        >
          <Database size={18} />
        </button>
        <!-- svelte-ignore a11y-click-events-have-key-events -->
        <!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
        <button
          class="activity-item {$workspaceStore.activeSidebarTab === 'boards' && showSidebar
            ? 'active'
            : ''}"
          onclick={() => handleActivityTabClick("boards")}
          title="Target Config"
        >
          <Settings size={18} />
        </button>
        <!-- svelte-ignore a11y-click-events-have-key-events -->
        <!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
        <button
          class="activity-item {$workspaceStore.activeSidebarTab === 'libraries' && showSidebar
            ? 'active'
            : ''}"
          onclick={() => handleActivityTabClick("libraries")}
          title="Library Manager"
        >
          <Package size={18} />
        </button>
      </nav>

      <!-- Sidebar Panel Column -->
      {#if showSidebar}
        <aside
          class="workspace-panel sidebar-panel"
          style="width: {sidebarWidth}px;"
        >
        {#if $workspaceStore.activeSidebarTab === "explorer"}
          <div
            class="panel-header"
            style="height: auto; padding: 10px 14px; display: flex; flex-direction: column; align-items: flex-start; gap: 8px; border-bottom: 1px solid var(--border-color);"
          >
            {#if $workspaceStore.activeProjectId && activeProject}
              <div
                class="active-project-manager"
                style="display: flex; align-items: center; justify-content: space-between; width: 100%; border-bottom: 1px solid var(--border-color); padding-bottom: 8px; margin-bottom: 4px;"
              >
                {#if editingProjectNameId === $workspaceStore.activeProjectId}
                  <input
                    type="text"
                    class="project-rename-input"
                    bind:value={renamingName}
                    onkeydown={async (e) => {
                      if (e.key === "Enter") {
                        const val = renamingName.trim();
                        if (val) {
                          await actions.renameProject(
                            $workspaceStore.activeProjectId!,
                            val,
                          );
                        }
                        editingProjectNameId = null;
                      } else if (e.key === "Escape") {
                        editingProjectNameId = null;
                      }
                    }}
                    onblur={async () => {
                      const val = renamingName.trim();
                      if (val) {
                        await actions.renameProject(
                          $workspaceStore.activeProjectId!,
                          val,
                        );
                      }
                      editingProjectNameId = null;
                    }}
                    use:focusElement
                  />
                {:else}
                  <!-- svelte-ignore a11y-click-events-have-key-events -->
                  <!-- svelte-ignore a11y-no-static-element-interactions -->
                  <div
                    class="project-title-clickable"
                    title="Click to rename project"
                    onclick={() => {
                      editingProjectNameId = $workspaceStore.activeProjectId;
                      renamingName = activeProject.name;
                    }}
                    style="font-size: 0.72rem; font-weight: 700; color: var(--text-active); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 130px; cursor: pointer; display: flex; align-items: center; gap: 6px;"
                  >
                    <Cpu size={12} style="color: var(--accent-violet);" />
                    <span>{activeProject.name}</span>
                  </div>
                {/if}

                <div style="display: flex; align-items: center; gap: 4px;">
                  <button
                    class="project-control-btn"
                    title="Rename Project"
                    onclick={() => {
                      editingProjectNameId = $workspaceStore.activeProjectId;
                      renamingName = activeProject.name;
                    }}
                  >
                    <Sliders size={12} />
                  </button>
                  <button
                    class="project-control-btn delete-hover"
                    title="Delete Project"
                    onclick={() => {
                      deleteConfirmModal = {
                        show: true,
                        projectId: $workspaceStore.activeProjectId!,
                        projectName: activeProject.name,
                        isActiveProject: true,
                      };
                    }}
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              </div>
            {/if}
            <div
              style="display: flex; align-items: center; justify-content: space-between; width: 100%;"
            >
              <div class="panel-title">PROJECT EXPLORER</div>
              <div class="pane-header-actions" style="display: flex; gap: 6px;">
                <button
                  type="button"
                  class="close-ai-btn"
                  title="New File"
                  onclick={() => {
                    inputPromptModal = {
                      show: true,
                      title: "Create New File",
                      placeholder: "e.g. src/main.c",
                      value: "",
                      actionType: "file",
                      folderPath: "",
                    };
                  }}
                >
                  <Plus size={13} />
                </button>
                <button
                  type="button"
                  class="close-ai-btn"
                  title="New Folder"
                  onclick={() => {
                    inputPromptModal = {
                      show: true,
                      title: "Create New Folder",
                      placeholder: "e.g. src/components",
                      value: "",
                      actionType: "folder",
                      folderPath: "",
                    };
                  }}
                >
                  <FolderOpen size={12} />
                </button>
              </div>
            </div>
          </div>

          <div
            class="panel-body flex-container-explorer"
            style="display: flex; flex-direction: column; gap: 16px;"
          >
            <div class="explorer-section">
              <div class="file-list">
                <div style="margin-bottom: 2px;">
                  <!-- svelte-ignore a11y-click-events-have-key-events -->
                  <!-- svelte-ignore a11y-no-static-element-interactions -->
                  <div
                    class="file-item folder"
                    onclick={() => {
                      showConfigurator = true;
                    }}
                  >
                    <Blocks size={14} style="color: var(--accent-violet);" />
                    <span>Embedded Configurator</span>
                  </div>
                  
                  {#snippet fileNodeSnippet(item)}
                    {#if item.isFolder}
                      <div style="margin-bottom: 2px;">
                        <div class="file-item folder" style="display: flex; align-items: center; justify-content: space-between; width: 100%; padding-right: 8px;">
                          <div style="display: flex; align-items: center; gap: 6px;">
                            <Folder
                              size={14}
                              style="color: var(--accent-violet);"
                            />
                            <span>{item.name}</span>
                          </div>
                          <div class="folder-actions">
                            <button
                              type="button"
                              class="folder-action-btn create-file-btn"
                              title="New File in folder"
                              onclick={(e) => {
                                e.stopPropagation();
                                inputPromptModal = {
                                  show: true,
                                  title: `Create New File in ${item.name}`,
                                  placeholder: "filename.c",
                                  value: "",
                                  actionType: "file",
                                  folderPath: item.path.replace(/^\//, "")
                                };
                              }}
                            >
                              <Plus size={11} />
                            </button>
                            <button
                              type="button"
                              class="folder-action-btn create-folder-btn"
                              title="New Folder in folder"
                              onclick={(e) => {
                                e.stopPropagation();
                                inputPromptModal = {
                                  show: true,
                                  title: `Create New Folder in ${item.name}`,
                                  placeholder: "foldername",
                                  value: "",
                                  actionType: "folder",
                                  folderPath: item.path.replace(/^\//, "")
                                };
                              }}
                            >
                              <FolderOpen size={10} />
                            </button>
                            <button
                              type="button"
                              class="folder-action-btn delete-hover"
                              title="Delete Folder"
                              onclick={(e) => {
                                e.stopPropagation();
                                fileDeleteConfirmModal = {
                                  show: true,
                                  path: item.path,
                                  isFolder: true
                                };
                              }}
                            >
                              <Trash2 size={10} />
                            </button>
                          </div>
                        </div>
                        <div class="folder-contents" style="padding-left: 12px; border-left: 1px solid var(--border-color); margin-left: 6px;">
                          {#each item.children || [] as child}
                            {@render fileNodeSnippet(child)}
                          {/each}
                        </div>
                      </div>
                    {:else}
                      <!-- svelte-ignore a11y-click-events-have-key-events -->
                      <!-- svelte-ignore a11y-no-static-element-interactions -->
                      <div
                        class="file-item {$workspaceStore.activeFile === item.path ? 'active' : ''}"
                        onclick={() => actions.setActiveFile(item.path)}
                        style="display: flex; align-items: center; justify-content: space-between; width: 100%; padding-right: 8px;"
                      >
                        <div style="display: flex; align-items: center; gap: 6px;">
                          <File size={14} style="color: var(--text-muted);" />
                          <span>{item.name}</span>
                        </div>
                        <div class="file-actions">
                          <button
                            type="button"
                            class="file-action-btn delete-hover"
                            title="Delete File"
                            onclick={(e) => {
                              e.stopPropagation();
                              fileDeleteConfirmModal = {
                                show: true,
                                path: item.path,
                                isFolder: false
                              };
                            }}
                          >
                            <Trash2 size={11} />
                          </button>
                        </div>
                      </div>
                    {/if}
                  {/snippet}

                  <div class="folder-contents">
                    {#each $workspaceStore.fileTree as item}
                      {@render fileNodeSnippet(item)}
                    {/each}
                  </div>
                </div>
              </div>
            </div>

            <!-- QUICK ACCESS section -->
            <div class="explorer-sub-section">
              <div class="explorer-sub-header">QUICK ACCESS</div>

              <button
                type="button"
                class="quick-access-item"
                onclick={() => {
                  inputPromptModal = {
                    show: true,
                    title: "Create New Project",
                    placeholder: "e.g. Blinky Project",
                    value: "",
                    actionType: "project",
                  };
                }}
              >
                <div style="display: flex; align-items: center; gap: 8px;">
                  <Plus size={13} style="color: var(--accent-violet);" />
                  <span>New Project</span>
                </div>
              </button>

              <button
                type="button"
                class="quick-access-item"
                onclick={() => actions.setShowWelcomeScreen(true)}
              >
                <div style="display: flex; align-items: center; gap: 8px;">
                  <FolderOpen size={13} style="color: var(--accent-violet);" />
                  <span>Open Folder...</span>
                </div>
                <span class="shortcut-tag">Ctrl+O</span>
              </button>

              <button
                type="button"
                class="quick-access-item"
                onclick={() => actions.setShowWelcomeScreen(true)}
              >
                <div style="display: flex; align-items: center; gap: 8px;">
                  <Blocks size={13} style="color: var(--accent-violet);" />
                  <span>Open Workspace...</span>
                </div>
                <span class="shortcut-tag">Ctrl+K Ctrl+O</span>
              </button>

              <button
                type="button"
                class="quick-access-item"
                onclick={() =>
                  (recentProjectsExpanded = !recentProjectsExpanded)}
              >
                <div style="display: flex; align-items: center; gap: 8px;">
                  <Sliders size={13} style="color: var(--accent-violet);" />
                  <span>Recent Projects</span>
                </div>
                <span class="shortcut-tag"
                  >{recentProjectsExpanded ? "▼" : "▶"}</span
                >
              </button>

              {#if recentProjectsExpanded}
                <div
                  class="recent-projects-list"
                  style="padding-left: 16px; display: flex; flex-direction: column; gap: 4px; margin-top: 4px;"
                >
                  {#each $workspaceStore.projectsList as project}
                    <button
                      type="button"
                      class="quick-access-item"
                      style="padding: 4px 8px; font-size: 0.7rem; justify-content: flex-start; gap: 6px;"
                      onclick={async () => {
                        await actions.loadProject(project.id);
                        recentProjectsExpanded = false;
                      }}
                    >
                      <Cpu size={11} style="color: var(--text-dark);" />
                      <span
                        style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;"
                        >{project.name}</span
                      >
                    </button>
                  {/each}
                  {#if $workspaceStore.projectsList.length === 0}
                    <div
                      style="font-size: 0.65rem; color: var(--text-dark); padding: 4px 8px; font-style: italic;"
                    >
                      No recent projects
                    </div>
                  {/if}
                </div>
              {/if}
            </div>

            <!-- RAG Context indicator shortcut inside explorer -->
            <div class="explorer-sub-section">
              <div class="explorer-sub-header">RAG DATABASES CONTEXT</div>
              {#each $workspaceStore.ragDocuments as doc}
                <button
                  type="button"
                  class="quick-access-item"
                  onclick={() => actions.setActiveSidebarTab("rag")}
                  style="cursor: pointer; display: flex; align-items: center; justify-content: space-between;"
                >
                  <span
                    style="font-family: var(--font-mono); font-size: 0.65rem; color: var(--accent-cyan); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 140px;"
                    >{doc.name}</span
                  >
                  <span class="shortcut-tag">{doc.size}</span>
                </button>
              {/each}
            </div>

            <!-- Live hardware connection status -->
            <div class="explorer-sub-section">
              <div class="explorer-sub-header">HARDWARE STATUS</div>
              <div
                class="workspace-item-row"
                style="display: flex; align-items: center; justify-content: space-between; font-size: 0.65rem;"
                title={$workspaceStore.deviceStatus.detail}
              >
                <span
                  >{$workspaceStore.deviceStatus.target ||
                    "STM32 Target"}:</span
                >
                <span
                  style="color: {$workspaceStore.deviceStatus.connected
                    ? 'var(--accent-success)'
                    : 'var(--text-dark)'}; font-weight: bold;"
                >
                  {$workspaceStore.deviceStatus.connected
                    ? `CONNECTED (${$workspaceStore.deviceStatus.probe || "ST-Link"})`
                    : "NO DEVICE"}
                </span>
              </div>
            </div>
          </div>
        {/if}

        {#if $workspaceStore.activeSidebarTab === "search"}
          <div class="panel-header">
            <div class="panel-title">Search Workspace</div>
          </div>
          <div class="panel-body">
            <div class="sidebar-search-panel">
              <input type="text" placeholder="Search string..." />
              <input type="text" placeholder="Files to include (e.g. *.c)" />
              <div
                style="font-size: 0.75rem; color: var(--text-dark); margin-top: 10px;"
              >
                No active search results. Press Enter to search.
              </div>
            </div>
          </div>
        {/if}

        {#if $workspaceStore.activeSidebarTab === "git"}
          <div class="panel-header">
            <div class="panel-title">Source Control</div>
          </div>
          <div class="panel-body">
            <div
              class="sidebar-git-panel"
              style="display: flex; flex-direction: column; gap: 8px; padding: 12px;"
            >
              <input
                type="text"
                placeholder="Commit message (Ctrl+Enter)..."
                bind:value={gitCommitMessage}
                disabled={gitCommitting}
                onkeydown={async (e) => {
                  if (e.key === "Enter" && e.ctrlKey && !gitCommitting) {
                    const msg = gitCommitMessage.trim();
                    if (msg) {
                      gitCommitting = true;
                      gitCommitFeedback = "";
                      try {
                        await actions.commitChanges(msg);
                        gitCommitMessage = "";
                        gitCommitFeedback = "Commit successful!";
                        setTimeout(() => {
                          gitCommitFeedback = "";
                        }, 3000);
                      } catch (err) {
                        gitCommitFeedback = "Failed to commit.";
                        setTimeout(() => {
                          gitCommitFeedback = "";
                        }, 4000);
                      } finally {
                        gitCommitting = false;
                      }
                    }
                  }
                }}
                style="width: 100%; padding: 6px 10px; font-size: 0.76rem;"
              />
              <button
                class="git-commit-btn"
                disabled={!gitCommitMessage.trim() || gitCommitting}
                onclick={async () => {
                  const msg = gitCommitMessage.trim();
                  if (msg) {
                    gitCommitting = true;
                    gitCommitFeedback = "";
                    try {
                      await actions.commitChanges(msg);
                      gitCommitMessage = "";
                      gitCommitFeedback = "Commit successful!";
                      setTimeout(() => {
                        gitCommitFeedback = "";
                      }, 3000);
                    } catch (err) {
                      gitCommitFeedback = "Failed to commit.";
                      setTimeout(() => {
                        gitCommitFeedback = "";
                      }, 4000);
                    } finally {
                      gitCommitting = false;
                    }
                  }
                }}
                style="width: 100%; margin-top: 4px;"
              >
                {gitCommitting ? "Committing..." : "Commit Changes"}
              </button>

              {#if gitCommitFeedback}
                <div
                  style="font-size: 0.72rem; text-align: center; margin-top: 2px; font-weight: 500;
                  {gitCommitFeedback.includes('Failed')
                    ? 'color: var(--accent-error);'
                    : 'color: var(--accent-success);'}"
                >
                  {gitCommitFeedback}
                </div>
              {/if}

              <div
                style="font-size: 0.75rem; color: var(--text-muted); margin-top: 12px; border-top: 1px solid var(--border-color); padding-top: 8px;"
              >
                <strong style="display: block; margin-bottom: 6px;">
                  Changed Files ({$workspaceStore.gitChanges.length})
                </strong>

                <div
                  style="max-height: 250px; overflow-y: auto; display: flex; flex-direction: column; gap: 4px;"
                >
                  {#each $workspaceStore.gitChanges as change}
                    <div
                      style="display: flex; justify-content: space-between; align-items: center; padding: 4px 8px; background: rgba(255,255,255,0.02); border-radius: 3px; font-family: var(--font-mono); font-size: 0.7rem;"
                    >
                      <span
                        style="text-overflow: ellipsis; overflow: hidden; white-space: nowrap; max-width: 180px; color: var(--text-active);"
                        title={change.path}
                      >
                        {change.path}
                      </span>
                      <span
                        style="font-weight: 700; font-size: 0.65rem; padding: 1px 4px; border-radius: 2px;
                        {change.status.includes('M')
                          ? 'color: var(--accent-warning); background: rgba(245,158,11,0.1);'
                          : change.status.includes('?')
                            ? 'color: var(--accent-cyan); background: rgba(6,182,212,0.1);'
                            : change.status.includes('A')
                              ? 'color: var(--accent-success); background: rgba(16,185,129,0.1);'
                              : change.status.includes('D')
                                ? 'color: var(--accent-error); background: rgba(239,68,68,0.1);'
                                : 'color: var(--text-muted);'}"
                      >
                        {change.status}
                      </span>
                    </div>
                  {/each}

                  {#if $workspaceStore.gitChanges.length === 0}
                    <div
                      style="font-size: 0.7rem; color: var(--text-dark); padding: 8px 0; font-style: italic;"
                    >
                      No staged or unstaged changes.
                    </div>
                  {/if}
                </div>
              </div>
            </div>
          </div>
        {/if}



        {#if $workspaceStore.activeSidebarTab === "rag"}
          <RagUploadPanel />
        {/if}

        {#if $workspaceStore.activeSidebarTab === "boards"}
          <div class="panel-header">
            <div class="panel-title">Target Config</div>
          </div>
          <div class="panel-body">
            <div class="boards-config-panel">
              <div class="config-group">
                <!-- svelte-ignore a11y-label-has-associated-control -->
                <label>MCU Board Target</label>
                <select
                  class="config-select"
                  value={$workspaceStore.selectedBoard}
                  onchange={(e) =>
                    actions.setSelectedBoard(e.currentTarget.value as any)}
                >
                  <option value="STM32F401">STM32F401 (Cortex-M4)</option>
                  <option value="ESP32-S3">ESP32-S3 (Xtensa LX7)</option>
                  <option value="RP2040">RP2040 (Cortex-M0+)</option>
                </select>
              </div>
              <div class="config-group">
                <!-- svelte-ignore a11y-label-has-associated-control -->
                <label>Debugger Probe</label>
                <select
                  class="config-select"
                  value={$workspaceStore.selectedProbe}
                  onchange={(e) =>
                    actions.setSelectedProbe(e.currentTarget.value as any)}
                >
                  <option value="ST-Link V2">ST-Link V2 (SWD)</option>
                  <option value="J-Link">J-Link (SWD/JTAG)</option>
                  <option value="CMSIS-DAP">CMSIS-DAP (SWD)</option>
                </select>
              </div>
              <div class="config-group">
                <!-- svelte-ignore a11y-label-has-associated-control -->
                <label>Toolchain compiler Path</label>
                <div class="path-input-wrapper">
                  <input
                    type="text"
                    class="config-input"
                    value={$workspaceStore.toolchainPath}
                    onchange={(e) =>
                      actions.setToolchainPath(e.currentTarget.value)}
                  />
                  <button
                    class="browse-btn"
                    onclick={() =>
                      actions.setToolchainPath("/usr/bin/arm-none-eabi-gcc")}
                    >Reset</button
                  >
                </div>
              </div>
            </div>
          </div>
        {/if}

        {#if $workspaceStore.activeSidebarTab === "libraries"}
          <LibraryManager />
        {/if}
      </aside>

      <!-- Sidebar Drag Handle -->
      <!-- svelte-ignore a11y-no-static-element-interactions -->
      <div
        class="resize-handle vertical-handle"
        onmousedown={() => {
          isDraggingLeft = true;
          document.body.classList.add("dragging-col");
        }}
        style="left: {sidebarWidth + 52}px;"
      ></div>
      {/if}

      <!-- Center Workspace Area (Editor + Bottom Drawer) -->
      <main class="center-editor-panel editor-container">
        <!-- Editor Frame -->
        <section class="monaco-editor-frame">
          <!-- Editor Header Tab bar -->
          <div class="editor-tabs">
            {#each $workspaceStore.openFiles as path}
              <!-- svelte-ignore a11y-click-events-have-key-events -->
              <!-- svelte-ignore a11y-no-static-element-interactions -->
              <div
                class="editor-tab {path === $workspaceStore.activeFile
                  ? 'active'
                  : ''}"
                onclick={() => actions.setActiveFile(path)}
              >
                {#if path === $workspaceStore.activeFile}
                  <div class="active-tab-top-bar"></div>
                {/if}
                <FileCode
                  size={12}
                  style="color: {path === $workspaceStore.activeFile
                    ? 'var(--accent-violet-hover)'
                    : 'var(--text-dark)'};"
                />
                <span>{path.split("/").pop()}</span>
                <!-- svelte-ignore a11y-click-events-have-key-events -->
                <!-- svelte-ignore a11y-no-static-element-interactions -->
                <span
                  class="close-tab"
                  onclick={(e) => {
                    e.stopPropagation();
                    actions.closeFileTab(path);
                  }}
                  title="Close Tab">×</span
                >
              </div>
            {/each}
          </div>

          <!-- Active Editor Display -->
          <div class="monaco-editor-wrapper">
            {#if $workspaceStore.activeFile}
              <div class="monaco-container" use:initMonaco></div>
              <div class="editor-bottom-bar">
                <span>Ln {currentLine}, Col {currentColumn}</span>
                <span>Spaces: 4</span>
                <span>UTF-8</span>
                <span>LF</span>
                <span>C</span>
                <span>{$workspaceStore.selectedBoard}RETx</span>
              </div>
            {:else}
              <div class="empty-editor-state">
                <h2
                  style="color: var(--text-muted); font-weight: 500; font-size: 1.1rem; letter-spacing: 0.5px; margin-bottom: 2rem;"
                >
                  HARDCORE IDE WORKSPACE
                </h2>
                <div class="quick-actions-row">
                  <button
                    class="action-card"
                    onclick={() => actions.setActiveSidebarTab("explorer")}
                  >
                    <Folder size={24} style="color: var(--accent-blue);" />
                    <span>Open Project Folder</span>
                  </button>
                  <button
                    class="action-card"
                    onclick={() => {
                      showConfigurator = true;
                    }}
                  >
                    <Settings size={24} style="color: var(--accent-orange);" />
                    <span>Configure Target Hardware</span>
                  </button>
                  <button
                    class="action-card"
                    onclick={() => actions.setTerminalOpen(true)}
                  >
                    <MonitorPlay
                      size={24}
                      style="color: var(--accent-green);"
                    />
                    <span>Open Terminal &rarr;</span>
                  </button>
                </div>
              </div>
            {/if}


          </div>
        </section>

        <!-- Bottom Drawer Resizer Handle (inline flex child, sits between editor and terminal) -->
        <!-- svelte-ignore a11y-no-static-element-interactions -->
        {#if $workspaceStore.terminalOpen}
          <div
            class="resize-handle horizontal-handle"
            onmousedown={() => {
              isDraggingBottom = true;
              document.body.classList.add("dragging-row");
            }}
          ></div>
        {/if}

        <!-- Bottom Drawer Frame -->
        {#if $workspaceStore.terminalOpen}
          <footer
            class="helix-bottom-drawer"
            style="height: {bottomDrawerHeight}px;"
          >
            <!-- Tabs bar -->
            <div class="drawer-tabs">
              <div class="tab-group">
                <button
                  class="drawer-tab {$workspaceStore.activeBottomTab ===
                  'terminal'
                    ? 'active'
                    : ''}"
                  onclick={() => actions.setBottomTab("terminal")}
                >
                  <span>SERIAL TERMINAL</span>
                </button>

                <button
                  class="drawer-tab {$workspaceStore.activeBottomTab ===
                  'registers'
                    ? 'active'
                    : ''}"
                  onclick={() => actions.setBottomTab("registers")}
                >
                  <span>SFR REGISTERS</span>
                </button>
                <button
                  class="drawer-tab {$workspaceStore.activeBottomTab ===
                  'memory'
                    ? 'active'
                    : ''}"
                  onclick={() => actions.setBottomTab("memory")}
                >
                  <span>BUILD OUTPUT</span>
                </button>
              </div>
              <div class="drawer-actions">
                {#if $workspaceStore.activeBottomTab === "memory"}
                  <button
                    class="drawer-icon-btn"
                    type="button"
                    onclick={copyBuildOutput}
                    disabled={$workspaceStore.buildLogs.length === 0}
                    title={buildOutputCopied ? "Copied" : "Copy Build Output"}
                    aria-label={buildOutputCopied
                      ? "Copied build output"
                      : "Copy build output"}
                  >
                    {#if buildOutputCopied}
                      <Check size={13} />
                    {:else}
                      <Copy size={13} />
                    {/if}
                  </button>
                {/if}
                <button
                  class="close-ai-btn"
                  type="button"
                  onclick={() => actions.setTerminalOpen(false)}
                  title="Minimize Terminal"
                >
                  <X size={13} />
                </button>
              </div>
            </div>

            <!-- Active tab view -->
            <div class="drawer-content">
              {#if $workspaceStore.activeBottomTab === "terminal"}
                <div class="serial-panel">
                  <div class="terminal-scroll">
                    {#each $workspaceStore.serialLogs as log}
                      <div class="terminal-line">{log}</div>
                    {/each}
                    <div bind:this={terminalEndRef}></div>
                  </div>
                  <form class="terminal-input-bar" onsubmit={handleSerialSend}>
                    <span class="prompt">COM4 &gt;</span>
                    <input
                      type="text"
                      class="terminal-input"
                      placeholder="Send serial bytes to MCU..."
                      bind:value={serialInput}
                    />
                    <button type="submit">SEND</button>
                    <select
                      class="baud-rate-select"
                      value={$workspaceStore.baudRate}
                      onchange={(e) =>
                        actions.setBaudRate(Number(e.currentTarget.value))}
                      style="background: var(--bg-primary); border: 1px solid var(--border-color); color: var(--text-active); font-size: 0.72rem; padding: 4px 8px; border-radius: var(--radius-sm); outline: none; margin-left: 8px; cursor: pointer; transition: border-color 0.15s ease;"
                    >
                      <option value={9600}>9600 baud</option>
                      <option value={19200}>19200 baud</option>
                      <option value={38400}>38400 baud</option>
                      <option value={57600}>57600 baud</option>
                      <option value={74880}>74880 baud</option>
                      <option value={115200}>115200 baud</option>
                      <option value={230400}>230400 baud</option>
                      <option value={460800}>460800 baud</option>
                      <option value={921600}>921600 baud</option>
                    </select>
                  </form>
                </div>
              {/if}



              {#if $workspaceStore.activeBottomTab === "registers"}
                <div class="registers-panel">
                  <div class="peripheral-list">
                    {#each $workspaceStore.registers as reg}
                      <!-- svelte-ignore a11y-click-events-have-key-events -->
                      <!-- svelte-ignore a11y-no-static-element-interactions -->
                      <div
                        class="peripheral-item {selectedPeripheral === reg.name
                          ? 'active'
                          : ''}"
                        onclick={() => (selectedPeripheral = reg.name)}
                      >
                        <div
                          style="display: flex; align-items: center; gap: 8px;"
                        >
                          <Cpu size={12} style="color: var(--accent-violet);" />
                          <span>{reg.name}</span>
                        </div>
                        <span class="peripheral-address">{reg.value}</span>
                      </div>
                    {/each}
                  </div>

                  <div class="register-details-grid">
                    {#each $workspaceStore.registers as reg}
                      {#if selectedPeripheral === reg.name}
                        {#each reg.bits || [] as bit}
                          <div class="register-row">
                            <div class="register-row-header">
                              <span class="register-name">{bit.name}</span>
                              <span class="register-value"
                                >0x{bit.value.toString(16).toUpperCase()}</span
                              >
                            </div>
                            <div class="register-desc">{bit.description}</div>
                            <div
                              style="display: flex; justify-content: space-between; align-items: center; font-size: 0.65rem; color: var(--text-dark); margin-top: 4px;"
                            >
                              <span>Range: {bit.range}</span>
                            </div>
                          </div>
                        {/each}
                      {/if}
                    {/each}
                  </div>
                </div>
              {/if}

              {#if $workspaceStore.activeBottomTab === "memory"}
                <div class="serial-panel">
                  <div
                    class="terminal-scroll"
                    style="font-family: var(--font-mono);"
                  >
                    {#each $workspaceStore.buildLogs as log}
                      <div
                        class="terminal-line"
                        style="color: {log.includes('Successful')
                          ? 'var(--accent-success)'
                          : log.includes('Error')
                            ? 'var(--accent-error)'
                            : '#94A3B8'};"
                      >
                        {log}
                      </div>
                    {/each}
                    <div bind:this={buildOutputEndRef}></div>
                  </div>
                </div>
              {/if}
            </div>
          </footer>
        {/if}

        <!-- Terminal Toggle Pill -->
        {#if !$workspaceStore.terminalOpen}
          <!-- svelte-ignore a11y-click-events-have-key-events -->
          <!-- svelte-ignore a11y-no-static-element-interactions -->
          <div
            class="terminal-toggle-pill"
            onclick={() => actions.setTerminalOpen(true)}
          >
            <Sliders size={12} />
            <span>TERMINAL</span>
          </div>
        {/if}
      </main>

      <!-- Right Panel Resizer Handle -->
      <!-- svelte-ignore a11y-no-static-element-interactions -->
      {#if showConfigurator || showCopilot}
        <div
          class="resize-handle vertical-handle"
          onmousedown={() => {
            isDraggingRight = true;
            document.body.classList.add("dragging-col");
          }}
          style="right: {rightSidebarWidth}px;"
        ></div>
      {/if}

      <!-- Right AI Panel Column -->
      <aside
        class="split-sidebar-right right-ai-panel"
        style="width: {rightSidebarWidth}px; display: {(showConfigurator || showCopilot) ? 'flex' : 'none'};"
      >

        {#if showConfigurator}
          <section
            class="sidebar-right-pane embedded-configurator-pane"
            style={showCopilot ? `flex: ${rightPaneSplit} ${rightPaneSplit} 0%;` : "flex: 1 1 0%;"}
          >
            <EmbeddedConfigurator
              selectedBoard={$workspaceStore.selectedBoard}
              onClose={() => (showConfigurator = false)}
              isDetached={false}
              onDetach={() => (showConfigurator = false)}
            />
          </section>
        {/if}

        {#if showConfigurator && showCopilot}
          <div class="right-pane-resizer" onmousedown={startRightResize} />
        {/if}

        {#if showCopilot}
        <section
          class="sidebar-right-pane ai-copilot-pane"
          class:expanded={!showConfigurator}
          style={showConfigurator ? `flex: ${100 - rightPaneSplit} ${100 - rightPaneSplit} 0%;` : "flex: 1 1 0%;"}
        >
          <!-- Chat Header -->
          <div class="ai-chat-header">
            <div class="ai-chat-header-info">
              <div class="ai-avatar-badge">
                <Sparkles size={12} />
              </div>
              <div>
                <div class="ai-chat-title">HARDCOREAI COPILOT</div>
                <div class="ai-chat-subtitle">
                  Embedded AI Assistant · Online
                </div>
              </div>
            </div>
            <div style="display: flex; gap: 6px;">
              {#if $workspaceStore.activeProjectId}
                <button
                  class="close-ai-btn"
                  onclick={() =>
                    actions.clearChat($workspaceStore.activeProjectId!)}
                  title="Clear Conversation History"
                >
                  <Trash2 size={13} />
                </button>
              {/if}
              <button
                class="close-ai-btn"
                onclick={() => (showCopilot = false)}
                title="Minimize panel"
              >
                <X size={13} />
              </button>
            </div>
          </div>

          <!-- Chat messages view -->
          <div
            class="ai-copilot-chat-content"
            bind:this={chatContentEl}
            onscroll={handleChatScroll}
          >
            {#if !$workspaceStore.aiMessages.some((m) => m.sender === "user")}
              <div class="copilot-welcome-container">
                <div class="copilot-welcome-title">
                  Hello! I'm HardcoreAI Copilot
                </div>
                <div class="copilot-welcome-subtitle">
                  Ask me anything about your embedded project.
                </div>

                <div class="copilot-welcome-grid">
                  <button
                    type="button"
                    class="copilot-shortcut-card"
                    onclick={() =>
                      actions.sendAiMessage(
                        "Explain the code in the active file.",
                      )}
                  >
                    <FileCode size={14} class="shortcut-card-icon" />
                    <span>Explain this code</span>
                  </button>

                  <button
                    type="button"
                    class="copilot-shortcut-card"
                    onclick={() =>
                      actions.sendAiMessage(
                        "Fix any errors in the current code.",
                      )}
                  >
                    <AlertTriangle size={14} class="shortcut-card-icon" />
                    <span>Fix errors</span>
                  </button>



                  <button
                    type="button"
                    class="copilot-shortcut-card"
                    onclick={() =>
                      actions.sendAiMessage(
                        "Optimize the performance of this code.",
                      )}
                  >
                    <Cpu size={14} class="shortcut-card-icon" />
                    <span>Optimize this code</span>
                  </button>
                </div>
              </div>
            {:else}
              {#each $workspaceStore.aiMessages as msg}
                <div class="chat-row {msg.sender}">
                  {#if msg.sender === "ai"}
                    <div class="chat-avatar ai-avatar">
                      <Sparkles size={9} />
                    </div>
                  {:else}
                    <div class="chat-avatar user-avatar">DEV</div>
                  {/if}
                  <div class="chat-msg-block {msg.sender}">
                    <div class="chat-msg-meta">
                      <span class="chat-msg-sender"
                        >{msg.sender === "ai" ? "HARDCOREAI" : "You"}</span
                      >
                      <span class="chat-msg-time">{msg.timestamp}</span>
                    </div>
                    <div class="chat-msg-bubble {msg.sender}">
                      <!-- Live agent trace: thinking, function-call cards, code cards -->
                      {#if msg.steps && msg.steps.length > 0}
                        <div class="agent-trace">
                          {#each msg.steps as step}
                            {#if step.kind === "think"}
                              <div class="agent-think-step">
                                <span class="agent-think-icon">💭</span>
                                <span class="agent-think-text-inline"
                                  >{step.text}</span
                                >
                              </div>
                            {:else if step.kind === "call"}
                              <div class="agent-call-card">
                                <span class="agent-call-icon"
                                  ><Sparkles size={11} /></span
                                >
                                <span class="agent-call-name">{step.name}</span>
                                <span class="agent-call-args"
                                  >({step.args
                                    ? Object.entries(step.args)
                                        .map(
                                          ([k, v]) =>
                                            `${k}: ${JSON.stringify(v)}`,
                                        )
                                        .join(", ")
                                    : ""})</span
                                >
                              </div>
                            {:else if step.kind === "code"}
                              <div class="agent-code-card">
                                <div class="agent-code-head">
                                  <span class="agent-code-file"
                                    >{step.path}</span
                                  >
                                  <span class="agent-code-badge">generated</span
                                  >
                                </div>
                                <pre class="agent-code-body"><code
                                    >{step.code}</code
                                  ></pre>
                              </div>
                            {:else if step.kind === "proposal"}
                              <div
                                class="agent-proposal-card"
                                class:allowed={step.decision === "allowed"}
                                class:rejected={step.decision === "rejected"}
                              >
                                <div class="agent-proposal-head">
                                  <span class="agent-proposal-file"
                                    >{step.deleted
                                      ? "🗑 "
                                      : ""}{step.path}</span
                                  >
                                  <span
                                    class="agent-proposal-badge {step.decision}"
                                  >
                                    {step.decision === "allowed"
                                      ? "✓ Applied"
                                      : step.decision === "rejected"
                                        ? "✕ Rejected"
                                        : "Proposed change"}
                                  </span>
                                </div>
                                <pre class="agent-diff-body"><code
                                    >{#each computeProposalDiff(step.old || "", step.deleted ? "" : step.code || "") as line}<span
                                        class="diff-line {line.type}"
                                        >{line.text}</span
                                      >{"\n"}{/each}</code
                                  ></pre>
                                {#if (step.decision || "pending") === "pending"}
                                  <div class="agent-proposal-actions">
                                    <button
                                      class="proposal-btn allow"
                                      onclick={() =>
                                        actions.approveProposal(
                                          msg.id,
                                          step.path || "",
                                        )}>Allow</button
                                    >
                                    <button
                                      class="proposal-btn reject"
                                      onclick={() =>
                                        actions.rejectProposal(
                                          msg.id,
                                          step.path || "",
                                        )}>Reject</button
                                    >
                                  </div>
                                {/if}
                              </div>
                            {:else if step.kind === "result"}
                              {#if step.result && step.result.includes("=== Unified Diff ===")}
                                <div class="agent-result-line">
                                  ↳ Code edits applied:
                                </div>
                                <div class="agent-diff-card">
                                  <pre class="agent-diff-body"><code
                                      >{#each parseDiff(step.result) as line}<span
                                          class="diff-line {line.type}"
                                          >{line.text}</span
                                        >{"\n"}{/each}</code
                                    ></pre>
                                </div>
                              {:else}
                                <div class="agent-result-line">
                                  ↳ {step.result}
                                </div>
                              {/if}
                            {:else if step.kind === "note"}
                              <div class="agent-note-line">{step.text}</div>
                            {:else if step.kind === "error"}
                              <div class="agent-error-line">⚠ {step.text}</div>
                            {/if}
                          {/each}
                        </div>
                      {/if}

                      <!-- Collapsible streamed thinking (italic) -->
                      {#if msg.thinking && msg.thinking.trim()}
                        <div
                          class="agent-think-block"
                          class:collapsed={msg.thinkingCollapsed}
                        >
                          <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
                          <div
                            class="agent-think-header"
                            onclick={() => {
                              msg.thinkingCollapsed = !msg.thinkingCollapsed;
                            }}
                          >
                            <span class="agent-think-caret"
                              >{msg.thinkingCollapsed ? "▸" : "▾"}</span
                            >
                            <span class="agent-think-label"
                              >{msg.thinkingDone
                                ? "Thought"
                                : "Thinking…"}</span
                            >
                          </div>
                          {#if !msg.thinkingCollapsed}
                            <p class="agent-think-text">{msg.thinking}</p>
                          {/if}
                        </div>
                      {/if}

                      {#if msg.text && msg.text.trim()}
                        <div class="chat-markdown">
                          {@html renderMarkdown(msg.text)}
                        </div>
                      {/if}

                      {#if msg.streaming}
                        <div class="agent-work-indicator" aria-live="polite">
                          <div class="agent-work-mark">
                            <Sparkles size={12} />
                            <span></span>
                          </div>
                          <div class="agent-work-body">
                            <div class="agent-work-label">
                              {agentWorkingPhrase}
                            </div>
                            <div class="agent-work-meter"><span></span></div>
                          </div>
                        </div>
                      {/if}

                      {#if msg.status === "waiting_for_user" && msg.options && msg.options.length > 0}
                        {#if msg.inputType === "radio"}
                          <div class="chat-radio-list">
                            {#each msg.options as option}
                              <label
                                class="chat-radio-item"
                                class:disabled={msg.submitted}
                              >
                                <input
                                  type="radio"
                                  name="radio-{msg.id}"
                                  value={option}
                                  disabled={msg.submitted}
                                  checked={msg.submitted
                                    ? msg.selectedValue === option
                                    : chatRadioSelections[msg.id] === option}
                                  onchange={() => {
                                    if (!msg.submitted)
                                      chatRadioSelections[msg.id] = option;
                                  }}
                                />
                                <span class="custom-radio"></span>
                                <span class="radio-label">{option}</span>
                              </label>
                            {/each}
                          </div>
                          {#if !msg.submitted}
                            <button
                              class="chat-submit-choice-btn"
                              disabled={!chatRadioSelections[msg.id]}
                              onclick={() => {
                                const val = chatRadioSelections[msg.id];
                                if (val) {
                                  msg.selectedValue = val;
                                  actions.sendAiMessage(val);
                                }
                              }}
                            >
                              Submit Choice
                            </button>
                          {:else}
                            <div class="chat-submitted-badge">
                              Submitted: <strong
                                >{msg.selectedValue ||
                                  chatRadioSelections[msg.id]}</strong
                              >
                            </div>
                          {/if}
                        {:else if msg.inputType === "checkbox"}
                          <div class="chat-checkbox-list">
                            {#each msg.options as option}
                              {@const isChecked = msg.submitted
                                ? Array.isArray(msg.selectedValue)
                                  ? msg.selectedValue.includes(option)
                                  : msg.selectedValue === option
                                : (
                                    chatCheckboxSelections[msg.id] || []
                                  ).includes(option)}
                              <label
                                class="chat-checkbox-item"
                                class:disabled={msg.submitted}
                              >
                                <input
                                  type="checkbox"
                                  value={option}
                                  disabled={msg.submitted}
                                  checked={isChecked}
                                  onchange={(e) => {
                                    if (msg.submitted) return;
                                    const arr =
                                      chatCheckboxSelections[msg.id] || [];
                                    if (e.currentTarget.checked) {
                                      chatCheckboxSelections[msg.id] = [
                                        ...arr,
                                        option,
                                      ];
                                    } else {
                                      chatCheckboxSelections[msg.id] =
                                        arr.filter((o) => o !== option);
                                    }
                                  }}
                                />
                                <span class="custom-checkbox"></span>
                                <span class="checkbox-label">{option}</span>
                              </label>
                            {/each}
                          </div>
                          {#if !msg.submitted}
                            <button
                              class="chat-submit-choice-btn"
                              disabled={!(
                                chatCheckboxSelections[msg.id] &&
                                chatCheckboxSelections[msg.id].length > 0
                              )}
                              onclick={() => {
                                const val =
                                  chatCheckboxSelections[msg.id] || [];
                                msg.selectedValue = val;
                                actions.sendAiMessage(val.join(", "));
                              }}
                            >
                              Submit Selection
                            </button>
                          {:else}
                            <div class="chat-submitted-badge">
                              Submitted: <strong>
                                {Array.isArray(msg.selectedValue)
                                  ? msg.selectedValue.join(", ")
                                  : msg.selectedValue}
                              </strong>
                            </div>
                          {/if}
                        {:else if msg.inputType === "select"}
                          <div class="chat-select-wrapper">
                            <select
                              class="chat-select-dropdown"
                              disabled={msg.submitted}
                              value={msg.submitted
                                ? msg.selectedValue
                                : chatDropdownSelections[msg.id] || ""}
                              onchange={(e) => {
                                if (!msg.submitted)
                                  chatDropdownSelections[msg.id] =
                                    e.currentTarget.value;
                              }}
                            >
                              <option value="" disabled
                                >-- Select Option --</option
                              >
                              {#each msg.options as option}
                                <option value={option}>{option}</option>
                              {/each}
                            </select>
                          </div>
                          {#if !msg.submitted}
                            <button
                              class="chat-submit-choice-btn"
                              disabled={!chatDropdownSelections[msg.id]}
                              onclick={() => {
                                const val = chatDropdownSelections[msg.id];
                                if (val) {
                                  msg.selectedValue = val;
                                  actions.sendAiMessage(val);
                                }
                              }}
                            >
                              Submit Choice
                            </button>
                          {:else}
                            <div class="chat-submitted-badge">
                              Submitted: <strong
                                >{msg.selectedValue ||
                                  chatDropdownSelections[msg.id]}</strong
                              >
                            </div>
                          {/if}
                        {:else}
                          <!-- inputType === 'buttons' or default fallback -->
                          {#if !msg.submitted}
                            <div class="chat-options-container">
                              {#each msg.options as option}
                                {#if option.toLowerCase().startsWith("other")}
                                  <button
                                    class="chat-option-btn chat-option-other"
                                    onclick={() => {
                                      chatOtherOpen[msg.id] =
                                        !chatOtherOpen[msg.id];
                                    }}
                                  >
                                    {option}
                                  </button>
                                {:else}
                                  <button
                                    class="chat-option-btn"
                                    onclick={() => {
                                      msg.selectedValue = option;
                                      actions.sendAiMessage(option);
                                    }}
                                  >
                                    {option}
                                  </button>
                                {/if}
                              {/each}
                            </div>
                            {#if chatOtherOpen[msg.id]}
                              <div class="chat-other-input-row">
                                <input
                                  type="text"
                                  class="chat-other-input"
                                  placeholder="Describe it yourself…"
                                  bind:value={chatOtherText[msg.id]}
                                  onkeydown={(e) => {
                                    if (
                                      e.key === "Enter" &&
                                      chatOtherText[msg.id]?.trim()
                                    ) {
                                      msg.selectedValue =
                                        chatOtherText[msg.id].trim();
                                      actions.sendAiMessage(
                                        chatOtherText[msg.id].trim(),
                                      );
                                    }
                                  }}
                                />
                                <button
                                  class="chat-submit-choice-btn"
                                  disabled={!chatOtherText[msg.id]?.trim()}
                                  onclick={() => {
                                    const v = chatOtherText[msg.id]?.trim();
                                    if (v) {
                                      msg.selectedValue = v;
                                      actions.sendAiMessage(v);
                                    }
                                  }}
                                >
                                  Send
                                </button>
                              </div>
                            {/if}
                          {:else}
                            <div class="chat-submitted-badge">
                              Submitted: <strong>{msg.selectedValue}</strong>
                            </div>
                          {/if}
                        {/if}
                      {/if}

                      {#if msg.status === "waiting_for_approval"}
                        <div class="chat-approval-gate-card">
                          <div class="approval-gate-header">
                            <div class="approval-icon-pulse">
                              <Sparkles size={14} />
                            </div>
                            <div class="approval-header-texts">
                              <div class="approval-gate-title">
                                PLAN APPROVAL REQUIRED
                              </div>
                              <div class="approval-gate-subtitle">
                                Confirm plan to execute code updates
                              </div>
                            </div>
                          </div>

                          {#if msg.plan}
                            <div class="chat-plan-steps">
                              {#each msg.plan
                                .split("\n")
                                .filter(Boolean) as step}
                                <div class="plan-step-item">
                                  <span class="plan-step-dot"></span>
                                  <span class="plan-step-text">{step}</span>
                                </div>
                              {/each}
                            </div>
                          {/if}

                          {#if !msg.submitted}
                            <div class="chat-approval-actions">
                              <button
                                class="chat-approve-btn-premium"
                                onclick={() => {
                                  msg.selectedValue = "APPROVED";
                                  actions.sendAiMessage("APPROVE");
                                }}
                              >
                                Accept & Generate
                              </button>
                              <button
                                class="chat-reject-btn"
                                onclick={() => {
                                  aiInput =
                                    "Reject: I would like you to change...";
                                  const inp = document.querySelector(
                                    ".chat-input-field",
                                  ) as HTMLInputElement;
                                  if (inp) inp.focus();
                                }}
                              >
                                Reject & Revise
                              </button>
                            </div>
                          {:else}
                            <div class="chat-submitted-badge plan-approved">
                              <span class="status-dot active"></span>
                              <span>Plan Approved & Executed</span>
                            </div>
                          {/if}
                        </div>
                      {/if}
                    </div>
                  </div>
                </div>
              {/each}
            {/if}

            {#if $workspaceStore.aiWaiting}
              <div class="chat-row ai">
                <div class="chat-avatar ai-avatar"><Sparkles size={9} /></div>
                <div class="chat-msg-block ai">
                  <div class="chat-msg-meta">
                    <span class="chat-msg-sender">HARDCOREAI</span>
                  </div>
                  <div class="chat-msg-bubble ai waiting-bubble">
                    <span class="dot"></span>
                    <span class="dot"></span>
                    <span class="dot"></span>
                  </div>
                </div>
              </div>
            {/if}
          </div>

          <!-- Input Box -->
          <div class="chat-input-zone" style="position: relative;">
            {#if showScrollToBottom}
              <div class="scroll-to-bottom-container">
                <button
                  type="button"
                  class="scroll-to-bottom-btn"
                  onclick={scrollToBottom}
                  title="Scroll to bottom"
                >
                  <ArrowDown size={12} />
                  <span>Scroll to Bottom</span>
                </button>
              </div>
            {/if}
            {#if showFileTagDropdown}
              {@const filtered = projectFilesList.filter(f => f.toLowerCase().includes(fileTagFilter))}
              {#if filtered.length > 0}
                <div class="file-tag-autocomplete">
                  <div class="autocomplete-header">Tag Project Files</div>
                  {#each filtered as file, i}
                    <!-- svelte-ignore a11y-click-events-have-key-events -->
                    <!-- svelte-ignore a11y-no-static-element-interactions -->
                    <div
                      class="autocomplete-item {i === fileTagIndex ? 'selected' : ''}"
                      onclick={() => insertFileTag(file)}
                      onmouseenter={() => (fileTagIndex = i)}
                    >
                      <FileCode size={12} style="color: var(--accent-violet);" />
                      <span>{file}</span>
                    </div>
                  {/each}
                </div>
              {/if}
            {/if}
            {#if activeAgentStreaming}
              <div
                class="chat-stop-generating-row"
                style="display: flex; justify-content: center; margin-bottom: 8px;"
              >
                <button
                  type="button"
                  class="stop-generating-btn"
                  onclick={() => actions.cancelAiMessage()}
                  style="display: flex; align-items: center; gap: 6px; padding: 6px 12px; font-size: 0.72rem; font-weight: 600; border-radius: var(--radius-sm); border: 1px solid var(--border-color); background: var(--bg-tertiary); color: var(--text-active); cursor: pointer; transition: all 0.2s;"
                >
                  <div
                    style="width: 8px; height: 8px; background: var(--accent-error); border-radius: 1px;"
                  ></div>
                  <span>Stop Generating</span>
                </button>
              </div>
            {/if}
            {#if queuedAiFollowup}
              <div class="chat-followup-queued">
                <span class="chat-followup-dot"></span>
                <span class="chat-followup-label">Follow-up queued</span>
                <span class="chat-followup-text">{queuedAiFollowup}</span>
                <button
                  type="button"
                  class="chat-followup-clear"
                  title="Clear queued follow-up"
                  onclick={() => actions.clearQueuedAiFollowup()}
                >
                  <X size={10} />
                </button>
              </div>
            {/if}
            <form
              class="chat-input-form"
              class:streaming={activeAgentStreaming}
              onsubmit={handleAiSend}
            >
              <input
                type="text"
                class="chat-input-field"
                placeholder={activeAgentStreaming
                  ? "Type a follow-up while HARDCOREAI works..."
                  : "Ask about registers, RAG docs, or request a code fix..."}
                bind:value={aiInput}
                bind:this={fileTagInputRef}
                oninput={handleChatInput}
                onkeydown={handleChatInputKeyDown}
              />
              <button
                type="submit"
                class="chat-send-btn"
                class:followup={activeAgentStreaming}
                disabled={!aiInput.trim()}
                title={activeAgentStreaming ? "Queue follow-up" : "Send"}
              >
                <Send size={13} />
              </button>
            </form>
            <div class="chat-input-hint">
              {activeAgentStreaming
                ? "Agent running · next prompt will send as a follow-up"
                : "Press Enter to send · Press @ to select files"}
            </div>
          </div>
        </section>
        {/if}
      </aside>

      <!-- AI Panel Collapsed Sidebar Strip -->
      {#if !showConfigurator || !showCopilot}
        <div class="right-collapsed-strips-wrapper">
          {#if !showConfigurator}
            <!-- svelte-ignore a11y-click-events-have-key-events -->
            <!-- svelte-ignore a11y-no-static-element-interactions -->
            <div
              class="ai-collapsed-strip"
              onclick={() => (showConfigurator = true)}
              title="Open Configurator"
            >
              <div class="ai-collapsed-icon"><Sliders size={14} /></div>
              <div class="ai-collapsed-label">CONFIGURATOR</div>
            </div>
          {/if}
          {#if !showCopilot}
            <!-- svelte-ignore a11y-click-events-have-key-events -->
            <!-- svelte-ignore a11y-no-static-element-interactions -->
            <div
              class="ai-collapsed-strip"
              onclick={() => (showCopilot = true)}
              title="Open AI Copilot"
            >
              <div class="ai-collapsed-icon"><Sparkles size={14} /></div>
              <div class="ai-collapsed-label">AI COPILOT</div>
              <div class="ai-collapsed-dot"></div>
            </div>
          {/if}
        </div>
      {/if}
    </div>

    <footer class="hardcoreai-status-bar">
      <div class="status-bar-left">
        <button
          class="status-bar-item branch-status active-branch"
          type="button"
          onclick={() => actions.setActiveSidebarTab("git")}
          title="Open source control"
        >
          <GitBranch size={13} />
          <span class="branch-name">main*</span>
        </button>

        <button
          class="status-bar-item probe-status {$workspaceStore.serialConnected
            ? 'connected'
            : ''}"
          type="button"
          onclick={() => actions.toggleSerialConnection()}
          title="Toggle ST-Link probe connection"
        >
          <span class="ready-dot-glow"></span>
          <span>{$workspaceStore.selectedProbe} (SWD)</span>
        </button>
        <button
          class="status-bar-item"
          type="button"
          onclick={() => {
            showConfigurator = true;
          }}
          title="Open target configurator"
        >
          <Cpu size={13} />
          <span>{$workspaceStore.selectedBoard}RETx</span>
        </button>
        <button
          class="status-bar-item"
          type="button"
          onclick={() => {
            actions.setTerminalOpen(true);
            actions.setBottomTab("terminal");
          }}
          title="Open serial terminal"
        >
          <MonitorPlay size={13} />
          <span>COM4: {$workspaceStore.baudRate}</span>
        </button>
      </div>

      <div class="status-bar-right">
        <button
          class="status-bar-item"
          type="button"
          onclick={() => actions.setTerminalOpen(!$workspaceStore.terminalOpen)}
          title="Toggle bottom panel"
        >
          <Sliders size={13} />
          <span>{$workspaceStore.terminalOpen ? "Panel" : "Panel Hidden"}</span>
        </button>
        <button
          class="status-bar-item"
          type="button"
          onclick={() => {
            actions.setTerminalOpen(true);
            actions.setBottomTab("registers");
          }}
          title="Open register view"
        >
          <Database size={13} />
          <span>Ln {currentLine}, Col {currentColumn}</span>
        </button>
        <span class="status-bar-item text-only">Spaces: 4</span>
        <span class="status-bar-item text-only">UTF-8</span>
        <span class="status-bar-item text-only">LF</span>
        <span class="status-bar-item text-only">C</span>
        <button
          class="status-bar-item ready-status"
          type="button"
          onclick={() => actions.pollDeviceStatus()}
          title="Refresh device status"
        >
          <span class="ready-dot-glow"></span>
          <span
            >{$workspaceStore.deviceStatus.connected
              ? "Ready"
              : "No Device"}</span
          >
        </button>
        <button
          class="status-bar-item icon-only"
          type="button"
          onclick={() => actions.setActiveSidebarTab("boards")}
          title="Board settings"
        >
          <Settings size={13} />
        </button>
      </div>
    </footer>
  {/if}
</div>

<!-- Delete Project Confirmation Modal -->
{#if deleteConfirmModal.show}
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div
    class="delete-modal-backdrop"
    onclick={() => (deleteConfirmModal.show = false)}
  >
    <div class="delete-modal-card" onclick={(e) => e.stopPropagation()}>
      <div class="delete-modal-header">
        <div class="delete-modal-title">
          <AlertTriangle size={16} class="delete-warning-icon" />
          <span>Confirm Deletion</span>
        </div>
        <button
          class="delete-close-btn"
          onclick={() => (deleteConfirmModal.show = false)}
          title="Close"
        >
          <X size={14} />
        </button>
      </div>

      <div class="delete-modal-body">
        <p class="delete-msg-main">
          Are you sure you want to delete <strong
            >'{deleteConfirmModal.projectName}'</strong
          >?
        </p>
        {#if deleteConfirmModal.isActiveProject}
          <p class="delete-msg-sub">
            This will permanently erase all project files and close the active
            workspace. This action cannot be undone.
          </p>
        {:else}
          <p class="delete-msg-sub">
            This will permanently erase all project files from the database.
            This action cannot be undone.
          </p>
        {/if}
      </div>

      <div class="delete-modal-footer">
        <button
          class="delete-btn-cancel"
          onclick={() => (deleteConfirmModal.show = false)}
        >
          Cancel
        </button>
        <button
          class="delete-btn-confirm"
          onclick={async () => {
            const id = deleteConfirmModal.projectId;
            const isActive = deleteConfirmModal.isActiveProject;
            deleteConfirmModal.show = false;
            if (isActive) {
              await actions.deleteActiveProject(id);
            } else {
              await actions.deleteProject(id);
            }
          }}
        >
          <Trash2 size={13} style="margin-right: 4px;" />
          Delete Workspace
        </button>
      </div>
    </div>
  </div>
{/if}

<!-- Delete File/Folder Confirmation Modal -->
{#if fileDeleteConfirmModal.show}
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div
    class="delete-modal-backdrop"
    onclick={() => (fileDeleteConfirmModal.show = false)}
  >
    <div class="delete-modal-card" onclick={(e) => e.stopPropagation()}>
      <div class="delete-modal-header">
        <div class="delete-modal-title">
          <AlertTriangle size={16} class="delete-warning-icon" />
          <span>Confirm File Deletion</span>
        </div>
        <button
          class="delete-close-btn"
          onclick={() => (fileDeleteConfirmModal.show = false)}
          title="Close"
        >
          <X size={14} />
        </button>
      </div>

      <div class="delete-modal-body">
        <p class="delete-msg-main">
          Are you sure you want to delete <strong
            >'{fileDeleteConfirmModal.path.split('/').pop()}'</strong
          >?
        </p>
        {#if fileDeleteConfirmModal.isFolder}
          <p class="delete-msg-sub">
            This will permanently delete the folder <strong>{fileDeleteConfirmModal.path}</strong> and all of its contents. This action cannot be undone.
          </p>
        {:else}
          <p class="delete-msg-sub">
            This will permanently delete the file <strong>{fileDeleteConfirmModal.path}</strong>. This action cannot be undone.
          </p>
        {/if}
      </div>

      <div class="delete-modal-footer">
        <button
          class="delete-btn-cancel"
          onclick={() => (fileDeleteConfirmModal.show = false)}
        >
          Cancel
        </button>
        <button
          class="delete-btn-confirm"
          onclick={async () => {
            const path = fileDeleteConfirmModal.path;
            const isFolder = fileDeleteConfirmModal.isFolder;
            fileDeleteConfirmModal.show = false;
            if (isFolder) {
              await actions.deleteFolder(path);
            } else {
              await actions.deleteFile(path);
            }
          }}
        >
          <Trash2 size={13} style="margin-right: 4px;" />
          Delete
        </button>
      </div>
    </div>
  </div>
{/if}

<!-- Input Prompt Modal (New File / New Folder) -->
{#if inputPromptModal.show}
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div
    class="delete-modal-backdrop"
    onclick={() => (inputPromptModal.show = false)}
  >
    <div class="delete-modal-card" onclick={(e) => e.stopPropagation()}>
      <div class="delete-modal-header">
        <div class="delete-modal-title">
          {#if inputPromptModal.actionType === "file"}
            <Plus size={15} style="color: var(--accent-violet);" />
          {:else if inputPromptModal.actionType === "project"}
            <Cpu size={14} style="color: var(--accent-violet);" />
          {:else}
            <FolderOpen size={14} style="color: var(--accent-violet);" />
          {/if}
          <span>{inputPromptModal.title}</span>
        </div>
        <button
          class="delete-close-btn"
          onclick={() => (inputPromptModal.show = false)}
          title="Close"
        >
          <X size={14} />
        </button>
      </div>

      <div class="delete-modal-body">
        <div class="modal-param-group">
          <!-- svelte-ignore a11y-label-has-associated-control -->
          <label
            style="font-size: 0.68rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px; display: block;"
          >
            Name / Path
          </label>
          <input
            type="text"
            class="modal-input"
            placeholder={inputPromptModal.placeholder}
            bind:value={inputPromptModal.value}
            onkeydown={(e) => {
              if (e.key === "Enter") {
                const val = inputPromptModal.value.trim();
                if (val) {
                  inputPromptModal.show = false;
                  if (inputPromptModal.actionType === "file") {
                    actions.createFile(val, inputPromptModal.folderPath);
                  } else if (inputPromptModal.actionType === "project") {
                    (async () => {
                      try {
                        const folderPath = await api.pickFolder();
                        if (!folderPath) return; // user cancelled
                        const project = await api.createProject(
                          inputPromptModal.value.trim(),
                          "Created from IDE",
                          folderPath,
                        );
                        await actions.loadProject(project.id);
                        await actions.loadProjects();
                        actions.setActiveSidebarTab("explorer");
                        actions.addBuildLog(
                          "Created new embedded project template successfully.",
                        );
                      } catch (e: any) {
                        actions.addBuildLog(
                          "Failed to create project: " + e.message,
                        );
                      }
                    })();
                  } else {
                    actions.createFolder(val, inputPromptModal.folderPath);
                  }
                }
              } else if (e.key === "Escape") {
                inputPromptModal.show = false;
              }
            }}
            use:focusElement
          />
        </div>
      </div>

      <div class="delete-modal-footer">
        <button
          class="delete-btn-cancel"
          onclick={() => (inputPromptModal.show = false)}
        >
          Cancel
        </button>
        <button
          class="save-btn"
          disabled={!inputPromptModal.value.trim()}
          onclick={() => {
            const val = inputPromptModal.value.trim();
            if (val) {
              inputPromptModal.show = false;
              if (inputPromptModal.actionType === "file") {
                actions.createFile(val, inputPromptModal.folderPath);
              } else if (inputPromptModal.actionType === "project") {
                (async () => {
                  try {
                    const folderPath = await api.pickFolder();
                    if (!folderPath) return; // user cancelled
                    const project = await api.createProject(
                      inputPromptModal.value.trim(),
                      "Created from IDE",
                      folderPath,
                    );
                    await actions.loadProject(project.id);
                    await actions.loadProjects();
                    actions.setActiveSidebarTab("explorer");
                    actions.addBuildLog(
                      "Created new embedded project template successfully.",
                    );
                  } catch (e: any) {
                    actions.addBuildLog(
                      "Failed to create project: " + e.message,
                    );
                  }
                })();
              } else {
                actions.createFolder(val, inputPromptModal.folderPath);
              }
            }
          }}
        >
          Create
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  /* Custom layouts specifically needed for Svelte overlays and resize indicators */
  /* Vertical handles (left/right sidebars) remain absolute */
  .vertical-handle {
    position: absolute;
    top: 50px;
    bottom: 0;
    width: 4px;
    cursor: col-resize;
    z-index: 1000;
    transition: background-color 0.2s ease;
  }

  .vertical-handle:hover {
    background-color: var(--accent-violet);
  }

  /* Horizontal handle (bottom terminal) is an inline flex child */
  .horizontal-handle {
    width: 100%;
    height: 4px;
    flex-shrink: 0;
    cursor: row-resize;
    background-color: var(--border-color);
    transition: background-color 0.2s ease;
  }

  .horizontal-handle:hover {
    background-color: var(--accent-violet);
  }


  .configurator-toggle-tab {
    background: none;
    border: none;
    outline: none;
    color: var(--text-muted);
    font-family: var(--font-sans);
    font-size: 0.72rem;
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 0 12px;
    border-left: 1px solid var(--border-color);
    cursor: pointer;
  }

  .configurator-toggle-tab:hover {
    color: var(--text-bright);
    background: #12121a;
  }

  .chat-code-block {
    background: #060609;
    border: 1px solid #1a1a24;
    border-radius: var(--radius-sm);
    padding: 8px;
    font-family: var(--font-mono);
    font-size: 0.68rem;
    color: #f8fafc;
    overflow-x: auto;
    margin: 6px 0 0 0;
  }

  /* ── Live agent trace (streamed) ───────────────────────────────── */
  .agent-trace {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin-bottom: 6px;
  }

  /* Collapsible thinking block — italic, dimmed */
  .agent-think-block {
    border-left: 2px solid #2a2a3a;
    padding-left: 8px;
    margin-bottom: 6px;
  }
  .agent-think-header {
    display: flex;
    align-items: center;
    gap: 5px;
    cursor: pointer;
    user-select: none;
    font-size: 0.66rem;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .agent-think-header:hover {
    color: var(--text-bright);
  }
  .agent-think-caret {
    font-size: 0.6rem;
    opacity: 0.7;
  }
  .agent-think-text {
    margin: 4px 0 0 0;
    font-style: italic;
    font-size: 0.74rem;
    line-height: 1.5;
    color: #8b8ba0;
  }

  /* Function-call card */
  .agent-call-card {
    display: flex;
    align-items: center;
    gap: 6px;
    background: rgba(99, 102, 241, 0.08);
    border: 1px solid rgba(99, 102, 241, 0.25);
    border-radius: var(--radius-sm);
    padding: 5px 8px;
    font-family: var(--font-mono);
    font-size: 0.68rem;
    flex-wrap: wrap;
  }
  .agent-call-icon {
    color: #818cf8;
    display: flex;
  }
  .agent-call-name {
    color: #c7d2fe;
    font-weight: 700;
  }
  .agent-call-args {
    color: #6b7280;
    word-break: break-all;
  }

  /* Code card */
  .agent-code-card {
    border: 1px solid #1a1a24;
    border-radius: var(--radius-sm);
    overflow: hidden;
    background: #060609;
  }
  .agent-code-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 4px 8px;
    background: #0c0c14;
    border-bottom: 1px solid #1a1a24;
  }
  .agent-code-file {
    font-family: var(--font-mono);
    font-size: 0.66rem;
    color: #c7d2fe;
  }
  .agent-code-badge {
    font-size: 0.58rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #10b981;
    background: rgba(16, 185, 129, 0.12);
    border-radius: 3px;
    padding: 1px 5px;
  }
  .agent-code-body {
    margin: 0;
    padding: 8px;
    font-family: var(--font-mono);
    font-size: 0.66rem;
    color: #f8fafc;
    max-height: 280px;
    overflow: auto;
  }

  .agent-result-line {
    font-size: 0.66rem;
    color: #6b7280;
    font-family: var(--font-mono);
    padding-left: 4px;
  }
  /* "small task, no planning needed" style notes */
  .agent-note-line {
    font-size: 0.7rem;
    color: #93c5a0;
    background: rgba(16, 185, 129, 0.07);
    border-left: 2px solid rgba(16, 185, 129, 0.4);
    padding: 4px 8px;
    border-radius: 3px;
  }
  .agent-error-line {
    font-size: 0.68rem;
    color: #fca5a5;
  }

  .agent-work-indicator {
    display: grid;
    grid-template-columns: 24px 1fr;
    align-items: center;
    gap: 8px;
    margin-top: 2px;
    padding: 8px;
    border-radius: 8px;
    background: linear-gradient(
        90deg,
        rgba(6, 182, 212, 0.08),
        rgba(139, 92, 246, 0.08)
      ),
      #08080d;
    border: 1px solid rgba(99, 102, 241, 0.22);
  }

  .agent-work-mark {
    position: relative;
    width: 24px;
    height: 24px;
    border-radius: 7px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #c7d2fe;
    background: rgba(99, 102, 241, 0.13);
    overflow: hidden;
  }

  .agent-work-mark span {
    position: absolute;
    inset: -45% auto -45% -30%;
    width: 8px;
    background: rgba(255, 255, 255, 0.24);
    transform: rotate(18deg);
    animation: agent-scan 1.8s infinite ease-in-out;
  }

  .agent-work-body {
    min-width: 0;
  }

  .agent-work-label {
    color: #dbeafe;
    font-size: 0.7rem;
    font-weight: 700;
    line-height: 1.2;
  }

  .agent-work-meter {
    position: relative;
    height: 3px;
    margin-top: 6px;
    overflow: hidden;
    border-radius: 999px;
    background: rgba(148, 163, 184, 0.14);
  }

  .agent-work-meter span {
    position: absolute;
    inset: 0 auto 0 0;
    width: 42%;
    border-radius: inherit;
    background: linear-gradient(90deg, #06b6d4, #8b5cf6, #10b981);
    animation: agent-meter 1.45s infinite ease-in-out;
  }

  @keyframes agent-scan {
    0% {
      transform: translateX(0) rotate(18deg);
      opacity: 0;
    }
    25% {
      opacity: 1;
    }
    100% {
      transform: translateX(52px) rotate(18deg);
      opacity: 0;
    }
  }

  @keyframes agent-meter {
    0% {
      transform: translateX(-120%);
    }
    55% {
      transform: translateX(95%);
    }
    100% {
      transform: translateX(250%);
    }
  }

  .waiting-bubble-inline {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 2px 0;
  }

  .chat-followup-queued {
    display: grid;
    grid-template-columns: auto auto 1fr auto;
    align-items: center;
    gap: 7px;
    min-height: 28px;
    border-radius: 8px;
    border: 1px solid rgba(6, 182, 212, 0.24);
    background: rgba(6, 182, 212, 0.07);
    padding: 5px 6px 5px 8px;
  }

  .chat-followup-dot {
    width: 6px;
    height: 6px;
    border-radius: 999px;
    background: #06b6d4;
    box-shadow: 0 0 8px rgba(6, 182, 212, 0.7);
    animation: followup-pulse 1.4s infinite ease-in-out;
  }

  .chat-followup-label {
    color: #a5f3fc;
    font-size: 0.62rem;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    white-space: nowrap;
  }

  .chat-followup-text {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--text-muted);
    font-size: 0.7rem;
  }

  .chat-followup-clear {
    width: 20px;
    height: 20px;
    border: none;
    border-radius: 6px;
    color: var(--text-muted);
    background: transparent;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .chat-followup-clear:hover {
    color: var(--text-bright);
    background: rgba(255, 255, 255, 0.06);
  }

  .chat-input-form.streaming {
    border-color: rgba(6, 182, 212, 0.32);
    box-shadow: 0 0 0 2px rgba(6, 182, 212, 0.07);
  }

  .chat-send-btn.followup {
    background: linear-gradient(135deg, #0891b2, #8b5cf6);
  }

  .chat-send-btn.followup:hover:not(:disabled) {
    background: linear-gradient(135deg, #06b6d4, #a78bfa);
  }

  @keyframes followup-pulse {
    0%,
    100% {
      transform: scale(0.75);
      opacity: 0.55;
    }
    50% {
      transform: scale(1);
      opacity: 1;
    }
  }

  /* "Other — describe it yourself" free-text row */
  .chat-other-input-row {
    display: flex;
    gap: 6px;
    margin-top: 6px;
  }
  .chat-other-input {
    flex: 1;
    background: #0c0c14;
    border: 1px solid #2a2a3a;
    border-radius: var(--radius-sm);
    padding: 6px 8px;
    color: var(--text-bright);
    font-size: 0.72rem;
  }
  .chat-other-input:focus {
    outline: none;
    border-color: #6366f1;
  }
  .chat-option-other {
    border-style: dashed;
  }

  /* Plot statistics */
  .plot-stats-overlay {
    position: absolute;
    top: 10px;
    right: 20px;
    display: flex;
    gap: 12px;
    z-index: 10;
  }

  .stat-lbl {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 0.68rem;
    font-weight: 600;
    color: var(--text-muted);
    background: rgba(15, 15, 23, 0.85);
    backdrop-filter: blur(4px);
    border: 1px solid var(--border-color);
    border-radius: 4px;
    padding: 4px 8px;
  }

  .stat-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
  }

  .stat-dot.temp {
    background: #f59e0b;
  }
  .stat-dot.volt {
    background: #06b6d4;
  }
  .stat-dot.curr {
    background: #10b981;
  }

  .stat-val {
    color: var(--text-bright);
    font-family: var(--font-mono);
  }

  /* Typing indicator dots animation */
  .dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background-color: var(--accent-violet);
    animation: bounce 1.2s infinite ease-in-out;
    display: inline-block;
  }

  .dot:nth-child(2) {
    animation-delay: 0.2s;
  }

  .dot:nth-child(3) {
    animation-delay: 0.4s;
  }

  @keyframes bounce {
    0%,
    80%,
    100% {
      transform: scale(0.6);
      opacity: 0.5;
    }
    40% {
      transform: scale(1);
      opacity: 1;
    }
  }
  .chat-options-container {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin-top: 12px;
  }
  .chat-option-btn {
    background-color: var(--card-bg-light);
    border: 1px solid var(--border-color);
    color: var(--text-color);
    padding: 8px 12px;
    border-radius: 4px;
    cursor: pointer;
    font-size: 13px;
    text-align: left;
    transition: all 0.2s ease;
  }
  .chat-option-btn:hover {
    background-color: var(--primary-light);
    border-color: var(--primary-color);
  }
  .chat-plan-preview {
    background-color: var(--bg-dark);
    padding: 10px;
    border-radius: 4px;
    margin-top: 10px;
    font-size: 13px;
    border-left: 3px solid var(--accent-orange);
  }
  .chat-plan-preview strong {
    color: var(--accent-orange);
    display: block;
    margin-bottom: 4px;
  }
  .chat-plan-preview p {
    margin: 0;
    color: var(--text-color-muted);
  }
  .chat-approval-container {
    margin-top: 12px;
  }
  .chat-approve-btn {
    background-color: var(--accent-orange);
    color: white;
    border: none;
    padding: 8px 16px;
    border-radius: 4px;
    cursor: pointer;
    font-size: 13px;
    font-weight: 600;
    width: 100%;
    transition: opacity 0.2s ease;
  }
  .chat-approve-btn:hover {
    opacity: 0.9;
  }

  /* Inline thinking step styling */
  .agent-think-step {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    margin: 6px 0;
    padding: 6px 10px;
    background: rgba(255, 255, 255, 0.02);
    border-left: 2px solid rgba(255, 255, 255, 0.15);
    border-radius: 0 4px 4px 0;
    font-size: 0.78rem;
    color: #a1a1aa;
  }
  .agent-think-icon {
    font-size: 0.9rem;
    opacity: 0.8;
  }
  .agent-think-text-inline {
    margin: 0;
    font-style: italic;
    line-height: 1.4;
  }

  /* Unified Diff visualization styles */
  .agent-diff-card {
    background: #0f1419; /* dark terminal background */
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 6px;
    margin: 8px 0;
    overflow: hidden;
    max-width: 100%;
  }
  .agent-diff-body {
    margin: 0;
    padding: 10px;
    font-family: var(--font-mono, monospace);
    font-size: 0.72rem;
    line-height: 1.5;
    overflow-x: auto;
    white-space: pre;
  }
  .diff-line {
    display: block;
    width: 100%;
    padding: 0 4px;
  }
  .diff-line.add {
    background: rgba(16, 185, 129, 0.15); /* green addition */
    color: #34d399;
  }
  .diff-line.del {
    background: rgba(239, 68, 68, 0.15); /* red deletion */
    color: #f87171;
  }
  .diff-line.meta {
    color: #60a5fa; /* blue headers/hunks */
    font-weight: bold;
    background: rgba(96, 165, 250, 0.05);
  }
  .diff-line.file {
    color: #a78bfa; /* violet file paths */
    font-weight: bold;
  }
  .diff-line.normal {
    color: #d4d4d8;
  }

  /* Agent file-change proposal card (Allow / Reject) */
  .agent-proposal-card {
    background: #0f1419;
    border: 1px solid rgba(96, 165, 250, 0.35);
    border-radius: 8px;
    margin: 10px 0;
    overflow: hidden;
    max-width: 100%;
  }
  .agent-proposal-card.allowed {
    border-color: rgba(16, 185, 129, 0.45);
  }
  .agent-proposal-card.rejected {
    border-color: rgba(239, 68, 68, 0.35);
    opacity: 0.65;
  }
  .agent-proposal-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    padding: 7px 10px;
    background: rgba(255, 255, 255, 0.03);
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  }
  .agent-proposal-file {
    font-family: var(--font-mono, monospace);
    font-size: 0.74rem;
    color: #e4e4e7;
    font-weight: 600;
  }
  .agent-proposal-badge {
    font-size: 0.66rem;
    padding: 2px 7px;
    border-radius: 10px;
    background: rgba(96, 165, 250, 0.15);
    color: #93c5fd;
    white-space: nowrap;
  }
  .agent-proposal-badge.allowed {
    background: rgba(16, 185, 129, 0.18);
    color: #34d399;
  }
  .agent-proposal-badge.rejected {
    background: rgba(239, 68, 68, 0.18);
    color: #f87171;
  }
  .agent-proposal-actions {
    display: flex;
    gap: 8px;
    padding: 8px 10px;
    border-top: 1px solid rgba(255, 255, 255, 0.08);
    background: rgba(255, 255, 255, 0.02);
  }
  .proposal-btn {
    flex: 1;
    padding: 6px 10px;
    border-radius: 6px;
    font-size: 0.74rem;
    font-weight: 600;
    cursor: pointer;
    border: 1px solid transparent;
    transition:
      background 0.12s,
      border-color 0.12s;
  }
  .proposal-btn.allow {
    background: rgba(16, 185, 129, 0.18);
    color: #34d399;
    border-color: rgba(16, 185, 129, 0.4);
  }
  .proposal-btn.allow:hover {
    background: rgba(16, 185, 129, 0.3);
  }
  .proposal-btn.reject {
    background: rgba(239, 68, 68, 0.12);
    color: #f87171;
    border-color: rgba(239, 68, 68, 0.35);
  }
  .proposal-btn.reject:hover {
    background: rgba(239, 68, 68, 0.22);
  }

  /* Scroll to bottom button styling */
  .scroll-to-bottom-container {
    position: absolute;
    top: -38px;
    left: 50%;
    transform: translateX(-50%);
    z-index: 1000;
    pointer-events: none;
  }

  .scroll-to-bottom-btn {
    pointer-events: auto;
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    color: var(--text-active);
    padding: 5px 12px;
    border-radius: 16px;
    font-size: 0.7rem;
    font-weight: 600;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 6px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4), 0 0 10px rgba(139, 92, 246, 0.1);
    transition: all 0.2s ease-in-out;
  }

  .scroll-to-bottom-btn:hover {
    background: var(--bg-secondary);
    border-color: var(--accent-violet);
    color: var(--accent-violet-hover);
    transform: translateY(-1px);
    box-shadow: 0 6px 16px rgba(0, 0, 0, 0.5), 0 0 14px rgba(139, 92, 246, 0.2);
  }
</style>
