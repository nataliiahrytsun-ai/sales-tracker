# AGENTS.md

## Source of Truth

Product requirements: `docs/Implementation_Plan.docx`

Implementation milestones: `docs/MILESTONES.md`

Initial UI mockup: `docs/Zeichnung.svg`

The Implementation Plan defines product behavior, scope, business rules, and acceptance criteria.

Do not invent product functionality. If a product requirement, permission, or business rule is unclear, explain the ambiguity and ask for clarification.

For minor technical decisions that do not change product behavior, choose the simplest conventional solution.

## Scope

* Implement only the requested phase or task.
* Do not implement future enhancements unless explicitly requested.
* Keep changes small and avoid unrelated refactoring.
* Do not add unnecessary dependencies.

## Project Setup

If the project structure does not exist, create a simple conventional FastAPI structure suitable for the requested phase.

Keep configuration, routes, database models, business logic, templates, static files, migrations, and tests separated.

Do not create components that are not needed for the current phase.

## Technology Stack

Backend:

* Python 3.12
* FastAPI
* SQLModel
* SQLite
* Alembic

Frontend:

* Jinja2
* HTMX
* Chart.js
* Minimal JavaScript
* Responsive CSS

Do not replace this stack without an explicit requirement.

## Code Quality

* Follow PEP 8 and use type hints.
* Prefer readability over clever abstractions.
* Keep functions small and focused.
* Keep business logic out of routes and templates.
* Reuse existing code where practical.

## Database

* Use Alembic for schema changes.
* Enable SQLite foreign keys.
* Preserve existing data where practical.
* Enforce one outreach record per user and date at the database level.

## Product Invariants

* A mismatch between country totals and unique companies shows a warning but does not prevent saving.
* Missing mood remains missing and is not treated as neutral.
* Rates must safely handle missing values and division by zero.
* Use the exact values and definitions from the Implementation Plan.

## Users, Security, and Privacy

* The application has one authenticated user type; do not implement separate roles.
* All authenticated users have the same application permissions.
* Users may create, edit, and delete only their own activity records.
* Dashboard and export access is available to all authenticated users.
* Never store plaintext passwords.
* Enforce authentication and record ownership on the server.
* Treat employee sentiment as sensitive data and expose it only to authenticated users.
* Store and log only necessary information.

## Testing

Before completing a task:

- Add or update relevant unit tests.
- Run the relevant unit tests and configured project checks.
- Fix failures caused by the changes.
- Verify migrations and database constraints when applicable.
- Ensure existing functionality still works.

Before completing a milestone:

- Run the full unit test suite.
- Perform the milestone manual test checklist.
- Record the commands, results, and any unresolved defects.
- Do not mark the milestone complete if required tests fail.

In the final response, summarize changed files, automated test results,
manual test results, migrations, and unresolved issues.