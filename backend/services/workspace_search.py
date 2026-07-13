from pathlib import Path
from fnmatch import fnmatch

IGNORE_DIRS = {
    ".git",
    ".pio",
    ".vscode",
    ".idea",
    "__pycache__",
    "node_modules",
    "build",
    "dist",
    ".cache",
    "venv",
}

DEFAULT_PATTERNS = [
    "*.c",
    "*.h",
    "*.cpp",
    "*.hpp",
    "*.s",
    "*.ld",
    "*.txt",
    "*.md",
    "*.json",
    "*.yaml",
    "*.yml",
]


class WorkspaceSearch:

    def __init__(self, workspace: str):
        self.workspace = Path(workspace)

    def search(self, query: str, include: str = "*.c,*.h"):

        if not query.strip():
            return []

        patterns = [
            p.strip()
            for p in include.split(",")
            if p.strip()
        ]

        if not patterns:
            patterns = DEFAULT_PATTERNS

        results = []

        for file in self.workspace.rglob("*"):

            if not file.is_file():
                continue

            if any(part in IGNORE_DIRS for part in file.parts):
                continue

            if not any(fnmatch(file.name, p) for p in patterns):
                continue

            try:

                with open(file, "r", encoding="utf-8", errors="ignore") as f:

                    for lineno, line in enumerate(f, start=1):

                        column = line.lower().find(query.lower())

                        if column != -1:

                            results.append(
                                {
                                    "file": str(file.relative_to(self.workspace)),
                                    "line": lineno,
                                    "column": column + 1,
                                    "text": line.strip(),
                                }
                            )

            except Exception:
                pass

        return results