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
    paradigm: str = "frequentist"
    evidence: Optional[float] = None
    additional_table: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def interpretation(self) -> Optional[str]:
        """
        Returns an interpretation string depending on statistical paradigm.
        - Frequentist: based on p-value
        - Bayesian: based on Bayes Factor (evidence)
        """

        # -----------------------------
        # Frequentist interpretation
        # -----------------------------
        if self.paradigm == "frequentist":
            if self.p_value is None:
                return None

            if self.p_value < 0.001:
                sig = "highly significant"
            elif self.p_value < 0.05:
                sig = "statistically significant"
            else:
                sig = "not statistically significant"

            return f"{self.test_name} result is {sig} (p = {self.p_value:.5f})."

        # -----------------------------
        # Bayesian interpretation
        # -----------------------------
        if self.paradigm == "bayesian":
            if self.evidence is None:
                return None

            bf = self.evidence

            if bf < 1:
                interp = "evidence favors the null hypothesis"
            elif bf < 3:
                interp = "anecdotal evidence for the alternative hypothesis"
            elif bf < 10:
                interp = "moderate evidence for the alternative hypothesis"
            else:
                interp = "strong evidence for the alternative hypothesis"

            return f"{self.test_name} result shows {interp} (BF10 = {bf:.3f})."

        return None

    def to_dict(self) -> Dict[str, Any]:
        """
        Unified dictionary export supporting both paradigms.
        """

        return {
            "test_name": self.test_name,
            "paradigm": self.paradigm,
            "statistic": self.statistic,
            "p_value": self.p_value,
            "evidence": self.evidence,  # Bayes Factor if Bayesian
            "effect_size": self.effect_size,
            "ci_low": self.ci_low,
            "ci_high": self.ci_high,
            "additional_table": self.additional_table,
            "metadata": self.metadata,
            "interpretation": self.interpretation(),
        }
