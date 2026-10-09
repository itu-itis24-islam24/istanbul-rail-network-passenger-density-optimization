"""
=============================================================================
Urban Transit OD Matrix Estimator  —  IBB Raylı Sistem Edition
=============================================================================
Method : Principle of Diurnal Asymmetry + Conservation of Flow
Input  : rayli_sistem_temiz.csv  (3.45 M rows, 23 lines, 266 stations)
Output : estimated_hourly_od_matrix.csv

Real-world anomalies handled
-----------------------------
A. Single-station lines (NOSTRAM, T3, TF1)
   After zeroing the self-loop (j != i) there are ZERO valid destinations.
   These lines are quarantined before OD computation, logged, and written
   to a separate "unroutable" report.  They must not enter the assertion.

B. Minimal-station lines (F1, F4, TF2, TUNEL -- 2 stations each)
   After self-loop removal only 1 destination remains.  PATH B uniform
   fallback fires: P = 1.0 for the single valid destination.

C. Literal station name "NAN" (NOSTRAM, T3)
   pandas converts "NAN" -> float NaN unless keep_default_na=False is set.
   The CSV reader is patched to prevent this silent data corruption.

D. Ghost hours / zero-volume windows
   The dataset as delivered has no zero-volume rows, but the pipeline
   defends against them anyway for production robustness (PATH C).

Normalisation decision tree (three paths, fully vectorised)
------------------------------------------------------------
  PATH A -- Normal gravity    row_total > 0
            P = raw_weight / row_total

  PATH B -- Uniform fallback  row_total == 0  AND  origin_entries > 0
            P = 1 / (N_line - 1)   for j != i
            P = 0.0                for j == i
            Fires on minimal-station lines and any station whose
            footprint weights are all zero.

  PATH C -- Ghost hour        origin_entries == 0
            P = 0.0  unconditionally; excluded from CoF assertion.

=============================================================================
"""

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# 0.  CONSTANTS
# ---------------------------------------------------------------------------
AM_START, AM_END = 7, 10          # morning rush  07:00 - 10:00  (inclusive)
PM_START, PM_END = 17, 20         # evening rush  17:00 - 20:00  (inclusive)

INPUT_FILE      = "rayli_sistem_temiz.csv"
OUTPUT_FILE     = "estimated_hourly_od_matrix.csv"
UNROUTABLE_FILE = "unroutable_single_station_lines.csv"

COF_TOLERANCE   = 1e-4            # max allowed |row_sum - 1.0|


# ---------------------------------------------------------------------------
# 1.  DATA VALIDATION & PREPROCESSING
# ---------------------------------------------------------------------------
def preprocess(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Validate schema, cast types, sanitise edge cases, and quarantine
    single-station lines that cannot produce valid OD pairs.

    Returns
    -------
    df_routable   : clean records for lines with >= 2 stations
    df_unroutable : records from single-station lines (logged, not modelled)
    """
    required = {"hat_adi", "durak_adi", "tarih", "saat", "toplam_yolcu"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Input DataFrame is missing columns: {missing}")

    df = df.copy()

    # Cast and sanitise numeric fields
    df["saat"] = pd.to_numeric(df["saat"], errors="coerce")
    df["toplam_yolcu"] = (
        pd.to_numeric(df["toplam_yolcu"], errors="coerce")
          .fillna(0)
          .clip(lower=0)
          .astype(float)
    )
    df = df.dropna(subset=["saat"])
    df["saat"] = df["saat"].astype(int)

    # Anomaly C: ensure durak_adi is always a plain string
    # keep_default_na=False at read time prevents "NAN"->float NaN, but
    # this cast is a belt-and-suspenders guard for downstream safety.
    df["hat_adi"]   = df["hat_adi"].astype(str).str.strip()
    df["durak_adi"] = df["durak_adi"].astype(str).str.strip()

    # Anomaly A: quarantine single-station lines
    # A line with only 1 unique station has no valid destination after the
    # j != i constraint is enforced.  Keeping them would make row sums
    # collapse to 0.0 and crash the Conservation-of-Flow assertion.
    station_counts = df.groupby("hat_adi")["durak_adi"].nunique()
    single_lines   = set(station_counts[station_counts < 2].index)

    df_unroutable = df[df["hat_adi"].isin(single_lines)].copy()
    df_routable   = df[~df["hat_adi"].isin(single_lines)].copy()

    return df_routable, df_unroutable


# ---------------------------------------------------------------------------
# 2.  BUILD PER-LINE FOOTPRINT WEIGHTS
# ---------------------------------------------------------------------------
def build_footprint_weights(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate across ALL dates for each (hat_adi, durak_adi) and compute:

      am_weight    : total boardings during morning rush (07-10)
      pm_weight    : total boardings during evening rush (17-20)
      daily_weight : total boardings across the full day

    Summing rather than averaging preserves relative station magnitude and
    is robust to days with missing records.
    Row-wise normalisation to a true probability is performed in step 3.
    """
    is_am = df["saat"].between(AM_START, AM_END)
    is_pm = df["saat"].between(PM_START, PM_END)
    key   = ["hat_adi", "durak_adi"]

    am_agg    = df[is_am].groupby(key, sort=False)["toplam_yolcu"].sum().rename("am_weight")
    pm_agg    = df[is_pm].groupby(key, sort=False)["toplam_yolcu"].sum().rename("pm_weight")
    daily_agg = df.groupby(key, sort=False)["toplam_yolcu"].sum().rename("daily_weight")

    weights = (
        pd.concat([am_agg, pm_agg, daily_agg], axis=1)
          .reset_index()
          .fillna(0)
    )
    return weights


# ---------------------------------------------------------------------------
# 3.  COMPUTE HOURLY OD PROBABILITIES  --  VECTORISED (hardened)
# ---------------------------------------------------------------------------
def compute_od_probabilities(
    hourly: pd.DataFrame,
    weights: pd.DataFrame,
) -> pd.DataFrame:
    """
    Produces a long-form OD probability matrix for every combination of
    (hat_adi, saat, origin_durak, destination_durak).

    All operations use numpy broadcasting or pandas transform -- no iterrows.

    Three-path normalisation
    ~~~~~~~~~~~~~~~~~~~~~~~~
    PATH A  Normal gravity   (row_total > 0)
            P = raw_weight / row_total

    PATH B  Uniform fallback (row_total == 0 AND origin_entries > 0)
            Fires when all destination weights collapse to 0 after zeroing
            the self-loop.  Applies to 2-station lines and any station whose
            footprint is entirely zero in the selected diurnal window.
            P = 1 / (N_line - 1)  for j != i
            P = 0.0               for j == i

    PATH C  Ghost hour       (origin_entries == 0)
            Operationally dead origin at this hour.
            P = 0.0  unconditionally; excluded from CoF assertion.
    """
    # 3a. Aggregate to (line, hour, station)
    entries = (
        hourly
        .groupby(["hat_adi", "saat", "durak_adi"], sort=False)["toplam_yolcu"]
        .sum()
        .reset_index()
        .rename(columns={"durak_adi": "origin_durak",
                         "toplam_yolcu": "origin_entries"})
    )

    # 3b. Cross-join origins with all destinations on the same line
    line_station_map = (
        weights[["hat_adi", "durak_adi"]]
        .drop_duplicates()
        .rename(columns={"durak_adi": "destination_durak"})
    )
    od_pairs = entries.merge(line_station_map, on="hat_adi", how="left")

    # 3c. Attach destination footprint weights
    dest_w = weights.rename(columns={
        "durak_adi"    : "destination_durak",
        "am_weight"    : "dest_am",
        "pm_weight"    : "dest_pm",
        "daily_weight" : "dest_daily",
    })
    od_pairs = od_pairs.merge(
        dest_w[["hat_adi", "destination_durak", "dest_am", "dest_pm", "dest_daily"]],
        on=["hat_adi", "destination_durak"],
        how="left",
    ).fillna({"dest_am": 0.0, "dest_pm": 0.0, "dest_daily": 0.0})

    # 3d. Zero out self-loops (j == i)
    # Boolean numpy array reused below for PATH B uniform weight computation.
    is_self = (od_pairs["origin_durak"] == od_pairs["destination_durak"]).to_numpy()
    od_pairs.loc[is_self, ["dest_am", "dest_pm", "dest_daily"]] = 0.0

    # 3e. Diurnal weight selection (np.select -- no Python loops)
    #   AM hours  -> destination's PM footprint
    #               workplaces are busy at PM -> they attract morning commuters
    #   PM hours  -> destination's AM footprint
    #               residential hubs are busy at AM -> they attract returnees
    #   Off-peak  -> destination's daily baseline (no directional signal)
    saat_np = od_pairs["saat"].to_numpy()
    cond_am = (saat_np >= AM_START) & (saat_np <= AM_END)
    cond_pm = (saat_np >= PM_START) & (saat_np <= PM_END)

    od_pairs["raw_weight"] = np.select(
        [cond_am,                         cond_pm],
        [od_pairs["dest_pm"].to_numpy(),  od_pairs["dest_am"].to_numpy()],
        default=od_pairs["dest_daily"].to_numpy(),
    )

    # 3f. Per-origin row totals (normalisation denominator)
    #    groupby + transform broadcasts the group sum back to every row.
    group_keys = ["hat_adi", "saat", "origin_durak"]
    row_totals = (
        od_pairs
        .groupby(group_keys, sort=False)["raw_weight"]
        .transform("sum")
        .to_numpy()
    )

    # 3g. PATH B: build the uniform fallback weight
    #   ZERO-SUM CHECK -- count valid (non-self) destinations per origin group.
    #   For a 2-station line: n_valid = 1  ->  P = 1.0 for that destination.
    n_valid_dests = (
        pd.Series((~is_self).astype(float), index=od_pairs.index)
        .groupby([od_pairs["hat_adi"],
                  od_pairs["saat"],
                  od_pairs["origin_durak"]])
        .transform("sum")
        .to_numpy()
    )
    # Belt-and-suspenders floor at 1.0; quarantine already removed 1-station
    # lines, but this guards against any future pathological input.
    n_valid_safe   = np.where(n_valid_dests > 0, n_valid_dests, 1.0)

    # Uniform probability per valid cell; self-loop cells resolve to 0.0
    # because (~is_self) is False (0.0) for those rows.
    uniform_weight = (~is_self).astype(float) / n_valid_safe

    # 3h. PATH classification masks
    origin_entries_np = od_pairs["origin_entries"].to_numpy()

    is_ghost_hour   = origin_entries_np == 0.0              # PATH C
    is_zero_sum_row = (row_totals == 0.0) & ~is_ghost_hour  # PATH B

    # 3i. Three-path normalisation (two nested np.where -- no iterrows)
    #
    #   Inner np.where: PATH A vs PATH B
    gravity_or_uniform = np.where(
        is_zero_sum_row,
        uniform_weight,                                      # PATH B -- uniform
        od_pairs["raw_weight"].to_numpy() / np.where(       # PATH A -- gravity
            row_totals == 0.0, 1.0, row_totals              #   safe divisor
        ),
    )
    #   Outer np.where: suppress everything for PATH C ghost-hour origins
    od_pairs["hourly_percentage"] = np.where(
        is_ghost_hour,
        0.0,                                                 # PATH C -- ghost
        gravity_or_uniform,
    )

    # 3j. Absolute estimated passenger flow
    od_pairs["estimated_passenger_flow"] = (
        od_pairs["origin_entries"] * od_pairs["hourly_percentage"]
    ).round(2)

    return od_pairs


# ---------------------------------------------------------------------------
# 4.  ASYMMETRY INDEX  (diagnostic / metadata)
# ---------------------------------------------------------------------------
def compute_asymmetry_index(weights: pd.DataFrame) -> pd.DataFrame:
    """
    AI_i = (AM_i - PM_i) / (AM_i + PM_i)

      AI > +0.15  ->  SOURCE  (residential / commuter origin)
      AI < -0.15  ->  SINK    (workplace / education destination)
      |AI| <= 0.15 -> BALANCED (interchange or mixed-use)
    """
    denom = weights["am_weight"] + weights["pm_weight"]
    w = weights.copy()
    w["asymmetry_index"] = np.where(
        denom > 0,
        (w["am_weight"] - w["pm_weight"]) / denom,
        0.0,
    )
    w["station_type"] = pd.cut(
        w["asymmetry_index"],
        bins=[-1.01, -0.15, 0.15, 1.01],
        labels=["SINK (Workplace/School)", "BALANCED", "SOURCE (Residential)"],
    )
    return w


# ---------------------------------------------------------------------------
# 5.  MAIN PIPELINE
# ---------------------------------------------------------------------------
def estimate_od_matrix(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Full pipeline:
      preprocess -> quarantine -> footprints -> AI index
      -> OD probabilities -> conditional assertion -> CSV export

    Assertion contract
    ------------------
    Conservation of Flow is verified ONLY on rows that are:
      (a) Active    : origin_entries > 0          (excludes PATH C ghost hours)
      (b) Routable  : line has >= 2 unique stations (excludes Anomaly A lines)

    A masked assertion prevents spurious failures on legitimate structural
    data gaps without concealing genuine normalisation bugs.
    """
    print("=" * 65)
    print(" Urban Transit OD Matrix Estimator -- IBB Rayli Sistem")
    print("=" * 65)

    # Step 1: Preprocess & quarantine
    print("\n[1/6] Preprocessing & quarantining single-station lines ...")
    df_routable, df_unroutable = preprocess(df)

    unroutable_lines = sorted(df_unroutable["hat_adi"].unique())
    routable_lines   = sorted(df_routable["hat_adi"].unique())

    print(f"      Total raw records         : {len(df):,}")
    print(f"      Routable records          : {len(df_routable):,}  "
          f"({len(routable_lines)} lines)")
    print(f"      Quarantined records       : {len(df_unroutable):,}  "
          f"({len(unroutable_lines)} single-station lines: "
          f"{', '.join(unroutable_lines)})")
    print(f"      Unique routable stations  : "
          f"{df_routable['durak_adi'].nunique()}")

    if not df_unroutable.empty:
        df_unroutable.to_csv(UNROUTABLE_FILE, index=False)
        print(f"      Unroutable lines written  -> {UNROUTABLE_FILE}")

    # Step 2: Build footprint weights
    print("\n[2/6] Building per-line station footprint weights ...")
    weights = build_footprint_weights(df_routable)
    print(f"      Weight table rows: {len(weights):,} station entries")

    # Step 3: Asymmetry Index
    print("\n[3/6] Computing Asymmetry Indices ...")
    ai_summary = compute_asymmetry_index(weights)

    type_dist = (
        ai_summary
        .groupby(["hat_adi", "station_type"], observed=True)
        .size()
        .unstack(fill_value=0)
    )
    print(type_dist.to_string())

    # Step 4: OD probability matrix
    print("\n[4/6] Computing OD conditional probabilities (vectorised) ...")
    od_full = compute_od_probabilities(df_routable, weights)
    print(f"      Long-form OD rows: {len(od_full):,}")

    # Step 5: Conditional Conservation-of-Flow assertion
    print("\n[5/6] Running conditional Conservation-of-Flow assertion ...")

    # Assertable rows = active (entries > 0) AND on a routable line.
    # Single-station lines are already absent from od_full (quarantined).
    # Ghost-hour origins (PATH C) are filtered by the entries > 0 mask.
    active_mask = od_full["origin_entries"] > 0

    n_active = (
        od_full.loc[active_mask, ["hat_adi", "saat", "origin_durak"]]
        .drop_duplicates().__len__()
    )
    n_ghost = (
        od_full.loc[~active_mask, ["hat_adi", "saat", "origin_durak"]]
        .drop_duplicates().__len__()
    )
    print(f"      Active origin-hour pairs  : {n_active:,}")
    print(f"      Ghost-hour pairs skipped  : {n_ghost:,}")

    od_active = od_full[active_mask]
    row_sums  = (
        od_active
        .groupby(["hat_adi", "saat", "origin_durak"])["hourly_percentage"]
        .sum()
    )

    if row_sums.empty:
        print("      [WARN] No active rows -- entire dataset has zero boardings.")
    else:
        deviations    = (row_sums - 1.0).abs()
        max_deviation = deviations.max()
        n_violations  = (deviations > COF_TOLERANCE).sum()

        print(f"      Max row-sum deviation from 1.0 : {max_deviation:.4e}")
        print(f"      Rows violating tolerance {COF_TOLERANCE:.0e}   : {n_violations}")

        if n_violations > 0:
            print("\n      -- Top violations --")
            print(deviations[deviations > COF_TOLERANCE]
                  .sort_values(ascending=False).head(10).to_string())

        assert max_deviation < COF_TOLERANCE, (
            f"Conservation of Flow violated (max deviation = {max_deviation:.6f}). "
            "Inspect stations with zero footprint weights across all periods."
        )
        print(f"      [OK] All {len(row_sums):,} active rows sum to 1.0 within tolerance.")

    # PATH B diagnostic: which origins triggered the uniform fallback?
    path_b_mask = (
        active_mask &
        (od_full
         .groupby(["hat_adi", "saat", "origin_durak"])["raw_weight"]
         .transform("sum") == 0.0)
    )
    path_b_origins = (
        od_full[path_b_mask][["hat_adi", "saat", "origin_durak"]]
        .drop_duplicates()
    )
    if path_b_origins.empty:
        print("      [OK] PATH B (uniform fallback) not needed.")
    else:
        summary = (
            path_b_origins
            .groupby("hat_adi")["saat"]
            .agg(n_hours="count", earliest="min", latest="max")
        )
        print(f"\n      [WARN] PATH B fired on {len(path_b_origins):,} origin-hour(s):")
        print(summary.to_string())

    # Step 6: Finalise and export
    print(f"\n[6/6] Writing output ...")
    output_cols = [
        "hat_adi", "saat", "origin_durak", "destination_durak",
        "hourly_percentage", "estimated_passenger_flow",
    ]
    od_result = (
        od_full[output_cols]
        .sort_values(["hat_adi", "saat", "origin_durak", "destination_durak"])
        .reset_index(drop=True)
    )

    od_result.to_csv(OUTPUT_FILE, index=False, float_format="%.6f")
    print(f"      [OK] {len(od_result):,} OD pair records -> {OUTPUT_FILE}")

    return od_result, ai_summary


# ---------------------------------------------------------------------------
# 6.  ENTRY POINT
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"Loading {INPUT_FILE} ...")
    df_raw = pd.read_csv(
        INPUT_FILE,
        keep_default_na=False,   # Anomaly C: keep literal "NAN" as string
        dtype={
            "hat_adi"     : str,
            "durak_adi"   : str,
            "tarih"       : str,
            "saat"        : "Int64",
            "toplam_yolcu": "Int64",
        },
    )
    print(f"Loaded {len(df_raw):,} rows.\n")

    od_matrix, ai_table = estimate_od_matrix(df_raw)

    # Spot checks
    print("\n-- M2 line, saat=8 (AM peak gravity) --")
    print(od_matrix.query("hat_adi == 'M2' and saat == 8").to_string(index=False))

    print("\n-- F1 line, saat=8 (PATH B: 2-station uniform) --")
    print(od_matrix.query("hat_adi == 'F1' and saat == 8").to_string(index=False))

    print("\n-- MARMARAY line, saat=18 (PM peak gravity) --")
    print(od_matrix.query("hat_adi == 'MARMARAY' and saat == 18").head(20).to_string(index=False))

    print("\nDone.")
