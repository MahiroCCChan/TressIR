# Benchmark scaffold

TressIR's main empirical question is whether a structured hair representation changes what a general-purpose agent can reliably author compared with direct Blender manipulation.

A benchmark contribution should control the comparison instead of mixing different models, prompts, or iteration budgets.

## Suggested case layout

```text
benchmarks/
  case_name/
    task.md
    references/
    allowed_inputs.md
    protocol.md
    results/
      direct_blender/
      tressir/
```

Do not commit copyrighted character assets unless redistribution is permitted.

## Minimum protocol fields

Record:

- operator/model name and version;
- date;
- exact task statement;
- available reference views;
- tool access;
- context/prompt files;
- iteration or time/tool-call budget;
- human feedback allowed;
- stopping rule;
- output screenshots from fixed views;
- geometry diagnostics;
- failure notes.

## Interpretation

A single successful case is qualitative evidence, not a general benchmark result. Repeated cases and repeated runs are preferred.

Visual quality and technical validity should be reported separately. A manifold mesh can still be a poor reconstruction, and a visually convincing result may still contain production issues.
