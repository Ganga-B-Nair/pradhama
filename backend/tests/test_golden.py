"""Golden-bundle regression test — docs/HACKATHON_PLAN.md §9.

Runs against a SEPARATE database (`trace_test`, not `trace_demo`) so repeated
test runs during the hackathon never show up in the case list the judges see,
and the live demo's case history (kept across runs, per team decision) is
never disturbed.

TODO(V/G): fill in once golden/expected.json exists and the pipeline runs
end-to-end. Not meant to pass before CP2 (H11).
"""
import json
import os

import pytest

os.environ["MONGO_DB"] = "trace_test"  # must be set before app.db is imported anywhere


EXPECTED_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "golden", "expected.json")


@pytest.mark.skip(reason="golden/expected.json and the pipeline aren't wired up yet")
def test_golden_bundle_end_to_end():
    with open(EXPECTED_PATH) as f:
        expected = json.load(f)

    # TODO: create a case in trace_test, upload the golden bundle files,
    # run the pipeline, and assert against `expected` (11 events, the gaps
    # that should fire, 4 BNS suggestions, 2 referrals).
    raise NotImplementedError
