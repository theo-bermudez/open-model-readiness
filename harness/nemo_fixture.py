"""Original four-prompt NeMo integration fixture; not a standard benchmark.

Loaded by NeMo as --bench harness/nemo_fixture.py. Requires the optional pinned
NeMo environment described in reports/nemo-feasibility.md. No dataset download.
"""
from nemo_evaluator.environments.custom import benchmark, scorer
from nemo_evaluator.scoring import ScorerInput, exact_match

from harness.matched_replay import FIXTURES


# NeMo 0.3.0 forwards every dataset column as verify(**metadata). A column
# named "expected" collides with verify's positional parameter; use "answer".
def fixture_rows():
    return [{"id": f["id"], "prompt": f["prompt"], "answer": f["expected"]} for f in FIXTURES]


@benchmark(name="omr_original_fixture", dataset=fixture_rows,
           prompt="{prompt}", target_field="answer")
@scorer
def original_fixture_scorer(sample: ScorerInput) -> dict:
    return exact_match(sample)
