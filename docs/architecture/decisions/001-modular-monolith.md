# ADR-001: Use a Modular Monolith

## Status

Accepted

## Date

2026-09-27

## Context

The product is a self-hosted task tracker.

The initial product consists of several related domains:

* organizations;
* users;
* teams;
* projects;
* project members;
* project workflows;
* tasks;
* comments;
* attachments;
* notifications;
* search;
* saved filters.

These domains have many direct relationships and share the same authorization and transactional boundaries.

A microservice architecture would introduce additional operational complexity:

* service discovery;
* network communication;
* distributed authentication context;
* multiple deployment units;
* distributed transactions;
* inter-service failures;
* duplicated infrastructure;
* more complicated local development.

The MVP does not require independent scaling or independent deployment of these domains.

## Decision

The backend will be implemented as a **modular monolith**.

All MVP backend domains run inside one FastAPI application and one deployment unit.

The codebase must still maintain explicit domain and layer boundaries.

The architecture must not become an unstructured monolith.

---

## Structure

The backend uses explicit layers:

```text
Router
  ↓
Schema
  ↓
Authorization
  ↓
Service
  ↓
Repository
  ↓
Database
```

Domains should be separated logically even though they share one application process and database.

---

## Consequences

### Positive

* simple local development;
* simple self-hosted deployment;
* straightforward database transactions;
* low network overhead;
* easier debugging;
* fewer infrastructure dependencies;
* easier Codex-assisted development;
* simpler API contracts between domains.

### Negative

* one deployment unit;
* less independent scaling;
* stronger coupling through the shared database;
* future extraction requires deliberate boundaries.

---

## Rules

The modular monolith must not become an excuse for unrestricted coupling.

New functionality must:

1. have a clear domain owner;
2. use explicit service boundaries;
3. avoid direct access to another module's internals;
4. use repositories for persistence;
5. keep authorization at the appropriate boundary.

Cross-domain dependencies must be documented when they become significant.

---

## Future Extraction

A module may be extracted into a separate service only when there is a concrete reason, such as:

* independent scaling requirements;
* independent deployment requirements;
* significant operational isolation;
* clear ownership boundary;
* measurable performance or reliability benefit.

Microservices must not be introduced speculatively.

## Rejected Alternative

### Microservices from the beginning

Rejected for the MVP because the operational and distributed-system complexity is not justified by current product requirements.

The system may evolve toward services later without requiring the MVP to start with that architecture.
