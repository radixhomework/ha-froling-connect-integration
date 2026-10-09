# AGENTS.md — working rules for coding agents

Rules for AI agents (and anyone acting as one) working in this repository.
Project-specific details live in the repo's own documentation (see
PRODUCT.md / ARCHITECTURE.md) — read them before touching code.

## Commit policy

- **Commit and push only on the user's explicit demand.** Finishing a
  task, passing tests, or reaching "done" is never consent to commit.
- **Sole exception — quality-check rounds**: when the user asks for a
  quality check (or when the quality-fix loop below is running), the agent
  is autonomous: it commits and pushes its fixes on its own so the fresh
  analyses (Sonar, CodeQL) run, without asking each time.
- If the user asks to hold for local testing, report "done, ready to test"
  and stop — don't ask again; wait for an explicit go.
- Conventional-commit style, English (`feat:`, `fix:`, `refactor:`,
  `docs:` …), body bullets explaining the why. Feature work on `feat/*`
  branches opened as PRs. Quality-fix iterations on the same branch/PR.
- When the working tree contains files the agent did not create, inspect
  them and say so before staging everything.

## Agent-local files are never committed

- **Never stage or commit agent-specific directories and files**
  (`.zcode/`, `.claude/`, `.agents/`, `.cursor/`, `.aider*`, and the like).
  They are machine-local configuration, not project content. This repo's
  `.gitignore` covers them; if a new one appears, propose adding it to
  `.gitignore` rather than committing the path.

## Quality gates

Before calling implementation work done, check all three sources and fix
what they report:

1. **SonarCloud / SonarQube** — quality gate passing; no new bugs,
   vulnerabilities, or smells on changed code.
2. **CodeQL** — no new code-scanning alerts.
3. **PR comments** — bot and human review comments addressed.

(Status: the CI wiring for CodeQL and SonarQube is not yet in place — see
ARCHITECTURE.md, Quality and CI.)

## Iteration policy

Fix what was found, push, wait for fresh analyses, then re-check all three
sources — repeat until clean.

**Stop rule: 3 iterations maximum, autonomously.** After 3 fix/verify
iterations, stop and report remaining findings and what was tried; wait for
the user's decision instead of looping further.

**During these fix/verify rounds the agent is autonomous**: it commits and
pushes each fix itself (this is the only case where committing without an
explicit user demand is allowed — see Commit policy), within the
quality-check scope only. It does not use that autonomy to commit anything
unrelated to the findings.

## Testing stance

- Do not build heavy test suites unless asked. Verify by compiling,
  building, and exercising the real endpoints/pages.
- When the user says to do fewer tests and move on, move on — don't stall
  on ceremony.
- Exception in this repository: the OpenSpec spec scenarios are the
  acceptance criteria (see Workflow), so tests covering them are required
  work, not ceremony.

## Workflow

- Development follows the OpenSpec workflow under `openspec/`
  (propose → apply → archive): `/opsx:propose` (planning only — never
  implement in the same turn), `/opsx:apply` (task-by-task, tick
  checkboxes), `/opsx:archive` when done. Use the OpenSpec CLI and skills
  rather than hand-editing change artifacts or hand-scaffolding changes.
- Spec scenarios in `openspec/` are the acceptance criteria: implementation
  work is done when every applicable scenario has a corresponding passing
  test.
- **Documentation is part of the workflow**: planning artifacts, spec
  updates, and the PRODUCT.md / ARCHITECTURE.md changes implied by a change
  are maintained as the change progresses — not deferred to "later".
  `/opsx:archive` is only done once the documentation reflects the
  implemented behavior.

## Product & architecture documentation

**`PRODUCT.md` and `ARCHITECTURE.md` are mandatory in every repository and
must be kept up to date as part of the development process — not as an
afterthought.**

- **Maintain them continuously**: any feature, refactor, or infrastructure
  change that alters behavior, structure, or deployment includes the
  corresponding doc update in the same change — same commit series.
  Documentation drift is treated as incomplete work.
- When starting a task, read both files first; if the code and the docs
  disagree, surface the discrepancy to the user instead of silently
  trusting either one.

## Documentation edits need approval

`AGENTS.md`, `PRODUCT.md`, and `ARCHITECTURE.md` are the three living
documents of this project. **When something seems like it should be added to
or changed in one of them, do not edit silently: propose the change to the
user and wait for approval.** This applies during planning, implementation,
and review — including routine syncs.

## Keeping this file honest

Delete any section that doesn't apply to this repository, and add
repo-specific sections (stack conventions, build/test commands) below.
