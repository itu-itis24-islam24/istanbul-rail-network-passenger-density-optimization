import pandas as pd

DEMAND_FILE = "rayli_sistem_temiz.csv"
TRAIN_FILE = "hourly_metro_train_numbers.csv"
EFFORT_FILE = "operational_effort_coefficients.csv"

OUTPUT_FILE = "baseline_load_ratios_no_m1_merge.csv"
MISSING_REPORT_FILE = "baseline_load_ratio_missing_report_no_m1_merge.csv"


def normalize_line_column(df, col):
    df[col] = df[col].astype(str).str.strip().str.upper()
    return df


def capacity_key(line):
    """
    IMPORTANT:
    M1A and M1B are NOT merged as demand/trip lines.
    They only use M1 as capacity key, because the capacity file has one M1
    vehicle capacity entry and the vehicle type is assumed to be the same.
    """
    if line in ["M1A", "M1B"]:
        return "M1"
    return line


def main():
    demand = pd.read_csv(DEMAND_FILE)
    trains = pd.read_csv(TRAIN_FILE)
    effort = pd.read_csv(EFFORT_FILE)

    demand = normalize_line_column(demand, "hat_adi")
    trains = normalize_line_column(trains, "hat_adi")
    effort = normalize_line_column(effort, "line")

    demand["saat"] = pd.to_numeric(demand["saat"], errors="coerce")
    demand["toplam_yolcu"] = pd.to_numeric(demand["toplam_yolcu"], errors="coerce")
    trains["saat"] = pd.to_numeric(trains["saat"], errors="coerce")
    trains["sefer_sayisi"] = pd.to_numeric(trains["sefer_sayisi"], errors="coerce")
    effort["standard_capacity_passengers"] = pd.to_numeric(
        effort["standard_capacity_passengers"], errors="coerce"
    )
    effort["effort_per_extra_trip"] = pd.to_numeric(
        effort["effort_per_extra_trip"], errors="coerce"
    )

    # Demand: keep each line separate.
    # First sum all stations for each line-date-hour.
    daily_line_hour = (
        demand.dropna(subset=["hat_adi", "tarih", "saat", "toplam_yolcu"])
        .groupby(["hat_adi", "tarih", "saat"], as_index=False)["toplam_yolcu"]
        .sum()
        .rename(columns={"toplam_yolcu": "daily_hourly_demand"})
    )

    # Then average daily line-hour demand over available dates.
    avg_demand = (
        daily_line_hour
        .groupby(["hat_adi", "saat"], as_index=False)
        .agg(
            avg_hourly_demand=("daily_hourly_demand", "mean"),
            median_hourly_demand=("daily_hourly_demand", "median"),
            max_hourly_demand=("daily_hourly_demand", "max"),
            observed_day_count=("daily_hourly_demand", "count"),
        )
    )

    # Train counts: keep M1A and M1B separate.
    trains_clean = (
        trains.dropna(subset=["hat_adi", "saat", "sefer_sayisi"])
        .groupby(["hat_adi", "saat"], as_index=False)["sefer_sayisi"]
        .sum()
    )

    # Capacity match only.
    # M1A and M1B use the M1 capacity row, but they remain separate lines.
    trains_clean["capacity_line_key"] = trains_clean["hat_adi"].map(capacity_key)

    effort_small = effort[
        ["line", "standard_capacity_passengers", "effort_per_extra_trip"]
    ].copy()
    effort_small = effort_small.rename(columns={"line": "capacity_line_key"})

    train_capacity = trains_clean.merge(
        effort_small,
        on="capacity_line_key",
        how="left",
    )

    # Merge demand by original hat_adi and saat.
    # This prevents M1A and M1B from being merged into M1.
    baseline = train_capacity.merge(
        avg_demand,
        on=["hat_adi", "saat"],
        how="left",
    )

    baseline["baseline_capacity_passengers"] = (
        baseline["sefer_sayisi"] * baseline["standard_capacity_passengers"]
    )
    baseline["baseline_operational_effort"] = (
        baseline["sefer_sayisi"] * baseline["effort_per_extra_trip"]
    )
    baseline["baseline_load_ratio"] = (
        baseline["avg_hourly_demand"] / baseline["baseline_capacity_passengers"]
    )

    output_cols = [
        "hat_adi",
        "capacity_line_key",
        "saat",
        "avg_hourly_demand",
        "median_hourly_demand",
        "max_hourly_demand",
        "observed_day_count",
        "sefer_sayisi",
        "standard_capacity_passengers",
        "baseline_capacity_passengers",
        "baseline_load_ratio",
        "effort_per_extra_trip",
        "baseline_operational_effort",
    ]

    baseline_out = baseline[output_cols].copy()

    # Keep only line-hours where demand exists and capacity is positive.
    valid = baseline_out[
        baseline_out["avg_hourly_demand"].notna()
        & baseline_out["standard_capacity_passengers"].notna()
        & (baseline_out["baseline_capacity_passengers"] > 0)
    ].copy()

    # Missing report
    missing_rows = []

    for line in sorted(
        train_capacity.loc[
            train_capacity["standard_capacity_passengers"].isna(), "hat_adi"
        ].unique()
    ):
        missing_rows.append({
            "issue": "train_count_line_has_no_capacity_match",
            "hat_adi": line,
            "saat": None,
            "detail": "Sefer sayısı var ama capacity dosyasında eşleşen kapasite yok.",
        })

    no_demand = baseline[
        baseline["avg_hourly_demand"].isna()
    ][["hat_adi", "saat", "capacity_line_key"]].drop_duplicates()

    for _, r in no_demand.iterrows():
        missing_rows.append({
            "issue": "train_count_line_hour_has_no_demand",
            "hat_adi": r["hat_adi"],
            "saat": int(r["saat"]),
            "detail": (
                "Sefer sayısı var ama yolcu talebinde aynı hat-saat yok. "
                "M1A/M1B kapasite için M1'e bağlandı ama talep birleştirilmedi."
            ),
        })

    train_line_hours = set(
        map(tuple, trains_clean[["hat_adi", "saat"]].drop_duplicates().values.tolist())
    )

    for _, r in avg_demand[["hat_adi", "saat"]].drop_duplicates().iterrows():
        if (r["hat_adi"], r["saat"]) not in train_line_hours:
            missing_rows.append({
                "issue": "demand_line_hour_has_no_train_count",
                "hat_adi": r["hat_adi"],
                "saat": int(r["saat"]),
                "detail": (
                    f"Yolcu talebi var ama sefer sayısı dosyasında "
                    f"{r['hat_adi']} için aynı hat-saat yok."
                ),
            })

    missing_report = pd.DataFrame(missing_rows)

    valid.to_csv(OUTPUT_FILE, index=False)
    missing_report.to_csv(MISSING_REPORT_FILE, index=False)

    print(f"Saved: {OUTPUT_FILE}")
    print(f"Saved: {MISSING_REPORT_FILE}")
    print(f"Rows in output: {len(valid)}")
    print("Lines in output:", sorted(valid["hat_adi"].unique()))


if __name__ == "__main__":
    main()
