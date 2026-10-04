# Agent Instructions

Rules for AI agents (and anyone acting as one) working in this repository.

## Commit policy

- **Never commit or push anything unless the user has explicitly asked for it.**
  Finishing a task, passing tests, or reaching "done" is never consent to
  commit. Wait for an explicit instruction in the conversation.

## Workflow

- Development follows the OpenSpec workflow under `openspec/`
  (propose → apply → archive). Use the OpenSpec CLI and skills rather than
  hand-editing change artifacts or hand-scaffolding changes.
- Spec scenarios in `openspec/` are the acceptance criteria: implementation
  work is done when every applicable scenario has a corresponding passing test.

## Quality gates

All implementation work must pass these checks before being considered done:

1. **CodeQL** — static analysis with no new high/critical alerts.
2. **SonarQube** — quality gate passing: no new bugs, vulnerabilities, or
   code smells on changed code.
3. **PR comment review** — review comments are addressed in an autonomous
   loop of **at most 3 iterations**. After 3 iterations, stop and ask the
   user what to do instead of looping further.

(Status: the CI wiring for CodeQL and SonarQube is not yet in place — see
ARCHITECTURE.md, Quality and CI.)

## Maintaining the core documentation

`AGENT.md`, `PRODUCT.md`, and `ARCHITECTURE.md` are the three living documents
of this project. **When something seems like it should be added to or changed
in one of them, do not edit silently: propose the addition to the user and
wait for approval.** This applies during planning, implementation, and review.
