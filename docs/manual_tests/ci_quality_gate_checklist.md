# Milestone 3 CI Quality Gate: Manual Test Checklist

Record each test as **Pass**, **Fail**, or **Blocked**.

| Test | Status | Evidence |
| --- | --- | --- |
| Workflow YAML defines one `quality-gate` job with Python 3.12 | Pass | Local inspection of `.github/workflows/ci.yml`. |
| Workflow triggers on pushes to `main`, pull requests targeting `main`, and manual dispatch | Pass | Local inspection of workflow triggers. |
| CI commands match the documented local dependency, compile, Alembic, and full pytest checks | Pass | Local CI-equivalent commands completed successfully. |
| CI SQLite and pytest temporary paths use `$RUNNER_TEMP` | Pass | The pytest step environment and command reference only the runner temporary directory. |
| Workflow contains no deploy, secrets, matrix, caching, artifacts, or ignored failures | Pass | Local workflow audit completed. |
| The workflow appears in the GitHub Actions interface | Blocked | Requires commit and push, which are outside this task. |
| A push to `main` completes `quality-gate` successfully | Blocked | First real GitHub-hosted run requires commit and push. |
| A pull request targeting `main` completes `quality-gate` successfully | Blocked | Requires a pushed branch and pull request. |
| `quality-gate` is configured as a required status check or Ruleset condition | Blocked | Repository settings must be configured separately. |
| Future deployment depends on successful `quality-gate` completion | Blocked | Deployment is intentionally outside this CI-only task. |
