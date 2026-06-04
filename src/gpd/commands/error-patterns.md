---
name: gpd:error-patterns
description: View accumulated physics error patterns for this project
argument-hint: "[category]"
context_mode: project-required
allowed-tools:
  - file_read
  - shell
  - search_files
  - find_files
help:
  group: Tangents, memory, and exports
  order: 600
  compact_description: Review common project-specific errors
  display_signature: gpd:error-patterns [category]
  examples:
    - gpd:error-patterns sign-error
  notes:
    - Pattern-library categories include sign-error, factor-error, convention-pitfall, convergence-issue, approximation-failure, numerical-instability, conceptual-error, and dimensional-error.
---


<objective>
Display accumulated physics error patterns from `GPD/ERROR-PATTERNS.md`. Optionally filter by category.

Error patterns are recorded by the debugger after confirming root causes. They capture project-specific failure modes so that verifiers, planners, and executors can proactively check for recurrence.

The same-named workflow owns category validation and uses the live pattern-library vocabulary.
  </objective>

<execution_context>
@{GPD_INSTALL_DIR}/workflows/error-patterns.md
@GPD/ERROR-PATTERNS.md
</execution_context>

<process>

**Pre-flight check:**
```bash
test -d GPD || { echo "Error: No GPD project found. Initialize a GPD project first."; exit 1; }
```

<step name="check_file">
```bash
test -f GPD/ERROR-PATTERNS.md && echo "EXISTS" || echo "MISSING"
```

**If MISSING:**

```
No error patterns recorded yet.

Error patterns are captured by gpd:debug when root causes are confirmed.
They help the verifier and planner proactively check for recurring issues.

---

Start a debugging session with gpd:debug to begin building the pattern database.
```

Exit.
</step>

<step name="read_patterns">
Read `GPD/ERROR-PATTERNS.md`.

**If $ARGUMENTS provided (category filter):**

Filter the patterns table to show only rows matching the category. Display:

```
## Error Patterns: {category}

{filtered table rows}

---

Showing {N} of {total} patterns. Run `gpd:error-patterns` to see all.
```

**If no arguments (show all):**

Display the full contents formatted as:

```
## Project Error Patterns

{full table}

---

{total} patterns recorded. Filter by category: `gpd:error-patterns sign-error`
```

</step>

<step name="global_patterns">
**Also show relevant patterns from the global cross-project library.**

```bash
gpd pattern init 2>/dev/null || true
DOMAIN=$(grep -m1 "domain:" GPD/PROJECT.md 2>/dev/null | sed 's/.*: *//' || echo "")
GLOBAL=$(gpd --raw pattern list ${DOMAIN:+--domain "$DOMAIN"} 2>/dev/null)
```

If global patterns exist (count > 0), append:

```
## Cross-Project Patterns

{pattern list from global library, sorted by severity}

---

Global library: {count} patterns. Search: `gpd pattern search "keyword"`
```

</step>

</process>
