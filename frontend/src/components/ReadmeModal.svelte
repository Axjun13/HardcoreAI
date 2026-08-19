<script lang="ts">
  import { X, BookOpen } from "lucide-svelte";

  export let onClose: () => void;
</script>

<div class="readme-backdrop" role="presentation">
  <section class="readme-modal" role="dialog" aria-modal="true" aria-labelledby="readme-title">
    <header class="readme-header">
      <div class="readme-heading">
        <BookOpen size={19} />
        <div>
          <p class="readme-eyebrow">HARDCOREAI</p>
          <h2 id="readme-title">Getting Started</h2>
        </div>
      </div>
      <button type="button" class="readme-close" onclick={onClose} aria-label="Close Getting Started" title="Close">
        <X size={18} />
      </button>
    </header>

    <div class="readme-content">
      <p class="readme-lead">Welcome to HardcoreAI, your AI-powered firmware engineering platform.</p>
      <p>HardcoreAI understands your hardware, documentation, and project requirements before generating firmware—helping you move from board selection → research → firmware → hardware.</p>

      <h3>1. Select Your Board</h3>
      <p>Start by selecting the development board or microcontroller you are working with.</p>
      <p>Choose your:</p>
      <ul><li>Development board</li><li>Microcontroller</li><li>Required peripherals</li><li>Hardware configuration</li></ul>
      <p>Make sure the selected board matches the actual hardware you are using.</p>

      <h3>2. Research Your Project</h3>
      <p>Before generating firmware, use Research Mode. Tell HardcoreAI what you want to build and provide relevant project information, such as:</p>
      <ul><li>Project requirements</li><li>Datasheets and reference manuals</li><li>Schematics and pin requirements</li><li>Sensor/module documentation</li><li>Existing firmware</li></ul>
      <p>HardcoreAI analyzes pin mappings, clocks, peripherals, registers, dependencies, and hardware constraints. Review the research before generating firmware.</p>
      <div class="readme-example"><strong>Example</strong><br />“I want to interface an MPU6050 over I2C1 and send the sensor data over USART2. Research the required hardware configuration and identify the relevant pins, clocks and peripherals.”</div>

      <h3>3. Generate Firmware</h3>
      <p>Once research is complete, ask HardcoreAI to generate firmware. Specify required functionality, peripheral configuration, protocols, sensors, interrupts, timing requirements, and existing code constraints.</p>

      <h3>4. Build &amp; Check</h3>
      <p>Build the generated firmware before flashing. Check compilation errors, warnings, dependencies, pin and clock configuration, peripheral conflicts, and register problems. If the build fails, provide the error output to HardcoreAI so it can identify the root cause.</p>

      <h3>5. Flash Your Hardware</h3>
      <p>Once the firmware builds successfully, connect your board, select the programming/debugging interface, flash it, reset the board, and test the expected behavior.</p>
      <p class="readme-flow">Generate → Build → Flash → Test</p>

      <h3>6. Debug &amp; Iterate</h3>
      <p>If the firmware does not behave as expected, tell HardcoreAI what happened. It can investigate across Firmware → Hardware Configuration → Peripheral Configuration → Documentation. Then repeat: <strong>Build → Flash → Test</strong>.</p>

      <h3>Recommended HardcoreAI Workflow</h3>
      <p class="readme-workflow">Select Board → Define Project → Research → Review Hardware Configuration → Generate Firmware → Build &amp; Check → Flash → Test on Hardware → Debug &amp; Iterate</p>

      <div class="readme-golden"><strong>The Golden Rule</strong><br />Research first. Generate second. Flash last.</div>
      <p>HardcoreAI connects the entire workflow: Hardware → Documentation → Reasoning → Firmware → Build → Hardware Testing → Debugging.</p>
    </div>
  </section>
</div>

<style>
  .readme-backdrop{position:fixed;inset:0;z-index:1100;display:flex;justify-content:flex-end;background:rgba(4,5,12,.42);backdrop-filter:blur(2px);animation:readme-fade-in .25s ease-out}
  .readme-modal{width:min(52vw,760px);height:100%;display:flex;flex-direction:column;background:var(--bg-secondary,#11111a);border-left:1px solid rgba(139,92,246,.5);box-shadow:-18px 0 70px #000b;color:var(--text-active,#f8fafc);overflow:hidden;animation:readme-slide-in .32s cubic-bezier(.22,.8,.25,1)}
  .readme-header{display:flex;align-items:center;justify-content:space-between;padding:18px 22px;border-bottom:1px solid var(--border-color,#292938);background:rgba(139,92,246,.08)}
  .readme-heading{display:flex;align-items:center;gap:11px;color:var(--accent-violet-hover,#a78bfa)}
  .readme-eyebrow{margin:0 0 2px;font-size:10px;letter-spacing:.12em;font-weight:700}.readme-header h2{margin:0;font-size:21px;color:var(--text-active,#f8fafc)}
  .readme-close{display:grid;place-items:center;padding:7px;border:1px solid var(--border-color,#292938);border-radius:6px;background:transparent;color:var(--text-muted,#94a3b8);cursor:pointer}.readme-close:hover{color:var(--text-active,#f8fafc);border-color:var(--accent-violet,#8b5cf6)}
  .readme-content{overflow:auto;padding:24px 28px 30px;line-height:1.58;color:var(--text-muted,#cbd5e1);font-size:13px}.readme-content p{margin:0 0 12px}.readme-lead{font-size:15px;color:var(--text-active,#f8fafc)}.readme-content h3{margin:23px 0 8px;color:var(--text-active,#f8fafc);font-size:15px}.readme-content ul{margin:0 0 12px;padding-left:22px}.readme-example,.readme-golden{margin:14px 0;padding:12px 14px;border-left:3px solid var(--accent-violet,#8b5cf6);background:var(--accent-violet-muted,rgba(139,92,246,.08));border-radius:0 6px 6px 0}.readme-flow{color:var(--accent-cyan,#06b6d4);font-weight:700}.readme-workflow{color:var(--accent-violet-hover,#a78bfa);font-weight:600}.readme-golden{color:var(--text-active,#f8fafc);border-left-color:var(--accent-cyan,#06b6d4)}
  @keyframes readme-slide-in{from{transform:translateX(100%);opacity:.65}to{transform:translateX(0);opacity:1}}
  @keyframes readme-fade-in{from{opacity:0}to{opacity:1}}
  @media(max-width:640px){.readme-modal{width:100%}.readme-content{padding:20px 18px 24px}.readme-header{padding:15px 17px}}
</style>
