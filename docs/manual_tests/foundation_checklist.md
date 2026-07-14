# Milestone 1 Foundation Step: Manual Test Checklist

Record each test as **Pass**, **Fail**, or **Blocked**.

| Test | Status | Evidence |
| --- | --- | --- |
| Start with `python -m uvicorn app.main:app` | Pass | Uvicorn reported application startup complete on `127.0.0.1:8000`. |
| Request `GET http://127.0.0.1:8000/health` | Pass | Response status was HTTP 200. |
| Verify the health-check response body | Pass | Response body was `{"status":"ok"}`. |
| Stop the application after the check | Pass | The background server job reached the `Stopped` state. |
