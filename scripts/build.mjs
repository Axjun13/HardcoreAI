#!/usr/bin/env node
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const backendDir = resolve(repoRoot, "backend");
const frontendDir = resolve(repoRoot, "frontend");
const isWindows = process.platform === "win32";
const npmCommand = isWindows ? "npm.cmd" : "npm";
const backendSources = [
  "main.py",
  "api",
  "services",
  "schemas",
  "db",
  "core",
  "agent",
  "llm",
  "rag",
];

function backendPython() {
  const venvPython = isWindows
    ? resolve(backendDir, ".venv", "Scripts", "python.exe")
    : resolve(backendDir, ".venv", "bin", "python");

  if (existsSync(venvPython)) {
    return venvPython;
  }

  return isWindows ? "python" : "python3";
}

function runStep(name, command, args, cwd) {
  console.log(`\n[${name}] ${command} ${args.join(" ")}`);

  const result = spawnSync(command, args, {
    cwd,
    shell: false,
    stdio: "inherit",
  });

  if (result.error) {
    console.error(`[${name}] failed to start: ${result.error.message}`);
    process.exit(1);
  }

  if (result.status !== 0) {
    console.error(`[${name}] failed with exit code ${result.status}`);
    process.exit(result.status || 1);
  }
}

if (process.argv.includes("--help") || process.argv.includes("-h")) {
  console.log(`Build HardcoreAI as a single FastAPI-served web app.

Usage:
  node scripts/build.mjs

Output:
  frontend/dist is served by backend/main.py in production.`);
  process.exit(0);
}

runStep("frontend", npmCommand, ["run", "build"], frontendDir);
runStep(
  "backend",
  backendPython(),
  ["-m", "compileall", "-q", ...backendSources],
  backendDir,
);

console.log("\nSingle app build is ready.");
console.log("Run it with:");
console.log("  node scripts/run-build.mjs --skip-build");
