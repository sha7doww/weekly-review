---
name: weekly-review
description: Generate a personal weekly review report by aggregating Claude Code conversations, GitHub PR/issue activity, local git commits, user braindump entries, and Tencent Meeting minutes for a fixed ISO-week date range.
triggers:
  - write weekly review
  - generate weekly review
  - weekly review
  - weekly summary
  - week in review
  - what did I do this week
arguments:
  - name: week
    description: ISO week identifier like `2026-W15`. Mutually exclusive with --from/--to.
  - name: from
    description: Start date `YYYY-MM-DD` (local tz, inclusive).
  - name: to
    description: End date `YYYY-MM-DD` (local tz, inclusive).
---

# weekly-review

Generate an inward-facing weekly review. Aggregate 5 data sources (Claude Code conversations, GitHub PR/Issue/events, local git commits, user braindump, Tencent Meeting minutes), then do the clustering, time-share estimation, key-decision writeup, reflection, and next-week plan yourself.

**"A week" is always the 7 days the user explicitly names, or the complete ISO week immediately before the current one** — never "the last 7 days from today."

## Pre-check

From the skill directory (the directory containing `SKILL.md`, referred to below as `$SKILL_DIR`):

```bash
ls "$SKILL_DIR/config.json" 2>/dev/null
```

If it doesn't exist, enter the **first-run config** flow; otherwise go straight to **execution**.

## First-run config

Interactively ask the user and write `$SKILL_DIR/config.json`, using `$SKILL_DIR/assets/config-template.json` as the skeleton:

1. `github_username`: run `gh api user -q .login` for a suggestion and have the user confirm.
2. `git_authors`: read defaults from `git config --global user.email` and `git config --global user.name`, then ask whether to add more (e.g. email aliases from other machines). Separate by space or comma.
3. `local_git_dirs`: default `~/Work/Projects`; let the user confirm or append.
4. `timezone`: default `Asia/Shanghai`; let the user confirm.
5. `braindump_path`: default `~/Documents/weekly-braindump.md`; let the user confirm or change.
6. `tencent_meeting_dir`: default empty (collector skipped). If the user has Tencent Meeting minutes auto-routed to a directory, point this at it (e.g. `~/Work/Data/tencent-meeting-minutes`). The collector looks for files named `<YYYYMMDDHHMMSS>-<room>-纪要文本-<N>.txt`.
7. `session_min_messages` (default 3), `session_min_duration_seconds` (default 120), `exclude_project_cwds` (default `[]`): mention that these can be edited later in `config.json`.

After writing, read the fields back to the user for a final glance. Then move into the execution flow.

**Full field reference: `references/config-guide.md`.**

## Execution flow

### 1. Resolve the date range

Pick a date pair from the user's message:

- User says `--week 2026-W15`, `2026-W15`, or `week 15` → parse as ISO week.
- User says `2026-04-13 to 2026-04-19` → parse as `--from/--to`.
- User gives no date at all → use the previous complete ISO week. Print the range you picked and have the user confirm ("Using 2026-W15 (2026-04-13 ~ 2026-04-19), okay? Tell me if you want a different range.").

### 2. Collect data in parallel

Run from `$SKILL_DIR` (substituting the actual `--week` or `--from/--to` values):

```bash
cd "$SKILL_DIR"
python3 scripts/collect_claude_code.py     --week 2026-W15 --output .cache/claude_code_sessions.json &
python3 scripts/collect_github.py          --week 2026-W15 --output .cache/github.json &
python3 scripts/collect_local_git.py       --week 2026-W15 --output .cache/local_git.json &
python3 scripts/collect_braindump.py       --week 2026-W15 --output .cache/braindump.md &
python3 scripts/collect_tencent_meeting.py --week 2026-W15 --output .cache/tencent_meetings.json &
wait
```

(In Claude Code the way to run these in parallel is "5 Bash tool calls in a single message"; a single shell `& wait` is fine too — pick your style.)

If any script exits non-zero: read stderr and tell the user what went wrong (common causes: `gh` not logged in, empty `git_authors`, misspelled timezone). **Do not continue to report generation yet.**

### 3. Read and categorize

Read the five files plus `config.json`:

- `.cache/claude_code_sessions.json`
- `.cache/github.json`
- `.cache/local_git.json`
- `.cache/braindump.md`
- `.cache/tencent_meetings.json`
- `config.json` — focus on the `categories` field

**Categorization rules**:
- `categories` is empty → first run: skim every session's `first_user_message`, every commit's `subject`, and every meeting's `topic`/`summary`; cluster into 5–8 natural categories (e.g. "Eng: Project A", "Eng: Project B", "Collaboration", "Learning/exploration", "Misc"). Give each category a `name` and 3–8 `keywords`. Show your grouping to the user for confirmation, then append to `config.json.categories` (with `source: "auto"` and `added_at` = today).
- `categories` is non-empty → assign entries to existing categories by keyword match; if you see a consistent, significant new pattern, propose a new category and append after user confirmation.
- Any category with no activity for > 4 weeks → flag in the appendix: "Category X has had no activity for N weeks — archive?"

**Data source schemas: `references/data-sources.md`.**

### 4. Generate the inward-facing report

Follow `references/report-template.md`. Key sections:

- **Highlights**: TL;DR, 3–5 bullets.
- **Activity by category**: what was actually done in each, with commit SHAs / PR #s / jsonl path references.
- **Time allocation table**: estimate share using Claude Code message counts + commit counts + PR counts per category. Meetings do **not** contribute to this table (duration can't be inferred from minutes).
- **Key decisions**: choices made this week that will affect the future. For each: decision / context / outcome / how to retrieve the original discussion. Meeting bodies are a prime source — treat the full transcript under each meeting's `body` field as primary input here.
- **Reflection**: what went well / what to improve — 2–4 each. If the data isn't enough, say so honestly.
- **Next week**: P0/P1/P2.
- **Appendix**: session list, exploratory aggregate, commit detail, meetings list (with date + room + topic + one-line `summary`, no body).

Exploratory sessions collapse to a single line by default; if one has a standout first message, you can call it out individually. Meetings are always listed individually in the appendix (each one is a distinct event), but their content is **not** pasted into the report body — extract decisions, action items, and context into the appropriate sections (Highlights / Key decisions / Category activity), and link back to the meeting by date and topic for traceback.

**Do not fabricate.** Every factual claim must be traceable to the collected data.

### 5. Write the report

```bash
mkdir -p "$SKILL_DIR/reports"
# write to "$SKILL_DIR/reports/<ISO-week>.md"
```

The ISO week in the filename comes from the resolved range. If the user-specified range doesn't cleanly match an ISO week (e.g. partial or cross-week), use `from..to.md` instead.

### 6. Self-check (subagent)

Use an Explore subagent to verify:
- Pick 3 random factual claims and confirm them against `.cache/*.json` or the original jsonl.
- Do the category shares add up to roughly 100%?
- Were newly-added categories actually written back to `config.json.categories`?

After the subagent reports back, fix any issues before delivering. If a claim cannot be traced, either mark it "(this claim could not be verified from the data sources — please confirm manually)" or remove it.

### 7. Deliver

Tell the user:
- Report path (relative path + `file://` link)
- One-line summary of the data coverage (from the `stats` fields)
- Any unverifiable claims that were kept (if any)
- Category changes (new additions / archive suggestions, if any)

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `gh: not found` | `gh` not installed | `brew install gh && gh auth login` |
| `HTTP 401` from `gh api` | token expired | `gh auth refresh -s repo` |
| `git_authors` is empty | config not filled in | edit `config.json` or trigger the first-run config flow |
| `claude_code_sessions.json` is empty but you know you used it that week | `exclude_project_cwds` filtered it out / wrong timezone | check config; `ls -la ~/.claude/projects/` to see mtimes |
| Script errors with `ZoneInfoNotFoundError` | timezone string misspelled | test with `python3 -c "import zoneinfo; zoneinfo.ZoneInfo('Asia/Shanghai')"` |
| Few commits in the report but you definitely committed locally | `git_authors` not matching (e.g. you switched emails) | add the new email/name to `config.json.git_authors` |
| `tencent_meetings.json` is empty but you know you had meetings | `tencent_meeting_dir` is empty / wrong path / no files land there | check config and `ls <dir>`; make sure the export filename still follows `<14-digit>-<room>-纪要文本-<N>.txt` |
