<script lang="ts">
  import { X, MessageSquare, Check } from "lucide-svelte";
  import { api } from "../api";

  export let onClose: () => void;
  let feedback = "";
  let willingToPay: boolean | null = null;
  let saving = false;
  let saved = false;
  let error = "";

  async function submit() {
    if (willingToPay === null) { error = "Please choose Yes or No."; return; }
    saving = true; error = "";
    try {
      await api.saveProjectLimitFeedback(feedback, willingToPay);
      saved = true;
      setTimeout(onClose, 900);
    } catch (e) { error = e instanceof Error ? e.message : "Unable to save feedback."; }
    finally { saving = false; }
  }
</script>

<div class="limit-backdrop" role="presentation">
  <section class="limit-modal" role="dialog" aria-modal="true" aria-labelledby="limit-title">
    <button class="limit-close" type="button" aria-label="Close" onclick={onClose}><X size={17} /></button>
    <div class="limit-icon"><MessageSquare size={20} /></div>
    <p class="limit-eyebrow">FREE PLAN LIMIT</p>
    <h2 id="limit-title">You’ve crossed the 2-project limit</h2>
    <p class="limit-copy">You’ve reached the two-project free limit. Help us shape HardcoreAI by sharing your feedback.</p>
    <label class="question">Would you be willing to pay for HardcoreAI?</label>
    <div class="choice-row">
      <button type="button" class:chosen={willingToPay === true} onclick={() => willingToPay = true}>Yes</button>
      <button type="button" class:chosen={willingToPay === false} onclick={() => willingToPay = false}>No</button>
    </div>
    <label class="feedback-label">Anything else you’d like us to know? <span>Optional</span>
      <textarea bind:value={feedback} maxlength="2000" rows="4" placeholder="Tell us what would make HardcoreAI worth paying for..."></textarea>
    </label>
    {#if error}<p class="limit-error">{error}</p>{/if}
    <button class="submit-feedback" type="button" disabled={saving || saved} onclick={submit}>
      {#if saved}<Check size={16} /> Feedback saved{:else}{saving ? "Saving..." : "Send feedback"}{/if}
    </button>
  </section>
</div>

<style>
  .limit-backdrop{position:fixed;inset:0;z-index:1200;display:grid;place-items:center;padding:20px;background:rgba(3,4,10,.76);backdrop-filter:blur(5px);animation:limit-fade .2s ease-out}.limit-modal{position:relative;width:min(450px,100%);padding:30px;background:var(--bg-secondary,#11111a);border:1px solid rgba(139,92,246,.45);border-radius:14px;box-shadow:0 25px 80px #000b;color:var(--text-active,#f8fafc);animation:limit-pop .25s ease-out}.limit-close{position:absolute;top:14px;right:14px;display:grid;place-items:center;padding:6px;border:1px solid var(--border-color,#292938);border-radius:6px;background:transparent;color:var(--text-muted,#94a3b8);cursor:pointer}.limit-icon{display:grid;place-items:center;width:38px;height:38px;margin-bottom:15px;border-radius:10px;background:rgba(139,92,246,.14);color:var(--accent-violet-hover,#a78bfa)}.limit-eyebrow{margin:0 0 5px;color:var(--accent-violet-hover,#a78bfa);font-size:10px;font-weight:700;letter-spacing:.12em}.limit-modal h2{margin:0 0 10px;font-size:21px}.limit-copy{margin:0 0 22px;color:var(--text-muted,#a1a1aa);line-height:1.5}.question,.feedback-label{display:grid;gap:8px;font-size:13px;font-weight:600}.choice-row{display:flex;gap:9px;margin:10px 0 18px}.choice-row button{flex:1;padding:10px;border:1px solid var(--border-color,#292938);border-radius:7px;background:var(--bg-tertiary,#191923);color:var(--text-muted,#cbd5e1);cursor:pointer}.choice-row button.chosen{border-color:var(--accent-violet,#8b5cf6);background:rgba(139,92,246,.16);color:var(--text-active,#fff)}.feedback-label span{color:var(--text-muted,#94a3b8);font-weight:400}.feedback-label textarea{width:100%;resize:vertical;padding:10px;border:1px solid var(--border-color,#292938);border-radius:7px;background:var(--bg-tertiary,#191923);color:var(--text-active,#fff);font:inherit}.submit-feedback{display:flex;align-items:center;justify-content:center;gap:7px;width:100%;margin-top:17px;padding:11px;border:0;border-radius:7px;background:var(--accent-violet,#7c3aed);color:#fff;font-weight:700;cursor:pointer}.submit-feedback:disabled{opacity:.6;cursor:default}.limit-error{margin:10px 0 0;color:#fca5a5;font-size:12px}@keyframes limit-fade{from{opacity:0}to{opacity:1}}@keyframes limit-pop{from{transform:translateY(8px) scale(.98);opacity:0}to{transform:none;opacity:1}}
</style>
