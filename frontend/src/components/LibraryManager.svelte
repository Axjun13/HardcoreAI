<script lang="ts">
  import { workspaceStore, actions } from "../store";
  import {
    Search,
    Package,
    PackageCheck,
    PackagePlus,
    RefreshCw,
    Trash2,
    ChevronDown,
    ChevronRight,
    ExternalLink,
    AlertCircle,
    CheckCircle2,
    Clock,
    Loader,
    Tag,
    Cpu,
    User,
    Star,
  } from "lucide-svelte";

  // Reactive state from store
  $: tab = $workspaceStore.libraryManagerTab;
  $: availableLibraries = $workspaceStore.availableLibraries;
  $: installedLibraries = $workspaceStore.installedLibraries;
  $: libraryCategories = $workspaceStore.libraryCategories;
  $: installStatus = $workspaceStore.libraryInstallStatus;
  $: installError = $workspaceStore.libraryInstallError;
  $: loading = $workspaceStore.librariesLoading;
  $: hasProject = !!$workspaceStore.activeProjectId;

  // Local search state — debounced to avoid hammering the backend
  let localSearch = $workspaceStore.librarySearchQuery;
  let searchTimer: ReturnType<typeof setTimeout>;

  function onSearch(e: Event) {
    const val = (e.target as HTMLInputElement).value;
    localSearch = val;
    clearTimeout(searchTimer);
    actions.setLibrarySearch(val);
    searchTimer = setTimeout(() => {
      actions.fetchAvailableLibraries();
    }, 300);
  }

  function onCategoryFilter(cat: string) {
    const current = $workspaceStore.librarySelectedCategory;
    const next = current === cat ? "" : cat;
    actions.setLibraryCategory(next);
    actions.fetchAvailableLibraries();
  }

  // Expanded card state (local)
  let expandedLibrary: string | null = null;
  function toggleExpand(id: string) {
    expandedLibrary = expandedLibrary === id ? null : id;
  }

  // Computed: mark available libraries that are installed
  $: installedIds = new Set(installedLibraries.map((l: any) => l.id));

  function getInstallStatus(id: string): "idle" | "confirming" | "installing" | "installed" | "error" {
    if (installedIds.has(id)) return "installed";
    return installStatus[id] ?? "idle";
  }

  // Category colour map
  const categoryColors: Record<string, string> = {
    RTOS: "var(--accent-violet)",
    CMSIS: "var(--accent-cyan)",
    HAL: "var(--accent-cyan)",
    Networking: "#06b6d4",
    Security: "#f59e0b",
    Communication: "#3b82f6",
    Sensor: "#10b981",
    Display: "#8b5cf6",
    Data: "#ec4899",
    Custom: "#64748b",
  };

  function categoryColor(cat: string) {
    return categoryColors[cat] ?? "var(--text-muted)";
  }
</script>

<div class="lib-panel">
  <!-- Header -->
  <div class="lib-header">
    <div class="lib-title-row">
      <Package size={14} style="color: var(--accent-violet);" />
      <span class="lib-title">LIBRARY MANAGER</span>
    </div>

    <!-- Tab bar -->
    <div class="lib-tabs">
      <!-- svelte-ignore a11y-click-events-have-key-events -->
      <!-- svelte-ignore a11y-no-static-element-interactions -->
      <div
        class="lib-tab {tab === 'discover' ? 'active' : ''}"
        onclick={() => actions.setLibraryManagerTab("discover")}
      >
        <Search size={11} />
        Discover
      </div>
      <!-- svelte-ignore a11y-click-events-have-key-events -->
      <!-- svelte-ignore a11y-no-static-element-interactions -->
      <div
        class="lib-tab {tab === 'installed' ? 'active' : ''}"
        onclick={() => actions.setLibraryManagerTab("installed")}
      >
        <PackageCheck size={11} />
        Installed
        {#if installedLibraries.length > 0}
          <span class="lib-badge">{installedLibraries.length}</span>
        {/if}
      </div>
      <!-- svelte-ignore a11y-click-events-have-key-events -->
      <!-- svelte-ignore a11y-no-static-element-interactions -->
      <div
        class="lib-tab {tab === 'updates' ? 'active' : ''}"
        onclick={() => actions.setLibraryManagerTab("updates")}
      >
        <RefreshCw size={11} />
        Updates
      </div>
    </div>
  </div>

  <!-- ── DISCOVER TAB ── -->
  {#if tab === "discover"}
    <div class="lib-search-bar">
      <Search size={12} style="color: var(--text-muted); flex-shrink: 0;" />
      <input
        type="text"
        class="lib-search-input"
        placeholder="Search libraries..."
        value={localSearch}
        oninput={onSearch}
      />
    </div>

    <!-- Category chips -->
    {#if libraryCategories.length > 0}
      <div class="lib-categories">
        {#each libraryCategories as cat}
          <!-- svelte-ignore a11y-click-events-have-key-events -->
          <!-- svelte-ignore a11y-no-static-element-interactions -->
          <div
            class="lib-cat-chip {$workspaceStore.librarySelectedCategory === cat ? 'active' : ''}"
            style={$workspaceStore.librarySelectedCategory === cat
              ? `background: ${categoryColor(cat)}22; border-color: ${categoryColor(cat)}; color: ${categoryColor(cat)};`
              : ""}
            onclick={() => onCategoryFilter(cat)}
          >
            {cat}
          </div>
        {/each}
      </div>
    {/if}

    <!-- Library list -->
    <div class="lib-list">
      {#if loading}
        <div class="lib-empty-state">
          <Loader size={20} style="animation: spin 1s linear infinite; color: var(--accent-violet);" />
          <span>Loading libraries...</span>
        </div>
      {:else if availableLibraries.length === 0}
        <div class="lib-empty-state">
          <Package size={28} style="color: var(--text-muted); opacity: 0.4;" />
          <span>No libraries found</span>
          <span style="font-size: 0.68rem; color: var(--text-muted); opacity: 0.6;">Try a different search or category</span>
        </div>
      {:else}
        {#each availableLibraries as lib (lib.id)}
          {@const status = getInstallStatus(lib.id)}
          {@const isExpanded = expandedLibrary === lib.id}
          <!-- svelte-ignore a11y-click-events-have-key-events -->
          <!-- svelte-ignore a11y-no-static-element-interactions -->
          <div
            class="lib-card {isExpanded ? 'expanded' : ''} {status === 'installed' ? 'lib-card-installed' : ''}"
            onclick={() => toggleExpand(lib.id)}
          >
            <!-- Card top row -->
            <div class="lib-card-header">
              <div class="lib-card-left">
                <div class="lib-name-row">
                  <span class="lib-name">{lib.name}</span>
                  <span class="lib-version-badge">v{lib.version}</span>
                  {#if status === "installed"}
                    <span class="lib-installed-badge">
                      <CheckCircle2 size={10} /> Installed
                    </span>
                  {/if}
                </div>
                <div class="lib-meta-row">
                  <span class="lib-meta-item" title="Author">
                    <User size={9} style="opacity:0.5;" />
                    {lib.author}
                  </span>
                  <span
                    class="lib-cat-tag"
                    style="color: {categoryColor(lib.category)}; border-color: {categoryColor(lib.category)}40;"
                  >
                    <Tag size={9} />
                    {lib.category}
                  </span>
                </div>
              </div>
              <div class="lib-card-right" onclick={(e) => e.stopPropagation()}>
                <!-- Install button state machine -->
                {#if status === "idle"}
                  {#if hasProject}
                    <button
                      class="lib-install-btn"
                      onclick={() => actions.confirmInstallLibrary(lib.id)}
                    >
                      <PackagePlus size={11} />
                      Install
                    </button>
                  {:else}
                    <button class="lib-install-btn" disabled title="Open a project first">
                      <PackagePlus size={11} />
                      Install
                    </button>
                  {/if}
                {:else if status === "confirming"}
                  <div class="lib-confirm-row">
                    <span class="lib-confirm-text">Add to project?</span>
                    <button
                      class="lib-confirm-btn yes"
                      onclick={() => actions.installLibrary(lib.id)}
                    >Yes</button>
                    <button
                      class="lib-confirm-btn no"
                      onclick={() => actions.cancelInstallLibrary(lib.id)}
                    >No</button>
                  </div>
                {:else if status === "installing"}
                  <div class="lib-installing-indicator">
                    <Loader size={11} style="animation: spin 1s linear infinite;" />
                    <span>Installing...</span>
                  </div>
                {:else if status === "installed"}
                  <div class="lib-installed-indicator">
                    <CheckCircle2 size={12} style="color: #10b981;" />
                    <span>Installed</span>
                  </div>
                {:else if status === "error"}
                  <button
                    class="lib-install-btn error"
                    title={installError[lib.id] || "Install failed"}
                    onclick={() => actions.confirmInstallLibrary(lib.id)}
                  >
                    <AlertCircle size={11} />
                    Retry
                  </button>
                {/if}
                <div class="lib-expand-icon">
                  {#if isExpanded}
                    <ChevronDown size={13} style="color: var(--text-muted);" />
                  {:else}
                    <ChevronRight size={13} style="color: var(--text-muted);" />
                  {/if}
                </div>
              </div>
            </div>

            <!-- Expanded detail -->
            {#if isExpanded}
              <div class="lib-card-detail" onclick={(e) => e.stopPropagation()}>
                <p class="lib-description">{lib.description}</p>
                <div class="lib-detail-meta">
                  {#if lib.targets?.length > 0}
                    <div class="lib-detail-row">
                      <Cpu size={10} style="color: var(--text-muted);" />
                      <span class="lib-detail-label">Targets:</span>
                      <div class="lib-target-chips">
                        {#each lib.targets as target}
                          <span class="lib-target-chip">{target}</span>
                        {/each}
                      </div>
                    </div>
                  {/if}
                  {#if lib.license}
                    <div class="lib-detail-row">
                      <Tag size={10} style="color: var(--text-muted);" />
                      <span class="lib-detail-label">License:</span>
                      <span class="lib-detail-value">{lib.license}</span>
                    </div>
                  {/if}
                  {#if lib.pio_name}
                    <div class="lib-detail-row">
                      <Package size={10} style="color: var(--text-muted);" />
                      <span class="lib-detail-label">PIO:</span>
                      <span class="lib-detail-value" style="font-family: 'JetBrains Mono', monospace; font-size: 0.65rem;">{lib.pio_name}</span>
                    </div>
                  {/if}
                  {#if lib.note}
                    <div class="lib-note">
                      <AlertCircle size={10} style="color: #f59e0b; flex-shrink:0;" />
                      <span>{lib.note}</span>
                    </div>
                  {/if}
                </div>
                {#if lib.homepage}
                  <a
                    href={lib.homepage}
                    target="_blank"
                    rel="noopener noreferrer"
                    class="lib-homepage-link"
                    onclick={(e) => e.stopPropagation()}
                  >
                    <ExternalLink size={10} />
                    View Documentation
                  </a>
                {/if}
              </div>
            {/if}
          </div>
        {/each}
      {/if}
    </div>

  <!-- ── INSTALLED TAB ── -->
  {:else if tab === "installed"}
    <div class="lib-list" style="padding-top: 8px;">
      {#if !hasProject}
        <div class="lib-empty-state">
          <Package size={28} style="color: var(--text-muted); opacity: 0.4;" />
          <span>No project open</span>
          <span style="font-size: 0.68rem; color: var(--text-muted); opacity: 0.6;">Open a project to see its installed libraries</span>
        </div>
      {:else if installedLibraries.length === 0}
        <div class="lib-empty-state">
          <PackagePlus size={28} style="color: var(--text-muted); opacity: 0.4;" />
          <span>No libraries installed</span>
          <span style="font-size: 0.68rem; color: var(--text-muted); opacity: 0.6;">Use the Discover tab to install libraries</span>
        </div>
      {:else}
        {#each installedLibraries as lib (lib.id)}
          <div class="lib-installed-row">
            <div class="lib-installed-info">
              <div class="lib-installed-name">
                <PackageCheck size={12} style="color: #10b981; flex-shrink: 0;" />
                <span>{lib.name}</span>
                <span class="lib-version-badge">{lib.version ?? "custom"}</span>
              </div>
              <div class="lib-meta-row" style="padding-left: 4px;">
                <span
                  class="lib-cat-tag"
                  style="color: {categoryColor(lib.category)}; border-color: {categoryColor(lib.category)}40;"
                >
                  <Tag size={9} />
                  {lib.category}
                </span>
                {#if lib.targets?.length > 0}
                  {#each lib.targets.slice(0, 2) as t}
                    <span class="lib-target-chip">{t}</span>
                  {/each}
                {/if}
              </div>
            </div>
            <button
              class="lib-uninstall-btn"
              title="Uninstall {lib.name}"
              onclick={() => actions.uninstallLibrary(lib.id)}
            >
              <Trash2 size={12} />
            </button>
          </div>
        {/each}
      {/if}
    </div>

  <!-- ── UPDATES TAB ── -->
  {:else if tab === "updates"}
    <div class="lib-list">
      <div class="lib-empty-state" style="padding-top: 40px;">
        <RefreshCw size={28} style="color: var(--text-muted); opacity: 0.3;" />
        <span style="color: var(--text-muted);">Update checking</span>
        <span style="font-size: 0.68rem; color: var(--text-muted); opacity: 0.55; text-align: center; max-width: 160px; line-height: 1.5;">
          Coming soon — automatically detect when installed libraries have newer versions available.
        </span>
      </div>
    </div>
  {/if}
</div>

<style>
  .lib-panel {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: hidden;
    background: var(--bg-primary);
  }

  /* Header */
  .lib-header {
    border-bottom: 1px solid var(--border-color);
    flex-shrink: 0;
  }

  .lib-title-row {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 10px 14px 6px;
  }

  .lib-title {
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    color: var(--text-muted);
  }

  /* Tabs */
  .lib-tabs {
    display: flex;
    gap: 0;
    padding: 0 8px;
  }

  .lib-tab {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 6px 10px;
    font-size: 0.69rem;
    font-weight: 500;
    color: var(--text-muted);
    cursor: pointer;
    border-bottom: 2px solid transparent;
    transition: color 0.15s, border-color 0.15s;
    user-select: none;
    white-space: nowrap;
  }

  .lib-tab:hover {
    color: var(--text-active);
  }

  .lib-tab.active {
    color: var(--accent-violet);
    border-bottom-color: var(--accent-violet);
  }

  .lib-badge {
    background: var(--accent-violet);
    color: white;
    border-radius: 8px;
    padding: 0 5px;
    font-size: 0.6rem;
    font-weight: 700;
    line-height: 1.6;
    min-width: 16px;
    text-align: center;
  }

  /* Search */
  .lib-search-bar {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    border-bottom: 1px solid var(--border-color);
    flex-shrink: 0;
  }

  .lib-search-input {
    flex: 1;
    background: transparent;
    border: none;
    outline: none;
    color: var(--text-active);
    font-size: 0.75rem;
    font-family: inherit;
  }

  .lib-search-input::placeholder {
    color: var(--text-muted);
    opacity: 0.6;
  }

  /* Category chips */
  .lib-categories {
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
    padding: 8px 12px;
    border-bottom: 1px solid var(--border-color);
    flex-shrink: 0;
  }

  .lib-cat-chip {
    font-size: 0.63rem;
    padding: 2px 8px;
    border-radius: 10px;
    border: 1px solid var(--border-color);
    color: var(--text-muted);
    cursor: pointer;
    transition: all 0.15s;
    user-select: none;
  }

  .lib-cat-chip:hover {
    border-color: var(--accent-violet);
    color: var(--accent-violet);
  }

  .lib-cat-chip.active {
    font-weight: 600;
  }

  /* Library list */
  .lib-list {
    flex: 1;
    overflow-y: auto;
    padding: 6px 0;
    scrollbar-width: thin;
    scrollbar-color: var(--border-color) transparent;
  }

  .lib-empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
    padding: 48px 20px;
    color: var(--text-muted);
    font-size: 0.75rem;
    text-align: center;
  }

  /* Library card */
  .lib-card {
    border-bottom: 1px solid var(--border-color);
    cursor: pointer;
    transition: background 0.12s;
    padding: 0;
  }

  .lib-card:hover {
    background: rgba(255, 255, 255, 0.025);
  }

  .lib-card.expanded {
    background: rgba(139, 92, 246, 0.04);
    border-bottom-color: rgba(139, 92, 246, 0.2);
  }

  .lib-card.lib-card-installed {
    border-left: 2px solid #10b981;
  }

  .lib-card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 9px 12px;
    gap: 8px;
  }

  .lib-card-left {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .lib-name-row {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
  }

  .lib-name {
    font-size: 0.75rem;
    font-weight: 600;
    color: var(--text-active);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 130px;
  }

  .lib-version-badge {
    font-size: 0.6rem;
    padding: 1px 6px;
    border-radius: 6px;
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid var(--border-color);
    color: var(--text-muted);
    font-family: 'JetBrains Mono', monospace;
    white-space: nowrap;
    flex-shrink: 0;
  }

  .lib-installed-badge {
    display: flex;
    align-items: center;
    gap: 3px;
    font-size: 0.6rem;
    color: #10b981;
    background: rgba(16, 185, 129, 0.1);
    border: 1px solid rgba(16, 185, 129, 0.3);
    border-radius: 6px;
    padding: 1px 6px;
    flex-shrink: 0;
  }

  .lib-meta-row {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }

  .lib-meta-item {
    display: flex;
    align-items: center;
    gap: 3px;
    font-size: 0.63rem;
    color: var(--text-muted);
  }

  .lib-cat-tag {
    display: flex;
    align-items: center;
    gap: 3px;
    font-size: 0.62rem;
    font-weight: 600;
    border: 1px solid;
    border-radius: 6px;
    padding: 1px 6px;
  }

  /* Card right — install controls */
  .lib-card-right {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-shrink: 0;
  }

  .lib-install-btn {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 0.68rem;
    font-weight: 600;
    padding: 4px 10px;
    border-radius: 5px;
    border: 1px solid rgba(139, 92, 246, 0.5);
    background: rgba(139, 92, 246, 0.08);
    color: var(--accent-violet);
    cursor: pointer;
    transition: all 0.15s;
    white-space: nowrap;
  }

  .lib-install-btn:hover:not(:disabled) {
    background: rgba(139, 92, 246, 0.2);
    border-color: var(--accent-violet);
  }

  .lib-install-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .lib-install-btn.error {
    border-color: rgba(239, 68, 68, 0.5);
    background: rgba(239, 68, 68, 0.08);
    color: #ef4444;
  }

  .lib-confirm-row {
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .lib-confirm-text {
    font-size: 0.65rem;
    color: var(--text-muted);
    white-space: nowrap;
  }

  .lib-confirm-btn {
    font-size: 0.65rem;
    font-weight: 600;
    padding: 3px 8px;
    border-radius: 4px;
    cursor: pointer;
    transition: all 0.12s;
  }

  .lib-confirm-btn.yes {
    background: rgba(16, 185, 129, 0.15);
    border: 1px solid rgba(16, 185, 129, 0.4);
    color: #10b981;
  }

  .lib-confirm-btn.yes:hover {
    background: rgba(16, 185, 129, 0.3);
  }

  .lib-confirm-btn.no {
    background: rgba(239, 68, 68, 0.1);
    border: 1px solid rgba(239, 68, 68, 0.3);
    color: #ef4444;
  }

  .lib-confirm-btn.no:hover {
    background: rgba(239, 68, 68, 0.2);
  }

  .lib-installing-indicator,
  .lib-installed-indicator {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 0.67rem;
    color: var(--text-muted);
    white-space: nowrap;
  }

  .lib-expand-icon {
    display: flex;
    align-items: center;
    opacity: 0.5;
  }

  /* Expanded detail */
  .lib-card-detail {
    padding: 0 12px 12px 12px;
    border-top: 1px solid rgba(255, 255, 255, 0.04);
  }

  .lib-description {
    font-size: 0.72rem;
    color: var(--text-muted);
    line-height: 1.55;
    margin: 10px 0 10px;
  }

  .lib-detail-meta {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin-bottom: 10px;
  }

  .lib-detail-row {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .lib-detail-label {
    font-size: 0.65rem;
    color: var(--text-muted);
    font-weight: 600;
    min-width: 46px;
  }

  .lib-detail-value {
    font-size: 0.67rem;
    color: var(--text-active);
    opacity: 0.8;
  }

  .lib-target-chips {
    display: flex;
    gap: 4px;
    flex-wrap: wrap;
  }

  .lib-target-chip {
    font-size: 0.6rem;
    padding: 1px 6px;
    border-radius: 4px;
    background: rgba(6, 182, 212, 0.08);
    border: 1px solid rgba(6, 182, 212, 0.25);
    color: var(--accent-cyan);
    font-weight: 500;
  }

  .lib-note {
    display: flex;
    align-items: flex-start;
    gap: 5px;
    font-size: 0.65rem;
    color: #f59e0b;
    background: rgba(245, 158, 11, 0.06);
    border: 1px solid rgba(245, 158, 11, 0.2);
    border-radius: 4px;
    padding: 6px 8px;
    line-height: 1.45;
    margin-top: 4px;
  }

  .lib-homepage-link {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 0.67rem;
    color: var(--accent-violet);
    text-decoration: none;
    opacity: 0.75;
    transition: opacity 0.15s;
  }

  .lib-homepage-link:hover {
    opacity: 1;
    text-decoration: underline;
  }

  /* Installed tab rows */
  .lib-installed-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 9px 12px;
    border-bottom: 1px solid var(--border-color);
    gap: 8px;
    transition: background 0.12s;
    border-left: 2px solid #10b981;
  }

  .lib-installed-row:hover {
    background: rgba(255, 255, 255, 0.02);
  }

  .lib-installed-info {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .lib-installed-name {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 0.74rem;
    font-weight: 600;
    color: var(--text-active);
  }

  .lib-uninstall-btn {
    padding: 5px;
    border-radius: 5px;
    border: 1px solid transparent;
    background: transparent;
    color: var(--text-muted);
    cursor: pointer;
    transition: all 0.15s;
    flex-shrink: 0;
    display: flex;
    align-items: center;
  }

  .lib-uninstall-btn:hover {
    background: rgba(239, 68, 68, 0.1);
    border-color: rgba(239, 68, 68, 0.3);
    color: #ef4444;
  }

  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }
</style>
