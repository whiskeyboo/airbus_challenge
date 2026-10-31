# Handoff template

Write updates under your owned `docs/handoffs/agent-<role>/` directory. Keep entries short and concrete. Do not overwrite another agent's status file.

```text
Agent / date / task:
Branch and base commit:
Status: in_progress | ready_for_review | blocked

Outcome:
What now works, for which data mode/airports/horizons?

Files and public interfaces changed:
List owned changes. Identify proposed shared changes separately.

Verification:
Exact commands run:
Exit/results:
Real data or fixtures:
Artifacts and run/data hashes:
What these checks establish:
What remains untested:

Scientific semantics:
Target and population:
Availability assumptions:
Source coverage and exclusions:
Any effect on splits, units, calibration, or label interpretation:

Dependencies / blockers:
Precise missing input or decision:
Independent work completed meanwhile:

Integration request:
What the lead/next agent should do:
Compatibility/migration notes:
Known limitations and next step:
```

For interface proposals add old/new schema versions, consumer impact, and a fixture demonstrating the new contract. Do not say "all tests pass" without recording which tests actually ran.
