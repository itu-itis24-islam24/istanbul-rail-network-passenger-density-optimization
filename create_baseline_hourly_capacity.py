import csv
from pathlib import Path

train_path = Path("hourly_metro_train_numbers.csv")
effort_path = Path("operational_effort_coefficients.csv")
out_path = Path("baseline_hourly_capacity.csv")

# Load capacity / effort coefficients
with effort_path.open(newline="", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    effort_rows = list(reader)

capacity_by_line = {row["line"].strip(): row for row in effort_rows}

# Train frequency file has M1A/M1B, capacity file has shared M1 capacity.
line_mapping = {
    "M1A": "M1",
    "M1B": "M1",
}

output_rows = []
unmatched = set()

with train_path.open(newline="", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    for row in reader:
        hat_adi = row["hat_adi"].strip()
        saat = row["saat"].strip()
        capacity_line_key = line_mapping.get(hat_adi, hat_adi)
        cap = capacity_by_line.get(capacity_line_key)

        if cap is None:
            unmatched.add(hat_adi)
            continue

        sefer_sayisi = int(row["sefer_sayisi"])
        standard_capacity = float(cap["standard_capacity_passengers"])
        effort_per_extra_trip = float(cap["effort_per_extra_trip"])

        baseline_capacity = sefer_sayisi * standard_capacity
        baseline_operational_effort = sefer_sayisi * effort_per_extra_trip

        output_rows.append({
            "hat_adi": hat_adi,
            "capacity_line_key": capacity_line_key,
            "saat": saat,
            "sefer_sayisi": sefer_sayisi,
            "standard_capacity_passengers": int(standard_capacity) if standard_capacity.is_integer() else standard_capacity,
            "baseline_capacity_passengers": int(baseline_capacity) if baseline_capacity.is_integer() else baseline_capacity,
            "effort_per_extra_trip": effort_per_extra_trip,
            "baseline_operational_effort": baseline_operational_effort,
        })

fieldnames = [
    "hat_adi",
    "capacity_line_key",
    "saat",
    "sefer_sayisi",
    "standard_capacity_passengers",
    "baseline_capacity_passengers",
    "effort_per_extra_trip",
    "baseline_operational_effort",
]

with out_path.open("w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(output_rows)

print(f"Saved {len(output_rows)} rows to {out_path}")
if unmatched:
    print("Unmatched lines:", sorted(unmatched))
