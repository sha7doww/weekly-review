# Inward weekly review template (v1)

Every section is written **for yourself**: you can be candid, emotional, and admit when you don't know.

Filename: `reports/YYYY-Www.md`, using the ISO week number (Monday-starting). Example: `2026-W15.md` covers 2026-04-13 ~ 2026-04-19.

## Template

```markdown
# 2026-W15 Weekly Review (2026-04-13 ~ 2026-04-19, Asia/Shanghai)

> Generated: 2026-04-20 10:00
> Data coverage: 17 substantive + 9 exploratory Claude Code sessions; 7 PRs / 2 issues / 54 GitHub events; 38 local commits across 6 repos; 5 braindump entries.

## Highlights (TL;DR)
- The 3–5 things most worth remembering, one line each.
- Pointers to details: "see §X".

## Activity by category

### Eng: AutoIdea (time share ~45%)
- What you actually did (concrete: features / files / outcomes, with commit SHAs or PR numbers)
- Reference sessions: [session abc123](/Users/.../abc123.jsonl) (use file:// links to jsonl_path for future traceback)

### Eng: weekly-review (time share ~20%)
...

### Other: misc / comms / learning (time share ~15%)
...

> If **Other** keeps exceeding 20% → consider promoting it to a new named category.

## Time allocation table

| Category | Claude Code messages | Local commits | PRs | Estimated share |
|---|---|---|---|---|
| Eng: AutoIdea | 120 | 22 | 4 | 45% |
| ... |

Shares are **rough estimates**, weighted by message count — precision is not the point.

## Key decisions

For each **choice made this week that will affect the future**, write a short block:

- **Decision**: replace X with Y
- **Context**: X was causing … under high concurrency
- **Outcome**: keeping X for now; re-evaluate after next week's load test
- **Where to look it up again**: session xxx / PR #42 / braindump 2026-04-15

## Reflection

### What went well
- 2–4 items. Be concrete — "finished on time" doesn't count.

### What to improve
- 2–4 items. Be honest. No moralizing.
- Possible action: ……

## Next week

- **P0 (must-do)**: 1–3 items
- **P1 (should-do)**: 2–4 items
- **P2 (could-do)**: everything else

## One-line reminder to self

> …… one line.

---

## Appendix: data references

<details>
<summary>Claude Code sessions included</summary>

- [2026-04-13 10:15-11:40 AutoIdea](file:///Users/.../abc123.jsonl) (15 user msgs)
- ...

</details>

<details>
<summary>Exploratory sessions aggregated (not expanded)</summary>

9 short chats covering: xxx, yyy, zzz (Claude's summary)

</details>

<details>
<summary>Commit detail</summary>

- `abc123` feat: ... (+48 / -12, 3 files) — AutoIdea@main
- ...

</details>
```

## Principles when generating

1. **Don't fabricate.** Every factual claim must be traceable to `.cache/*.json` or the original jsonl.
2. **Short beats vague.** "Replaced X with Y" is better than "performed architectural optimization."
3. **Back time shares with data.** Weight by messages + commits + PRs, not gut feel.
4. **Keep the links.** Embed jsonl paths, PR URLs, commit SHAs in the report so you can retrace later.
5. **Always write reflection.** If the data isn't enough for real reflection, say exactly that: "the data this week doesn't support clear reflection — remember to log braindump next time."

## Self-check

After writing, have a subagent do 3 things:
1. Pick 3 random factual claims and verify them against the original jsonl / github.json.
2. Check that the shares add up to roughly 100%.
3. Check that every category appears in `config.json.categories` (any new ones must have been appended back).
