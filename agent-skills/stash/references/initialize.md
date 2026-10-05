# Initialize or reassess a project

Use the registered project's directory and the actual stash CLI/server. Existing folders stay in place. For a new empty directory use `stash projects create /absolute/new/path`; the parent must exist. Creating an application scaffold remains part of the user's development task.

Inspect existing memory with `stash --json projects show` and `stash --json context`. If unregistered, use `stash register /absolute/path`. Registration reuses project identity and records; legacy `.trackle/` memory is copied to `.stash/` with the original preserved.

`stash init . --goal "Intended outcome"` can register and perform the first assessment in one command. Its optional `--file` fills empty metadata while preserving human content; it still returns a reviewable assessment.

Establish the intended purpose and requirements from the user or existing documentation. Ask when neither establishes intent. Do not invent missing product requirements.

```sh
stash --actor Codex --kind agent --json assessments run --goal "User's actual intended outcome"
```

Use `--mode new` for a fresh project and `--file /tmp/assessment-request.json` to submit `mode`, `goal`, `requirements` (strings) and optional `run_checks` (advertised names). Inspection checks manifest/Python syntax without executing repository commands. Run available checks only within the user's authorized scope; selecting `run_checks` executes project code. A command failure is an observation to investigate, not proof of a particular bug. Commands are bounded to 60 seconds each and full output is not stored.

Read the saved assessment ID/revision, inspected file references, check results, existing brief/issues/decisions/handoffs, and current Git state. Inspect relevant source entry points, modules, tests and repository docs in place to explain purpose, architecture, implemented features, limitations, and current work. Exclude dependency/build output, secret files, Git internals and symlinks. The initial deterministic assessment has bounded coverage; supplement it with semantic analysis rather than treating source annotations as confirmed bugs.

Submit a refinement using the original assessment revision:

```json
{
  "revision": "revision-returned-by-assessment",
  "proposed": {
    "description": "Purpose supported by inspected documentation/code",
    "purpose": "User's intended outcome",
    "brief": "Architecture and features with file references; observed state; verified checks; assumptions/unknowns; concrete next action",
    "focus": "Actual current focus",
    "next_step": "Concrete supported next task"
  },
  "analysis": "What was inspected and what the evidence supports",
  "findings": [
    {
      "title": "Concrete supported issue",
      "type": "bug",
      "description": "Trigger, observed behavior, expected behavior and reproduction/verification evidence",
      "evidence": ["src/example.ts:42"],
      "confidence": "observed"
    }
  ]
}
```

```sh
stash --actor Codex --kind agent --json assessments refine ASSESSMENT_ID --file /tmp/refinement.json
```

Every finding must reference an observed project file (optional line number) or a recorded check name. Use `inferred` or `needs_review` when behavior is not reproduced. Do not fabricate checks or claim annotations establish defects. Reuse existing issues where appropriate; assessment acceptance matches stable candidate identity or normalized title and preserves existing status and human text.

Review current/proposed metadata and candidates. Select only authorized changes; populated fields are not automatically replaced. Submit the new refinement revision:

```json
{
  "revision": "revision-returned-by-refinement",
  "fields": ["brief", "next_step"],
  "candidates": ["candidate-id-from-the-assessment"],
  "enable_watcher": true
}
```

```sh
stash --actor Codex --kind agent --json assessments approve ASSESSMENT_ID --file /tmp/approval.json
```

Approval saves selected context, deduplicated issues, an initial unfinished session/checkpoint and tracking settings/baseline in one recovery journal. The watcher supplies file facts while stash runs; optional hooks require separate installation/trust and explicit semantic checkpoints. On stale code, Git state, metadata or draft conflicts, reassess and reconcile instead of refreshing the revision blindly.

Run this workflow again to reassess. Keep previous assessments, decisions and sessions historical; absence of a candidate never closes an existing issue. The browser's Overview supports the same inspection, context corrections, candidate review, explicit checks and acceptance; agent refinement JSON can be imported there for human review.
