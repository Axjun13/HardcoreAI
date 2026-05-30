#!/usr/bin/env node
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const backendDir = resolve(repoRoot, "backend");
const isWindows = process.platform === "win32";
const backendHost = process.env.BACKEND_HOST || "127.0.0.1";
const backendPort = process.env.BACKEND_PORT || "62018";

function commandExists(command) {
  const result = spawnSync(command, ["--version"], {
    stdio: "ignore",
    shell: false,
  });
  return result.status === 0;
}

function backendPython() {
  const venvPython = isWindows
    ? resolve(backendDir, ".venv", "Scripts", "python.exe")
    : resolve(backendDir, ".venv", "bin", "python");

  if (existsSync(venvPython)) {
    return venvPython;
  }

  return isWindows ? "python" : "python3";
}

function backendCommand() {
  const uvCommand = isWindows ? "uv.exe" : "uv";

  if (commandExists(uvCommand)) {
    return {
      command: uvCommand,
      args: [
        "run",
        "uvicorn",
        "main:app",
        "--host",
        backendHost,
        "--port",
        backendPort,
      ],
    };
  }

  return {
    command: backendPython(),
    args: [
      "-m",
      "uvicorn",
      "main:app",
      "--host",
      backendHost,
      "--port",
      backendPort,
    ],
  };
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
    process.exit(result.status || 1);
  }
}

if (process.argv.includes("--help") || process.argv.includes("-h")) {
  console.log(`Build and run the single FastAPI-served app.

Usage:
  node scripts/run-build.mjs
  node scripts/run-build.mjs --skip-build

Environment:
  BACKEND_HOST  Backend bind host, default 127.0.0.1
  BACKEND_PORT  Backend bind port, default 62018`);
  process.exit(0);
}

if (!process.argv.includes("--skip-build")) {
  runStep("build", process.execPath, [resolve(repoRoot, "scripts", "build.mjs")], repoRoot);
}

const backend = backendCommand();

console.log(`\nServing single app at http://${backendHost}:${backendPort}`);
runStep("backend", backend.command, backend.args, backendDir);
