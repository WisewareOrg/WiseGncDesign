# Contributing to WiseGncDesign

WiseGncDesign is public. Tickets, branches, pull-request linkage and pull-request titles follow
[WisewareOrg/.github's PROCESS.md](https://github.com/WisewareOrg/.github/blob/main/PROCESS.md),
not restated here.

## CI checks

Every pull request against the default branch runs `process-gates.yml`:

- `check-branch` — the branch is named `<type>_<number>-<name>` for an open, milestoned issue
  carrying exactly one type label, and the PR's Development field links that issue
  (PROCESS.md PROC-001–PROC-008, PROC-010).
- `pr-title` — the PR title is a Conventional Commits subject (PROC-009).
- `repo-floor` — the repository's rulesets meet [`repository-floor.yml`](https://github.com/WisewareOrg/.github/blob/main/repository-floor.yml)
  (PROC-011).

A PR whose base is not the default branch needs the Development-field link written by hand — see
WiseKiosk's [`link-pr` skill](https://github.com/WisewareOrg/WiseKiosk/blob/main/.claude/skills/link-pr/SKILL.md)
for the GraphQL mutation; `Closes #N` in the body only writes that record on a default-base PR.

`checks.yml` runs the lint, requirements and test jobs; see the
[README's Recipes and CI section](README.md#recipes-and-ci).

## Generated code

**Generated code is never committed.** Only hand-written sources are tracked: FPP, `.in`
templates, CMake, Python, C++ and docs. Anything rendered or generated (rendered templates, F´
autocoder output, generated converters, dictionaries, built extensions) is produced at build or
import time into a build or temp directory and stays untracked. A Python build's dictionary is one
case, generated into a temp dir as
[ADR 0004 rev 2](docs/decisions/0004-hold-both-builds-to-one-fpp-contract-spoken-in-fprime-s-names.md)
records.
