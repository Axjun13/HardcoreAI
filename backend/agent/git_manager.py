import os
import subprocess
from pathlib import Path

class GitManager:
    def __init__(self, project_id: str):
        self.project_id = project_id
        # Safe storage path in backend/data/workspaces/<project_id>
        self.workspace_dir = Path("data/workspaces") / str(project_id)
        
    def ensure_repo(self):
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        git_dir = self.workspace_dir / ".git"
        if not git_dir.exists():
            self._run_git(["init"])
            # Set dummy configs to ensure commit succeeds
            self._run_git(["config", "user.name", "HardcoreAI Copilot"])
            self._run_git(["config", "user.email", "copilot@hardcore-ai.local"])
            
    def _run_git(self, args: list[str]) -> subprocess.CompletedProcess:
        """Run a git command in the workspace directory."""
        print(f"[GitManager] Running command: git {' '.join(args)} in {self.workspace_dir.absolute()}")
        try:
            # On Windows, shell=True can be helpful for finding the git executable
            # but we will try running directly first.
            res = subprocess.run(
                ["git"] + args,
                cwd=str(self.workspace_dir),
                capture_output=True,
                text=True,
                check=False
            )
            print(f"[GitManager] Direct run exit code: {res.returncode}")
            if res.returncode != 0:
                print(f"[GitManager] Direct run stderr: {res.stderr}")
            return res
        except FileNotFoundError as fnf:
            print(f"[GitManager] FileNotFoundError on direct run: {fnf}. Trying shell=True...")
            # Try with shell=True if direct execution fails (common in some Windows environments)
            try:
                res = subprocess.run(
                    " ".join(["git"] + [f'"{a}"' if " " in a else a for a in args]),
                    cwd=str(self.workspace_dir),
                    shell=True,
                    capture_output=True,
                    text=True,
                    check=False
                )
                print(f"[GitManager] Shell run exit code: {res.returncode}")
                if res.returncode != 0:
                    print(f"[GitManager] Shell run stderr: {res.stderr}")
                return res
            except Exception as e:
                print(f"[GitManager] Exception on shell run: {e}")
                class DummyProcess:
                    def __init__(self, err_msg):
                        self.returncode = 127
                        self.stdout = ""
                        self.stderr = f"git command failed to start: {err_msg}"
                return DummyProcess(str(e))

    def sync_db_to_disk(self, files: dict[str, dict[str, str]]):
        """Materialize files stored in the DB dict to the local workspace on disk."""
        self.ensure_repo()
        
        # Walk local disk to see what files exist currently
        disk_files = set()
        for root, dirs, filenames in os.walk(self.workspace_dir):
            # Ignore git and build directories
            for ignored in [".git", ".pio", ".vscode"]:
                if ignored in dirs:
                    dirs.remove(ignored)
                    
            for f in filenames:
                # Ignore platformio config files
                if f in ["platformio.ini", ".gitignore"]:
                    continue
                    
                full_path = Path(root) / f
                rel_path = full_path.relative_to(self.workspace_dir)
                disk_files.add(rel_path.as_posix())
                
        # Write files from the database files_dict
        for path, meta in files.items():
            content = meta.get("content", "")
            file_path = self.workspace_dir / path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write file if content is different or file doesn't exist
            if not file_path.exists() or file_path.read_text(encoding="utf-8") != content:
                file_path.write_text(content, encoding="utf-8")
                
            posix_path = Path(path).as_posix()
            if posix_path in disk_files:
                disk_files.remove(posix_path)
                
        # Remove local files that are no longer in the DB files_dict
        for path in disk_files:
            file_path = self.workspace_dir / path
            if file_path.exists() and file_path.is_file():
                file_path.unlink()
                
    def commit_changes(self, message: str) -> bool:
        """Create a git commit if there are any unstaged or modified files."""
        self.ensure_repo()
        # Stage all changes
        self._run_git(["add", "."])
        # Check porcelain status to see if anything is modified/new/deleted
        status = self._run_git(["status", "--porcelain"])
        if not status.stdout.strip():
            return False # Nothing changed, skip commit
            
        res = self._run_git(["commit", "-m", message])
        return res.returncode == 0

    def get_status(self) -> list[dict]:
        self.ensure_repo()
        res = self._run_git(["status", "--porcelain"])
        print(f"[GitManager] get_status status code: {res.returncode}, stdout: {res.stdout.strip()}")
        if res.returncode != 0:
            return []
        
        status_list = []
        for line in res.stdout.splitlines():
            if not line.strip():
                continue
            # porcelain format is: XY path
            xy = line[:2]
            path = line[3:].strip()
            status_list.append({
                "path": path,
                "status": xy.strip()
            })
        print(f"[GitManager] Parsed status list: {status_list}")
        return status_list

    def get_log(self) -> str:
        self.ensure_repo()
        res = self._run_git(["log", "--oneline", "--decorate", "--graph", "-n", "20"])
        if res.returncode != 0:
            return f"Error: {res.stderr or 'No commits yet.'}"
        return res.stdout
        
    def get_diff(self, commit_a: str, commit_b: str) -> str:
        self.ensure_repo()
        res = self._run_git(["diff", commit_a, commit_b])
        if res.returncode != 0:
            return f"Error: {res.stderr}"
        return res.stdout
        
    def get_show(self, commit: str) -> str:
        self.ensure_repo()
        res = self._run_git(["show", commit])
        if res.returncode != 0:
            return f"Error: {res.stderr}"
        return res.stdout
