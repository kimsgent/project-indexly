from datetime import date

PROFILE_STRUCTURES = {
    "it": [
        "IT/Projects/Active",
        "IT/Projects/Archived",
        "IT/Projects/Templates",
        "IT/Code/Scripts",
        "IT/Code/Tools",
        "IT/Code/Experiments",
        "IT/Docs/Architecture",
        "IT/Docs/Notes",
        "IT/Docs/Manuals",
        "IT/Configs",
        "IT/Logs",
        "IT/Resources",
    ],
    "researcher": [
        "Research/Papers/Drafts",
        "Research/Papers/Submitted",
        "Research/Papers/Published",
        "Research/Data/Raw",
        "Research/Data/Cleaned",
        "Research/Data/Results",
        "Research/Notes",
        "Research/References/PDFs",
        "Research/Presentations",
        "Research/Admin",
    ],
    "engineer": [
        "Engineering/Projects/Design",
        "Engineering/Projects/Simulation",
        "Engineering/Projects/Calculations",
        "Engineering/Projects/Reports",
        "Engineering/CAD",
        "Engineering/Standards",
        "Engineering/Drawings",
        "Engineering/Photos",
        "Engineering/Archive",
    ],
    "health": [
        "Health/Patients",
        "Health/Reports",
        "Health/Imaging",
        "Health/Lab",
        "Health/Admin",
        "Health/Guidelines",
        "Health/Archive",
    ],
    "data": [
        "Data/Projects",
        "Data/Datasets",
        "Data/Experiments",
        "Data/Visuals",
        "Data/Archive",
    ],
    "media": [
        "Media/Shoots",
        "Media/Catalogs",
        "Media/Presets",
        "Media/Video",
        "Media/Clients",
        "Media/Archive",
    ],
}


PROFILE_NEXT_STEPS = {
    "it": "Place active projects under IT/Projects/Active and archive aggressively.",
    "researcher": "Never modify raw research data. Keep work reproducible.",
    "engineer": "Keep CAD, calculations, and reports strictly separated.",
    "health": "Create patient folders manually. Maintain audit trails.",
    "data": "Use --project-name to initialize a project. Raw data is immutable.",
    "media": "Import RAW files only. Never overwrite originals.",
}


def build_data_project_structure(project_name: str) -> list[str]:
    base = f"Data/Projects/{project_name}"
    return [
        f"{base}/Data/Raw",
        f"{base}/Data/Processed",
        f"{base}/Data/Output",
        f"{base}/Notebooks",
        f"{base}/Scripts",
        f"{base}/Reports",
    ]


def build_media_shoot_structure(shoot_name: str | None = None) -> list[str]:
    today = date.today().isoformat()[:7]  # YYYY-MM
    shoot = f"{today}-{shoot_name}" if shoot_name else today
    base = f"Media/Shoots/{shoot}"
    return [
        f"{base}/RAW",
        f"{base}/Edited",
        f"{base}/Export",
    ]
