<purpose>

Mark a completed research milestone (for example v1.0, v1.1, or v2.0) as done,
archive the milestone evidence, update MILESTONES.md through the CLI writer, and
prepare the next research stage.

Milestone completion is allowed only after included phases have completed their
verification/readiness-gated phase closeout. A phase that has not passed
`gpd --raw phase closeout-readiness <phase> --require-verification` and
`gpd phase complete <phase>` is not ready for milestone archive.

</purpose>

<required_reading>

1. `{GPD_INSTALL_DIR}/templates/milestone.md`
2. `{GPD_INSTALL_DIR}/templates/milestone-archive.md`
3. `GPD/ROADMAP.md`
4. `GPD/REQUIREMENTS.md`
5. `GPD/PROJECT.md`

</required_reading>

<archival_behavior>

When a research milestone completes, the CLI owns the durable archive/write
transaction:

1. Archive ROADMAP evidence to `GPD/milestones/v[X.Y]-ROADMAP.md`
2. Archive requirements to `GPD/milestones/v[X.Y]-REQUIREMENTS.md`
3. Move an optional milestone audit file into `GPD/milestones/`
4. Write or upsert the MILESTONES.md entry
5. Update STATE/state.json through the canonical state path
6. Sync checkpoint shelf metadata

**Context Efficiency:** Archives keep ROADMAP.md and REQUIREMENTS.md from
becoming the only history source.

**ROADMAP archive** uses `{GPD_INSTALL_DIR}/templates/milestone-archive.md`.
Load the template only when writing or checking archive content.

</archival_behavior>

<authority_boundary>

- `gpd milestone complete` is the single source of truth for archive files,
  MILESTONES.md entry shape, roadmap-plus-disk union readiness, state update,
  optional audit capture, and rollback on failure.
- Do not manually append a MILESTONES.md entry before or after the CLI writer.
- Do not delete or rewrite source planning files unless the archive exists and
  the workflow has explicit user confirmation for that destructive branch.
- Branch handling is a user-confirmed operational step, not a prompt-local shell
  parser. Present exact commands only after the branch set and action are known.

</authority_boundary>

<process>

<step name="verify_readiness">

Use the same readiness semantics as `gpd milestone complete`: the milestone
phase set is the roadmap-plus-disk union.

```bash
ROADMAP=$(gpd --raw roadmap analyze)
```

The roadmap-plus-disk union includes roadmap phases and on-disk phase
directories. Standalone `PLAN.md` / `SUMMARY.md` artifacts count the same as
numbered `*-PLAN.md` / `*-SUMMARY.md` artifacts.

Verify before continuing:

- every included phase is closed;
- any current phase with complete summaries has gone through `gpd phase
  complete` after readiness passed;
- missing, stale, or non-passing verification is routed to `gpd:verify-work`;
- phase count and plan count match the CLI readiness view;
- `progress_percent` is 100 percent for the included milestone scope.

Present a concise scope summary:

```text
Milestone: v[X.Y] [Name]
Includes: [phase range or list]
Status: all included phases closed
Plans: [completed]/[total]
```

If scope is ambiguous, ask whether to wait, adjust scope, or continue with the
detected milestone. In supervised/custom confirmation modes, wait for explicit
approval before archive mutation.

</step>

<step name="extract_accomplishments">

Use summary artifacts to identify 4-6 research accomplishments. Prefer the
summary frontmatter/body one-liner helper:

```bash
gpd --raw summary-extract "$summary" --field one_liner | gpd json get .one_liner --default ""
```

Do not build a separate MILESTONES.md entry by hand. The extracted
accomplishments are context for review; `gpd milestone complete` writes the
entry.

</step>

<step name="research_digest">

Create `GPD/milestones/v[X.Y]/RESEARCH-DIGEST.md` only when it adds useful
research synthesis beyond the archived roadmap and summaries.

Keep it compact:

- narrative arc;
- key results and evidence paths;
- methods and conventions that changed;
- open questions and next-stage risks;
- dependency graph or carry-forward notes that future phases need.

Use loaded summaries, requirements, project state, convention lock, result
registry, and paper/figure paths as evidence. Do not paste a long template into
the prompt; load or draft only the sections needed for the milestone.

</step>

<step name="project_evolution_review">

Review `GPD/PROJECT.md` once at milestone scale:

- update "What This Is" and the core research question if the project evolved;
- move completed requirements to validated status with milestone reference;
- keep still-active requirements visible for the next stage;
- add or revise limitations, out-of-scope items, parameter regimes, and known
  risks;
- record durable decisions with outcomes when the summaries justify them.

Keep edits evidence-backed. Do not convert uncertain results into validated
project facts.

</step>

<step name="archive_milestone">

Run the archive writer after readiness, optional digest creation, and project
review are complete:

```bash
ARCHIVE=$(gpd milestone complete "v[X.Y]" --name "[Milestone Name]")
```

Stop on failure. The writer handles archive creation, MILESTONES.md upsert,
state update, checkpoint sync, and rollback of partial archive writes.

The MILESTONES.md entry includes version, date, phase/plan/task counts,
accomplishments extracted from summary artifacts (`SUMMARY.md` and
`*-SUMMARY.md`), and an `**Archived evidence:**` block listing roadmap,
requirements, research digest, and audit archive paths. Missing audit/digest
evidence is encoded by the writer; never add free-form "NOT PRESENT" lines.

</step>

<step name="archive_cleanup_confirmation">

Only after archive files exist, ask before any destructive cleanup or roadmap
reorganization. Use the standard checkpoint prompt shape:

```text
Archive cleanup [Y/n/e]
Y - continue with the selected cleanup/reorganization
n - leave source planning files as-is
e - edit the cleanup scope, then ask again
```

**Edit branch:** If the user chooses `e`, collect the custom cleanup scope or
push options, render the exact action that would run, and re-present the updated `[Y/n/e]` prompt once
before mutating. Do not treat the edit text itself as approval.

Archive-before-delete is mandatory. If any expected archive path is missing,
skip cleanup and report the missing path.

</step>

<step name="branch_and_tag">

Branch and tag handling is optional and user-confirmed. Do not parse git branch
names in prompt prose. Inspect branches with normal git tooling only when the
researcher asks for branch handling or the init/context payload already names a
branch strategy.

**For "per-phase" strategy:**
```bash
if [ "$BRANCHING_STRATEGY" = "per-phase" ]; then
  echo "Merge or preserve completed phase branches only after user confirmation."
fi
```

**For "per-milestone" strategy:**
```bash
if [ "$BRANCHING_STRATEGY" = "per-milestone" ]; then
  echo "Merge or preserve the milestone branch only after user confirmation."
fi
```

Present a compact choice:

```text
Branch/tag action [Y/n/e]
Y - create the selected tag or perform the selected merge/push
n - leave branches/tags unchanged
e - edit the branch, remote, tag, or push options, then ask again
```

**Edit branch:** If the user chooses `e`, collect the custom remote or push
options, render the exact push command that would run, and re-present the updated `[Y/n/e]` prompt once
before pushing. Do not treat the edit text itself as approval.

Never force-delete branches without explicit confirmation that names the
branches.

</step>

<step name="commit_and_next">

Commit milestone archive/project changes after validation. Include only files
changed by this workflow.

Then route the next stage:

## > Next Up

Primary: `gpd:new-milestone`

If the researcher is continuing immediately, collect the new milestone goal and
use `gpd:new-milestone` rather than embedding new milestone planning here.

</step>

</process>

<output>

Report:

```markdown
## Milestone v[X.Y] Complete

Archive writer: `gpd milestone complete "v[X.Y]" --name "[Milestone Name]"`

Archived:
- `GPD/milestones/v[X.Y]-ROADMAP.md`
- `GPD/milestones/v[X.Y]-REQUIREMENTS.md`
- `GPD/milestones/v[X.Y]/RESEARCH-DIGEST.md` if created
- optional audit archive if present

Updated:
- `GPD/MILESTONES.md`
- `GPD/PROJECT.md` if project evolution was needed
- `GPD/STATE.md` / `GPD/state.json` through the CLI writer

## > Next Up

Primary: `gpd:new-milestone`
```

</output>

<checklist>

- [ ] All included phases are closed after verification/readiness-gated closeout
- [ ] Milestone scope was confirmed when ambiguous
- [ ] Accomplishments came from summary artifacts
- [ ] Optional research digest is evidence-backed and compact
- [ ] `gpd milestone complete` wrote archive/MILESTONES/state outputs
- [ ] Archive paths exist before cleanup or deletion
- [ ] `[Y/n/e]` edit branches require re-confirmation before mutation
- [ ] Next command uses `## > Next Up`

</checklist>
