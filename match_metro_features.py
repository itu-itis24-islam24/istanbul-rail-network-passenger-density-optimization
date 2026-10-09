import numpy as np
import pandas as pd

METRO_PATH   = "rayli_sistem_temiz.csv"
MATCHES_PATH = "big3_22kasım_24ekim.csv"
OUTPUT_PATH  = "match_station_offset_features.csv"
OFFSET_RANGE = (-12, 12)

def load_metro(path):
    df = pd.read_csv(path, encoding="utf-8-sig",
                     dtype={"hat_adi": "string", "durak_adi": "string"})
    df = df.rename(columns={"hat_adi": "line", "durak_adi": "station",
                             "tarih": "date", "saat": "hour",
                             "toplam_yolcu": "passengers"})
    bad = (df["station"].isna() | df["line"].isna() |
           df["station"].str.upper().eq("NAN") | df["line"].str.upper().eq("NAN"))
    df = df[~bad].copy()
    df["date"]       = pd.to_datetime(df["date"], errors="coerce")
    df["hour"]       = pd.to_numeric(df["hour"], errors="coerce").astype("Int8")
    df["passengers"] = pd.to_numeric(df["passengers"], errors="coerce").fillna(0).astype("int32")
    df = df.dropna(subset=["date", "hour"])
    df["datetime"] = df["date"] + pd.to_timedelta(df["hour"].astype("int8"), unit="h")
    df["line"]    = df["line"].astype("category")
    df["station"] = df["station"].astype("category")
    return df[["line", "station", "datetime", "passengers"]].reset_index(drop=True)


def load_matches(path):
    df = pd.read_csv(path, encoding="utf-8-sig")
    df = df.rename(columns={"Team": "team", "Date": "date", "Time": "time"})
    df["team"] = df["team"].str.strip().str.lower()
    df["match_datetime"] = pd.to_datetime(
        df["date"].astype(str) + " " + df["time"].astype(str), errors="coerce")
    df = df.dropna(subset=["match_datetime"])
    df["match_hour_bucket"] = df["match_datetime"].dt.floor("h")
    return df[["team", "match_datetime", "match_hour_bucket"]].reset_index(drop=True)


def build_baseline(metro, match_dates):
    base = metro[~metro["datetime"].dt.normalize().isin(match_dates)]
    base = base.assign(weekday=base["datetime"].dt.weekday.astype("int8"),
                       hour=base["datetime"].dt.hour.astype("int8"))
    return (base.groupby(["line", "station", "weekday", "hour"], observed=True)["passengers"]
                .agg(baseline_mean="mean", baseline_std="std")
                .reset_index()
                .assign(baseline_std=lambda x: x["baseline_std"].fillna(0.0)))


def run(metro_path, matches_path, output_path, offset_range):
    metro   = load_metro(metro_path)
    matches = load_matches(matches_path)

    baseline = build_baseline(metro, matches["match_datetime"].dt.normalize().unique())

    lo, hi = offset_range
    grid   = matches.merge(pd.DataFrame({"hour_offset": np.arange(lo, hi + 1, dtype="int8")}),
                           how="cross")
    grid["query_datetime"] = (grid["match_hour_bucket"]
                              + pd.to_timedelta(grid["hour_offset"].astype("int16"), unit="h"))

    merged = (grid
              .merge(metro, left_on="query_datetime", right_on="datetime", how="inner")
              .drop(columns=["datetime"]))

    merged = merged.assign(
        weekday=merged["query_datetime"].dt.weekday.astype("int8"),
        hour=merged["query_datetime"].dt.hour.astype("int8"),
    ).merge(baseline, on=["line", "station", "weekday", "hour"], how="left")

    merged["change"] = merged["passengers"] - merged["baseline_mean"]

    feat = (merged
            .groupby(["team", "line", "station", "hour_offset"], observed=True)
            .agg(mean_change=("change", "mean"))
            .reset_index())

    feat["mean_change"] = feat["mean_change"].round(2)
    feat = feat.sort_values(["team", "line", "station", "hour_offset"]).reset_index(drop=True)
    feat.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"Saved {len(feat):,} rows -> {output_path}")
    return feat


if __name__ == "__main__":
    run(METRO_PATH, MATCHES_PATH, OUTPUT_PATH, OFFSET_RANGE)
