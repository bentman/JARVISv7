# Extensions Desktop Acceptance (windows-amd64)

ADR 0006 requires the Extensions panel to work as a control surface in the native
desktop on `windows-amd64`. That host class cannot be exercised from a Linux
development host, so this checklist produces the missing evidence.

Record for each step: the step number, `PASS` / `FAIL` / `SKIPPED`, and what was
observed. Report the host class as `windows-amd64` and attach the backend log path
for any failure.

## Preparation

```powershell
.\backend\.venv\Scripts\python scripts\validate_backend.py profile
.\backend\.venv\Scripts\python scripts\run_backend.py
npm --prefix desktop run tauri dev
```

The backend must report `readiness=ready` before starting the desktop. Open the
advanced control panel and select the **Extensions** category.

## Checklist

| # | Step | Expected observation |
|---|---|---|
| 1 | Open the Extensions category | List/detail split renders; families are listed with counts; no load errors unless a definition is genuinely broken |
| 2 | Filter by family | The list narrows and the selected extension stays selected if it still matches |
| 3 | Select a `skill` extension, choose **Show body** | The skill body renders in a collapsed block; it is read on demand, not preloaded |
| 4 | Select any extension and read its detail | Version, source, provenance, trust, state, readiness, availability, and any collisions are shown; an unavailable extension explains itself |
| 5 | Disable then re-enable an extension | State changes; a second change from a stale view reports a revision conflict and reloads rather than overwriting |
| 6 | Retire an extension | Retirement is accepted and is terminal; the extension cannot return to enabled |
| 7 | Create an MCP connection from the Actions panel using `extension-definition-write` | The connection appears in the Extensions list with `operator` trust and `data/extensions` provenance |
| 8 | Select that MCP connection | The credential form is visible even though no operations have been discovered yet |
| 9 | Store a credential | The panel reports the credential was stored; the secret never appears in the rendered page or in any log |
| 10 | Invoke the `discover` operation | An approval is requested for a stdio connection; approving runs discovery and health becomes `ready` |
| 11 | Re-open the panel after discovery | Discovered `tool:`, `resource:`, and `prompt:` operations are listed |
| 12 | Restart the backend, reopen the panel | The discovered operations are still listed and health reads `unknown` until rediscovery |
| 13 | Submit an operation form with a typed field | Values are coerced by type; an invalid number or malformed JSON reports which field is wrong |
| 14 | Invoke an operation that requires approval | The run appears as `awaiting_approval` with Approve and Decline available |
| 15 | Approve it | The run proceeds and its result is shown |
| 16 | Invoke a long-running operation and press **Cancel** | A confirmation is requested; declining leaves the run alone, confirming cancels it |
| 17 | Trigger an operation that requests operator input | The elicitation or permission form renders and the answer is accepted |
| 18 | Select an OAuth-configured MCP connection | The OAuth block reports `Not authorized.` with a **Connect** button |
| 19 | Press **Connect** | An authorization URL opens in the default browser; the panel asks for the returned code |
| 20 | Paste the authorization code | The panel reports the connection is authorized and the status flips to `Authorized.` |
| 21 | Break a definition on disk and reload | The load error is listed with its source and reason, and the rest of the catalog still renders |
| 22 | Close and reopen the panel while a run is active | Run polling resumes; typing in a field is not interrupted by the refresh |

## Notes

- Steps 7, 10, 14, and 15 exercise the ADR 0005 ladder. Confirm the corresponding
  turn or action evidence exists rather than trusting the panel text alone.
- Step 9 and step 20 are the security-relevant steps: no secret and no PKCE
  verifier may appear in the desktop process, the rendered page, or the logs.
- If a step cannot run because a dependency is unavailable on the host, record it
  as `SKIPPED` with the reason. Do not record it as a pass.
