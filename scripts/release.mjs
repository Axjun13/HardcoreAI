#!/usr/bin/env node
import {
  copyFileSync,
  cpSync,
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { gzipSync } from "node:zlib";
import { dirname, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const releaseDir = resolve(process.env.RELEASE_OUTPUT_DIR || resolve(repoRoot, "release"));
const appName = "hardcoreai-single-app";
const stageDir = resolve(releaseDir, appName);
const version = sanitizeVersion(
  process.env.RELEASE_VERSION || process.env.GITHUB_REF_NAME || "local",
);
const archivePath = resolve(releaseDir, `${appName}-${version}.tar.gz`);

const backendFiles = [
  "main.py",
  "pyproject.toml",
  "uv.lock",
];
const backendDirs = [
  "api",
  "services",
  "schemas",
  "db",
  "core",
  "agent",
  "llm",
  "rag",
  "vendor",
];
const excludedNames = new Set([
  ".env",
  ".venv",
  "__pycache__",
  ".pytest_cache",
  ".mypy_cache",
  ".ruff_cache",
  "node_modules",
  ".pio",
]);
const forbiddenReleaseIdentifiers = [
  "OPENROUTER_API_KEY",
  "GEMINI_API_KEY",
  "DEEPSEEK_API_KEY",
  "SARVAM_API_KEY",
  "BRAVE_API_KEY",
  "SUPABASE_SERVICE_KEY",
  "SUPABASE_SERVICE_ROLE_KEY",
];

function sanitizeVersion(value) {
  return value.replace(/[^0-9A-Za-z._-]/g, "-");
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

function copyDirectory(source, target) {
  cpSync(source, target, {
    recursive: true,
    filter: (path) => !excludedNames.has(path.split(/[\\/]/).pop() || ""),
  });
}

function copyReleaseFiles() {
  rmSync(stageDir, { recursive: true, force: true });
  mkdirSync(resolve(stageDir, "backend"), { recursive: true });
  mkdirSync(resolve(stageDir, "frontend"), { recursive: true });

  for (const file of backendFiles) {
    copyFileSync(resolve(repoRoot, "backend", file), resolve(stageDir, "backend", file));
  }

  for (const dir of backendDirs) {
    const src = resolve(repoRoot, "backend", dir);
    // vendor/ (bundled flash binaries) is optional — fetched per-platform and may
    // be absent in a source checkout. Skip silently rather than failing the build.
    if (!existsSync(src)) continue;
    copyDirectory(src, resolve(stageDir, "backend", dir));
  }

  copyDirectory(
    resolve(repoRoot, "frontend", "dist"),
    resolve(stageDir, "frontend", "dist"),
  );

  writeFileSync(
    resolve(stageDir, "README.md"),
    `# HardcoreAI Single App

This package contains the FastAPI backend plus the built Svelte app in frontend/dist.

Run:

  cd backend
  uv sync --frozen
  uv run uvicorn main:app --host 0.0.0.0 --port 62018

Then open:

  http://127.0.0.1:62018
`,
  );
}

function assertReleaseContainsNoSecrets(root) {
  const violations = [];
  for (const entry of tarEntries(root)) {
    if (entry.type !== "0") continue;
    const base = entry.tarName.split("/").pop() || "";
    if (base === ".env" || base.startsWith(".env.")) {
      violations.push(`${entry.tarName}: environment file`);
      continue;
    }
    if (entry.stats.size > 5_000_000) continue;
    const content = readFileSync(entry.path, "utf8");
    for (const identifier of forbiddenReleaseIdentifiers) {
      if (content.includes(identifier)) {
        violations.push(`${entry.tarName}: ${identifier}`);
      }
    }
    if (/eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]{20,}/.test(content)) {
      violations.push(`${entry.tarName}: JWT-like credential`);
    }
    if (/(?:sk-or-v1-|AIzaSy)[A-Za-z0-9_-]{20,}/.test(content)) {
      violations.push(`${entry.tarName}: provider-key-like credential`);
    }
  }
  if (violations.length) {
    throw new Error(`Release secret scan failed:\n${violations.join("\n")}`);
  }
}

function tarHeader(name, size, mode, mtime, type) {
  const header = Buffer.alloc(512);
  const encodedName = Buffer.from(name);

  if (encodedName.length > 100) {
    const index = name.length - 100;
    const prefix = name.slice(0, index).replace(/\/$/, "");
    const basename = name.slice(index).replace(/^\//, "");

    if (Buffer.byteLength(prefix) > 155 || Buffer.byteLength(basename) > 100) {
      throw new Error(`Path is too long for ustar: ${name}`);
    }

    header.write(basename, 0, 100);
    header.write(prefix, 345, 155);
  } else {
    header.write(name, 0, 100);
  }

  writeOctal(header, mode, 100, 8);
  writeOctal(header, 0, 108, 8);
  writeOctal(header, 0, 116, 8);
  writeOctal(header, size, 124, 12);
  writeOctal(header, Math.floor(mtime / 1000), 136, 12);
  header.fill(0x20, 148, 156);
  header.write(type, 156, 1);
  header.write("ustar", 257, 6);
  header.write("00", 263, 2);
  header.write("hardcoreai", 265, 32);
  header.write("hardcoreai", 297, 32);

  let checksum = 0;
  for (const byte of header) {
    checksum += byte;
  }

  const checksumText = checksum.toString(8).padStart(6, "0");
  header.write(`${checksumText}\0 `, 148, 8);
  return header;
}

function writeOctal(buffer, value, offset, length) {
  const text = value.toString(8).padStart(length - 1, "0");
  buffer.write(`${text}\0`, offset, length);
}

function tarEntries(root, current = root) {
  const entries = [];

  for (const name of readdirSync(current).sort()) {
    if (excludedNames.has(name)) {
      continue;
    }

    const path = resolve(current, name);
    const stats = statSync(path);
    const tarName = relative(dirname(root), path).replace(/\\/g, "/");

    if (stats.isDirectory()) {
      entries.push({ path, stats, tarName: `${tarName}/`, type: "5" });
      entries.push(...tarEntries(root, path));
    } else if (stats.isFile()) {
      entries.push({ path, stats, tarName, type: "0" });
    }
  }

  return entries;
}

function createTarGz(source, target) {
  const chunks = [];

  for (const entry of tarEntries(source)) {
    const size = entry.type === "0" ? entry.stats.size : 0;
    chunks.push(tarHeader(entry.tarName, size, entry.stats.mode & 0o777, entry.stats.mtimeMs, entry.type));

    if (entry.type === "0") {
      const data = readFileSync(entry.path);
      chunks.push(data);

      const padding = (512 - (data.length % 512)) % 512;
      if (padding > 0) {
        chunks.push(Buffer.alloc(padding));
      }
    }
  }

  chunks.push(Buffer.alloc(1024));
  writeFileSync(target, gzipSync(Buffer.concat(chunks), { level: 9 }));
}

if (process.argv.includes("--help") || process.argv.includes("-h")) {
  console.log(`Build and package the single FastAPI-served app for release.

Usage:
  node scripts/release.mjs
  node scripts/release.mjs --skip-build

Environment:
  RELEASE_VERSION     Archive version suffix, default local
  RELEASE_OUTPUT_DIR  Alternate output directory (useful for CI verification)`);
  process.exit(0);
}

if (!process.argv.includes("--skip-build")) {
  runStep("build", process.execPath, [resolve(repoRoot, "scripts", "build.mjs")], repoRoot);
}

if (!existsSync(resolve(repoRoot, "frontend", "dist", "index.html"))) {
  console.error("frontend/dist/index.html was not found. Run node scripts/build.mjs first.");
  process.exit(1);
}

mkdirSync(releaseDir, { recursive: true });
copyReleaseFiles();
assertReleaseContainsNoSecrets(stageDir);
createTarGz(stageDir, archivePath);

console.log(`\nRelease package created: ${relative(repoRoot, archivePath)}`);
