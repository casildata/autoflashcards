import pytest
from make_fixtures import build_cells_pdf, build_two_column_pdf


@pytest.fixture(scope="session")
def cells_pdf(tmp_path_factory):
    return build_cells_pdf(tmp_path_factory.mktemp("fixtures") / "cells.pdf")


@pytest.fixture(scope="session")
def two_column_pdf(tmp_path_factory):
    return build_two_column_pdf(tmp_path_factory.mktemp("fixtures") / "two_column.pdf")
