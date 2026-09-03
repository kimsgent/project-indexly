# Responsive static prototype

> **Authority:** informative interaction reference only
> **Volatility:** medium
> **Runtime:** static local files with illustrative data; no Indexly service/API

This self-contained prototype visualizes the interaction direction captured by
the [local web UI blueprint](../README.md). Open `index.html` directly in a
browser; no package install, server, account, database, or network connection is
required.

For direct visual review, append `?view=settings` or `?view=activity` to the
local file URL, or append `?dialog=export` to open the export review state.
These query parameters are prototype conveniences, not the production URL
contract.

## What it demonstrates

- a dominant, scan-friendly Search canvas with restrained file-type markers;
- distinct FTS/regex-oriented search controls and a contextual result inspector;
- a proposed Activity page and index-health presentation using explicitly
  illustrative states rather than fabricated live telemetry;
- an Indexing Settings concept that keeps source roots and index action outside
  the Search workspace;
- OCR mode and external Tesseract setup that distinguish PATH discovery from a
  future validated absolute executable override;
- an exact-result export concept with Markdown, PDF, text, and JSON choices,
  registered destination, PDF capability notice, and no-overwrite default;
- explicit FTS/regex mode, bounded-page cues, and plan-before-index interaction;
- proposed workspace-specific enabled views and startup selection through
  **Manage views**;
- proposed virtual-tag collection and manual color-tag organization;
- an inspector that closes, reopens, and resizes with pointer or keyboard
  (Arrow keys and Home/End);
- a labelled workspace-navigation drawer at tablet widths, collapsed inspector
  behavior there, and a full-width contextual inspector on narrow screens; and
- skip navigation, focus handling, reduced-motion behavior, semantic labels,
  and non-color-only state cues that implementation should preserve and test.

## What it does not demonstrate

- a web host, API, application-service layer, authentication/session, or CSP;
- real search, index, health, sync, settings, tags, workspaces, or job data;
- safe filesystem registration, file preview, “open original,” export, writer
  coordination, cancellation, or persistence;
- implemented CLI parity, dependency packaging, migration, or release support;
  or
- proof of accessibility, security, privacy, performance, or cross-platform
  acceptance.

Every count, filename, timestamp, path, status, and action outcome in the page is
sample data. Prototype controls must be removed, clearly labelled, or connected
to an approved real contract before a production stage can be accepted.

The Markdown export choice is deliberately shown as planned. Current source
advertises `md` in the search parser but does not yet dispatch it to a Markdown
exporter; the blueprint records that gap and its required regression test.

## Normative references

- [Architecture decisions](../architecture/decisions.md)
- [System architecture](../architecture/system-architecture.md)
- [Contracts and invariants](../architecture/contracts.md)
- [Scope and parity](../product/scope-and-parity.md)
- [Implementation status](../delivery/implementation-status.md)
- [Validation strategy](../delivery/validation.md)

When the prototype conflicts with any normative document, the normative
document wins. The [current-work file](../delivery/current-work.md) determines
whether prototype changes are authorized in the active task.
