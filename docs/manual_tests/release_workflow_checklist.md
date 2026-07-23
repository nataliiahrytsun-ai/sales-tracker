# Milestone 3 Release Workflow: Manual Test Checklist

Record each test as **Pass**, **Fail**, or **Blocked**. Local checks use only a
temporary SQLite database and do not represent a production deployment.

| Test | Status | Evidence |
| --- | --- | --- |
| Release check accepts exact successful `/health` and `/ready` responses | Pass | Local smoke test against a temporary current-head database returned exit code 0. |
| Release check handles a base URL with a trailing slash | Pass | Automated isolated test confirmed normalized `/health` and `/ready` URLs. |
| Release check rejects non-HTTP(S) URLs and embedded credentials | Pass | Automated isolated tests returned safe validation failures without network access. |
| Release check fails when `/ready` returns HTTP 503 | Pass | Local smoke test changed only the temporary revision and returned a nonzero exit code. |
| Failed release check omits database paths, revisions, response bodies, and tracebacks | Pass | Local smoke output contained only the endpoint and HTTP status category. |
| Pre-release backup is created and verified against production storage | Blocked | Requires the real production database and approved backup location. |
| Production SQLite path is confirmed as persistent storage | Blocked | Hosting and persistent storage are not selected. |
| Production migration completes during the approved release window | Blocked | No production deployment is performed in this task. |
| Production application starts from the selected CI-verified commit | Blocked | Requires a committed release and production runtime. |
| Production rollback is rehearsed with approved data-loss handling | Blocked | Requires production operational approval and rollback window. |
| Real production domain and HTTPS endpoints pass release check | Blocked | Domain and HTTPS termination remain undecided. |
