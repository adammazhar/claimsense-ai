# CLAUDE.md

Standing rules for every session in this repository. They apply to all work, in every milestone.

## Language

- Write in **American English** everywhere: docs, code, comments, identifiers, commit messages and
  diagram labels. For example: color, labeled, modeling, organize, license, behavior, center,
  canceled, gray, artifact, defense, analyze.
- Before any commit, sweep the files you changed for British spellings.

## Shell and commits

- The shell is **Windows PowerShell 5.1**.
- Commit messages go in a file in `tmp/` and are committed with `git commit -F tmp/<file>`.
  PowerShell 5.1 doesn't pipe a here-string to a native command's stdin.
- **Never commit** `.env`, `docs/ik/` or `tmp/`. Before staging, check that nothing under them is
  staged.
- **Show `git status` and get the user's approval before any commit or push.** Approval for one
  commit doesn't extend to the next.

## Processes

- Stop only processes you started, and only by their exact PID. Never stop processes by name.

## Requirements

- The course materials in `docs/ik/` are the source of requirements.
- The brief in `docs/ik/` (`ClaimSense AI capstone - Brief, submissions and grading.pdf`) is the
  **grading source of truth**. Where another document disagrees with it, the brief wins.
- `docs/ik/` is never committed.

## Checks to run before showing git status

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe scripts\check_eval_cases.py
```

- **Regenerate derived files after their source changes.** After changing a contract, run
  `scripts/generate_schemas.py`. After changing an eval case, run `scripts/build_fixtures.py`. After
  changing a pricing input, update `docs/engagement/pricing.md` to match `scripts/pricing.py`.
- **Keep the page limits.** The charter and the SoW must each fit 2 pages when rendered. Render
  them into `tmp/` to check.
