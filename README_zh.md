# weekly-review（中文版）

一个给自己做 weekly review 并生成周报的 Claude Code skill。

> 英文版见 [`README.md`](README.md)，这是保留的中文版。

聚合四个数据源来还原一周做了什么：
1. **Claude Code 对话记录**（`~/.claude/projects/`）
2. **GitHub PR / Issue / Events**（公开 + 私有仓库，通过 `gh` CLI）
3. **本地 git commits**（配置的所有目录，包括没 push 的）
4. **用户 braindump**（一个纯 markdown 文件，自己随手记的日记）

由 Claude 完成归类、时间分配估算、关键决策梳理、反思和下周计划。

**"一周"是显式给出的固定时段**（比如 `2026-W15` 或 `2026-04-13 到 2026-04-19`），不是"离今天最近的 7 天"。

## 前置条件

- Python 3.9+（stdlib only，不需要装任何依赖）
- `gh` CLI 已安装并登录（`gh auth login`），token 需要 `repo` scope
- `git` CLI

## 安装

```bash
mkdir -p ~/.claude/skills
ln -s "$(pwd)" ~/.claude/skills/weekly-review
```

（`$(pwd)` 要在本项目根目录执行。也可以改成绝对路径 `/Users/you/Work/Projects/weekly-review`。）

验证：

```bash
ls -la ~/.claude/skills/weekly-review
```

应该看到一个软链指向本项目。

## 第一次使用

在任何 Claude Code session 里输入 "写周报" 或 "生成周报"。

第一次会问你 5 个问题来生成 `config.json`：

1. GitHub 用户名（默认从 `gh api user` 读）
2. Git 作者身份列表（默认从 `git config --global user.{email,name}` 读，可以加别的）
3. 本地 git 目录（默认 `~/Work/Projects`）
4. 时区（默认 `Asia/Shanghai`）
5. Braindump 文件路径（默认 `~/Documents/weekly-braindump.md`，不存在会自动创建空文件）

之后的任何一次调用都会直接执行。字段说明见 [`references/config-guide.md`](references/config-guide.md)。

## 使用

在 Claude Code 里触发 skill，然后按需给参数：

- `写周报 2026-W15`
- `写上周的周报`（skill 会自动选上一个完整 ISO 周）
- `生成 2026-04-13 到 2026-04-19 的周报`

产物：`reports/2026-W15.md`（文件名已从 `_周报.md` 改为纯 ISO 周）。

## Braindump 文件格式

两种写法都行：

```markdown
## 2026-04-13 周一
- 和 X 对齐了 Y 的范围
- 下午 Z 性能问题排查到 3 层

## 2026-04-14
- 发布 v0.2.1
- 读完了 xxx 论文
```

或者混着用：

```markdown
- 2026-04-13 和 X 对齐
* 2026-04-14 发布 v0.2.1
```

建议你养成每天往这个文件里随手记几行的习惯 — 周末生成周报的时候就有原材料了。

## 目录结构

```
weekly-review/
├── SKILL.md              # skill 入口（触发词 + 执行流程）
├── README.md             # 英文版（当前仓库默认）
├── README_zh.md          # 本文
├── config.json           # 你的配置（gitignored，首次运行生成）
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
│   └── collect_braindump.py
├── reports/              # 产物（gitignored）
│   └── 2026-W15.md
└── .cache/               # 采集脚本中间产物（gitignored，可删）
```

## 手动跑单个采集脚本（调试用）

每个脚本都可以直接跑：

```bash
cd ~/.claude/skills/weekly-review  # 或项目根目录

# 上一个完整 ISO 周（默认）
python3 scripts/collect_claude_code.py --output .cache/claude_code_sessions.json

# 显式指定 ISO 周
python3 scripts/collect_github.py --week 2026-W15 --output .cache/github.json

# 显式指定日期范围
python3 scripts/collect_local_git.py --from 2026-04-13 --to 2026-04-19 --output .cache/local_git.json

# 看 stderr 里的 range 打印确认时区正确
```

## 不会做的事

- 不采集 Cowork / Claude Desktop 非 CLI 的对话
- 不采集 Linear / Jira / Calendar / 浏览器 / shell history
- 不生成对外周报（v1 只有对内版本）
- 不做敏感信息过滤

需要哪个扩展就手动往 `scripts/` 里加一个同样 CLI 约定（`--from/--to/--week/--config/--output`）的脚本，然后在 `SKILL.md` 的 workflow 里加一行调用。
