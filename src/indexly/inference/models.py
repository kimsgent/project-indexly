from dataclasses import dataclass, field
from typing import Dict, Any, Optional


@dataclass
class InferenceResult:
    test_name: str
    statistic: Optional[float]
    p_value: Optional[float]
    effect_size: Optional[float] = None
    ci_low: Optional[float] = None
    ci_high: Optional[float] = None
    additional_table: Optional[Dict[str, Any]] = field(default=None)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def interpretation(self) -> Optional[str]:
        if self.p_value is None:
            return None

        if self.p_value < 0.001:
            sig = "highly significant"
        elif self.p_value < 0.05:
            sig = "statistically significant"
        else:
            sig = "not statistically significant"

        return f"{self.test_name} result is {sig} (p = {self.p_value:.5f})."

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_name": self.test_name,
            "statistic": self.statistic,
            "p_value": self.p_value,
            "effect_size": self.effect_size,
            "ci_low": self.ci_low,
            "ci_high": self.ci_high,
            "additional_table": self.additional_table,
            "metadata": self.metadata,
            "interpretation": self.interpretation(),
        }
