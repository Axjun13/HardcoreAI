<script lang="ts">
  import { api } from "../api";
  import { workspaceStore, actions } from "../store";
  import { Brain, Check, FileText, Package, Sparkles } from "lucide-svelte";

  let idea = "";
  let notes = "";
  let loading = false;
  let message = "";
  let state: any = null;
  let selected = new Set<string>();

  $: projectId = $workspaceStore.activeProjectId;
  $: provider = ($workspaceStore as any).selectedProvider || "deepseek";
  $: summaryBlocks = formatSummary(state?.summary || "");

  function stripMarkdown(value: string) {
    return value
      .replace(/\*\*/g, "")
      .replace(/\s+/g, " ")
      .trim();
  }

  function splitSummaryLines(value: string) {
    const normalized = stripMarkdown(value)
      .replace(/\s+-\s+/g, "\n")
      .replace(/\s+(?=\d+\.\s+)/g, "\n");
    return normalized
      .split(/\n+/)
      .map((line) => line.trim())
      .filter(Boolean);
  }

  function formatSummary(value: string) {
    if (!value.trim()) return [];
    const sections = value
      .split(/(?=\*\*[^*]+:\*\*)/g)
      .map((part) => part.trim())
      .filter(Boolean);

    if (!sections.length) {
      return [{ title: "Summary", lines: splitSummaryLines(value) }];
    }

    return sections.map((section) => {
      const match = section.match(/^\*\*([^*]+):\*\*\s*([\s\S]*)$/);
      if (!match) return { title: "Summary", lines: splitSummaryLines(section) };
      return {
        title: stripMarkdown(match[1]),
        lines: splitSummaryLines(match[2]),
      };
    });
  }

  async function loadState() {
    if (!projectId) return;
    try {
      state = await api.getResearchState(projectId);
      selected = new Set((state.selected_components || []).map((item: any) => item.id));
    } catch (e) {
      message = e instanceof Error ? e.message : "Failed to load research state.";
    }
  }

  async function ideate() {
    if (!projectId || !idea.trim()) return;
    loading = true;
    message = "";
    try {
      const result = await api.ideateResearch(projectId, idea, provider);
      state = result.state;
      selected = new Set();
      message = "Research summary updated.";
    } catch (e) {
      message = e instanceof Error ? e.message : "Research failed.";
    } finally {
      loading = false;
    }
  }

  function toggle(id: string) {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    selected = next;
  }

  async function saveSelection(installLibraries = false) {
    if (!projectId) return;
    loading = true;
    try {
      const result = await api.selectResearchComponents(projectId, [...selected], notes, installLibraries);
      state = result.state;
      message = installLibraries ? "Selection saved and libraries prepared." : "Selection saved.";
    } catch (e) {
      message = e instanceof Error ? e.message : "Selection failed.";
    } finally {
      loading = false;
    }
  }

  async function preparePhase3() {
    if (!projectId) return;
    loading = true;
    try {
      await api.prepareResearchPhase3(projectId, true);
      message = "Phase 3 context stored and libraries added to platformio.ini.";
    } catch (e) {
      message = e instanceof Error ? e.message : "Phase 3 prepare failed.";
    } finally {
      loading = false;
    }
  }

  async function generateReadme() {
    if (!projectId) return;
    loading = true;
    try {
      await api.generateResearchReadme(projectId);
      await actions.refreshProjectFiles(projectId);
      message = "README.md generated from research, board, pins, and libraries.";
    } catch (e) {
      message = e instanceof Error ? e.message : "README generation failed.";
    } finally {
      loading = false;
    }
  }

  $: if (projectId && state === null) loadState();
</script>

<div class="research-panel">
  <div class="research-top">
    <div class="research-header">
      <div class="research-icon"><Brain size={16} /></div>
      <div>
        <div class="research-title">Research</div>
        <div class="research-subtitle">Plan parts, pins, libraries, and handoff.</div>
      </div>
    </div>

    <textarea
      bind:value={idea}
      class="research-input"
      placeholder="What are you building?"
      rows="3"
    ></textarea>
    <button class="research-primary" on:click={ideate} disabled={loading || !projectId || !idea.trim()}>
      <Sparkles size={14} />
      <span>{loading ? "Researching..." : "Research Components"}</span>
    </button>
  </div>

  <div class="research-scroll">
    {#if summaryBlocks.length}
      <div class="research-section">
        <div class="section-label">Condensed State</div>
        <div class="summary-stack">
          {#each summaryBlocks as block}
            <section class="summary-block">
              <div class="summary-title">{block.title}</div>
              {#each block.lines as line}
                <p>{line}</p>
              {/each}
            </section>
          {/each}
        </div>
      </div>
    {/if}

    {#if state?.recommendations?.length}
      <div class="research-section">
        <div class="section-label">Component Options</div>
        <div class="component-list">
          {#each state.recommendations as item}
            <button
              type="button"
              class:selected={selected.has(item.id)}
              class="component-card"
              on:click={() => toggle(item.id)}
            >
              <div class="component-row">
                <span>{item.name}</span>
                <span class="select-indicator">{#if selected.has(item.id)}<Check size={13} />{/if}</span>
              </div>
              <div class="component-meta">{item.category} - {item.id}</div>
              <p>{item.description}</p>
              <div class="component-diff">{item.difference}</div>
              {#if item.library_ids?.length || item.library_name}
                <div class="component-chip">Libraries: {[...(item.library_ids || []), item.library_name].filter(Boolean).join(", ")}</div>
              {/if}
              <div class="component-links">
                {#if item.datasheet_url}
                  <a href={item.datasheet_url} target="_blank" rel="noreferrer" on:click|stopPropagation>Datasheet</a>
                {/if}
                {#each item.buy_links || [] as link}
                  {#if link.url}
                    <a href={link.url} target="_blank" rel="noreferrer" on:click|stopPropagation>{link.vendor || link.label || "Buy"}</a>
                  {/if}
                {/each}
              </div>
            </button>
          {/each}
        </div>
      </div>

      <div class="research-section">
        <div class="section-label">Decision Notes</div>
        <textarea bind:value={notes} class="research-input notes-input" placeholder="Why these parts? Any constraints?" rows="3"></textarea>
        <div class="research-actions">
          <button on:click={() => saveSelection(false)} disabled={loading}>
            <Package size={13} /> Save
          </button>
          <button on:click={preparePhase3} disabled={loading}>
            <Package size={13} /> Phase 3
          </button>
          <button on:click={generateReadme} disabled={loading}>
            <FileText size={13} /> README
          </button>
        </div>
      </div>
    {:else if state}
      <div class="empty-state">
        No component options yet. Add a clearer idea and run research again.
      </div>
    {/if}

    {#if message}
      <div class="research-message">{message}</div>
    {/if}
  </div>
</div>

<style>
  .research-panel {
    height: 100%;
    min-height: 0;
    color: var(--text-primary);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    background: var(--bg-primary);
  }
  .research-top {
    flex: 0 0 auto;
    padding: 14px 16px 12px;
    border-bottom: 1px solid var(--border-color);
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .research-scroll {
    flex: 1 1 auto;
    min-height: 0;
    overflow-y: auto;
    padding: 14px 16px 18px;
    display: flex;
    flex-direction: column;
    gap: 14px;
    scrollbar-width: thin;
  }
  .research-header {
    display: flex;
    gap: 10px;
    align-items: center;
  }
  .research-icon {
    width: 28px;
    height: 28px;
    border: 1px solid rgba(139, 92, 246, 0.45);
    border-radius: 6px;
    color: var(--accent-violet);
    display: grid;
    place-items: center;
    background: rgba(139, 92, 246, 0.08);
  }
  .research-title {
    font-weight: 750;
    font-size: 0.92rem;
    line-height: 1.1;
  }
  .research-subtitle,
  .component-meta,
  .research-message,
  .empty-state {
    font-size: 0.72rem;
    color: var(--text-muted);
  }
  .research-input {
    width: 100%;
    min-height: 86px;
    resize: vertical;
    border: 1px solid var(--border-color);
    background: var(--bg-secondary);
    color: var(--text-primary);
    border-radius: 6px;
    padding: 10px;
    font: inherit;
    font-size: 0.8rem;
    line-height: 1.45;
    outline: none;
  }
  .research-input:focus {
    border-color: rgba(139, 92, 246, 0.8);
    box-shadow: 0 0 0 2px rgba(139, 92, 246, 0.16);
  }
  .notes-input {
    min-height: 74px;
    margin-bottom: 10px;
  }
  .research-primary,
  .research-actions button {
    border: 1px solid var(--border-color);
    background: var(--bg-secondary);
    color: var(--text-primary);
    border-radius: 6px;
    padding: 8px 10px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 7px;
    cursor: pointer;
    font-weight: 700;
    font-size: 0.78rem;
  }
  .research-primary {
    width: 100%;
    background: var(--accent-violet);
    color: white;
    border-color: transparent;
  }
  .research-primary:disabled,
  .research-actions button:disabled {
    cursor: default;
    opacity: 0.55;
  }
  .research-section {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .section-label {
    font-size: 0.66rem;
    text-transform: uppercase;
    letter-spacing: 0;
    color: var(--text-muted);
    font-weight: 800;
  }
  .summary-stack,
  .component-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .summary-block {
    border-left: 2px solid rgba(139, 92, 246, 0.75);
    padding: 7px 0 7px 10px;
    background: rgba(139, 92, 246, 0.04);
  }
  .summary-title {
    color: var(--text-primary);
    font-size: 0.78rem;
    font-weight: 800;
    margin-bottom: 4px;
  }
  .summary-block p {
    margin: 4px 0 0;
    color: var(--text-secondary);
    font-size: 0.76rem;
    line-height: 1.42;
  }
  .component-card {
    width: 100%;
    text-align: left;
    border: 1px solid var(--border-color);
    background: var(--bg-secondary);
    color: var(--text-primary);
    border-radius: 6px;
    padding: 10px;
    cursor: pointer;
  }
  .component-card:hover {
    border-color: rgba(139, 92, 246, 0.55);
  }
  .component-card.selected {
    border-color: var(--accent-violet);
    box-shadow: inset 3px 0 0 var(--accent-violet);
  }
  .component-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    font-weight: 750;
    font-size: 0.82rem;
    line-height: 1.25;
  }
  .select-indicator {
    width: 18px;
    height: 18px;
    flex: 0 0 auto;
    color: var(--accent-violet);
    display: grid;
    place-items: center;
  }
  .component-card p {
    font-size: 0.75rem;
    line-height: 1.38;
    margin: 7px 0;
    color: var(--text-secondary);
  }
  .component-diff {
    font-size: 0.72rem;
    color: var(--text-muted);
    line-height: 1.35;
    margin: 7px 0;
  }
  .component-chip {
    display: inline-flex;
    max-width: 100%;
    border: 1px solid rgba(139, 92, 246, 0.35);
    color: var(--text-secondary);
    border-radius: 5px;
    padding: 4px 6px;
    font-size: 0.68rem;
    line-height: 1.25;
    margin-bottom: 8px;
  }
  .component-links {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    font-size: 0.72rem;
  }
  .component-links a {
    color: var(--accent-violet);
    text-decoration: none;
    font-weight: 700;
  }
  .component-links a:hover {
    text-decoration: underline;
  }
  .research-actions {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 6px;
  }
  .research-message,
  .empty-state {
    border: 1px solid var(--border-color);
    border-radius: 6px;
    padding: 9px 10px;
    background: var(--bg-secondary);
    line-height: 1.4;
  }
</style>
