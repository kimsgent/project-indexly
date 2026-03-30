---
title: "Health Scoring Matrix"
linkTitle: "Scoring Matrix"
description: "Detailed AutoDoctor health scoring matrix showing deduction rules, issue text mapping, and score interpretation from root-cause analysis."
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
lastmod: "2026-03-15"
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
- Deductions are cumulative.
- Minimum score floor: `0`

## Deduction Matrix

| Condition | Issue text generated | Deduction |
|---|---|---|
| `FreeMemoryGB < 1` | `Low RAM available` | `-20` |
| `CurrentCPULoadPercent > 90` | `CPU saturation detected` | `-15` |
| Any disk with `FreeGB < 5` | `Low disk space` | `-20` |
| `HighDiskUsage` has entries | `Disk IO bottleneck detected` | `-20` |
| Any SMART `PredictFailure = true` | `Potential disk failure detected` | `-40` |
| `Connectivity.AvgLatencyMS > 200` | `High network latency` | `-10` |
| `Event Log ErrorCount > 30` | `High error rate in event logs` | `-10` |

## Summary Generation

- No triggered conditions -> `No major issues detected`
- Triggered conditions -> semicolon-separated issue list in `Summary`

Output contract:

```text
HealthScore = <0..100>
HealthText  = "<score> / 100"
Summary     = "<issue list>"
Details.DetectedIssues = [ ... ]
```

## Severity Mapping for Alerts

When issues are inserted into `alerts`:

- `Potential disk failure detected` -> `Critical`
- `Low disk space` -> `Critical`
- All others -> `Warning`

## Interpretation Guidance

| Score band | Interpretation |
|---|---|
| `90-100` | No major issues detected |
| `70-89` | Moderate degradation; review alerts and trends |
| `< 70` | High operational risk; triage and remediation recommended |

{{< alert title="Note" color="info" >}}
Health score is a heuristic operational indicator, not a complete reliability guarantee.
{{< /alert >}}

## Next Steps

- [Common Alerts and What to Do](../user-guide/common-alerts/)
- [Remediation Catalog](./remediation-catalog/)
