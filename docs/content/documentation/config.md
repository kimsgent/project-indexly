---
title: "Indexly Configuration & Features"
weight: 7
toc: true
type: docs
categories:
    - Features 
    - Advanced Usage
tags:
    - configuration
    - indexing
    - tagging
    - performance
    - usage
---

Explore how profiles, filters, tagging, and watchdog enhance search efficiency.

---

## Search Profiles

Save and reuse filters:

```bash
indexly search "project plan" --save-profile q3_plans
indexly search "budget" --profile q3_plans
````

Profiles stored in `profiles.json`.

> ![Profiles placeholder](/images/profiles-sample.png)

---

## Tagging System


### Add or Remove Tags Later

```bash
indexly tag add --files "." --tags notes.txt important
indexly tag remove --files "." --tags notes.txt draft
```

### Search by Tag

```bash
indexly search "keyword" --filter-tag urgent
```

> ![Sample Tags after search](/images/search-tags.png)

For more information on tagging please see [Indexly Tagging System](tagging.md)

---

## Watchdog (Real-Time Indexing)

```bash
indexly watch "C:/Users/Me/Documents"
```

> Note: Optional, resource intensive for large datasets.

---

## Performance & Smart Caching

* Each search query hashed (`calculate_query_hash()`)
* Cached results reused if valid
* Only reindex changed files
* Optional control with `--no-cache`


> ![Sample cache results](/images/search_cache_json.png)

---

## CSV Summary Analysis

```bash
indexly analyze-csv --file data.csv --format md --output summary.md
```

* Auto-detect delimiters
* Computes stats: mean, median, min, max, stddev, IQR
* Outputs in Markdown or TXT

> ![CSV stats placeholder](/images/csv-stats.png)

---

## Advanced Options

* `indexly stats` → DB overview
* `fts_index.db` → full-text index
* `profiles.json` → saved searches
* `search_cache.json` → recent content
