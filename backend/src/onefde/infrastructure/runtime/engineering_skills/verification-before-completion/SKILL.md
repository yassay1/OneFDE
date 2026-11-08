---
name: verification-before-completion
description: Verify the current source and registered checks before claiming a fix, successful build, or completed Engineering submission.
---

# Verification before completion

OneFDE adaptation of obra/superpowers; verification is tied to registered evidence rather than repeated full-suite runs. See bundled provenance and MIT license.

Identify which observed result supports each completion claim. Run every registered automatic check after the last relevant edit, from its registered directory, as a separate command exactly matching the registered string. Read output, exit code and timeout status. A build, linter, unit check and browser interaction establish different facts.

Reuse current successful evidence while the checked source remains unchanged. After an edit, rerun affected checks and every check required for submission. Keep existing acceptance tests intact. Distinguish pre-existing failures from regressions and record any missing evidence.

Once checks pass, summarize the fixed candidate and remaining limitations, then use the OneFDE Finish JSON contract. Business review stays pending for the owner; the trusted Worker performs independent validation. An unavailable optional tool is a recorded limitation, not a reason to repeat installation attempts or claim a browser pass.
