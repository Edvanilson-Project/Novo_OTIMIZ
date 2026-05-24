# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

## 0. Mandatory Project Memory

Before doing any work in this repository, read `CLAUDE_OPERATIONAL_MEMORY.md`.
For ongoing operational validation work, also read and update
`CLAUDE_OPERATIONAL_STATUS.md` so the current module, evidence, bugs, fixes,
tests, commits, and next steps stay persistent.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

---

## 5. Domain Knowledge — Optimizer (VSP/CSP)

Critical invariants to preserve when editing algorithm code:

**`max_vehicle_shift_minutes` vs `max_block_span_minutes`**
- `max_vehicle_shift_minutes` = driver duty duration (CCT/CLT Brasil, ~9.3h = 560 min). Constraint on the DRIVER.
- `max_block_span_minutes` = vehicle daily run limit (default 1440 min = full day). Constraint on the VEHICLE/BLOCK.
- One bus can run 20h served by 2-3 drivers via run-cutting in CSP. Never conflate the two.

**Set Partition constraint must be `== 1`, not `>= 1`**
- Each task must appear in exactly one duty (`== 1`).
- Covering (`>= 1`) allows duplicate coverage → MANDATORY_GROUP_SPLIT violation at roster validation.
- Files: `csp/set_partitioning.py`, `csp/set_partitioning_optimized.py`.

**Cost accounting in greedy VSP**
- `pairing_delta` is a heuristic bonus for trip-group pairing. It must be subtracted from `marginal_cost` before accumulating into `connection_cost`.
- Without this: `connection_cost` goes negative → total schedule cost is negative (invalid).

**VSP polynomial optimum**
- Single-depot VSP is solvable in polynomial time via min-cost flow (Löbel 1998).
- MCNF lower bound for the real Salvador timetable (298 trips, lines 1↔2): **14 vehicles**.
- Dilworth lower bound (max concurrent trips = 10) is theoretical; actual optimum is 14 due to deadhead constraints.
- All 7 algorithms should achieve 14 vehicles on this instance after correct parameterization.

**Cache fingerprint**
- Never include time-based components (e.g., `time.time() // 3600`) in cache keys — defeats TTL-based expiry.

**Async FastAPI routes**
- Never call synchronous Celery `.delay()` result fetching or blocking I/O directly in `async def` routes.
- Use `await asyncio.to_thread(...)` for CPU/blocking calls inside async routes.
