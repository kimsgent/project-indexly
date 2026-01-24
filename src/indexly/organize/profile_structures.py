from datetime import date

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


def build_media_shoot_structure(shoot_name: str | None = None) -> list[str]:
    today = date.today().isoformat()[:7]  # YYYY-MM
    shoot = f"{today}-{shoot_name}" if shoot_name else today
    base = f"Media/Shoots/{shoot}"
    return [
        f"{base}/RAW",
        f"{base}/Edited",
        f"{base}/Export",
    ]
