---
title: "Health Scoring Matrix"
linkTitle: "Scoring Matrix"
description: "Detailed AutoDoctor health scoring reference showing direct rule thresholds, weighted finding penalties, historical-state inputs, and summary generation."
slug: "health-scoring-matrix"
type: docs
aliases:
  - "/docs/autodoctor/reference/scoring/"
keywords:
  - "AutoDoctor health score"
  - "root cause deduction matrix"
  - "health score thresholds"
tags:
  - "health-score"
  - "reference"
  - "root-cause"
categories:
  - "autodoctor"
weight: 55
date: "2026-03-15"
lastmod: "2026-04-17"
draft: false
params:
  summary: "Understand exactly how health score is computed and why specific issues appear in summary output."
  robots: "index,follow"
  social_image: "/images/autodoctor-social-placeholder.png"
---

## Who This Is For

- Users interpreting health score changes between runs.
- Developers maintaining `agent/modules/rootcause.ps1`.

## Scoring Model

- Starting score: `100`
- Findings are ordered by severity, then category, then message.
- Deductions are cumulative but repeated findings in the same category taper off.
- Minimum score floor: `0`

## Finding Sources

Root Cause Analysis combines findings from these sources:

| Source | What it contributes |
|---|---|
| Direct rules | Current-run thresholds for memory, CPU, disk, network, and events |
| Validation | Data-quality findings such as incomplete inventory rows |
| Anomaly | Persistent or transient deviations identified by anomaly analysis |
| Correlation | Cross-metric reasoning such as CPU pressure without storage pressure |
| History | `Sustained`, `Transient`, and `Baseline` issues based on prior runs |

## Direct Rule Thresholds

| Condition | Issue text generated | Deduction |
|---|---|---|
| Free memory `< 1 GB` | `Low RAM available: only <x> GB free` | Weighted from finding severity |
| Memory used `>= 85%` | `Memory pressure detected: <x>% of RAM is in use` | Weighted from finding severity |
| CPU `>= 85%` | `CPU saturation detected at <x>%` | Weighted from finding severity |
| CPU `>= 70%` | `Elevated CPU load detected at <x>%` | Weighted from finding severity |
| Disk free `< 5 GB` or `< 10%` | `Low disk space detected on drive(s): ...` | Weighted from finding severity |
| Disk free `< 2 GB` on any flagged drive | same message, higher severity | Weighted from finding severity |
| Peak disk busy `>= 80%` | `Disk IO bottleneck detected: peak disk busy is <x>%` | Weighted from finding severity |
| Peak disk busy `>= 60%` | `Elevated disk IO activity detected: peak disk busy is <x>%` | Weighted from finding severity |
| Any SMART `PredictFailure = true` | `Potential disk failure detected` | Weighted from finding severity |
| Latency `>= 200 ms` | `High network latency detected: <x> ms average` | Weighted from finding severity |
| Latency `>= 100 ms` | `Elevated network latency detected: <x> ms average` | Weighted from finding severity |
| Event errors `>= 100` | `Very high error rate in event logs: <x> recent errors` | Weighted from finding severity |
| Event errors `>= 30` | `High error rate in event logs: <x> recent errors` | Weighted from finding severity |

## Historical-State Thresholds

History analysis evaluates CPU, memory, disk, and network against rolling telemetry:

| Metric | Threshold | Baseline multiplier | Minimum delta | Minimum trend samples |
|---|---|---|---|---|
| `CPU` | `80` | `1.5` | `10` | `4` |
| `Memory` | `85` | `1.5` | `8` | `4` |
| `Disk` | `90` | `1.5` | `5` | `4` |
| `Network` | `100` | `1.5` | `20` | `4` |

State rules:

- `Sustained`: threshold exceeded for `3` consecutive runs
- `Transient`: threshold exceeded only in the current run
- `Baseline Deviation`: current value is above `baseline * 1.5` and above the metric delta threshold with at least `3` historical samples
- `Increasing` / `Decreasing`: directional trend without a threshold breach

## Weighting Model

Base weights:

| Severity | Base weight |
|---|---|
| `Info` | `1` |
| `Warning` | `5` |
| `Critical` | `15` |

Additive adjustments:

| Condition | Adjustment |
|---|---|
| Source is `Anomaly` | `+2` |
| Source is `Validation` and severity is not `Info` | `+2` |
| Disk finding message contains `failure` | `+10` |
| Type is `Sustained` | `+6` |
| Type is `Persistent` | `+4` |
| Type is `Baseline` | `+4` |
| Type is `Transient` | `+1` |

Category tapering multipliers:

| Finding occurrence within same category | Multiplier |
|---|---|
| First | `1.0` |
| Second | `0.7` |
| Third | `0.5` |
| Fourth and later | `0.35` |

Special case:

- `Validation` findings with severity `Info` use half of the category factor.
- If anomaly findings exist and the score would still be above `95`, the score is capped at `95`.

## Summary Generation

- No triggered conditions -> `No major issues detected`
- Triggered conditions -> first four ordered finding messages joined with semicolons

Output contract:

```text
HealthScore = <0..100>
HealthText  = "<score> / 100"
Summary     = "<issue list>"
Details.DetectedIssues = [ ... ]
Details.ScoreBreakdown.Findings = [ weighted penalty breakdown ]
Details.ScoreBreakdown.Categories = [ penalty totals by category ]
```

## Severity Mapping for Alerts

When findings are inserted into `alerts`, AutoDoctor keeps the severity from the finding object when available. That means current alert summaries can include:

- `Critical`
- `Warning`
- `Info`

## Interpretation Guidance

| Score band | Interpretation |
|---|---|
| `90-100` | No major issues detected or only low-impact findings |
| `70-89` | Moderate degradation; one or more meaningful findings should be reviewed |
| `< 70` | High operational risk; sustained or critical issues are likely present |

{{< alert title="Note" color="info" >}}
Health score is a heuristic operational indicator, not a complete reliability guarantee.
{{< /alert >}}

## Next Steps

- [Common Alerts and What to Do](../user-guide/common-alerts/)
- [Remediation Catalog](./remediation-catalog/)
