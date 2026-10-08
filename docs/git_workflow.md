# FleetPulse Git workflow

Use `main` for reviewed, reproducible checkpoints. Make future changes on
focused branches such as `feature/<description>` or `fix/<description>`.
Commit one coherent change with a descriptive imperative subject and, when
useful, a body explaining validation and limitations. Preserve existing history;
do not backdate, make empty milestone commits, amend published commits or force-push.

## Before each commit

```powershell
git status --short --branch
git diff
git add <specific-reviewed-paths>
git diff --cached --stat
git diff --cached --check
.\.venv\Scripts\python.exe scripts/audit_git_index.py
git commit
```

The index audit checks the exact staged/tracked blobs, not just working files.
It rejects data/artifact paths, archive/CSV/Parquet/model/secret filenames,
files above 5 MB, and recognizable credential/private-key patterns. Files
above 1 MB are flagged for review. Pattern scanning is an additional check,
not proof that every possible secret format can be detected. Inspect staged
diffs and never paste credentials into source or reports.

Keep raw VED, generated layers, virtual environments, local secrets, caches,
logs and run-result artifacts out of Git. `.gitkeep` files may preserve directory
layout. Text reports record measured results; sensitive individual traces do
not belong in public demonstrations. Source attribution and acquisition logic
remain checked in; users acquire author data separately under its license.

## Validation

Use the existing environment and validated outputs; do not download or reprocess
the dataset merely to commit. Day 4 fixture checks are:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_day4_gold.py -q --basetemp=data/tmp/pytest-day4
```

Days 2–4 reports describe their own measured full-data validation. Day 4 tests
cover Gold without launching Spark or requiring a sensor corpus. Project-local
temporary directories stay ignored. The configured security approval mechanism
must be used if the environment restricts execution.

## GitHub publication gate

Check `gh auth status` and `git remote -v` first. Git author name/email should
match the user's chosen identity and an email verified on GitHub (or the exact
GitHub-provided noreply address). Never infer a noreply address or publish an
unverified author identity. Use repository-local identity settings if an update
is needed; do not modify global settings without authorization.

Creating a public repository and pushing require explicit user approval.
After approval, confirm owner/name/visibility and remote URL, then use an
ordinary push. Do not embed a token in a remote URL. If authentication is invalid,
the user must complete GitHub authentication before publication. After publishing,
use pull requests with scope, validation and limitations recorded; branch
protection can be configured separately with authorization.

This workflow does not authorize Day 5, model training or dashboard work.
