---
title: "Indexly Overview"
subtitle: "Your local file indexing and search tool"
description: "Indexly helps researchers and power users search Word, PDF, and text documents locally. Fast, offline, with tagging and FTS5."
keywords: ["Word document search", "offline file search", "FTS5 search tool", "research document indexing"]
weight: 5
type: docs
toc: true
categories:
    - Overview 
    - Getting Started
tags:
    - overview
    - features
    - usage
    - configuration
---

> *"You who searches, finds."*

Welcome to **Indexly** – your fast, flexible, full-text local file search engine. Powered by Python and SQLite FTS5, Indexly brings powerful content searching, tagging, exporting, and indexing to your terminal.

Works great on **Windows** (tested), Linux, and macOS. CLI-only for now; GUI may come later.

---

```mermaid

flowchart TD
    %% Nodes
    A["📘 Indexly Overview"]:::overview
    B["✨ Features Overview"]:::features
    C["⚙️ Configuration & Features"]:::config
    D["📖 Usage Guide"]:::usage
    E["🛠️ Developer Guide"]:::dev
    F["🏷️ Virtual Tag Detection"]:::tags
    G["🖥️ Customizing Windows Terminal"]:::terminal

    %% Links
    A --> B
    A --> C
    A --> D
    A --> E
    A --> F
    D --> G

    B -->|Dev references| E
    C -->|Profiles & advanced filters| D
    C -->|Dev references| E
    F -->|CLI usage| D
    F -->|Developer tag extension| E

    %% Styles
    classDef overview fill:#F0F8FF,stroke:#333,stroke-width:1px;
    classDef features fill:#FFFACD,stroke:#333,stroke-width:1px;
    classDef config fill:#E6E6FA,stroke:#333,stroke-width:1px;
    classDef usage fill:#F5F5DC,stroke:#333,stroke-width:1px;
    classDef dev fill:#FFE4E1,stroke:#333,stroke-width:1px;
    classDef tags fill:#F0FFF0,stroke:#333,stroke-width:1px;
    classDef terminal fill:#FFF0F5,stroke:#333,stroke-width:1px;

````
---

## Table of Contents

* [Features](/features)
* [Installation & Basic Usage](usage.md#basic-usage)
* [Search Profiles](config.md#search-profiles)
* [Tagging](config.md#tagging-system)
* [Exporting](usage.md#exporting)
* [Watchdog](config.md#watchdog-real-time-indexing)
* [Advanced Options](config.md#advanced-options)
* [Renaming Files with Patterns →](rename-file.md)
* [Extracting Minitab MTW files →](mtw-parser.md)
* [Data Analysis Overview →](data-analysis-overview.md)
* [Time-Series Visualization→](time-series-visualization.md)
* New in v1.0.6: [Indexly Doctor→](indexly-doctor.md)
* New in v1.0.6: [Semantic Indexing→](semantic-indexing-overview.md)
* New in v1.0.6: [Organizer, Lister & Backup/Restore→](organizer.md)
* [Developer Notes](developer.md)
* [License & Credits](#license-credits)

---

## Key Highlights

* Full-text search via SQLite FTS5
* Regex & fuzzy search
* Tagging & filtering
* CSV, JSON analysis & stats
* Watchdog real-time indexing
* Export to PDF, TXT, JSON
* Developer-friendly modular CLI

> For full instructions, explore [Usage Guide](usage.md), [Config & Features](config.md), or [Developer Notes](developer.md).

---

## Requirements

* Python 3.10+
* Run locally, no server needed

> ```bash
> pip install -r requirements.txt
> ```
> Or manually:
> ```bash
> pip install nltk pymupdf pytesseract pillow python-docx openpyxl rapidfuzz fpdf2 reportlab \
> beautifulsoup4 extract_msg eml-parser PyPDF2 watchdog colorama
> ```

📌 See [Installation Guide](usage.md#installation) for Windows tips.

---

## Workflow Overview

```mermaid
flowchart LR
    A[Index files 📂] --> B[Search 🔍]
    B --> C[Filter & tag 🏷️]
    C --> D[Export results 🧾]
````


---

## Related Docs

* [How to Use Indexly](usage.md)
* [Configuration & Filtering](config.md)
* [Developer Setup](developer.md)

---

## License & Credits

**Author:** N. K Franklin-Gent
Built with ❤️ for the curious mind.
Licensed under the [MIT License](LICENSE.txt).
