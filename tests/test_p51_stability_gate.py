import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments'))
from p51_run_stability import validate_stability_limits

def test_explicit_bounded_trial_only():
    validate_stability_limits(1800000,0)

@pytest.mark.parametrize('duration,cancel',[(0,0),(60000,0),(86400000,0),(1800000,1000),(True,0),(1800000.0,0)])
def test_short_unbounded_or_cancellable_runs_cannot_claim_thirty_minutes(duration,cancel):
    with pytest.raises(ValueError):validate_stability_limits(duration,cancel)
