# weekly-review

A Claude Code skill that generates a personal, inward-facing weekly review report.

It aggregates five data sources to reconstruct what you actually did in a given week:
1. **Claude Code conversations** (`~/.claude/projects/`)
2. **GitHub PRs / issues / events** (public + private repos, via the `gh` CLI)
3. **Local git commits** (all configured directories, including commits that were never pushed)
4. **User braindump** (a plain markdown file where you jot things down day to day)
5. **Tencent Meeting minutes** (optional — AI-generated `.txt` transcripts auto-routed to a local directory)

Claude does the clustering, time-share estimation, key-decision writeup, reflection, and next-week planning.

**"A week" is always an explicit fixed range** (e.g. `2026-W15` or `2026-04-13 to 2026-04-19`), never "the last 7 days from today."

A Chinese version of this README is kept at [`README_zh.md`](README_zh.md).

## Prerequisites

- Python 3.9+ (stdlib only — no package installs required)
- `gh` CLI installed and logged in (`gh auth login`); the token needs the `repo` scope
- `git` CLI

## Install

```bash
mkdir -p ~/.claude/skills
ln -s "$(pwd)" ~/.claude/skills/weekly-review
```

(Run `$(pwd)` from this project's root. You can also use an absolute path like `/Users/you/Work/Tools/weekly-review`.)

Verify:

```bash
ls -la ~/.claude/skills/weekly-review
```

You should see a symlink pointing to this project.

## First run

In any Claude Code session, say something like "write a weekly review" or "generate weekly review".

On the first run, the skill asks you 6 questions to create `config.json`:

1. GitHub username (default read from `gh api user`)
2. Git author identities (default read from `git config --global user.{email,name}`; you can add more)
3. Local git directories (default `~/Work/Projects`)
4. Timezone (default `Asia/Shanghai`)
5. Braindump file path (default `~/Documents/weekly-braindump.md`; an empty file is created if it doesn't exist)
6. Tencent Meeting minutes directory (default empty — skip the collector; point this at the directory where Tencent Meeting `.txt` exports land if you want meetings folded into the review)

All subsequent runs go straight to execution. Field reference: [`references/config-guide.md`](references/config-guide.md).

## Usage

Invoke the skill in Claude Code and pass arguments as needed:

- `write weekly review 2026-W15`
- `write last week's review` (picks the previous complete ISO week automatically)
- `generate weekly review for 2026-04-13 to 2026-04-19`

Output: `reports/2026-W15.md`.

## Braindump format

Either style works:

```markdown
## 2026-04-13 Mon
- aligned scope of Y with X
- spent the afternoon chasing a perf issue in Z

## 2026-04-14
- shipped v0.2.1
- finished reading the xxx paper
```

Or mixed inline bullets:

```markdown
- 2026-04-13 aligned with X
* 2026-04-14 shipped v0.2.1
```

Jotting a few lines into this file every day gives the weekend review something real to work with.

## Directory layout

```
weekly-review/
├── SKILL.md              # skill entry point (triggers + workflow)
├── README.md             # this file
├── README_zh.md          # Chinese translation
├── config.json           # your config (gitignored, created on first run)
├── docs/                 # sidecar docs for integrations and setup
│   └── TENCENT_MEETING.md
├── assets/
│   └── config-template.json
├── references/
│   ├── config-guide.md
│   ├── data-sources.md
│   └── report-template.md
├── scripts/
│   ├── _common.py
│   ├── collect_claude_code.py
│   ├── collect_github.py
│   ├── collect_local_git.py
│   ├── collect_braindump.py
│   └── collect_tencent_meeting.py
├── reports/              # output (gitignored)
│   └── 2026-W15.md
└── .cache/               # collector intermediate files (gitignored, safe to delete)
```

## Running collectors manually (for debugging)

Every collector can be run standalone:

```bash
cd ~/.claude/skills/weekly-review  # or the project root

# previous complete ISO week (default)
python3 scripts/collect_claude_code.py --output .cache/claude_code_sessions.json

# explicit ISO week
python3 scripts/collect_github.py --week 2026-W15 --output .cache/github.json

# explicit date range
python3 scripts/collect_local_git.py --from 2026-04-13 --to 2026-04-19 --output .cache/local_git.json

# tencent meeting minutes (requires config.tencent_meeting_dir to be set)
python3 scripts/collect_tencent_meeting.py --week 2026-W15 --output .cache/tencent_meetings.json

# the `[range]` line on stderr confirms the timezone conversion
```

## Tencent Meeting minutes (optional)

To fold Tencent Meeting AI-generated transcripts into the review:

1. Arrange for exports to land in a directory of your choice ([`docs/TENCENT_MEETING.md`](docs/TENCENT_MEETING.md) walks through a launchd-based auto-router for `~/Downloads`).
2. Set `tencent_meeting_dir` in `config.json` to that directory.
3. The collector picks up `.txt` files named `<YYYYMMDDHHMMSS>-<room>-纪要文本-<N>.txt` and uses the embedded `会议主题` / `发言人` / `会议摘要` header plus the transcript body.

Meeting content feeds into the *highlights* and *key decisions* sections of the report; a per-meeting appendix lists date / room / topic / summary for traceback. Meetings do not count toward the time-allocation table.

## What this skill deliberately does *not* do

- Does not collect Cowork / Claude Desktop (non-CLI) conversations
- Does not collect Linear / Jira / Calendar / browser history / shell history
- Does not generate outward-facing weekly reports (v1 is inward only)
- Does not filter sensitive information

If you need one of these, drop a script under `scripts/` following the same CLI convention (`--from/--to/--week/--config/--output`) and add one line to the workflow in `SKILL.md`.
