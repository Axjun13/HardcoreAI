<script lang="ts">
  let {
    size = "md",
    variant = "inline",
    label = undefined,
    messages = undefined,
    interval = 1600,
  }: {
    size?: "sm" | "md" | "lg";
    variant?: "inline" | "card" | "page";
    label?: string;
    messages?: string[];
    interval?: number;
  } = $props();

  const scale = { sm: 16, md: 22, lg: 34 };
  let index = $state(0);
  let visible = $state(true);
  $effect(() => {
    if (!messages || messages.length < 2) return;
    const id = window.setInterval(() => {
      visible = false;
      window.setTimeout(() => { index = (index + 1) % messages!.length; visible = true; }, 150);
    }, interval);
    return () => window.clearInterval(id);
  });
</script>

<div class="loader loader--{variant} loader--{size}" role="status" aria-live="polite">
  <div class="mark" style="width:{scale[size]}px; height:{scale[size] * 1.27}px" aria-hidden="true">
    <div class="piece p1"></div><div class="piece p2"></div><div class="piece p3"></div><div class="piece p4"></div><div class="spark"></div>
  </div>
  {#if label || messages}
    <div class="text">
      {#if label}<p class="label">{label}</p>{/if}
      {#if messages}<p class="msg" style="opacity:{visible ? 1 : 0}">{messages[index]}</p>{/if}
      {#if variant !== "inline"}<div class="rail"></div>{/if}
    </div>
  {/if}
</div>

<style>
  .loader{display:flex;align-items:center;gap:10px;font-family:var(--font-sans,ui-sans-serif,sans-serif)}.loader--sm{gap:8px}.loader--lg{gap:16px}.loader--card{width:300px;padding:16px 18px;background:#0f0f16;border:1px solid #1f1f2b;border-radius:10px}.loader--page{flex-direction:column;justify-content:center;padding:60px 20px}.mark{position:relative;flex:0 0 auto}.piece{position:absolute;background:linear-gradient(155deg,#8b7fd6,#241b4e);opacity:0}.p1{width:30%;height:30%;border-radius:50%;top:0;left:0;animation:dropIn 1.8s cubic-bezier(.2,.9,.2,1) infinite}.p2{width:30%;height:100%;border-radius:5px;top:0;right:0;animation:dropIn 1.8s cubic-bezier(.2,.9,.2,1) infinite .08s}.p3{width:30%;height:70%;border-radius:5px;bottom:0;left:0;animation:dropIn 1.8s cubic-bezier(.2,.9,.2,1) infinite .04s}.p4{width:30%;height:30%;border-radius:50%;bottom:0;right:0;animation:dropIn 1.8s cubic-bezier(.2,.9,.2,1) infinite .12s}.spark{position:absolute;left:50%;top:60%;width:14%;height:14%;margin:-7% 0 0 -7%;border-radius:50%;background:#d9a441;opacity:0;animation:spark 1.8s ease-in-out infinite}@keyframes dropIn{0%{opacity:0;transform:translateY(-3px) scale(.85)}22%,78%{opacity:1;transform:translateY(0) scale(1)}92%{opacity:0;transform:translateY(2px) scale(.94)}100%{opacity:0}}@keyframes spark{0%,28%,100%{opacity:0;box-shadow:0 0 0 #d9a441}36%{opacity:1;box-shadow:0 0 8px 2px #d9a441}46%{opacity:0}}.text{flex:1;min-width:0}.label{margin:0 0 4px;color:#f2f1f8;font-size:13.5px;font-weight:600}.loader--sm .label{font-size:12px}.msg{margin:0;color:#6e6a7c;font:11px var(--font-mono,ui-monospace,monospace);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;transition:opacity .18s ease}.rail{height:2px;margin-top:8px;background:#1f1f2b;border-radius:2px;overflow:hidden}.rail::after{content:"";display:block;width:40%;height:100%;background:linear-gradient(90deg,transparent,#8b7fd6,transparent);animation:sweep 1.3s ease-in-out infinite}@keyframes sweep{from{transform:translateX(-100%)}to{transform:translateX(350%)}}@media(prefers-reduced-motion:reduce){.piece,.spark,.rail::after{animation:none!important;opacity:1!important}}
</style>
