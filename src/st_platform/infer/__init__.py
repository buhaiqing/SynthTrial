"""st-infer: paired statistics, effect sizes, CUPED, multiple-comparison correction."""

from .cuped import assert_pre_treatment_covariate, cuped_adjust, fit_theta
from .effect import absolute_lift, relative_lift
from .multicorrect import benjamini_hochberg, bonferroni, holm
from .paired import mcnemar, paired_t_test, wilcoxon_signed_rank
from .result import PairedResult, assert_correction_applied

__all__ = [
    "PairedResult",
    "absolute_lift",
    "assert_correction_applied",
    "assert_pre_treatment_covariate",
    "benjamini_hochberg",
    "bonferroni",
    "cuped_adjust",
    "fit_theta",
    "holm",
    "mcnemar",
    "paired_t_test",
    "relative_lift",
    "wilcoxon_signed_rank",
]
