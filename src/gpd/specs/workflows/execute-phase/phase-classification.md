<purpose>
Classify the phase and choose execution policy without loading downstream authority.
</purpose>

<stage_boundary>
This stage reads only its manifest-selected payload and determines phase classes, context hints, convention posture, sequential/parallel overrides, and pre-execution specialist needs. It routes to wave planning; it does not spawn workers or close the phase.
</stage_boundary>

<process>

<step name="classify_phase">
Classify the phase type to drive agent selection and context budget decisions. Scan the phase goal and plan objectives for indicator keywords.

```bash
PHASE_CLASSIFICATION_INIT=$(gpd --raw init execute-phase "${PHASE_ARG}" --stage phase_classification)
if [ $? -ne 0 ] || [ -z "$PHASE_CLASSIFICATION_INIT" ]; then
  echo "ERROR: phase-classification stage refresh failed: $PHASE_CLASSIFICATION_INIT"
  exit 1
fi
```

Apply `PHASE_CLASSIFICATION_INIT.staged_loading.field_access_instruction` before reading `PHASE_CLASSIFICATION_INIT`.

Classify semantically. A phase may have multiple classes: `derivation`, `numerical`, `literature`, `paper-writing`, `formalism`, `analysis`, and `validation`; use `mixed` only when none of those apply.

Log the classification: `"Phase ${phase_number} classified as: ${PHASE_CLASSES[*]}"`

Use the classification for the local execution parameters below, specialist routing labels, and executor context hints.
</step>

<step name="adapt_to_computation_type">
Translate the phase classification into concrete execution parameters that drive wave-loop behavior. Set these variables before entering `execute_waves`:

Start from this default routing state: `CONVENTION_LOCK_REQUIRED=false`, no pre-execution specialists, `INTER_WAVE_CHECKS=[convention, dimensional]`, `EXECUTOR_CONTEXT_HINT=standard`, `WAVE_TIMEOUT_FACTOR=1.0`, `FORCE_SEQUENTIAL=false`, and no yolo restrictions.

Apply per-class overrides cumulatively:

| Class | Overrides |
|---|---|
| `derivation` | require convention lock, add identity scan, use `derivation-heavy`, increase timeout factor, require strict downstream checks in yolo |
| `numerical` | add convergence spot check, use `code-heavy`, route `gpd-experiment-designer` only when the phase or plan requires a standalone design handoff |
| `literature` | force sequential execution, use `reading-heavy`, keep convention-only inter-wave checks |
| `paper-writing` | route notation coordination when needed, add LaTeX compile smoke checks, use `prose-heavy` |
| `formalism` | require convention lock, route notation coordination when needed, add identity scan |
| `analysis` | add plausibility scan |
| `validation` | require strict downstream and inter-wave checks in yolo, add identity, convergence, and plausibility scans |

**Convention lock enforcement:**

If `CONVENTION_LOCK_REQUIRED=true`:

Run the convention lock gate and require a `locked` or `complete` result before execution. If it fails, halt with a concrete `gpd convention set` / `gpd:validate-conventions` repair route; derivation and formalism convention errors compound across every step.

**Hard gate:** when `CONVENTION_LOCK_REQUIRED=true` and conventions are not locked, execution MUST NOT proceed in any autonomy mode. Convention errors invalidate downstream results.

`pre_execution_specialists` consumes `PRE_EXECUTION_SPECIALISTS` and loads delegation guidance; this stage only chooses specialist types.

**Force-sequential override:**

If `FORCE_SEQUENTIAL=true`, override `PARALLELIZATION` to false for this phase regardless of config setting. Log: `"Phase class (${PHASE_CLASSES[*]}) forces sequential execution within waves."`

**YOLO mode restrictions:**

If `autonomy=yolo` and `YOLO_RESTRICTIONS` is non-empty, restrict yolo behavior: strict downstream checks remain mandatory and `no_skip_inter_wave` keeps inter-wave gates mandatory.

Log any restrictions: `"YOLO mode restricted for phase class (${PHASE_CLASSES[*]}): ${YOLO_RESTRICTIONS[*]}"`

Include `EXECUTOR_CONTEXT_HINT` in executor prompts:

```
<context_hint>{EXECUTOR_CONTEXT_HINT}</context_hint>
```

Hint meanings: `standard` balances derivation/code/prose; the `*-heavy` hints reserve context for their named work type without changing required gates.
</step>

<step name="validate_phase">
From init JSON: `phase_dir`, `plan_count`, `incomplete_count`.

Report: "Found {plan_count} plans in {phase_dir} ({incomplete_count} incomplete)"
</step>

</process>
