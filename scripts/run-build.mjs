#!/usr/bin/env node
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawn, spawnSync } from "node:child_process";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const backendDir = resolve(repoRoot, "backend");
const isWindows = process.platform === "win32";
const backendHost = process.env.BACKEND_HOST || "127.0.0.1";
const backendPort = process.env.BACKEND_PORT || "62018";

const children = new Set();
let shuttingDown = false;

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

function prefixStream(stream, name) {
  let pending = "";

  stream.on("data", (chunk) => {
    pending += chunk.toString();
    const lines = pending.split(/\r?\n/);
    pending = lines.pop() || "";

    for (const line of lines) {
      if (line.length > 0) {
        process.stdout.write(`[${name}] ${line}\n`);
      }
    }
  });

  stream.on("end", () => {
    if (pending.length > 0) {
      process.stdout.write(`[${name}] ${pending}\n`);
    }
  });
}

function startProcess(name, command, args, cwd, extraEnv = {}) {
  const env = { ...process.env, ...extraEnv };
  if (!("NO_COLOR" in env)) {
    env.FORCE_COLOR = env.FORCE_COLOR || "1";
  }

  const child = spawn(command, args, {
    cwd,
    detached: !isWindows,
    env,
    shell: false,
    stdio: ["ignore", "pipe", "pipe"],
  });

  children.add(child);
  prefixStream(child.stdout, name);
  prefixStream(child.stderr, name);

  child.on("error", (error) => {
    console.error(`[${name}] failed to start: ${error.message}`);
    stopAll(1);
  });

  child.on("exit", (code, signal) => {
    children.delete(child);

    if (!shuttingDown) {
      const detail = signal ? `signal ${signal}` : `exit code ${code}`;
      console.error(`[${name}] stopped with ${detail}`);
      stopAll(code || 1);
    }
  });

  return child;
}

function stopChild(child) {
  if (!child.pid || child.exitCode !== null) {
    return;
  }

  try {
    if (isWindows) {
      spawn("taskkill", ["/pid", String(child.pid), "/T", "/F"], {
        stdio: "ignore",
      });
    } else {
      process.kill(-child.pid, "SIGTERM");
    }
  } catch {
    try {
      child.kill("SIGTERM");
    } catch {
      // The process may have already exited.
    }
  }
}

function stopAll(exitCode = 0) {
  if (shuttingDown) {
    return;
  }

  shuttingDown = true;

  for (const child of children) {
    stopChild(child);
  }

  setTimeout(() => {
    for (const child of children) {
      if (!isWindows && child.pid && child.exitCode === null) {
        try {
          process.kill(-child.pid, "SIGKILL");
        } catch {
          // The process may have already exited.
        }
      }
    }
    process.exit(exitCode);
  }, 1500).unref();
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
console.log("Press Ctrl+C to stop.");

startProcess("backend", backend.command, backend.args, backendDir);

process.on("SIGINT", () => stopAll(0));
process.on("SIGTERM", () => stopAll(0));
