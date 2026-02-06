import pytest


def test_loki_e2e_removed():
    pytest.skip("E2E Loki test removed: project now uses Grafana Alloy to scrape logs from containers and files.")
