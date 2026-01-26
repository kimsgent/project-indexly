from pathlib import Path
from datetime import date
from typing import List


PROFILE_STRUCTURES = {
    "it": {
        "default": [
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
        "student": [
            "IT/Courses/Program/Modules",
            "IT/Courses/Program/Notes",
            "IT/Courses/Program/Labs",
            "IT/Courses/Program/Assignments",
            "IT/Courses/Program/Certificates",
            "IT/Courses/Program/Resources",
            "IT/Code/Scripts",
            "IT/Code/Tools",
            "IT/Docs/Notes",
            "IT/Docs/Manuals",
            "IT/Archive",
        ],
        "support": [
            "IT/Projects/Active",
            "IT/Projects/Archived",
            "IT/Operations/Incidents",
            "IT/Operations/Requests",
            "IT/Operations/Changes",
            "IT/Systems/Windows",
            "IT/Systems/Linux",
            "IT/Systems/Network",
            "IT/Systems/Cloud",
            "IT/Scripts/PowerShell",
            "IT/Scripts/Bash",
            "IT/Scripts/Python",
            "IT/Documentation/SOPs",
            "IT/Documentation/Runbooks",
            "IT/Documentation/HowTos",
            "IT/Software/Installers",
            "IT/Software/Licenses",
            "IT/Logs",
            "IT/Templates",
            "IT/Archive",
        ],
    },
    "education": {
        "default": [
            "Education/Courses/Online",
            "Education/Courses/InPerson",
            "Education/Courses/Certifications",
            "Education/Subjects",
            "Education/Materials/PDFs",
            "Education/Materials/Slides",
            "Education/Materials/Videos",
            "Education/Notes",
            "Education/Exams",
            "Education/References",
            "Education/Archive",
        ],
        "teacher": [
            "Education/Teaching/Courses/Active",
            "Education/Teaching/Courses/Archived",
            "Education/Teaching/LessonPlans",
            "Education/Teaching/Materials/Handouts",
            "Education/Teaching/Materials/Slides",
            "Education/Teaching/Materials/Assignments",
            "Education/Teaching/Assessments/Quizzes",
            "Education/Teaching/Assessments/Exams",
            "Education/Teaching/Assessments/Rubrics",
            "Education/Teaching/Students",
            "Education/Teaching/Administration",
            "Education/Teaching/Archive",
        ],
        "student": [
            "Education/Studies/Courses/Current",
            "Education/Studies/Courses/Completed",
            "Education/Studies/Notes",
            "Education/Studies/Assignments/Drafts",
            "Education/Studies/Assignments/Submitted",
            "Education/Studies/Exams/Practice",
            "Education/Studies/Exams/Results",
            "Education/Studies/Projects",
            "Education/Studies/Resources",
            "Education/Studies/Archive",
        ],
    },
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
        # Shoots base (each shoot gets dynamic YYYY-MM-ShootName subfolders)
        "Media/Shoots",
        # Clients folder with optional subfolders
        "Media/Clients",
        # Catalogs
        "Media/Catalogs/Lightroom",
        "Media/Catalogs/CaptureOne",
        # Presets
        "Media/Presets/Lightroom",
        "Media/Presets/CaptureOne",
        "Media/Presets/LUTs",
        # Video
        "Media/Video/Projects",
        "Media/Video/Footage",
        "Media/Video/Exports",
        # Assets
        "Media/Assets/Logos",
        "Media/Assets/Watermarks",
        "Media/Assets/Overlays",
        # Top-level archive
        "Media/Archive",
    ],
}


PROFILE_NEXT_STEPS = {
    "it": "Place active projects under IT/Projects/Active and archive aggressively.",
    "education": "Keep institutional documents separated from personal teaching or study material.",
    "teacher": "Organize by course first. Archive past semesters aggressively.",
    "student": "Keep assignments and exams immutable after submission.",
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


FALLBACK_FOLDER = "_Unknown"


def build_media_shoot_structure(
    media_root: str | Path, shoot_name: str | None = None
) -> List[Path]:
    """
    Build full Media hierarchy for professional photographers.

    Creates:
      - Top-level folders: Shoots, Clients, Catalogs, Presets, Video, Assets, Archive
      - Shoot scaffold (if shoot_name provided):
          00_RAW, 01_Cull, 02_Edits, 03_Exports/Web|Print|Social, 99_Archive
    """
    media_root = Path(media_root).resolve()
    today = date.today().isoformat()[:7]  # YYYY-MM
    shoot_folder = f"{today}-{shoot_name}" if shoot_name else None

    # 1️⃣ Top-level folders
    top_level = [
        media_root / "Shoots",
        media_root / "Clients",
        media_root / "Catalogs",
        media_root / "Presets",
        media_root / "Video",
        media_root / "Assets",
        media_root / "Archive",
    ]

    # 2️⃣ Client subfolders example (optional, can be extended dynamically)
    client_example = top_level[1] / "ClientA"
    client_subfolders = [
        client_example / "Contracts",
        client_example / "Invoices",
        client_example / "Briefs",
        client_example / "Deliverables",
    ]

    # 3️⃣ Catalogs / Presets subfolders
    catalog_subfolders = [
        top_level[2] / "Lightroom",
        top_level[2] / "CaptureOne",
    ]
    preset_subfolders = [
        top_level[3] / "Lightroom",
        top_level[3] / "CaptureOne",
        top_level[3] / "LUTs",
    ]

    # 4️⃣ Video subfolders
    video_subfolders = [
        top_level[4] / "Projects",
        top_level[4] / "Footage",
        top_level[4] / "Exports",
    ]

    # 5️⃣ Assets subfolders
    assets_subfolders = [
        top_level[5] / "Logos",
        top_level[5] / "Watermarks",
        top_level[5] / "Overlays",
    ]

    # 6️⃣ Dynamic shoot scaffold
    shoot_subfolders: List[Path] = []
    if shoot_folder:
        base = top_level[0] / shoot_folder
        shoot_subfolders = [
            base / "00_RAW",  # RAW images (lazy subfolders can be added later)
            base / "01_Cull",
            base / "02_Edits",
            base / "03_Exports" / "Web",
            base / "03_Exports" / "Print",
            base / "03_Exports" / "Social",
            base / "99_Archive",
        ]

    # Combine everything
    all_folders = (
        top_level
        + client_subfolders
        + catalog_subfolders
        + preset_subfolders
        + video_subfolders
        + assets_subfolders
        + shoot_subfolders
    )

    # Create folders on disk
    for folder in all_folders:
        folder.mkdir(parents=True, exist_ok=True)

    return all_folders


# Example usage:
if __name__ == "__main__":
    created = build_media_shoot_structure("/path/to/Media", shoot_name="Wedding-Julia")
    print(f"Created {len(created)} folders under Media/")
