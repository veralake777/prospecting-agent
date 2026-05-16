import csv
from pathlib import Path

def export_rows(path: str, rows: list[dict]):
    p = Path(path)
    if not rows:
        return p
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    return p
