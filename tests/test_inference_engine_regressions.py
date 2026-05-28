import os

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/indexly-mpl-cache")

import numpy as np
import pandas as pd
import pytest
import statsmodels.formula.api as smf
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.power import FTestAnovaPower, FTestPowerF2

from src.indexly.inference.anova import run_anova
from src.indexly.inference.bayesian import run_bayesian_ttest
from src.indexly.inference.cli import run_inference_engine
from src.indexly.inference.multiple_corrections import apply_correction
from src.indexly.inference.power import (
    eta_squared_to_cohen_f,
    power_anova,
    power_ols,
)
from src.indexly.inference.regression import run_ols


def test_bayesian_ttest_reports_bf10_as_alternative_evidence():
    base = [1, 2, 1, 2, 1, 2, 1, 2]
    null_df = pd.DataFrame({"group": ["A"] * 8 + ["B"] * 8, "y": base + base})
    shifted_df = pd.DataFrame(
        {"group": ["A"] * 8 + ["B"] * 8, "y": base + [v + 1 for v in base]}
    )

    null_result = run_bayesian_ttest(null_df, "y", "group")
    shifted_result = run_bayesian_ttest(shifted_df, "y", "group")

    assert null_result.paradigm == "bayesian"
    assert null_result.evidence == pytest.approx(null_result.additional_table["bf10"])
    assert null_result.evidence < 1
    assert shifted_result.evidence > 1
    assert shifted_result.evidence > null_result.evidence


def test_power_helpers_match_statsmodels_reference_implementations():
    f2, predictors, nobs = 0.15, 3, 80
    expected_ols = FTestPowerF2().power(
        effect_size=f2,
        df_num=predictors,
        df_denom=nobs - predictors - 1,
        alpha=0.05,
    )

    eta2, groups, total = 0.20, 3, 60
    cohen_f = eta_squared_to_cohen_f(eta2)
    expected_anova = FTestAnovaPower().power(
        effect_size=cohen_f,
        k_groups=groups,
        nobs=total,
        alpha=0.05,
    )

    assert power_ols(f2, predictors, nobs) == pytest.approx(expected_ols)
    assert power_anova(cohen_f, groups, total) == pytest.approx(expected_anova)


def test_multiple_corrections_match_statsmodels_and_preserve_order():
    p_values = np.array([0.04, 0.001, 0.03, 0.20])

    assert np.allclose(
        apply_correction(p_values, "holm"),
        multipletests(p_values, method="holm")[1],
    )
    assert np.allclose(
        apply_correction(p_values, "bh"),
        multipletests(p_values, method="fdr_bh")[1],
    )


def test_paired_ttest_dispatcher_populates_unified_result_fields():
    df = pd.DataFrame({"before": [10, 12, 13, 15], "after": [9, 10, 12, 14]})

    result = run_inference_engine(
        df,
        test="paired-ttest",
        x=["before", "after"],
        bootstrap=False,
    )

    assert result.test_name == "paired_ttest"
    assert result.effect_size == pytest.approx(2.5)
    assert result.ci_low is not None
    assert result.ci_high is not None
    assert result.metadata["effect_size_type"] == "cohens_dz"


def test_ols_single_predictor_vif_and_robust_ci_are_valid():
    rng = np.random.default_rng(42)
    x = np.linspace(1, 100, 120)
    y = 2 + 0.5 * x + rng.normal(0, x / 8, size=len(x))
    single_df = pd.DataFrame({"x": x, "y": y})

    single_result = run_ols(single_df, "y", ["x"], auto_route=True)
    assert single_result.additional_table["vif"]["VIF"][0] == pytest.approx(1.0)

    z = rng.normal(size=len(x))
    hetero_y = 2 + 0.5 * x + 0.1 * z + rng.normal(0, x / 8, size=len(x))
    df = pd.DataFrame({"x": x, "z": z, "y": hetero_y})
    result = run_ols(df, "y", ["x", "z"], auto_route=True)

    standard = smf.ols("y ~ x + z", data=df).fit()
    robust = standard.get_robustcov_results(cov_type="HC3")
    reported_ci = result.additional_table["coefficients_ci"].loc["x"].to_numpy()

    assert result.metadata["route_selected"] == "robust"
    assert np.allclose(reported_ci, robust.conf_int()[1])


def test_mixed_effects_dispatcher_builds_formula_from_cli_style_args():
    df = pd.DataFrame(
        {
            "subject": ["s1", "s1", "s2", "s2", "s3", "s3", "s4", "s4"],
            "x": [0, 1, 0, 1, 0, 1, 0, 1],
            "y": [1, 2, 1.5, 2.4, 0.8, 1.9, 1.2, 2.1],
        }
    )

    result = run_inference_engine(df, test="mixed", y="y", group="subject", x=["x"])

    assert result.test_name == "mixed_effects_model"
    assert result.metadata["formula"] == "y ~ x"


def test_anova_auto_route_uses_welch_for_normal_unequal_variance_groups():
    rng = np.random.default_rng(0)
    df = pd.DataFrame(
        {
            "group": np.repeat(["A", "B", "C"], 60),
            "y": np.concatenate(
                [
                    rng.normal(0, 1, 60),
                    rng.normal(0.2, 4, 60),
                    rng.normal(0.4, 7, 60),
                ]
            ),
        }
    )

    result = run_anova(df, "y", "group", auto_route=True)

    assert result.test_name == "welch_anova"
    assert result.metadata["route_selected"] == "welch_anova"
    assert not bool(result.additional_table["homogeneity"]["equal_variance"])
