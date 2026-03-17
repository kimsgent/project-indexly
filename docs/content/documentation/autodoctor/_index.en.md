---
title: "AutoDoctor Documentation"
linkTitle: "AutoDoctor"
description: "Official AutoDoctor documentation for users, technical operators, and developers. Covers installation, configuration, diagnostics, remediation, API, dashboard, and troubleshooting."
slug: "autodoctor"
type: docs
aliases:
  - "/docs/autodoctor/home/"
keywords:
  - "AutoDoctor"
  - "Windows diagnostics"
  - "AutoDoctor installation"
  - "AutoDoctor API"
  - "AutoDoctor dashboard"
tags:
  - "autodoctor"
  - "windows"
  - "diagnostics"
  - "operations"
categories:
  - "documentation"
weight: 1
date: "2026-03-15"
lastmod: "2026-03-15"
draft: false
params:
  summary: "Start here to install, run, and operate AutoDoctor across home, technical, and developer workflows."
  robots: "index,follow"
  social_image: "/images/autodoctor-social-placeholder.png"
---

## About This Documentation

This documentation is organized for three audiences:

- DIY/home users who want a safe first run and clear next steps.
- Technical users who need runtime, configuration, and service operations.
- Developers who need architecture, contracts, and extension details.

## Choose Your Path

- DIY path: [Getting Started](./getting-started/)
- Technical path: [Technical Guide](./technical-guide/)
- Developer path: [Developer Guide](./developer-guide/)
- Fast lookup: [Reference](./reference/)
- Problem solving: [Troubleshooting](./troubleshooting/)
- Quick answers: [FAQ](./faq/)

## Product Scope

AutoDoctor is a Windows diagnostics and remediation toolchain with:

- PowerShell diagnostic agent (`agent/`)
- SQLite persistence (`db/autodoctor.db`)
- FastAPI service (`server/api/`)
- Browser dashboard (`/dashboard`)

It is designed for local or controlled administrative environments.

## Core Capabilities

- Run host diagnostics (CPU, memory, disk, network, events, updates, drivers, software)
- Compute root-cause issues and health score
- Execute remediation actions
- Persist diagnostics, alerts, and telemetry to SQLite
- Serve health/status APIs and dashboard views

## Documentation Principles

- Plain language first, with technical terms defined when used.
- Consistent section structure across guides.
- Actionable examples with expected outcomes.
- Accessibility-first heading and link style.

{{< alert title="Note" color="info" >}}
Each page includes relative links so this doc set can be moved between local preview and production Hugo deployments without breaking navigation.
{{< /alert >}}

## Canonical URL Strategy (Recommended)

Use one canonical host for all published docs pages.

- Set `baseURL` in Hugo to your production docs host.
- Keep one canonical path per page (`slug` + section path).
- Add aliases only for legacy URLs during migration.
- Avoid publishing duplicate docs under multiple section roots.

For this project, publish docs under `https://projectindexly.com/autodoctor/` and redirect old paths to that canonical root.

## Next Steps

- Start with [Requirements](./getting-started/requirements/)
- Continue with [Installer Guide](./getting-started/install-inno/)
- Review [Configuration Precedence](./technical-guide/config-precedence/)
