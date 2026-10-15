import pandas as pd
import pytest

from backend.data import ProjectError
from backend.public_history import normalize_public_subset


def row(**changes):
    result = {"State Name": "Maharashtra", "District Name": "Pune", "Market Name": "Pune", "Variety": "Local",
        "Reported Date": "01 Jan 2021", "Min Price (Rs./Quintal)": 800, "Max Price (Rs./Quintal)": 1200,
        "Modal Price (Rs./Quintal)": 1000, "Arrivals (Tonnes)": 10}
    result.update(changes)
    return result


def test_published_source_mapping_and_no_imputation():
    frame, quality = normalize_public_subset(pd.DataFrame([row()]))
    assert frame.date.iloc[0] == "2021-01-01"
    assert frame.modal_price.iloc[0] == 1000
    assert frame.grade.iloc[0] == "Unspecified"
    assert quality["price_imputation"].startswith("None")


def test_pilot_excludes_other_varieties_and_unselected_markets():
    frame, quality = normalize_public_subset(pd.DataFrame([row(), row(Variety="Other"), row(**{"Market Name": "Unselected"})]))
    assert len(frame) == 1
    assert quality["selected_rows"] == 1


def test_zero_prices_and_conflicting_days_are_excluded():
    frame, quality = normalize_public_subset(pd.DataFrame([row(), row(**{"Modal Price (Rs./Quintal)": 1100}),
        row(**{"Reported Date": "02 Jan 2021", "Min Price (Rs./Quintal)": 0}), row(**{"Reported Date": "03 Jan 2021"})]))
    assert frame.date.tolist() == ["2021-01-03"]
    assert quality["invalid_price_rows_excluded"] == 1
    assert quality["conflicting_rows_excluded"] == 2


def test_published_source_schema_is_required():
    with pytest.raises(ProjectError, match="schema"):
        normalize_public_subset(pd.DataFrame([{"price": 1000}]))
