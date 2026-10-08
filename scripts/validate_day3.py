import pytest

if __name__ == "__main__":
    raise SystemExit(pytest.main(["tests/test_day3_feasibility.py", "tests/test_day3_silver.py", "-q", "-p", "no:cacheprovider",
                                 "--basetemp=data/tmp/pytest-day3", "--junitxml=results/day3/day3_pytest.xml"]))
