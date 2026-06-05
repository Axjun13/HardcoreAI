#!/usr/bin/env node
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawn, spawnSync } from "node:child_process";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const backendDir = resolve(repoRoot, "backend");
const frontendDir = resolve(repoRoot, "frontend");
const isWindows = process.platform === "win32";

const backendHost = process.env.BACKEND_HOST || "127.0.0.1";
const backendPort = process.env.BACKEND_PORT || "32018";
const emulatorHost = process.env.EMULATOR_HOST || "127.0.0.1";
const emulatorPort = process.env.EMULATOR_PORT || "32017";
const npmCommand = isWindows ? "npm.cmd" : "npm";

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
        "--reload",
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
      "--reload",
      "--host",
      backendHost,
      "--port",
      backendPort,
    ],
  };
}

function emulatorCommand() {
  const uvCommand = isWindows ? "uv.exe" : "uv";

  if (commandExists(uvCommand)) {
    return {
      command: uvCommand,
      args: ["run", "python", "-m", "emulator.app"],
    };
  }

  return {
    command: backendPython(),
    args: ["-m", "emulator.app"],
  };
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
    shell: isWindows,
    stdio: ["ignore", "pipe", "pipe"],
  });

  children.add(child);
  prefixStream(child.stdout, name);
  prefixStream(child.stderr, name);

  child.on("error", (error) => {
    console.error(`[${name}] Failed to start: ${error.message}`);
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

function printHelp() {
  console.log(`Run HardcoreAI backend and frontend dev servers.

Usage:
  node scripts/dev.mjs

Environment:
  BACKEND_HOST  Backend bind host, default 127.0.0.1
  BACKEND_PORT  Backend bind port, default 32018
  EMULATOR_HOST Emulator bind host, default 127.0.0.1
  EMULATOR_PORT Emulator bind port, default 32017

Services:
  backend   http://${backendHost}:${backendPort}
  emulator  http://${emulatorHost}:${emulatorPort}
  frontend  http://127.0.0.1:32016`);
}

if (process.argv.includes("--help") || process.argv.includes("-h")) {
  printHelp();
  process.exit(0);
}

const backend = backendCommand();
const emulator = emulatorCommand();

console.log("Starting HardcoreAI dev servers...");
console.log(`backend   http://${backendHost}:${backendPort}`);
console.log(`emulator  http://${emulatorHost}:${emulatorPort}`);
console.log("frontend  http://127.0.0.1:32016");
console.log("Press Ctrl+C to stop all.");

startProcess("backend", backend.command, backend.args, backendDir);
startProcess("emulator", emulator.command, emulator.args, backendDir, {
  EMULATOR_HOST: emulatorHost,
  EMULATOR_PORT: emulatorPort,
});
startProcess("frontend", npmCommand, ["run", "dev"], frontendDir);

process.on("SIGINT", () => stopAll(0));
process.on("SIGTERM", () => stopAll(0));
