"""Git repository management — operates on the real project folder when one is available.

If the project has a real on-disk path (``project.path``) and that folder
contains a ``.git`` directory, all operations target that folder (VS Code
behaviour).  Otherwise the internal ``data/workspaces/<id>`` backup repo is
used as a fallback so the agent's auto-commits still work.
"""

import os
import subprocess
from pathlib import Path
from datetime import datetime, timezone


class GitManager:
    def __init__(self, project_id: str, real_path: str | None = None):
        self.project_id = project_id
        
        # If real_path is not provided, fetch it from the DB to prevent callers
        # from accidentally defaulting to the internal fallback workspace.
        if real_path is None:
            if str(project_id).isdigit():
                from db.session import engine
                from sqlmodel import Session, select
                from db.models import ProjectRow
                with Session(engine) as session:
                    project = session.exec(select(ProjectRow).where(ProjectRow.id == int(project_id))).first()
                    if project and project.path:
                        real_path = project.path

        # Prefer the real project folder if it already has a .git directory.
        if real_path and (Path(real_path) / ".git").exists():
            self.workspace_dir = Path(real_path)
            self.using_real_path = True
        else:
            # Fall back to internal workspace — used ONLY for sync_db_to_disk / commit.
            # The panel will show the "no-repo" state for these projects.
            self.workspace_dir = Path("data/workspaces") / str(project_id)
            self.using_real_path = False

    # ------------------------------------------------------------------ #
    #  Low-level git runner                                               #
    # ------------------------------------------------------------------ #

    def _run_git(self, args: list[str]) -> subprocess.CompletedProcess:
        """Run a git command in the workspace directory."""
        print(f"[GitManager] Running: git {' '.join(args)} in {self.workspace_dir.absolute()}")
        try:
            res = subprocess.run(
                ["git"] + args,
                cwd=str(self.workspace_dir),
                capture_output=True,
                text=True,
                check=False,
            )
            if res.returncode != 0:
                print(f"[GitManager] stderr: {res.stderr.strip()}")
            return res
        except FileNotFoundError as fnf:
            print(f"[GitManager] git not found on PATH: {fnf}. Retrying with shell=True…")
            try:
                cmd = " ".join(["git"] + [f'"{a}"' if " " in a else a for a in args])
                res = subprocess.run(
                    cmd,
                    cwd=str(self.workspace_dir),
                    shell=True,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                return res
            except Exception as e:
                class _Fail:
                    returncode = 127
                    stdout = ""
                    stderr = f"git command failed to start: {e}"
                return _Fail()  # type: ignore[return-value]

    # ------------------------------------------------------------------ #
    #  Repo initialisation / detection                                    #
    # ------------------------------------------------------------------ #

    def is_git_repo(self) -> bool:
        """Return True only when the project's REAL folder contains a .git directory.
        The internal fallback workspace does not count — it must not appear as a repo
        in the UI (panel stays greyed-out for projects without a real git folder)."""
        return getattr(self, "using_real_path", False) and (self.workspace_dir / ".git").exists()

    def ensure_repo(self):
        """Create the workspace dir and init a bare git repo if missing."""
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        if not self.is_git_repo():
            self._run_git(["init"])
            self._run_git(["config", "user.name", "HardcoreAI Copilot"])
            self._run_git(["config", "user.email", "copilot@hardcore-ai.local"])

    # ------------------------------------------------------------------ #
    #  Status / diff                                                      #
    # ------------------------------------------------------------------ #

    def get_status(self) -> list[dict]:
        # Do NOT call ensure_repo() here — we only want to read existing repos.
        # If there is no .git, return empty (panel will show greyed-out state).
        if not self.is_git_repo():
            return []
        # -u (--untracked-files=all) expands directories so we see individual files
        # instead of just "src/" as a single entry.
        res = self._run_git(["status", "--porcelain", "-u"])
        if res.returncode != 0:
            return []

        # Map raw XY porcelain codes to VS Code-style single letters.
        def _vscode_letter(xy: str) -> str:
            xy = xy.strip()
            if xy in ("??", "!!"):
                return "U"  # Untracked
            if xy in ("M ", " M", "MM"):
                return "M"  # Modified
            if xy in ("A ", " A", "AM"):
                return "A"  # Added/staged
            if xy in ("D ", " D", "DD"):
                return "D"  # Deleted
            if xy.startswith("R"):
                return "R"  # Renamed
            if xy.startswith("C"):
                return "C"  # Copied
            if "U" in xy:
                return "C"  # Conflict
            return xy[0] if xy else "?"

        status_list = []
        for line in res.stdout.splitlines():
            if not line.strip():
                continue
            xy = line[:2]
            path = line[3:].strip()
            # Strip rename arrows: "old.c -> new.c" → "new.c"
            if " -> " in path:
                path = path.split(" -> ", 1)[1].strip()
            # Skip .gitkeep placeholder files — they are an internal folder trick
            if path.endswith(".gitkeep"):
                continue
            status_list.append({"path": path, "status": _vscode_letter(xy)})
        print(f"[GitManager] Parsed status list: {status_list}")
        return status_list

    # ------------------------------------------------------------------ #
    #  Commit                                                             #
    # ------------------------------------------------------------------ #

    def commit_changes(self, message: str) -> bool:
        """Stage everything and commit if there are pending changes."""
        self.ensure_repo()
        self._run_git(["add", "."])
        status = self._run_git(["status", "--porcelain"])
        if not status.stdout.strip():
            return False
        res = self._run_git(["commit", "-m", message])
        if res.returncode == 0:
            self._update_db_version()
            return True
        return False

    # ------------------------------------------------------------------ #
    #  Sync DB → disk (internal backup repo only)                        #
    # ------------------------------------------------------------------ #

    def sync_db_to_disk(self, files: dict[str, dict[str, str]]):
        """Materialise DB files onto disk (used by the internal backup repo)."""
        self.ensure_repo()

        disk_files: set[str] = set()
        for root, dirs, filenames in os.walk(self.workspace_dir):
            for ignored in [".git", ".pio", ".vscode", "__pycache__", "node_modules", ".venv", "venv", "env", "dist", "build", ".pytest_cache", ".svelte-kit", "data", "backend/data"]:
                if ignored in dirs:
                    dirs.remove(ignored)
            for f in filenames:
                if f in ["platformio.ini", ".gitignore"]:
                    continue
                full_path = Path(root) / f
                rel_path = full_path.relative_to(self.workspace_dir)
                disk_files.add(rel_path.as_posix())

        for path, meta in files.items():
            content = meta.get("content", "")
            file_path = self.workspace_dir / path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            if not file_path.exists() or file_path.read_text(encoding="utf-8") != content:
                file_path.write_text(content, encoding="utf-8")
            posix_path = Path(path).as_posix()
            if posix_path in disk_files:
                disk_files.remove(posix_path)

        for path in disk_files:
            file_path = self.workspace_dir / path
            if file_path.exists() and file_path.is_file():
                file_path.unlink()

    def sync_disk_to_db(self):
        """Read files from disk and overwrite the DB so the IDE reflects checkout changes."""
        if not str(self.project_id).isdigit():
            return
        from db.session import engine
        from sqlmodel import Session, select
        from db.models import CodeFileRow
        from core.config import now_utc

        disk_files = {}
        for root, dirs, filenames in os.walk(self.workspace_dir):
            for ignored in [".git", ".pio", ".vscode", "__pycache__", "node_modules", ".venv", "venv", "env", "dist", "build", ".pytest_cache", ".svelte-kit", "data", "backend/data"]:
                if ignored in dirs:
                    dirs.remove(ignored)
            for f in filenames:
                if f in ["platformio.ini", ".gitignore", ".gitkeep"]:
                    continue
                full_path = Path(root) / f
                rel_path = full_path.relative_to(self.workspace_dir).as_posix()
                try:
                    content = full_path.read_text(encoding="utf-8")
                    disk_files[rel_path] = content
                except Exception:
                    # Ignore binary files or unreadable files
                    pass

        with Session(engine) as session:
            existing_rows = session.exec(
                select(CodeFileRow).where(CodeFileRow.project_id == int(self.project_id))
            ).all()
            
            existing_map = {row.path: row for row in existing_rows}

            for path, content in disk_files.items():
                if path in existing_map:
                    row = existing_map[path]
                    if row.content != content:
                        row.content = content
                        row.updated_at = now_utc()
                        session.add(row)
                    del existing_map[path]
                else:
                    # Detect basic language
                    ext = path.split(".")[-1].lower() if "." in path else ""
                    lang_map = {"c": "c", "cpp": "cpp", "h": "c", "py": "python", "js": "javascript", "ts": "typescript", "json": "json", "md": "markdown"}
                    lang = lang_map.get(ext, "plaintext")
                    new_row = CodeFileRow(project_id=int(self.project_id), path=path, content=content, language=lang)
                    session.add(new_row)

            # Anything left in existing_map was deleted on disk during checkout
            for row in existing_map.values():
                session.delete(row)

            session.commit()

    # ------------------------------------------------------------------ #
    #  HEAD / branch info                                                 #
    # ------------------------------------------------------------------ #

    def get_current_head(self) -> dict:
        """Return {branch, detached, hash, short_hash}."""
        if not self.is_git_repo():
            return {"branch": None, "detached": False, "hash": None, "short_hash": None}

        # Current commit hash
        hash_res = self._run_git(["rev-parse", "HEAD"])
        head_hash = hash_res.stdout.strip() if hash_res.returncode == 0 else None
        short_hash = head_hash[:7] if head_hash else None

        # Check for detached HEAD
        sym_res = self._run_git(["symbolic-ref", "--short", "HEAD"])
        if sym_res.returncode == 0:
            branch = sym_res.stdout.strip()
            return {"branch": branch, "detached": False, "hash": head_hash, "short_hash": short_hash}
        else:
            return {"branch": None, "detached": True, "hash": head_hash, "short_hash": short_hash}

    def get_branches(self) -> list[str]:
        """Return a list of local branch names."""
        if not self.is_git_repo():
            return []
        res = self._run_git(["branch", "--format=%(refname:short)"])
        if res.returncode != 0:
            return []
        return [b.strip() for b in res.stdout.splitlines() if b.strip()]

    def create_branch(self, branch_name: str) -> dict:
        """Create a new branch and check it out."""
        if not self.is_git_repo():
            return {"success": False, "error": "Not a git repository"}
        import re
        if not re.match(r'^[a-zA-Z0-9_/\.\-]+$', branch_name):
            return {"success": False, "error": "Invalid branch name"}
        res = self._run_git(["checkout", "-b", branch_name])
        if res.returncode == 0:
            self.sync_disk_to_db()
            self._update_db_version()
            return {"success": True, "error": None}
        return {"success": False, "error": res.stderr.strip()}

    # ------------------------------------------------------------------ #
    #  Git log (structured for SVG graph)                                 #
    # ------------------------------------------------------------------ #

    def get_log_graph(self, n: int = 50) -> list[dict]:
        """Return a structured commit list for the frontend graph.

        Each entry: hash, short_hash, subject, author_name, author_email,
        date_iso, date_relative, refs (branch/tag names), parents (parent hashes)
        """
        if not self.is_git_repo():
            return []

        # Use pipe-safe separators that won't appear in commit messages
        SEP = "\x1f"
        LINE_SEP = "\x1e"
        fmt = SEP.join(["%H", "%h", "%s", "%an", "%ae", "%aI", "%ar", "%D", "%P"])
        res = self._run_git(
            ["log", "--all", "--topo-order", f"-{n}", f"--pretty=format:{fmt}{LINE_SEP}"]
        )
        if res.returncode != 0:
            print(f"[GitManager] get_log_graph failed: {res.stderr.strip()}")
            return []

        commits = []
        for raw in res.stdout.split(LINE_SEP):
            raw = raw.strip()
            if not raw:
                continue
            parts = raw.split(SEP)
            if len(parts) < 9:
                continue
            h, sh, subject, author_name, author_email, date_iso, date_rel, refs_raw, parents_raw = parts[:9]

            # Parse refs (branch / tag labels) — git %D gives "HEAD -> main, origin/main, tag: v1.0"
            refs: list[str] = []
            for ref in refs_raw.split(","):
                ref = ref.strip()
                if not ref:
                    continue
                if ref.startswith("HEAD ->"):
                    ref = ref[len("HEAD ->"):].strip()
                if ref:
                    refs.append(ref)

            parents = [p.strip() for p in parents_raw.split() if p.strip()]

            commits.append({
                "hash": h,
                "short_hash": sh,
                "subject": subject,
                "author_name": author_name,
                "author_email": author_email,
                "date_iso": date_iso,
                "date_relative": date_rel,
                "refs": refs,
                "parents": parents,
            })

        return commits

    # ------------------------------------------------------------------ #
    #  Checkout                                                           #
    # ------------------------------------------------------------------ #

    def _update_db_version(self, head_hash: str | None = None):
        """Update the ProjectRow.version_number with the current commit hash."""
        if not str(self.project_id).isdigit():
            return
        if not head_hash:
            head_hash = self.get_current_head().get("hash")
        if not head_hash:
            return
            
        from db.session import engine
        from sqlmodel import Session, select
        from db.models import ProjectRow
        with Session(engine) as session:
            project = session.exec(select(ProjectRow).where(ProjectRow.id == int(self.project_id))).first()
            if project:
                project.version_number = head_hash
                session.add(project)
                session.commit()

    def checkout_commit(self, ref: str) -> dict:
        """Checkout a specific commit or branch (detached HEAD for bare hash)."""
        if not self.is_git_repo():
            return {"success": False, "error": "Not a git repository", "head": None}
        # Sanitise ref — only allow hex chars, branch chars, slashes, dashes, dots
        import re
        if not re.match(r'^[a-zA-Z0-9_/\.\-]+$', ref):
            return {"success": False, "error": "Invalid ref", "head": None}
        res = self._run_git(["checkout", ref])
        head = self.get_current_head()
        if res.returncode == 0:
            self.sync_disk_to_db()
            self._update_db_version(head.get("hash"))
            return {"success": True, "error": None, "head": head}
        return {"success": False, "error": res.stderr.strip(), "head": head}

    def checkout_head(self) -> dict:
        """Return to the default branch (main → master → first local branch)."""
        if not self.is_git_repo():
            return {"success": False, "error": "Not a git repository", "head": None}
        branches = self.get_branches()
        target = None
        for preferred in ("main", "master"):
            if preferred in branches:
                target = preferred
                break
        if target is None and branches:
            target = branches[0]
        if target is None:
            return {"success": False, "error": "No local branches found", "head": self.get_current_head()}
        res = self._run_git(["checkout", target])
        head = self.get_current_head()
        if res.returncode == 0:
            self.sync_disk_to_db()
            self._update_db_version(head.get("hash"))
            return {"success": True, "error": None, "head": head}
        return {"success": False, "error": res.stderr.strip(), "head": head}

    # ------------------------------------------------------------------ #
    #  Legacy helpers (kept for backward compat)                         #
    # ------------------------------------------------------------------ #

    def get_log(self) -> str:
        if not self.is_git_repo():
            return "No git repository."
        res = self._run_git(["log", "--oneline", "--decorate", "--graph", "-n", "20"])
        if res.returncode != 0:
            return f"Error: {res.stderr or 'No commits yet.'}"
        return res.stdout

    def get_diff(self, commit_a: str, commit_b: str) -> str:
        if not self.is_git_repo():
            return "No git repository."
        res = self._run_git(["diff", commit_a, commit_b])
        if res.returncode != 0:
            return f"Error: {res.stderr}"
        return res.stdout

    def get_show(self, commit: str) -> str:
        if not self.is_git_repo():
            return "No git repository."
        res = self._run_git(["show", commit])
        if res.returncode != 0:
            return f"Error: {res.stderr}"
        return res.stdout
