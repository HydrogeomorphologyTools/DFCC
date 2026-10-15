"""Energy rule reproduces the stop points of the Procedura-DF Excel example (16_point_profile.xlsx)."""
import csv
from pathlib import Path
from dfcc.core import runout

D = Path(__file__).parent / "data"


def test_excel_profile():
    rows = list(csv.DictReader(open(D / "excel_profile.csv")))
    cls = [int(r["cls"]) for r in rows]
    x = [float(r["x"]) for r in rows]
    y = [float(r["y"]) for r in rows]
    z = [float(r["z"]) for r in rows]
    exp = [i for i, r in enumerate(rows) if r["excel_stop"] == "stop"]
    R = runout.profile_runout(cls, z, x, y)
    assert R.stops == exp == [101, 122, 152, 562]
    assert R.final_stop == 562
