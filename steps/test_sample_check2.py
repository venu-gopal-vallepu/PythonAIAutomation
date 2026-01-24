import time

import pytest


@pytest.mark.sanity
def test_sample_tc__4():
    marks = [1, 2, 4]
    time.sleep(1)
    assert len(marks) == 0

