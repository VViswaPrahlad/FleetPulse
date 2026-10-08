"""Run meaningful fixture validation with all test artifacts inside the project."""
import pytest

if __name__ == "__main__":
    raise SystemExit(pytest.main(["tests/test_ved_ingestion.py", "-q",
                                 "--basetemp=data/tmp/pytest-day2",
                                 "--junitxml=results/day2_pytest.xml"]))
