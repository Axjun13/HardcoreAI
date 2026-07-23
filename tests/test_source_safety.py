from backend.services.source_safety import (
    blocked_source_path,
    filter_project_files,
    merge_agent_file_changes,
)


def test_sensitive_and_build_paths_are_blocked():
    assert blocked_source_path(".env")
    assert blocked_source_path(".git/config")
    assert blocked_source_path(".pio/build/firmware.elf")
    assert blocked_source_path("certs/device-private.key")
    assert not blocked_source_path("src/main.c")


def test_filter_redacts_credentials_and_reports_manifest():
    safe, manifest = filter_project_files({
        ".env": {"language": "text", "content": "TOKEN=secret"},
        "src/main.c": {
            "language": "c",
            "content": (
                '#define WIFI_PASSWORD "secret"\n'
                'const char *mqtt_token = "also-secret";\n'
                "int main(void) { return 0; }\n"
            ),
        },
        "README.md": {"language": "markdown", "content": "Safe"},
    })

    assert ".env" not in safe
    assert safe["src/main.c"]["content"].count("[REDACTED]") == 2
    assert manifest["excluded"] == [".env"]
    assert manifest["redacted"] == ["src/main.c"]


def test_merge_never_deletes_excluded_files():
    original = {
        ".env": {"language": "text", "content": "TOKEN=secret"},
        "src/main.c": {"language": "c", "content": "old"},
    }
    safe, _manifest = filter_project_files(original)
    merged = merge_agent_file_changes(
        original,
        safe,
        {"src/main.c": {"language": "c", "content": "new"}},
    )

    assert merged[".env"] == original[".env"]
    assert merged["src/main.c"]["content"] == "new"
