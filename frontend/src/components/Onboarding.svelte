<script lang="ts">
  import { api } from "../api";

  export let onComplete: () => void;
  export let onDismiss: () => void;

  const roles = ["Student", "Hobbyist / Maker", "Embedded Engineer", "Firmware Engineer", "Hardware Engineer", "Researcher", "Startup Founder", "Product / Engineering", "Other"];
  const useCases = ["Firmware Development", "Hardware Prototyping", "PCB / Electronics Development", "Debugging", "Research", "Learning", "Product Development", "Other"];
  const companySizes = ["Individual", "2-10", "11-50", "51-200", "200+"];
  const referralSources = ["LinkedIn", "Friend / Colleague", "University", "GitHub", "Search", "Event", "Other"];

  let company_name = "", phone_number = "", role = "", about = "", primary_use_case = "", company_size = "", referral_source = "";
  let saving = false, error = "";

  async function submit() {
    error = "";
    if (!role || !primary_use_case) {
      error = "Please select your role and primary use case.";
      return;
    }
    saving = true;
    try {
      await api.saveOnboarding({
        company_name, phone_number, role, about, primary_use_case,
        company_size: company_size || null,
        referral_source: referral_source || null,
      });
      onComplete();
    } catch (err) {
      error = err instanceof Error ? err.message : "Unable to save your details.";
    } finally {
      saving = false;
    }
  }
</script>

<div class="onboarding-backdrop" role="presentation">
  <div class="onboarding-card" role="dialog" aria-modal="true" aria-labelledby="onboarding-title">
    <p class="eyebrow">WELCOME TO HARDCORE AI</p>
    <h2 id="onboarding-title">Tell us a little about yourself</h2>
    <p class="intro">This helps us understand how people are using Hardcore AI.</p>
    <form onsubmit={(event) => { event.preventDefault(); submit(); }}>
      <label>Company / Organization <span>Optional</span><input bind:value={company_name} maxlength="160" autocomplete="organization" /></label>
      <label>Phone number <span>Optional</span><input bind:value={phone_number} maxlength="32" type="tel" autocomplete="tel" placeholder="+1 555 123 4567" /></label>
      <div class="two-column">
        <label>Role <select bind:value={role} required><option value="" disabled>Select a role</option>{#each roles as item}<option value={item}>{item}</option>{/each}</select></label>
        <label>Primary use case <select bind:value={primary_use_case} required><option value="" disabled>Select a use case</option>{#each useCases as item}<option value={item}>{item}</option>{/each}</select></label>
      </div>
      <label>What do you do? <span>Optional</span><textarea bind:value={about} maxlength="600" rows="2" placeholder="A short description of what you work on"></textarea></label>
      <div class="two-column">
        <label>Company size <span>Optional</span><select bind:value={company_size}><option value="">Not provided</option>{#each companySizes as item}<option value={item}>{item}</option>{/each}</select></label>
        <label>How did you hear about us? <span>Optional</span><select bind:value={referral_source}><option value="">Not provided</option>{#each referralSources as item}<option value={item}>{item}</option>{/each}</select></label>
      </div>
      {#if error}<p class="error" role="alert">{error}</p>{/if}
      <footer><button type="button" class="secondary" onclick={onDismiss}>Not now</button><button type="submit" disabled={saving}>{saving ? "Saving?" : "Continue"}</button></footer>
    </form>
  </div>
</div>

<style>
  .onboarding-backdrop{position:fixed;inset:0;z-index:1000;display:grid;place-items:center;padding:18px;background:rgba(4,5,12,.72);backdrop-filter:blur(5px)}
  .onboarding-card{width:min(620px,100%);box-sizing:border-box;padding:26px;background:var(--bg-secondary,#11111a);border:1px solid var(--border-color,#292938);border-radius:12px;color:var(--text-bright,#f4f4f5);box-shadow:0 20px 70px #0008}
  .eyebrow{margin:0;color:var(--accent-violet,#a78bfa);font-size:11px;font-weight:700;letter-spacing:.1em}.onboarding-card h2{margin:7px 0;font-size:22px}.intro{margin:0 0 18px;color:var(--text-muted,#a1a1aa)}form{display:grid;gap:13px}label{display:grid;gap:6px;font-size:12px;font-weight:600}label span{color:var(--text-muted,#a1a1aa);font-weight:400}input,select,textarea,button{font:inherit;color:inherit;background:var(--bg-tertiary,#191923);border:1px solid var(--border-color,#292938);border-radius:6px;padding:9px 10px}textarea{resize:vertical}.two-column{display:grid;grid-template-columns:1fr 1fr;gap:12px}footer{display:flex;justify-content:flex-end;gap:9px;margin-top:3px}button{cursor:pointer}button:not(.secondary){background:var(--accent-violet,#7c3aed);border-color:transparent;font-weight:700}button:disabled{opacity:.55;cursor:default}.secondary{background:transparent}.error{margin:0;color:#fca5a5}@media(max-width:560px){.onboarding-card{padding:20px}.two-column{grid-template-columns:1fr}footer{justify-content:stretch}footer button{flex:1}}
</style>
