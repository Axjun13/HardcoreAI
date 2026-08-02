<script lang="ts">
  import { onDestroy, tick } from "svelte";
  import { api } from "../api";
  import { workspaceStore, actions } from "../store";
  import {
    Brain,
    Check,
    ChevronRight,
    Clock3,
    ExternalLink,
    FileText,
    LoaderCircle,
    Package,
    Plus,
    Send,
    Sparkles,
    Trash2,
  } from "lucide-svelte";

  export let onActMode: (
    startAgent?: boolean,
    handoff?: any,
  ) => void = () => {};

  let input = "";
  let notes = "";
  let loading = false;
  let notice = "";
  let state: any = null;
  let selected = new Set<string>();
  let activeContextId = "";
  let pendingUser = "";
  let streamingText = "";
  let thinkingLabel = "";
  let conversationEl: HTMLDivElement;
  let scrollFrame = 0;
  let stateProjectId = "";
  let phase3Activity: any = null;
  let phase3ActivityLog: any[] = [];
  let phase3Elapsed = 0;

  const phase3Clock = window.setInterval(() => {
    if (loading && stage === "verification") phase3Elapsed += 1;
  }, 1000);
  onDestroy(() => window.clearInterval(phase3Clock));

  $: projectId = $workspaceStore.activeProjectId;
  $: provider = $workspaceStore.selectedProvider || "cloud";
  $: contexts = state?.contexts || [];
  $: activeContext =
    contexts.find((item: any) => item.id === activeContextId) ||
    contexts[0] ||
    null;
  $: recommendations =
    activeContext?.recommendations || state?.recommendations || [];
  $: stage = state?.stage || "ideation";
  $: artifact =
    stage === "component_selection"
      ? state?.plan_markdown
      : stage === "verification"
        ? loading
          ? ""
          : state?.verification_markdown
        : stage === "final_review" || stage === "act"
          ? state?.final_markdown
          : "";
  $: todos = state?.todos || [];
  $: activePhase3Todo = todos.find(
    (todo: any) => todo.status === "in_progress",
  );
  $: phase3Progress = Math.max(
    0,
    Math.min(100, Number(phase3Activity?.progress_percent || 0)),
  );
  const verificationPhases = [
    "web_search",
    "source_review",
    "datasheet",
    "analysis",
    "validation",
  ];
  $: verificationPhaseIndex = verificationPhases.indexOf(phase3Activity?.phase);

  const stageCopy: Record<
    string,
    { label: string; help: string; action: string }
  > = {
    ideation: {
      label: "Discuss the idea",
      help: "Talk it through with the agent. Confirm only when the requirements feel right.",
      action: "Confirm idea",
    },
    component_selection: {
      label: "Choose components",
      help: "Review the plan and component tradeoffs, then select the parts to use.",
      action: "Confirm components",
    },
    verification: {
      label: "Verify integration",
      help: "The agent checks each component, updates missing catalogue facts, then generates pins, wiring, and configuration.",
      action: "Resume Phase 3",
    },
    final_review: {
      label: "Final review",
      help: "Approve the complete plan and TODO, or describe an edit below.",
      action: "Approve & enter Act mode",
    },
    act: {
      label: "Act mode ready",
      help: "The IDE and agent now have the confirmed plan, components, and dependencies.",
      action: "Open IDE",
    },
  };

  function escapeHtml(value: string) {
    return value.replace(
      /[&<>"']/g,
      (char) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#039;",
        })[char] || char,
    );
  }

  function renderMarkdown(value: string) {
    const safe = escapeHtml(value || "");
    return safe
      .replace(/^### (.+)$/gm, "<h3>$1</h3>")
      .replace(/^## (.+)$/gm, "<h2>$1</h2>")
      .replace(/^# (.+)$/gm, "<h1>$1</h1>")
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/^\- \[ \] (.+)$/gm, '<div class="task">☐ $1</div>')
      .replace(/^\- (.+)$/gm, '<div class="bullet">• $1</div>')
      .replace(/\n{2,}/g, "</p><p>")
      .replace(/\n/g, "<br>");
  }

  function syncSelection() {
    const context = contexts.find((item: any) => item.id === activeContextId);
    selected = new Set(
      context?.selected_component_ids ||
        (state?.selected_components || []).map((item: any) => item.id),
    );
    notes = context?.decision_notes || state?.decision_notes || "";
  }

  function formatElapsed(seconds: number) {
    const minutes = Math.floor(seconds / 60);
    const remainder = seconds % 60;
    return minutes
      ? `${minutes}m ${String(remainder).padStart(2, "0")}s`
      : `${remainder}s`;
  }

  function recordPhase3Activity(activity: any) {
    if (!activity) return;
    phase3Activity = activity;
    phase3Elapsed = Number(activity.elapsed_seconds ?? phase3Elapsed);
    const previous = phase3ActivityLog[phase3ActivityLog.length - 1];
    if (
      previous?.phase !== activity.phase ||
      previous?.component !== activity.component
    ) {
      phase3ActivityLog = [
        ...phase3ActivityLog,
        {
          phase: activity.phase,
          component: activity.component,
          title: activity.title,
          detail: activity.detail,
          at: new Date().toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
          }),
        },
      ].slice(-8);
    }
  }

  async function loadState(targetProjectId = projectId) {
    if (!targetProjectId) return;
    try {
      const result = await api.getResearchState(targetProjectId);
      if (targetProjectId !== projectId) return;
      state = result;
      activeContextId =
        state.active_context_id || state.contexts?.[0]?.id || "";
      syncSelection();
      if (
        state.stage === "verification" &&
        state.verification_activity?.title
      ) {
        phase3Activity = {
          ...state.verification_activity,
          status: "paused",
          title: "Phase 3 is ready to resume",
          detail:
            "The previous stream is no longer attached to this view. Resume Phase 3 to continue safely from component verification.",
        };
      }
    } catch (error) {
      notice =
        error instanceof Error ? error.message : "Could not load research.";
    }
  }

  function switchProject(nextProjectId: string | null) {
    stateProjectId = nextProjectId || "";
    state = null;
    activeContextId = "";
    selected = new Set();
    notes = "";
    notice = "";
    pendingUser = "";
    streamingText = "";
    thinkingLabel = "";
    phase3Activity = null;
    phase3ActivityLog = [];
    phase3Elapsed = 0;
    if (nextProjectId) loadState(nextProjectId);
  }

  async function createContext() {
    if (!projectId || loading) return;
    loading = true;
    try {
      const result = await api.createResearchContext(projectId);
      state = result.state;
      activeContextId = result.context.id;
      syncSelection();
    } finally {
      loading = false;
    }
  }

  function selectContext(id: string) {
    activeContextId = id;
    syncSelection();
    if (projectId) api.activateResearchContext(projectId, id).catch(() => {});
  }

  async function deleteContext(id: string) {
    if (!projectId || loading) return;
    const context = contexts.find((item: any) => item.id === id);
    if (
      !window.confirm(
        `Delete “${context?.title || "this idea"}” and its chat history?`,
      )
    )
      return;
    loading = true;
    notice = "";
    try {
      const result = await api.deleteResearchContext(projectId, id);
      state = result.state;
      activeContextId =
        state.active_context_id || state.contexts?.[0]?.id || "";
      syncSelection();
      notice = "Chat deleted.";
    } catch (error) {
      notice =
        error instanceof Error ? error.message : "Could not delete the chat.";
    } finally {
      loading = false;
    }
  }

  function hasRemoteImage(component: any) {
    return (
      typeof component?.thumbnail === "string" &&
      /^https?:\/\//i.test(component.thumbnail)
    );
  }

  function hideBrokenImage(event: Event) {
    (event.currentTarget as HTMLImageElement).style.display = "none";
  }

  function looksLikeFinalReviewQuestion(message: string) {
    const value = message.trim();
    const editVerb =
      "(?:add|change|edit|include|modify|remove|rename|replace|revise|set|switch|update|use)";
    const explicitEdit = new RegExp(
      `^(?:(?:can|could|will|would) you\\s+)?(?:please\\s+)?${editVerb}\\b|^(?:i want|i need|i(?:'d| would) like|let's|we should)\\b`,
      "i",
    ).test(value);
    if (explicitEdit) return false;
    return (
      /\?\s*$/.test(value) ||
      /^(can|could|did|do|does|how|is|should|what|when|where|which|who|why|will|would)\b/i.test(
        value,
      )
    );
  }

  function queueScroll() {
    cancelAnimationFrame(scrollFrame);
    scrollFrame = requestAnimationFrame(async () => {
      await tick();
      conversationEl?.scrollTo({
        top: conversationEl.scrollHeight,
        behavior: "smooth",
      });
    });
  }

  async function sendMessage() {
    if (!projectId || !input.trim() || loading) return;
    const normalizedInput = input
      .trim()
      .toLowerCase()
      .replace(/[.!]+$/, "");
    if (
      ["confirm", "confirmed", "yes", "approve", "approved"].includes(
        normalizedInput,
      )
    ) {
      input = "";
      await advance();
      return;
    }
    if (stage === "final_review") {
      const finalReviewMessage = input.trim();
      if (!looksLikeFinalReviewQuestion(finalReviewMessage)) {
        input = "";
        pendingUser = finalReviewMessage;
        streamingText = "";
        thinkingLabel = "Revising the final plan";
        queueScroll();
        await advance("revise", finalReviewMessage);
        return;
      }
    }
    const message = input.trim();
    input = "";
    pendingUser = message;
    streamingText = "";
    thinkingLabel =
      stage === "ideation"
        ? "Exploring your idea"
        : stage === "final_review"
          ? "Reviewing the final plan"
          : "Comparing the tradeoffs";
    loading = true;
    notice = "";
    let completed = false;
    queueScroll();
    try {
      await api.streamResearch(
        projectId,
        message,
        provider,
        activeContextId || undefined,
        (event: any) => {
          if (event.type === "status") {
            thinkingLabel = event.text || thinkingLabel;
          } else if (event.type === "delta") {
            thinkingLabel = "";
            streamingText += event.text || "";
            queueScroll();
          } else if (event.type === "done") {
            state = event.state;
            activeContextId =
              event.context?.id || state.active_context_id || activeContextId;
            completed = true;
            pendingUser = "";
            streamingText = "";
            thinkingLabel = "";
            syncSelection();
            queueScroll();
          } else if (event.type === "degraded") {
            thinkingLabel = "";
            notice =
              event.message || "The selected model is temporarily unavailable.";
          } else if (event.type === "error") {
            thinkingLabel = "";
            notice = event.message || "The research response was interrupted.";
          }
        },
      );
      if (!completed && !notice)
        notice = "The research stream ended before the response was saved.";
    } catch (error) {
      thinkingLabel = "";
      notice =
        error instanceof Error
          ? error.message
          : "The research agent could not respond.";
    } finally {
      loading = false;
    }
  }

  function toggleComponent(id: string) {
    const next = new Set(selected);
    next.has(id) ? next.delete(id) : next.add(id);
    selected = next;
  }

  async function advance(action = "confirm", message = "") {
    if (!projectId || loading) return;
    if (stage === "act") {
      onActMode(false, state);
      return;
    }
    loading = true;
    notice = "";
    try {
      if (
        (stage === "component_selection" || stage === "verification") &&
        action === "confirm"
      ) {
        phase3Elapsed = 0;
        phase3ActivityLog = [];
        phase3Activity = {
          status: "running",
          phase: "starting",
          title: "Starting Phase 3 integration verification",
          detail:
            "Building the component queue and preparing authoritative source checks.",
          progress_percent: 1,
          index: 0,
          total: selected.size,
        };
        await api.streamResearchVerification(
          projectId,
          [...selected],
          notes,
          provider,
          stage,
          (event: any) => {
            if (event.state) state = event.state;
            if (event.type === "activity") {
              recordPhase3Activity(event.activity);
              notice = event.activity?.title || "Phase 3 is working…";
            } else if (event.type === "heartbeat") {
              phase3Elapsed = Number(event.elapsed_seconds ?? phase3Elapsed);
            } else if (event.type === "component_warning") {
              recordPhase3Activity(
                event.activity || event.state?.verification_activity,
              );
              notice =
                event.message ||
                "The component check produced a warning; Phase 3 is continuing.";
            } else if (event.type === "component_done") {
              recordPhase3Activity(event.state?.verification_activity);
              notice = `${event.verification?.name || "Component"} checked.`;
            } else if (event.type === "done") {
              recordPhase3Activity(event.state?.verification_activity);
              notice = `Created ${event.artifacts.join(", ")}. Review the final plan below.`;
              actions.refreshProjectFiles(projectId);
            }
          },
        );
        if (state?.stage !== "final_review") {
          throw new Error(
            "Phase 3 ended before the final-review artifacts were saved. You can resume it safely.",
          );
        }
        return;
      }
      if (stage === "final_review" && action === "confirm") {
        notice =
          "Installing PlatformIO libraries and finalizing the plan — this can take a few minutes on first run…";
      }
      const result = await api.advanceResearch(
        projectId,
        action,
        [...selected],
        notes,
        message,
        provider,
        stage,
      );
      state = result.state;
      if (action === "revise") {
        pendingUser = "";
        streamingText = "";
        thinkingLabel = "";
        queueScroll();
      }
      // File-tree refresh is secondary to the workflow transition and can be
      // slow for large real project folders. Never keep the stage button in a
      // permanent "Working…" state while waiting for it.
      actions.refreshProjectFiles(projectId);
      notice = result.artifacts?.length
        ? `Created ${result.artifacts.join(", ")}.`
        : "Workflow updated.";
      if (result.act_mode) onActMode(true, result.state);
    } catch (error) {
      if (stage === "verification" || phase3Activity) {
        phase3Activity = {
          ...phase3Activity,
          status: "error",
          title: "Phase 3 stream was interrupted",
          detail:
            error instanceof Error
              ? error.message
              : "The verification stream stopped unexpectedly.",
        };
      }
      notice =
        error instanceof Error
          ? error.message
          : "Could not advance the workflow.";
      if (action === "revise") {
        pendingUser = "";
        thinkingLabel = "";
      }
      loadState(projectId);
    } finally {
      loading = false;
    }
  }

  $: if ((projectId || "") !== stateProjectId) switchProject(projectId);
</script>

<div class="research-view">
  <aside class="research-sidebar">
    <div class="brand"><Brain size={18} /><span>Research</span></div>
    <button class="new-idea" onclick={createContext} disabled={loading}
      ><Plus size={14} /> New idea</button
    >
    <div class="context-list">
      {#each contexts as context, index}
        <div class:active={context.id === activeContextId} class="context-row">
          <button
            class="context-open"
            onclick={() => selectContext(context.id)}
          >
            <span>{context.title || `Idea ${index + 1}`}</span><ChevronRight
              size={13}
            />
          </button>
          <button
            class="context-delete"
            onclick={() => deleteContext(context.id)}
            title="Delete chat"
            aria-label={`Delete ${context.title || `Idea ${index + 1}`}`}
          >
            <Trash2 size={13} />
          </button>
        </div>
      {/each}
    </div>
    {#if todos.length}
      <section class="todo-panel" aria-label="Mandatory workflow TODO list">
        <div class="todo-title">MANDATORY TODO</div>
        {#each todos as todo, index}
          <div
            class="todo-row {todo.status || 'pending'}"
            title={todo.detail || todo.label}
          >
            <span
              >{todo.status === "completed"
                ? "✓"
                : todo.status === "in_progress"
                  ? "●"
                  : todo.status === "warning"
                    ? "!"
                    : index + 1}</span
            >
            <p>{todo.label}</p>
          </div>
        {/each}
      </section>
    {/if}
    <div class="workflow">
      {#each ["ideation", "component_selection", "verification", "final_review", "act"] as item, index}
        <div
          class:current={item === stage}
          class:done={[
            "ideation",
            "component_selection",
            "verification",
            "final_review",
            "act",
          ].indexOf(stage) > index}
        >
          <span>{index + 1}</span>{stageCopy[item].label}
        </div>
      {/each}
    </div>
  </aside>

  <main class="research-chat">
    <header>
      <div>
        <h1>{stageCopy[stage]?.label}</h1>
        <p>{stageCopy[stage]?.help}</p>
      </div>
      <div class="stage-pill">
        Step {Math.max(
          1,
          [
            "ideation",
            "component_selection",
            "verification",
            "final_review",
            "act",
          ].indexOf(stage) + 1,
        )} of 5
      </div>
    </header>

    <div class="conversation" bind:this={conversationEl}>
      {#if stage === "verification"}
        <section
          class="phase3-monitor {loading
            ? 'running'
            : phase3Activity?.status || 'paused'}"
          aria-live="polite"
          aria-label="Phase 3 live progress"
        >
          <div class="monitor-glow"></div>
          <div class="monitor-header">
            <div class="monitor-agent">
              <span class="monitor-orbit"
                ><i><LoaderCircle size={20} /></i></span
              >
              <div>
                <span class="monitor-eyebrow"
                  >{loading ? "AGENT WORKING · LIVE" : "PHASE 3 PAUSED"}</span
                >
                <h2>{phase3Activity?.title || "Integration verification"}</h2>
              </div>
            </div>
            <div class="monitor-clock">
              <Clock3 size={13} /><span>{formatElapsed(phase3Elapsed)}</span>
            </div>
          </div>

          <div class="monitor-progress-head">
            <span
              >{phase3Activity?.component
                ? `Component ${phase3Activity.index || 1} of ${phase3Activity.total || selected.size}: ${phase3Activity.component}`
                : "Phase 3 integration package"}</span
            >
            <strong>{Math.round(phase3Progress)}%</strong>
          </div>
          <div class="monitor-progress">
            <span style={`width:${phase3Progress}%`}></span>
          </div>

          <div class="monitor-analysis">
            <span class="analysis-label">CURRENT OPERATION</span>
            <p>
              {phase3Activity?.detail ||
                activePhase3Todo?.detail ||
                "Waiting to continue the next verification operation."}
            </p>
            {#if loading}<span class="analysis-dots"><i></i><i></i><i></i></span
              >{/if}
          </div>

          {#if phase3Activity?.component}
            <div class="phase-track" aria-label="Component verification stages">
              {#each ["Search", "Sources", "Datasheet", "Cross-check", "Validate"] as label, index}
                <div
                  class:active={index === verificationPhaseIndex}
                  class:done={verificationPhaseIndex > index ||
                    phase3Activity?.phase === "component_done"}
                >
                  <span
                    >{verificationPhaseIndex > index ||
                    phase3Activity?.phase === "component_done"
                      ? "✓"
                      : index + 1}</span
                  >
                  <small>{label}</small>
                </div>
              {/each}
            </div>
          {/if}

          {#if phase3ActivityLog.length}
            <div class="activity-log">
              <div class="activity-log-title">LIVE ACTIVITY</div>
              {#each phase3ActivityLog.slice(-5).reverse() as item, index}
                <div class="activity-entry" class:latest={index === 0}>
                  <span class="activity-node"></span>
                  <time>{item.at}</time>
                  <div>
                    <strong>{item.title}</strong>{#if item.component}<small
                        >{item.component}</small
                      >{/if}
                  </div>
                </div>
              {/each}
            </div>
          {/if}

          {#if !loading}
            <button
              class="resume-phase3"
              onclick={() => advance()}
              disabled={selected.size === 0}
            >
              <Sparkles size={14} /> Resume Phase 3
            </button>
          {/if}
        </section>
      {/if}

      {#if stage === "final_review" && artifact}
        <article class="artifact-card">
          <div class="artifact-title">
            <FileText size={16} />
            final-review.md
          </div>
          <div class="markdown">{@html renderMarkdown(artifact)}</div>
        </article>
      {/if}

      {#if activeContext?.messages?.length}
        {#each activeContext.messages as message}
          <article class:user={message.role === "user"} class="message">
            <div class="avatar">{message.role === "user" ? "You" : "AI"}</div>
            <div class="message-body">
              {@html renderMarkdown(message.content)}
            </div>
          </article>
        {/each}
      {:else if stage === "ideation" && !pendingUser}
        <div class="empty">
          <Sparkles size={26} />
          <h2>What do you want to build?</h2>
          <p>
            Describe the idea, constraints, budget, expected behavior, or the
            hardware you already have.
          </p>
        </div>
      {/if}

      {#if pendingUser}
        <article class="message user arriving">
          <div class="avatar">You</div>
          <div class="message-body">{@html renderMarkdown(pendingUser)}</div>
        </article>
        <article class="message assistant-live arriving" aria-live="polite">
          <div class="avatar live-avatar">AI</div>
          <div class="message-body">
            {#if thinkingLabel && !streamingText}
              <div class="thinking-state">
                <span class="thinking-orbit"><i></i></span>
                <span>{thinkingLabel}</span>
                <span class="thinking-dots"><i></i><i></i><i></i></span>
              </div>
            {:else}
              <div class="streamed-copy">
                {@html renderMarkdown(streamingText)}<span class="stream-caret"
                ></span>
              </div>
            {/if}
          </div>
        </article>
      {/if}

      {#if artifact && stage !== "final_review"}
        <article class="artifact-card">
          <div class="artifact-title">
            <FileText size={16} />
            {stage === "component_selection"
              ? "plan.md"
              : stage === "verification"
                ? "verification.md"
                : "final-review.md"}
          </div>
          <div class="markdown">{@html renderMarkdown(artifact)}</div>
        </article>
      {/if}

      {#if stage === "component_selection" && recommendations.length}
        <section class="components">
          <h2>Proposed components</h2>
          <p>
            Select cards to include. You can keep chatting if you want
            alternatives.
          </p>
          <div class="component-grid">
            {#each recommendations as component}
              <article
                class:selected={selected.has(component.id)}
                class="component-card"
              >
                <button
                  class="component-select"
                  onclick={() => toggleComponent(component.id)}
                  aria-pressed={selected.has(component.id)}
                >
                  {#if hasRemoteImage(component)}
                    <img
                      class="component-image"
                      src={`/api/components/${encodeURIComponent(component.id)}/image`}
                      alt={component.name}
                      loading="lazy"
                      referrerpolicy="no-referrer"
                      onerror={hideBrokenImage}
                    />
                  {/if}
                  <div class="component-head">
                    <span class="package"><Package size={17} /></span><strong
                      >{component.name}</strong
                    ><span class="check"
                      >{#if selected.has(component.id)}<Check
                          size={14}
                        />{/if}</span
                    >
                  </div>
                  <small>{component.category} · {component.id}</small>
                  <p>{component.description}</p>
                  <div class="tradeoff">{component.difference}</div>
                  {#if component.library_ids?.length}<div class="chips">
                      {#each component.library_ids as library}<span
                          >{library}</span
                        >{/each}
                    </div>{/if}
                </button>
                {#if component.image_source_url || component.source_url || component.datasheet_url || component.buy_links?.length}
                  <div class="component-links">
                    {#if component.image_source_url || component.source_url}<a
                        href={component.image_source_url ||
                          component.source_url}
                        target="_blank"
                        rel="noreferrer">Source <ExternalLink size={11} /></a
                      >{/if}
                    {#if component.datasheet_url}<a
                        href={component.datasheet_url}
                        target="_blank"
                        rel="noreferrer">Datasheet <ExternalLink size={11} /></a
                      >{/if}
                    {#if component.buy_links?.[0]?.url}<a
                        href={component.buy_links[0].url}
                        target="_blank"
                        rel="noreferrer">Buy <ExternalLink size={11} /></a
                      >{/if}
                  </div>
                {/if}
              </article>
            {/each}
          </div>
          <textarea
            bind:value={notes}
            placeholder="Selection notes, constraints, variants, budget…"
          ></textarea>
        </section>
      {/if}
    </div>

    <footer>
      {#if stage === "final_review" && loading}
        <div class="review-processing" aria-live="polite" aria-busy="true">
          <span class="thinking-orbit"><i></i></span>
          <div>
            <strong>{thinkingLabel || "Writing the final-review response"}</strong>
            <small>Your request was sent and is being processed.</small>
          </div>
          <span class="thinking-dots"><i></i><i></i><i></i></span>
        </div>
      {/if}
      {#if notice}<div class="notice">{notice}</div>{/if}
      {#if stage !== "act"}
        <div class="composer">
          <textarea
            bind:value={input}
            onkeydown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                sendMessage();
              }
            }}
            placeholder={stage === "final_review"
              ? "Ask about the final plan or describe an edit…"
              : "Message the research agent…"}
          ></textarea>
          <button
            class="send"
            onclick={sendMessage}
            disabled={loading || !input.trim()}
            title="Send"><Send size={16} /></button
          >
        </div>
      {/if}
      <button
        class="confirm"
        onclick={() => advance()}
        disabled={loading ||
          ((stage === "component_selection" || stage === "verification") &&
            selected.size === 0)}
      >
        {loading ? "Working…" : stageCopy[stage]?.action}<ChevronRight
          size={15}
        />
      </button>
      <div class="hint">
        Confirm means this stage is authoritative. You can still revise the
        final plan before Act mode.
      </div>
    </footer>
  </main>
</div>

<style>
  .research-view {
    height: 100%;
    min-height: 0;
    max-height: 100%;
    display: grid;
    grid-template-columns: 250px minmax(0, 1fr);
    grid-template-rows: minmax(0, 1fr);
    background: var(--bg-primary);
    color: var(--text-primary);
    overflow: hidden;
  }
  .research-sidebar {
    min-height: 0;
    overflow: hidden;
    border-right: 1px solid var(--border-color);
    background: var(--bg-secondary);
    padding: 18px 12px;
    display: flex;
    flex-direction: column;
    gap: 14px;
  }
  .brand {
    display: flex;
    align-items: center;
    gap: 9px;
    padding: 0 8px;
    font-size: 16px;
    font-weight: 750;
  }
  .new-idea {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 7px;
    padding: 9px;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    background: var(--bg-tertiary);
    color: var(--text-primary);
    cursor: pointer;
  }
  .context-list {
    display: flex;
    flex-direction: column;
    gap: 4px;
    max-height: 36%;
    overflow: auto;
  }
  .context-row {
    display: flex;
    align-items: center;
    border-radius: 7px;
  }
  .context-row.active {
    background: rgba(124, 58, 237, 0.15);
  }
  .context-row button {
    display: flex;
    align-items: center;
    border: 0;
    background: transparent;
    color: var(--text-muted);
    cursor: pointer;
  }
  .context-row.active button {
    color: var(--text-primary);
  }
  .context-open {
    min-width: 0;
    flex: 1;
    justify-content: space-between;
    text-align: left;
    padding: 9px 6px 9px 10px;
  }
  .context-open span {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .context-delete {
    padding: 8px;
    opacity: 0;
  }
  .context-row:hover .context-delete,
  .context-delete:focus {
    opacity: 1;
    color: #ef4444;
  }
  .workflow {
    margin-top: auto;
    display: flex;
    flex-direction: column;
    gap: 12px;
    color: var(--text-dark);
    font-size: 12px;
  }
  .workflow div {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .workflow span {
    width: 20px;
    height: 20px;
    border: 1px solid var(--border-color);
    border-radius: 50%;
    display: grid;
    place-items: center;
    font-size: 10px;
  }
  .workflow .current {
    color: var(--text-primary);
  }
  .workflow .current span {
    border-color: var(--accent-violet);
    background: var(--accent-violet);
    color: white;
  }
  .workflow .done {
    color: var(--text-muted);
  }
  .research-chat {
    min-width: 0;
    min-height: 0;
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: hidden;
  }
  .research-chat > header {
    height: 72px;
    flex: none;
    padding: 0 28px;
    border-bottom: 1px solid var(--border-color);
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .research-chat h1 {
    font-size: 17px;
    margin: 0 0 4px;
  }
  .research-chat header p {
    margin: 0;
    color: var(--text-muted);
    font-size: 12px;
  }
  .stage-pill {
    font-size: 11px;
    padding: 6px 9px;
    border: 1px solid var(--border-color);
    border-radius: 99px;
    color: var(--text-muted);
  }
  .conversation {
    min-height: 0;
    flex: 1 1 auto;
    overflow-y: auto;
    overflow-x: hidden;
    padding: 28px max(28px, calc((100% - 900px) / 2));
    scrollbar-gutter: stable;
  }
  .message {
    display: grid;
    grid-template-columns: 36px 1fr;
    gap: 13px;
    padding: 18px 0;
  }
  .message.user {
    background: rgba(255, 255, 255, 0.018);
  }
  .avatar {
    width: 32px;
    height: 32px;
    border-radius: 9px;
    background: linear-gradient(135deg, #7c3aed, #06b6d4);
    display: grid;
    place-items: center;
    font-size: 10px;
    color: white;
    font-weight: 700;
  }
  .user .avatar {
    background: var(--bg-tertiary);
    color: var(--text-muted);
  }
  .message-body,
  .markdown {
    font-size: 14px;
    line-height: 1.65;
    color: var(--text-primary);
  }
  :global(.message-body h1),
  :global(.markdown h1) {
    font-size: 20px;
  }
  :global(.message-body h2),
  :global(.markdown h2) {
    font-size: 16px;
    margin-top: 22px;
  }
  :global(.message-body code),
  :global(.markdown code) {
    background: var(--bg-tertiary);
    padding: 2px 5px;
    border-radius: 4px;
  }
  :global(.bullet),
  :global(.task) {
    margin: 5px 0;
  }
  .empty {
    text-align: center;
    margin: 12vh auto;
    color: var(--text-muted);
    max-width: 520px;
  }
  .empty h2 {
    color: var(--text-primary);
    font-size: 24px;
    margin: 14px 0 8px;
  }
  .artifact-card {
    margin: 24px 0;
    border: 1px solid var(--border-color);
    border-radius: 12px;
    background: var(--bg-secondary);
    overflow: hidden;
  }
  .artifact-title {
    display: flex;
    gap: 8px;
    align-items: center;
    padding: 12px 16px;
    border-bottom: 1px solid var(--border-color);
    font-size: 12px;
    font-weight: 700;
    color: var(--accent-cyan);
  }
  .artifact-card .markdown {
    padding: 12px 20px 22px;
  }
  .components {
    margin: 28px 0;
  }
  .components > h2 {
    font-size: 18px;
    margin-bottom: 4px;
  }
  .components > p {
    color: var(--text-muted);
    font-size: 13px;
  }
  .component-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 12px;
    margin: 16px 0;
  }
  .component-card {
    overflow: hidden;
    padding: 0 15px 15px;
    text-align: left;
    border: 1px solid var(--border-color);
    border-radius: 10px;
    background: var(--bg-secondary);
    color: var(--text-primary);
    cursor: pointer;
  }
  .component-card:hover,
  .component-card.selected {
    border-color: var(--accent-violet);
    box-shadow: 0 0 0 1px rgba(124, 58, 237, 0.2);
  }
  .component-image {
    display: block;
    width: calc(100% + 30px);
    height: 138px;
    margin: 0 -15px 14px;
    object-fit: contain;
    background: white;
  }
  .component-head {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .package {
    width: 30px;
    height: 30px;
    display: grid;
    place-items: center;
    border-radius: 7px;
    background: rgba(124, 58, 237, 0.12);
    color: var(--accent-violet);
  }
  .component-head .check {
    margin-left: auto;
    width: 20px;
    height: 20px;
    border: 1px solid var(--border-color);
    border-radius: 5px;
    display: grid;
    place-items: center;
  }
  .selected .check {
    background: var(--accent-violet);
    color: white;
  }
  .component-grid small {
    display: block;
    color: var(--text-dark);
    margin: 8px 0;
  }
  .component-grid p {
    font-size: 12px;
    line-height: 1.45;
    color: var(--text-muted);
  }
  .tradeoff {
    font-size: 11px;
    color: var(--accent-cyan);
    margin: 8px 0;
  }
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
  }
  .chips span {
    font-size: 10px;
    padding: 3px 6px;
    border-radius: 99px;
    background: var(--bg-tertiary);
  }
  .component-links {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    margin-top: 10px;
  }
  .component-links a {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    color: var(--accent-cyan);
    font-size: 10px;
    text-decoration: none;
  }
  .components textarea {
    width: 100%;
    box-sizing: border-box;
    min-height: 72px;
    background: var(--bg-secondary);
    color: var(--text-primary);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 10px;
    resize: vertical;
  }
  .research-chat > footer {
    flex: none;
    position: relative;
    z-index: 4;
    padding: 12px max(28px, calc((100% - 900px) / 2)) 16px;
    border-top: 1px solid var(--border-color);
    background: var(--bg-primary);
    box-shadow: 0 -12px 28px rgba(0, 0, 0, 0.14);
  }
  .review-processing {
    display: grid;
    grid-template-columns: 22px minmax(0, 1fr) auto;
    align-items: center;
    gap: 10px;
    margin-bottom: 9px;
    padding: 10px 12px;
    border: 1px solid rgba(124, 58, 237, 0.42);
    border-radius: 9px;
    background: rgba(124, 58, 237, 0.08);
    color: var(--text-primary);
  }
  .review-processing strong,
  .review-processing small {
    display: block;
  }
  .review-processing strong {
    font-size: 12px;
  }
  .review-processing small {
    margin-top: 2px;
    color: var(--text-muted);
    font-size: 10px;
  }
  .composer {
    display: flex;
    gap: 8px;
    border: 1px solid var(--border-color);
    border-radius: 12px;
    background: var(--bg-secondary);
    padding: 7px;
  }
  .composer textarea {
    flex: 1;
    min-height: 42px;
    max-height: 120px;
    resize: none;
    border: 0;
    outline: 0;
    background: transparent;
    color: var(--text-primary);
    padding: 7px;
    font: inherit;
  }
  .send {
    width: 36px;
    height: 36px;
    align-self: flex-end;
    border: 0;
    border-radius: 8px;
    background: var(--accent-violet);
    color: white;
    display: grid;
    place-items: center;
    cursor: pointer;
  }
  .confirm {
    margin-top: 9px;
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    padding: 10px;
    border: 0;
    border-radius: 9px;
    background: linear-gradient(90deg, #7c3aed, #6d28d9);
    color: white;
    font-weight: 650;
    cursor: pointer;
  }
  .confirm:disabled,
  .send:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }
  .hint,
  .notice {
    text-align: center;
    color: var(--text-dark);
    font-size: 10px;
    margin-top: 6px;
  }
  .notice {
    color: var(--accent-cyan);
    font-size: 11px;
  }
  @media (max-width: 760px) {
    .research-view {
      grid-template-columns: 1fr;
    }
    .research-sidebar {
      display: none;
    }
    .conversation,
    .research-chat > footer {
      padding-left: 16px;
      padding-right: 16px;
    }
    .component-grid {
      grid-template-columns: 1fr;
    }
  }
  .component-card {
    padding: 0;
    cursor: default;
  }
  .component-select {
    display: block;
    width: 100%;
    padding: 0 15px 15px;
    text-align: left;
    border: 0;
    background: transparent;
    color: inherit;
    cursor: pointer;
  }
  .component-links {
    padding: 0 15px 12px;
    margin-top: 0;
  }
  .todo-panel {
    flex: 1 1 auto;
    min-height: 0;
    max-height: none;
    overflow: auto;
    border: 1px solid var(--border-color);
    border-radius: 9px;
    padding: 9px;
    background: var(--bg-primary);
  }
  .todo-title {
    font-size: 9px;
    letter-spacing: 0.12em;
    color: var(--text-dark);
    font-weight: 800;
    margin: 0 0 7px;
  }
  .todo-row {
    display: grid;
    grid-template-columns: 18px minmax(0, 1fr);
    gap: 6px;
    align-items: start;
    padding: 5px 0;
    color: var(--text-muted);
  }
  .todo-row span {
    width: 16px;
    height: 16px;
    border: 1px solid var(--border-color);
    border-radius: 50%;
    display: grid;
    place-items: center;
    font-size: 8px;
  }
  .todo-row p {
    margin: 0;
    font-size: 10px;
    line-height: 1.35;
  }
  .todo-row.completed {
    color: #22c55e;
  }
  .todo-row.in_progress {
    color: var(--accent-cyan);
  }
  .todo-row.warning {
    color: #f59e0b;
  }
  .workflow {
    flex: 0 0 auto;
    margin-top: 0;
  }
  @media (max-height: 820px) {
    .research-sidebar {
      padding-top: 12px;
      padding-bottom: 12px;
      gap: 10px;
    }
    .research-chat > header {
      height: 62px;
    }
    .conversation {
      padding-top: 18px;
      padding-bottom: 18px;
    }
    .research-chat > footer {
      padding-top: 8px;
      padding-bottom: 9px;
    }
    .composer textarea {
      min-height: 34px;
      padding-top: 4px;
      padding-bottom: 4px;
    }
    .confirm {
      margin-top: 7px;
      padding: 8px;
    }
    .hint {
      margin-top: 4px;
    }
  }
  .arriving {
    animation: message-arrive 0.28s cubic-bezier(0.2, 0.8, 0.2, 1) both;
  }
  .assistant-live {
    min-height: 74px;
  }
  .live-avatar {
    animation: avatar-breathe 1.8s ease-in-out infinite;
  }
  .thinking-state {
    display: flex;
    align-items: center;
    gap: 9px;
    min-height: 32px;
    color: var(--text-muted);
    font-size: 13px;
    font-style: italic;
  }
  .thinking-orbit {
    position: relative;
    width: 18px;
    height: 18px;
    border: 1px solid rgba(139, 92, 246, 0.32);
    border-radius: 50%;
    animation: orbit-spin 1.35s linear infinite;
  }
  .thinking-orbit i {
    position: absolute;
    left: 6px;
    top: -2px;
    width: 5px;
    height: 5px;
    border-radius: 50%;
    background: var(--accent-violet);
    box-shadow: 0 0 10px var(--accent-violet);
  }
  .thinking-dots {
    display: inline-flex;
    align-items: center;
    gap: 3px;
  }
  .thinking-dots i {
    width: 3px;
    height: 3px;
    border-radius: 50%;
    background: currentColor;
    animation: dot-wave 1.1s ease-in-out infinite;
  }
  .thinking-dots i:nth-child(2) {
    animation-delay: 0.14s;
  }
  .thinking-dots i:nth-child(3) {
    animation-delay: 0.28s;
  }
  .streamed-copy {
    animation: copy-reveal 0.18s ease-out;
  }
  .stream-caret {
    display: inline-block;
    width: 2px;
    height: 1em;
    margin-left: 3px;
    vertical-align: -0.12em;
    border-radius: 2px;
    background: var(--accent-violet);
    animation: caret-blink 0.85s steps(2, end) infinite;
  }
  @keyframes message-arrive {
    from {
      opacity: 0;
      transform: translateY(7px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }
  @keyframes avatar-breathe {
    0%,
    100% {
      box-shadow: 0 0 0 0 rgba(139, 92, 246, 0);
    }
    50% {
      box-shadow: 0 0 0 5px rgba(139, 92, 246, 0.12);
    }
  }
  @keyframes orbit-spin {
    to {
      transform: rotate(360deg);
    }
  }
  @keyframes dot-wave {
    0%,
    60%,
    100% {
      opacity: 0.28;
      transform: translateY(0);
    }
    30% {
      opacity: 1;
      transform: translateY(-3px);
    }
  }
  @keyframes copy-reveal {
    from {
      opacity: 0.35;
    }
    to {
      opacity: 1;
    }
  }
  @keyframes caret-blink {
    50% {
      opacity: 0;
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .arriving,
    .live-avatar,
    .thinking-orbit,
    .thinking-dots i,
    .stream-caret,
    .streamed-copy {
      animation: none;
    }
    .conversation {
      scroll-behavior: auto;
    }
  }
  .phase3-monitor {
    --monitor-surface-start: rgba(8, 15, 28, 0.98);
    --monitor-surface-end: rgba(12, 10, 24, 0.98);
    --monitor-panel: rgba(255, 255, 255, 0.025);
    --monitor-line: rgba(255, 255, 255, 0.06);
    --monitor-track: rgba(255, 255, 255, 0.07);
    --monitor-sheen: rgba(255, 255, 255, 0.65);
    position: relative;
    isolation: isolate;
    overflow: hidden;
    margin: 0 0 24px;
    border: 1px solid rgba(6, 182, 212, 0.28);
    border-radius: 14px;
    padding: 18px;
    color: var(--text-active);
    background: linear-gradient(
      145deg,
      var(--monitor-surface-start),
      var(--monitor-surface-end)
    );
    box-shadow: 0 18px 48px rgba(0, 0, 0, 0.24);
  }
  :global(.light-theme) .phase3-monitor {
    --monitor-surface-start: #fff;
    --monitor-surface-end: #f1f5f9;
    --monitor-panel: rgba(255, 255, 255, 0.72);
    --monitor-line: rgba(100, 116, 139, 0.2);
    --monitor-track: rgba(100, 116, 139, 0.18);
    --monitor-sheen: rgba(255, 255, 255, 0.82);
    border-color: rgba(8, 145, 178, 0.32);
    box-shadow: 0 18px 48px rgba(15, 23, 42, 0.12);
  }
  .monitor-glow {
    position: absolute;
    z-index: -1;
    width: 280px;
    height: 180px;
    right: -90px;
    top: -100px;
    border-radius: 50%;
    background: var(--accent-cyan-muted);
    filter: blur(28px);
  }
  .phase3-monitor.running .monitor-glow {
    animation: monitor-breathe 2.4s ease-in-out infinite;
  }
  .monitor-header,
  .monitor-agent,
  .monitor-progress-head,
  .monitor-clock {
    display: flex;
    align-items: center;
  }
  .monitor-header {
    justify-content: space-between;
    gap: 16px;
  }
  .monitor-agent {
    gap: 11px;
    min-width: 0;
  }
  .monitor-agent h2 {
    margin: 2px 0 0;
    font-size: 15px;
  }
  .monitor-eyebrow {
    display: block;
    color: var(--accent-cyan);
    font-size: 9px;
    line-height: 1;
    letter-spacing: 0.13em;
    font-weight: 850;
  }
  .monitor-orbit {
    width: 38px;
    height: 38px;
    flex: none;
    display: grid;
    place-items: center;
    border-radius: 11px;
    border: 1px solid rgba(6, 182, 212, 0.3);
    color: var(--accent-cyan);
    background: var(--accent-cyan-muted);
    box-shadow: inset 0 0 18px rgba(6, 182, 212, 0.06);
  }
  .monitor-orbit i {
    display: grid;
    place-items: center;
    font-style: normal;
  }
  .running .monitor-orbit i {
    animation: monitor-spin 1.25s linear infinite;
  }
  .monitor-clock {
    gap: 5px;
    color: var(--text-muted);
    font-size: 11px;
    font-variant-numeric: tabular-nums;
  }
  .monitor-progress-head {
    justify-content: space-between;
    gap: 12px;
    margin: 18px 0 7px;
    color: var(--text-muted);
    font-size: 11px;
  }
  .monitor-progress-head span {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .monitor-progress-head strong {
    color: var(--accent-cyan);
    font-variant-numeric: tabular-nums;
  }
  .monitor-progress {
    height: 5px;
    overflow: hidden;
    border-radius: 99px;
    background: var(--monitor-track);
  }
  .monitor-progress > span {
    position: relative;
    display: block;
    height: 100%;
    min-width: 3px;
    border-radius: inherit;
    background: linear-gradient(90deg, #7c3aed, #06b6d4);
    transition: width 0.5s cubic-bezier(0.2, 0.8, 0.2, 1);
  }
  .running .monitor-progress > span::after {
    content: "";
    position: absolute;
    inset: 0;
    width: 45%;
    background: linear-gradient(
      90deg,
      transparent,
      var(--monitor-sheen),
      transparent
    );
    animation: progress-sweep 1.6s ease-in-out infinite;
  }
  .monitor-analysis {
    position: relative;
    margin-top: 14px;
    padding: 12px 42px 12px 13px;
    border: 1px solid var(--monitor-line);
    border-radius: 9px;
    background: var(--monitor-panel);
  }
  .analysis-label {
    font-size: 8px;
    letter-spacing: 0.12em;
    color: var(--text-dark);
    font-weight: 800;
  }
  .monitor-analysis p {
    margin: 4px 0 0;
    color: var(--text-active);
    font-size: 12px;
    line-height: 1.45;
  }
  .analysis-dots {
    position: absolute;
    right: 14px;
    top: 50%;
    display: flex;
    gap: 3px;
  }
  .analysis-dots i {
    width: 4px;
    height: 4px;
    border-radius: 50%;
    background: var(--accent-cyan);
    animation: dot-wave 1.1s ease-in-out infinite;
  }
  .analysis-dots i:nth-child(2) {
    animation-delay: 0.14s;
  }
  .analysis-dots i:nth-child(3) {
    animation-delay: 0.28s;
  }
  .phase-track {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 4px;
    margin-top: 15px;
  }
  .phase-track div {
    position: relative;
    display: flex;
    align-items: center;
    gap: 5px;
    color: var(--text-dark);
    font-size: 9px;
  }
  .phase-track div:not(:last-child)::after {
    content: "";
    position: absolute;
    left: 22px;
    right: 2px;
    top: 7px;
    height: 1px;
    background: var(--border-color);
  }
  .phase-track span {
    z-index: 1;
    width: 15px;
    height: 15px;
    display: grid;
    place-items: center;
    border: 1px solid var(--border-color);
    border-radius: 50%;
    background: var(--bg-secondary);
    font-size: 7px;
  }
  .phase-track .done {
    color: #22c55e;
  }
  .phase-track .active {
    color: var(--accent-cyan);
  }
  .phase-track .active span {
    border-color: var(--accent-cyan);
    box-shadow: 0 0 0 4px rgba(6, 182, 212, 0.1);
    animation: phase-pulse 1.4s ease-in-out infinite;
  }
  .activity-log {
    margin-top: 15px;
    padding-top: 11px;
    border-top: 1px solid var(--monitor-line);
  }
  .activity-log-title {
    margin-bottom: 7px;
    color: var(--text-dark);
    font-size: 8px;
    letter-spacing: 0.12em;
    font-weight: 800;
  }
  .activity-entry {
    display: grid;
    grid-template-columns: 8px 58px minmax(0, 1fr);
    gap: 7px;
    align-items: start;
    padding: 3px 0;
    color: var(--text-dark);
    font-size: 9px;
  }
  .activity-entry.latest {
    color: var(--text-muted);
  }
  .activity-node {
    width: 5px;
    height: 5px;
    margin-top: 4px;
    border-radius: 50%;
    background: currentColor;
  }
  .activity-entry.latest .activity-node {
    background: var(--accent-cyan);
    box-shadow: 0 0 7px var(--accent-cyan);
  }
  .activity-entry time {
    font-variant-numeric: tabular-nums;
  }
  .activity-entry strong {
    display: block;
    color: inherit;
    font-weight: 650;
  }
  .activity-entry small {
    display: block;
    margin-top: 1px;
    color: var(--text-dark);
  }
  .resume-phase3 {
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 7px;
    margin-top: 14px;
    padding: 9px;
    border: 1px solid rgba(124, 58, 237, 0.4);
    border-radius: 8px;
    background: var(--accent-violet-muted);
    color: var(--text-active);
    cursor: pointer;
  }
  .phase3-monitor.error {
    border-color: rgba(239, 68, 68, 0.35);
  }
  .phase3-monitor.error .monitor-eyebrow {
    color: #ef4444;
  }
  .todo-row.in_progress span {
    border-color: var(--accent-cyan);
    background: rgba(6, 182, 212, 0.1);
    box-shadow: 0 0 0 0 rgba(6, 182, 212, 0.22);
    animation: todo-pulse 1.5s ease-out infinite;
  }
  .todo-row.in_progress p {
    animation: todo-text 1.8s ease-in-out infinite;
  }
  @keyframes monitor-spin {
    to {
      transform: rotate(360deg);
    }
  }
  @keyframes monitor-breathe {
    0%,
    100% {
      opacity: 0.5;
      transform: scale(0.9);
    }
    50% {
      opacity: 1;
      transform: scale(1.12);
    }
  }
  @keyframes progress-sweep {
    from {
      transform: translateX(-120%);
    }
    to {
      transform: translateX(320%);
    }
  }
  @keyframes phase-pulse {
    50% {
      box-shadow: 0 0 0 7px rgba(6, 182, 212, 0);
    }
  }
  @keyframes todo-pulse {
    70% {
      box-shadow: 0 0 0 7px rgba(6, 182, 212, 0);
    }
    100% {
      box-shadow: 0 0 0 0 rgba(6, 182, 212, 0);
    }
  }
  @keyframes todo-text {
    50% {
      color: #a5f3fc;
    }
  }
  @media (max-width: 640px) {
    .monitor-header {
      align-items: flex-start;
    }
    .monitor-clock {
      display: none;
    }
    .phase-track small {
      display: none;
    }
    .phase-track div {
      justify-content: center;
    }
    .phase-track div:not(:last-child)::after {
      left: 55%;
      right: -45%;
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .monitor-glow,
    .monitor-orbit i,
    .monitor-progress > span::after,
    .analysis-dots i,
    .phase-track .active span,
    .todo-row.in_progress span,
    .todo-row.in_progress p {
      animation: none;
    }
  }
  /* Phase-3 readability and connector layout overrides. */
  @media (min-width: 761px) {
    .research-view {
      grid-template-columns: 290px minmax(0, 1fr);
    }
  }
  .research-chat h1 {
    font-size: 20px;
  }
  .research-chat header p {
    font-size: 14px;
  }
  .stage-pill {
    font-size: 12px;
  }
  .workflow {
    font-size: 13px;
  }
  .todo-title {
    font-size: 10px;
  }
  .todo-row {
    grid-template-columns: 22px minmax(0, 1fr);
    gap: 8px;
    padding: 6px 0;
  }
  .todo-row span {
    width: 19px;
    height: 19px;
    font-size: 9px;
  }
  .todo-row p {
    font-size: 11.5px;
    line-height: 1.45;
  }
  .phase3-monitor {
    padding: 22px;
  }
  .monitor-agent h2 {
    font-size: 18px;
    line-height: 1.3;
  }
  .monitor-eyebrow {
    font-size: 11px;
    line-height: 1.2;
  }
  .monitor-clock {
    font-size: 13px;
  }
  .monitor-progress-head {
    font-size: 13px;
    margin-top: 20px;
  }
  .monitor-progress {
    height: 7px;
  }
  .analysis-label {
    font-size: 10px;
  }
  .monitor-analysis {
    padding: 15px 48px 15px 16px;
  }
  .monitor-analysis p {
    font-size: 14.5px;
    line-height: 1.55;
  }
  .phase-track {
    gap: 8px;
    margin: 20px 0 2px;
  }
  .phase-track div {
    position: relative;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: flex-start;
    gap: 8px;
    min-width: 0;
    color: var(--text-muted);
    font-size: 12px;
    text-align: center;
  }
  .phase-track div:not(:last-child)::after {
    z-index: 0;
    left: calc(50% + 15px);
    right: calc(-50% + 15px);
    top: 11px;
    height: 2px;
    background: var(--border-color);
  }
  .phase-track span {
    z-index: 1;
    width: 23px;
    height: 23px;
    flex: none;
    background: var(--bg-secondary);
    font-size: 10px;
  }
  .phase-track small {
    position: relative;
    z-index: 1;
    display: block;
    min-height: 18px;
    color: inherit;
    font-size: 12px;
    line-height: 1.35;
    white-space: nowrap;
  }
  .activity-log {
    margin-top: 20px;
    padding-top: 15px;
  }
  .activity-log-title {
    font-size: 10px;
    margin-bottom: 10px;
  }
  .activity-entry {
    grid-template-columns: 10px 82px minmax(0, 1fr);
    gap: 10px;
    padding: 5px 0;
    font-size: 12px;
    line-height: 1.35;
  }
  .activity-node {
    width: 7px;
    height: 7px;
    margin-top: 5px;
  }
  .activity-entry small {
    font-size: 11px;
    margin-top: 2px;
  }
  .resume-phase3 {
    padding: 12px;
    font-size: 14px;
  }
  .phase3-monitor.warning {
    border-color: rgba(245, 158, 11, 0.42);
  }
  @media (max-width: 640px) {
    .phase-track {
      gap: 2px;
    }
    .phase-track small {
      display: block;
      font-size: 10px;
      white-space: normal;
    }
    .phase-track div:not(:last-child)::after {
      left: calc(50% + 13px);
      right: calc(-50% + 13px);
      top: 11px;
    }
  }
</style>
