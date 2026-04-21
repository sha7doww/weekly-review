# `config.json` field reference

`config.json` lives at the skill root and is excluded by `.gitignore`. It is created interactively on first run; you can edit it by hand afterwards.

| Field | Type | Description | Default |
|---|---|---|---|
| `github_username` | string | GitHub login used for `gh api` queries | first-run suggestion comes from `gh api user` |
| `git_authors` | string[] | Substrings matched against local `git log --author=<x>` (name or email) | first-run defaults from `git config --global user.{email,name}` |
| `local_git_dirs` | string[] | Root directories scanned for git repos | first-run suggestion: `~/Work/Projects` |
| `timezone` | string | IANA timezone, e.g. `Asia/Shanghai`, `America/Los_Angeles` | `Asia/Shanghai` |
| `identity_blurb` | string | Opening blurb for outward-facing reports (unused in v1) | `""` |
| `braindump_path` | string | Path to the freeform braindump file; `~` is expanded | suggested: `~/Documents/weekly-braindump.md` |
| `session_min_messages` | int | Claude Code sessions with fewer user messages than this are tagged exploratory | `3` |
| `session_min_duration_seconds` | int | Sessions shorter than this are tagged exploratory | `120` |
| `exclude_project_cwds` | string[] | Claude Code project cwds to skip (e.g. throwaway experiment dirs) | `[]` |
| `categories` | object[] | Cached AI-clustered categories; written back by the skill after the first run | `[]` |

## `categories` shape

```json
[
  {
    "name": "eng-autoidea",
    "description": "Eng: AutoIdea project",
    "keywords": ["AutoIdea", "generator", "prompt"],
    "added_at": "2026-04-20",
    "source": "auto"
  }
]
```

`source` is either `auto` (AI clustered) or `manual` (hand-added).

## Applying changes

All fields are read fresh at script or skill startup — there is no cache, so edits take effect immediately. Note that changing `categories` does **not** retroactively re-categorize already-generated reports.
