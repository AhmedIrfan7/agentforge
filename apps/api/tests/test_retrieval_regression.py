"""Runs eval/regression.py's real retrieval-quality regression check
through pytest too (roadmap step 135), so a future change that
silently degrades keyword search fails CI, not just a manual
`python -m eval.regression` run.
"""

import pytest

from eval.regression import MIN_PRECISION, MIN_RECALL, run_regression


@pytest.mark.anyio
async def test_retrieval_quality_has_not_regressed() -> None:
    report = await run_regression()

    assert report.mean_precision >= MIN_PRECISION
    assert report.mean_recall >= MIN_RECALL
