# HARDCOREAI - Embedded Developer Workspace

A premium, modern embedded developer workspace built with Svelte 5, TypeScript, and Vite. Optimize compilation, flashing, and debug loops directly on target microcontrollers with zero unnecessary visual noise.

## Tech Stack
- **Framework**: [Svelte 5](https://svelte.dev/)
- **Language**: [TypeScript](https://www.typescriptlang.org/)
- **Build Tool**: [Vite](https://vite.dev/)
- **Backend**: [FastAPI](https://fastapi.tiangolo.com/)
- **Icons**: [Lucide Svelte](https://lucide.dev/guide/svelte)

---

## Getting Started

### 1. Prerequisites
Ensure you have [Node.js](https://nodejs.org/) and Python 3.12 installed.
The backend works best with [uv](https://docs.astral.sh/uv/), but the scripts
fall back to the active Python environment when possible.

### 2. Installation
Install frontend dependencies:
```bash
cd frontend
npm install
```

Install backend dependencies:
```bash
cd backend
uv sync
```

### 3. Development Servers
Start the backend and frontend dev servers together from the repo root:
```bash
node scripts/dev.mjs
```
Open **[http://127.0.0.1:32016/](http://127.0.0.1:32016/)** in your browser.
The frontend runs on port `32016`; the backend runs on port `32018`; the
emulator service runs on port `32017`.

---

## Scripts

### Dev
Run FastAPI with reload and Vite concurrently:
```bash
node scripts/dev.mjs
```

Optional backend bind settings:
```bash
BACKEND_HOST=127.0.0.1 BACKEND_PORT=32018 node scripts/dev.mjs
```
On Windows PowerShell:
```powershell
$env:BACKEND_HOST="127.0.0.1"; $env:BACKEND_PORT="32018"; node scripts/dev.mjs
```

### Build Single App
Build the Svelte app into `frontend/dist` and validate backend Python sources:
```bash
node scripts/build.mjs
```
FastAPI serves the built frontend from `frontend/dist`.

### Build And Run Single App
Build the single app, then run FastAPI serving the built Svelte app plus the
emulator service:
```bash
node scripts/run-build.mjs
```

If `frontend/dist` is already built:
```bash
node scripts/run-build.mjs --skip-build
```

Open **[http://127.0.0.1:32018/](http://127.0.0.1:32018/)**.
The emulator API is started automatically on `http://127.0.0.1:62017/`.

### Release Package
Create a release archive under `release/`:
```bash
RELEASE_VERSION=v0.1.0 node scripts/release.mjs
```
On Windows PowerShell:
```powershell
$env:RELEASE_VERSION="v0.1.0"; node scripts/release.mjs
```

The archive contains the backend source and built `frontend/dist`, excluding
local env files, virtual environments, Node dependencies, and generated build
artifacts.

### GitHub Releases
The GitHub Actions workflow at `.github/workflows/release.yml` publishes the
single-app archive to GitHub Releases.

Push a version tag to release:
```bash
git tag v0.1.0
git push origin v0.1.0
```

You can also run the workflow manually from GitHub Actions and provide a version
such as `v0.1.0`.

---

## Commands & Testing

### Type & Svelte Diagnostic Checks
Verify that the code has zero syntax or TypeScript errors:
```bash
cd frontend
npx svelte-check
```

### Frontend Build Only
Compile only the Vite frontend:
```bash
cd frontend
npm run build
```
The optimized frontend bundle will be created inside `frontend/dist/`.
