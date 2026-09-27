# Fix Bug

You are fixing a bug in the Task Tracker repository.

## Bug report

Use the bug description provided by the user as the primary input.

Do not assume the reported root cause is correct.

---

# Required workflow

## 1. Understand the bug

Read:

- root `AGENTS.md`;
- relevant nested `AGENTS.md`;
- applicable instructions;
- related product requirements;
- relevant implementation.

Identify:

- expected behavior;
- actual behavior;
- affected component;
- likely failure boundary.

---

# 2. Reproduce

Before changing production code, try to reproduce the problem.

Use:

- existing tests;
- API calls;
- local environment;
- targeted test;
- logs where available.

If reproduction is not possible,
state that explicitly.

Do not claim that the bug was reproduced if it was not.

---

# 3. Find root cause

Do not fix only the visible symptom.

Trace the flow:

    request
      ↓
    validation
      ↓
    authorization
      ↓
    service
      ↓
    repository
      ↓
    database

For frontend issues trace:

    user action
      ↓
    component
      ↓
    state/query
      ↓
    API
      ↓
    response
      ↓
    UI

Determine the actual root cause.

---

# 4. Regression test

Before fixing the bug, add a regression test whenever practical.

The regression test should fail with the buggy implementation
and pass after the fix.

The test should describe the expected behavior,
not the implementation details.

---

# 5. Implement the fix

Make the smallest correct change.

Do not:

- rewrite unrelated code;
- upgrade dependencies;
- refactor unrelated modules;
- change architecture unnecessarily.

If the bug reveals an architectural problem,
fix only what is necessary to restore the invariant.

---

# 6. Security

For authorization-related bugs,
verify both:

### Positive case

Authorized user can perform the operation.

### Negative case

Unauthorized user cannot perform the operation.

For resource isolation verify:

    Project A user
        ≠
    Project B resource

---

# 7. Workflow bugs

For task/status bugs verify:

    task.project_id == status.project_id

and test multiple projects with different workflows.

Never solve workflow bugs by hardcoding status names or IDs.

---

# 8. Validate

Run relevant tests.

Backend:

    make lint
    make typecheck
    make test

Frontend:

    make lint
    make typecheck
    make test-frontend

Run the regression test explicitly if useful.

---

# 9. Final review

Check:

- root cause actually fixed;
- regression test exists;
- no unrelated changes;
- authorization preserved;
- migration safe if applicable;
- no debug code;
- no secrets.

---

# Final response

Return:

## Root cause

What actually caused the bug.

## Fix

What changed.

## Regression test

What test was added.

## Validation

Commands actually executed.

## Notes

Any remaining limitations.
