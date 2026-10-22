# Task hierarchy and taxonomy

Project Hub stores task structure as journal events. Existing tasks remain
valid: missing taxonomy fields project to `type=task`, `priority=null`,
`parentTask=null`, `links=[]` and `weight=null` without rewriting history.

## Structure

`parentTask` is the single structural parent. Epic, Task and Bug may have
recursive children, while an Epic cannot be placed below a non-Epic task.
Cycles and unknown parents are rejected. Non-hierarchical relations are kept
in `links` with one of `blocks`, `blocked-by`, `related`, `duplicates` or
`duplicated-by`.

## Taxonomy

Task types are `epic`, `task` and `bug`. Priorities are `blocker`, `critical`,
`major`, `minor` and `trivial`. A missing priority is intentional until a user
or agent has enough context to classify it; the migration preview never invents
a priority.

## Progress and closure

`progressAggregate` counts the task's own stages and all descendants. `weight`
is reserved for future weighted progress; equal weighting is the current rule.
`maxDescendantPriority` is derived from unfinished descendants and does not
replace the task's own priority. It is primarily useful on Epics as a compact
signal for the highest-priority work still below them.
Automatic closure is allowed only when all descendants are done or cancelled.
Manual closure is always allowed and records a warning when unfinished children
remain. Tasks are archived or cancelled instead of physically deleted.

## Migration preview

`GET /api/v1/tasks/migration-preview?project=<project>` is read-only. It shows
the projected type, priority and parent for every task and reports how many
rows need review. It writes no journal events.
