#!/usr/bin/env node
/**
 * Vendor the flash/detect toolchain (OpenOCD) into backend/vendor/ so the shipped
 * app needs no manual install. Downloads the xpack-openocd release for the host
 * platform and extracts it to backend/vendor/openocd/<platform>/.
 *
 * Usage:
 *   node scripts/fetch-tools.mjs          # fetch for the current platform
 *   node scripts/fetch-tools.mjs --force  # re-download even if present
 *
 * The backend resolves the binary at vendor/openocd/<platform>/bin/openocd
 * (see backend/services/hardware.py: openocd_bin()). If you prefer to install
 * OpenOCD system-wide instead, the backend also falls back to `openocd` on PATH,
 * or honor the OPENOCD_BIN env var.
 */
import { existsSync, mkdirSync, rmSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const force = process.argv.includes("--force");

// xpack-dev-tools prebuilt OpenOCD — small, self-contained, multi-platform.
const VERSION = "0.12.0-3";
const BASE = `https://github.com/xpack-dev-tools/openocd-xpack/releases/download/v${VERSION}`;

function platformSlug() {
  if (process.platform === "win32") return "windows";
  if (process.platform === "darwin") return "macos";
  return "linux";
}

// Maps host -> (xpack asset arch, archive extension).
function asset() {
  const slug = platformSlug();
  const arch = process.arch === "arm64" ? "arm64" : "x64";
  if (slug === "windows") return { name: `xpack-openocd-${VERSION}-win32-${arch}.zip`, ext: "zip" };
  if (slug === "macos") return { name: `xpack-openocd-${VERSION}-darwin-${arch}.tar.gz`, ext: "tar.gz" };
  return { name: `xpack-openocd-${VERSION}-linux-${arch}.tar.gz`, ext: "tar.gz" };
}

function run(cmd, args, opts = {}) {
  const r = spawnSync(cmd, args, { stdio: "inherit", ...opts });
  if (r.status !== 0) {
    console.error(`[fetch-tools] command failed: ${cmd} ${args.join(" ")}`);
    process.exit(r.status || 1);
  }
}

const slug = platformSlug();
const destDir = resolve(repoRoot, "backend", "vendor", "openocd", slug);
const binName = slug === "windows" ? "openocd.exe" : "openocd";
const binPath = resolve(destDir, "bin", binName);

if (existsSync(binPath) && !force) {
  console.log(`[fetch-tools] OpenOCD already vendored at ${binPath} (use --force to refresh).`);
  process.exit(0);
}

const { name, ext } = asset();
const url = `${BASE}/${name}`;
const tmp = resolve(repoRoot, ".tmp-tools");
rmSync(tmp, { recursive: true, force: true });
mkdirSync(tmp, { recursive: true });
const archive = resolve(tmp, name);

console.log(`[fetch-tools] downloading ${url}`);
run("curl", ["-fL", "-o", archive, url]);

rmSync(destDir, { recursive: true, force: true });
mkdirSync(destDir, { recursive: true });

console.log(`[fetch-tools] extracting to ${destDir}`);
if (ext === "zip") {
  run("unzip", ["-q", archive, "-d", tmp]);
} else {
  run("tar", ["-xzf", archive, "-C", tmp]);
}

// xpack archives extract to a single top-level dir (xpack-openocd-<version>/).
// Move its contents up into destDir so bin/openocd lands at the documented path.
const extractedRoot = resolve(tmp, `xpack-openocd-${VERSION}`);
if (!existsSync(extractedRoot)) {
  console.error(`[fetch-tools] unexpected archive layout; expected ${extractedRoot}`);
  process.exit(1);
}
run("cp", ["-R", `${extractedRoot}/.`, destDir]);
rmSync(tmp, { recursive: true, force: true });

if (!existsSync(binPath)) {
  console.error(`[fetch-tools] OpenOCD binary not found at ${binPath} after extraction.`);
  process.exit(1);
}
console.log(`[fetch-tools] OpenOCD ready: ${binPath}`);
