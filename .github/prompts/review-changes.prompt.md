# Review Changes

Review the current changes in the Task Tracker repository.

Do not modify production code.

Your job is to find real defects.

---

# Read first

Read:

- root `AGENTS.md`;
- applicable nested `AGENTS.md`;
- relevant `.github/instructions/*.instructions.md`;
- product requirements relevant to the changed code;
- architecture documentation relevant to the changed code.

---

# Review order

Review in this order.

## 1. Correctness

Does the implementation satisfy the intended behavior?

Look for:

- incorrect conditions;
- missing cases;
- invalid state transitions;
- incorrect assumptions;
- race conditions.

---

## 2. Authorization

Check every changed endpoint and resource access.

Verify:

- authentication;
- organization isolation;
- project membership;
- object-level authorization;
- IDOR protection.

Try to reason about:

    User A → Project A

and:

    User A → Project B

The second must fail where appropriate.

---

## 3. Workflow integrity

For task/status changes verify:

    task.project_id == target_status.project_id

Check that:

- statuses are project-specific;
- status IDs are not hardcoded;
- Kanban does not assume fixed columns;
- task movement is validated;
- history is correct.

---

## 4. Database

Review:

- foreign keys;
- constraints;
- indexes;
- nullability;
- deletion behavior;
- transactions;
- migrations;
- existing data.

Look for migrations that are safe only on an empty database.

---

## 5. API

Review:

- request schemas;
- response schemas;
- status codes;
- validation;
- pagination;
- filtering;
- compatibility.

---

## 6. Performance

Look for:

- N+1 queries;
- unnecessary database requests;
- unbounded queries;
- expensive Python-side filtering;
- unnecessary frontend API requests.

Do not report theoretical performance issues
without a plausible impact.

---

## 7. Security

Look for:

- leaked secrets;
- unsafe file access;
- injection;
- authorization bypass;
- unsafe deserialization;
- path traversal;
- SSRF;
- sensitive logging.

---

## 8. Tests

Determine whether the tests actually prove the changed behavior.

Check negative cases,
not only successful requests.

---

# Severity

Use only:

### CRITICAL

Security breach, data loss,
or severe production failure.

### HIGH

Major functional or authorization defect.

### MEDIUM

Real defect or important edge case
that does not block the main workflow.

### LOW

Minor correctness or maintainability issue.

Do not report stylistic preferences as defects.

---

# Finding format

For each issue:

    [SEVERITY] Short title

    File:
    Line:

    Problem:
    Explain the concrete defect.

    Impact:
    Explain what can go wrong.

    Suggested fix:
    Give a concise direction.

Only report findings supported by the actual code.

---

# Final result

If issues exist:

    ## Findings

    [findings]

If no issues exist:

    ## Review result

    No blocking issues found.

    Checked:
    - correctness
    - authorization
    - database integrity
    - API
    - security
    - tests
    - architecture

Do not manufacture findings.
