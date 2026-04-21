# Data source reference

Structures produced by the four collector scripts. When generating the report, Claude reads the `.cache/` files against these schemas.

## 1. `claude_code_sessions.json`

Source: `scripts/collect_claude_code.py`, scanning `~/.claude/projects/<encoded-cwd>/<session-id>.jsonl`.

```jsonc
{
  "range": { "from": "2026-04-13", "to": "2026-04-19", "timezone": "Asia/Shanghai",
             "from_utc": "...", "to_utc": "..." },
  "stats": {
    "files_scanned": 131,
    "files_skipped_by_mtime": 88,
    "substantive_sessions": 17,
    "exploratory_sessions": 9,
    "total_user_messages": 234,
    "user_messages_by_project": { "/Users/sha7dow/Work/Projects/AutoIdea": 120, ... }
  },
  "sessions": [
    {
      "session_id": "f87d1df9-...",
      "cwd": "/Users/sha7dow/Work/Projects/AutoIdea",
      "jsonl_path": "/Users/sha7dow/.claude/projects/-Users-.../f87d1df9-....jsonl",
      "git_branch": "main",
      "start_utc": "2026-04-13T02:15:30+00:00",
      "end_utc": "2026-04-13T03:40:12+00:00",
      "duration_seconds": 5082,
      "user_messages": 15,
      "assistant_messages": 18,
      "first_user_message": "help me implement ... (≤500 chars)",
      "last_user_message": "looks ok, let's commit (≤300 chars)",
      "user_message_snippets": ["help me implement …", "tweak this …", ...],  // ≤40 items, each ≤100 chars
      "exploratory": false,
      "file_bytes": 524288
    }
  ],
  "exploratory_sessions": [ /* same shape, exploratory: true */ ]
}
```

**Noise filtering**: sessions tagged `exploratory=true` (below either the message-count or duration threshold) collapse by default into a single "N exploratory chats" line in the report, not expanded individually. If a particular exploratory session's `first_user_message` carries a clear signal (e.g. "why is kubectl apply hanging"), Claude may still call it out by name.

**Raw messages**: if you need the original conversation, read `jsonl_path` (one JSON object per line; filter `type in [user, assistant]` and `isMeta` is false).

## 2. `github.json`

Source: `scripts/collect_github.py`, via `gh api graphql` and `gh api /users/:u/events`.

```jsonc
{
  "range": { ... },
  "github_username": "sha7doww",
  "pull_requests": [
    {
      "__typename": "PullRequest",
      "number": 42,
      "title": "Fix race condition in worker pool",
      "url": "https://github.com/org/repo/pull/42",
      "state": "MERGED",
      "isDraft": false,
      "merged": true,
      "mergedAt": "2026-04-15T08:30:00Z",
      "createdAt": "2026-04-13T02:00:00Z",
      "closedAt": "2026-04-15T08:30:00Z",
      "additions": 42,
      "deletions": 18,
      "changedFiles": 3,
      "repository": { "nameWithOwner": "org/repo", "isPrivate": true },
      "commits": { "totalCount": 4 },
      "body": "..."
    }
  ],
  "issues": [ /* same shape, __typename: "Issue" */ ],
  "events": [
    { "type": "PushEvent", "repo": "org/repo", "created_at": "...",
      "ref": "refs/heads/feature-x", "commit_count": 3,
      "commit_messages": ["fix: ...", ...] },
    { "type": "PullRequestEvent", "action": "closed", "number": 42, ... }
  ],
  "stats": { "pr_count": 7, "issue_count": 2, "event_count": 54 }
}
```

**Notes**:
- GitHub search's `created:` filter uses UTC dates, which can differ from the local-timezone range by a few hours. In contrast, the `events[].created_at` values are precise UTC timestamps and are filtered against `from_utc..to_utc` exactly inside the script.
- Private repos are visible as long as the token has the `repo` scope.
- Both "authored" and "updated" PRs are collected, then deduped and merged.

## 3. `local_git.json`

Source: `scripts/collect_local_git.py`, scanning every `.git` repo under `config.local_git_dirs` (skipping `node_modules`, `.venv`, etc.).

```jsonc
{
  "range": { ... },
  "authors": ["sha7doww", "2453900478@qq.com"],
  "scanned_roots": ["/Users/sha7dow/Work/Projects"],
  "scanned_repo_count": 14,
  "stats": { "repos_with_activity": 6, "total_commits": 38, "total_insertions": 1200, "total_deletions": 430 },
  "repos": [
    {
      "repo": "/Users/sha7dow/Work/Projects/AutoIdea",
      "remote": "git@github.com:sha7doww/AutoIdea.git",
      "current_branch": "main",
      "commits": [
        {
          "sha": "abc123...",
          "author_name": "sha7doww",
          "author_email": "2453900478@qq.com",
          "authored_at": "2026-04-13T10:22:15+08:00",
          "subject": "feat: add prompt template cache",
          "body": "… (≤400 chars)",
          "files_changed": 3,
          "insertions": 48,
          "deletions": 12
        }
      ],
      "commit_count": 5,
      "insertions": 240,
      "deletions": 90,
      "wip_file_count": 2,
      "wip_sample": [" M src/foo.ts", "?? notes.txt"]
    }
  ]
}
```

**Authoritative commit source**: `gh search commits` has indexing lag and a low result cap, so the commits here are the source of truth. GitHub's `events[PushEvent].commit_messages` is only used to answer "which branch got pushed to today" and to link commits back to PRs.

## 4. `braindump.md`

Source: `scripts/collect_braindump.py`, extracting entries whose dates fall in the range from `config.braindump_path`.

Two supported formats:

**Format A — date headings** (recommended)

```markdown
## 2026-04-13 Mon
- aligned project Y scope with X
- started looking into Z's perf issue in the afternoon
### side notes
  productivity felt meh today
```

The entire section (until a same-or-higher-level heading) is kept as one entry.

**Format B — inline date bullets**

```markdown
- 2026-04-13 aligned Y scope with X
* 2026-04-14 spent 3 hours on Z
```

Output is a markdown fragment (not JSON) so it can be inlined directly into the "user notes" section of the report. When there are no entries, an HTML-comment placeholder is emitted.

## 5. Not collected, but easy to add

The resources below are not collected in v1. To add one, drop a script in `scripts/` that follows the same CLI convention (`--from/--to/--week/--config/--output`) and add one line to the workflow in `SKILL.md`.

- Linear/Jira: needs an extra API token
- macOS Calendar: needs Full Disk Access + parsing the `Calendar.app` database
- Obsidian daily notes: merge into the braindump logic
