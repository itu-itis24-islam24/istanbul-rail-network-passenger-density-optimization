import pandas as pd
import re


capacity_file = "istanbul_rayli_sistem_verileri_guncel.csv"

capacity_df = pd.read_csv(capacity_file)
capacity_df.head()


capacity_df.columns.tolist()


required_columns = [
    "Hat_Adi",
    "Set_Kapasitesi_Yolcu",
    "Toplam_Arac_Sayisi",
    "Ortalama_Hiz_km_h",
    "Set_Uzunlugu_Vagon"
]

missing_columns = [col for col in required_columns if col not in capacity_df.columns]

if missing_columns:
    raise ValueError(f"Missing columns in capacity file: {missing_columns}")

print("All required columns exist.")


capacity_df["line_raw"] = capacity_df["Hat_Adi"].astype(str).str.strip()
capacity_df["line"] = capacity_df["line_raw"].str.upper()

capacity_df[["Hat_Adi", "line"]].drop_duplicates().sort_values("line").head(50)


def is_selected_rail_line(line: str) -> bool:
    line = str(line).strip().upper()

    is_metro = bool(re.match(r"^M\d+[A-Z]?$", line))
    is_funicular = bool(re.match(r"^F\d+[A-Z]?$", line))

    # Some datasets may use TF for cable/funicular-like systems.
    # If your project does not want TF lines, remove this condition.
    is_tf_line = bool(re.match(r"^TF\d+[A-Z]?$", line))

    is_tunel = line in ["TUNEL", "TÜNEL"]
    is_marmaray = line == "MARMARAY"

    return is_metro or is_funicular or is_tf_line or is_tunel or is_marmaray


rail_df = capacity_df[capacity_df["line"].apply(is_selected_rail_line)].copy()

print("Selected lines:")
print(sorted(rail_df["line"].unique()))

rail_df


rail_df = rail_df[
    [
        "line",
        "Set_Kapasitesi_Yolcu",
        "Toplam_Arac_Sayisi",
        "Ortalama_Hiz_km_h",
        "Set_Uzunlugu_Vagon"
    ]
].copy()

rail_df = rail_df.rename(columns={
    "Set_Kapasitesi_Yolcu": "standard_capacity_passengers",
    "Toplam_Arac_Sayisi": "total_vehicle_count",
    "Ortalama_Hiz_km_h": "avg_speed_kmh",
    "Set_Uzunlugu_Vagon": "standard_wagon_count"
})

rail_df.head()


numeric_columns = [
    "standard_capacity_passengers",
    "total_vehicle_count",
    "avg_speed_kmh",
    "standard_wagon_count"
]

for col in numeric_columns:
    rail_df[col] = (
        rail_df[col]
        .astype(str)
        .str.replace(",", ".", regex=False)
        .str.extract(r"([-+]?[0-9]*\.?[0-9]+)", expand=False)
    )
    rail_df[col] = pd.to_numeric(rail_df[col], errors="coerce")

rail_df


def classify_system_type(line: str) -> str:
    line = str(line).strip().upper()

    if line == "MARMARAY":
        return "marmaray"
    if re.match(r"^M\d+[A-Z]?$", line):
        return "metro"
    if re.match(r"^F\d+[A-Z]?$", line) or re.match(r"^TF\d+[A-Z]?$", line) or line in ["TUNEL", "TÜNEL"]:
        return "funicular_or_cable"
    return "other"


rail_df["system_type"] = rail_df["line"].apply(classify_system_type)
rail_df[["line", "system_type"]].drop_duplicates().sort_values("line")


rail_df["effort_per_extra_trip"] = 1.00
rail_df["effort_unit"] = "one additional standard trip"
rail_df["cost_interpretation"] = "normalized operational effort, not monetary cost"

rail_df.head()


operational_effort_df = rail_df[
    [
        "line",
        "system_type",
        "standard_capacity_passengers",
        "effort_per_extra_trip",
        "effort_unit",
        "cost_interpretation",
        "total_vehicle_count",
        "avg_speed_kmh",
        "standard_wagon_count"
    ]
].copy()

operational_effort_df = operational_effort_df.sort_values(["system_type", "line"]).reset_index(drop=True)

operational_effort_df


print("Number of selected lines:", operational_effort_df["line"].nunique())
print("Selected lines:")
print(sorted(operational_effort_df["line"].unique()))

print("\nMissing values:")
print(operational_effort_df.isna().sum())


# The most important columns must not be missing.
critical_columns = [
    "line",
    "standard_capacity_passengers",
    "effort_per_extra_trip"
]

critical_missing = operational_effort_df[critical_columns].isna().sum()

if critical_missing.sum() > 0:
    raise ValueError(f"Critical missing values found:\n{critical_missing}")

print("Critical columns are complete.")


output_file = "operational_effort_coefficients.csv"

operational_effort_df.to_csv(output_file, index=False)

print(f"Saved: {output_file}")


check_df = pd.read_csv("operational_effort_coefficients.csv")
check_df
