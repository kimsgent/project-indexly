from .base_rules import get_destination as base_get_destination
from .data_rules import get_destination as data_get_destination
from .it_rules import get_destination as it_get_destination
from .health_rules import get_destination as health_get_destination
from .media_rules import get_destination as media_get_destination
from .education_rules import get_destination as education_get_destination

PROFILE_RULES = {
    "data": data_get_destination,
    "it": it_get_destination,
    "health": health_get_destination,
    "media": media_get_destination,
    "education": education_get_destination,
}
