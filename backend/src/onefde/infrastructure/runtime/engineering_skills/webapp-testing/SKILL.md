---
name: webapp-testing
description: Exercise a local web app in a real browser, including forms, imports, filters, downloads, responsive layouts and browser logs.
---

# Web application testing

OneFDE adaptation of anthropics/skills. Modified to use existing project tools, bounded dependency checks and fixed-source validation. See bundled provenance and Apache-2.0 license.

Inspect the project's existing browser test command and installed dependencies first. Check whether Playwright and a browser executable are already available before starting a browser test. Use the existing runner when present. A skill supplies a method; it does not install a browser or grant network access.

If dependencies are unavailable, record the exact missing dependency once and continue available checks. Report the browser criteria as unverified. Return a concrete setup requirement; do not cycle through package managers or install unrelated browser harnesses.

Start the app using its actual documented command. Wait for a visible readiness condition; on apps with polling, use a specific element or response rather than waiting indefinitely for network idle. Inspect the rendered page before selecting controls. Prefer accessible role/label selectors and assert observable behavior.

Cover the task's critical path and its relevant error path. For imports, verify input rows and displayed results; for exports, read the downloaded file and assert its contents. Exercise a narrow viewport when responsive behavior is required. Save screenshots and console errors as evidence in the permitted evidence location, outside frozen source unless explicitly allowed. Close test browsers and temporary servers in finally blocks. Report actual results separately from untested cases.
