---
name: systematic-debugging
description: Diagnose a failing check, build error, or unexpected runtime behavior before choosing a code fix.
---

# Systematic debugging

OneFDE adaptation of obra/superpowers; workflow shortened for one bounded Run. See bundled provenance and MIT license.

Read the actual error, command, exit code and affected source. Reproduce the smallest failing path with existing project commands. Compare it with a working path and trace the first incorrect value across component boundaries.

State a testable cause, then change one relevant part and rerun the failing case. Separate environment failures, missing dependencies, business unknowns and implementation defects. A failed command is evidence; a model explanation is a hypothesis.

After two unsuccessful fixes for the same symptom, stop repeating them. Inspect new evidence and choose a different hypothesis, or preserve the candidate and report the concrete blocker. Use needs_input only for an actual question that the owner or FDE can answer. Runtime limits and the existing submission contract remain authoritative.
