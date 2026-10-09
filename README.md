# Istanbul Metro Network Optimizer

An optimization model that decides how many trains each Istanbul metro line should run every hour. It trades total passenger waiting time against the cost of running trains, using real ridership data from the Istanbul Metropolitan Municipality (İBB). Term project for **YZV202E – Optimization for Data Science** at Istanbul Technical University (Spring 2026), team of four.

**Live dashboard:** [metro_optimizer_dashboard.html](https://itu-itis24-islam24.github.io/istanbul-rail-network-passenger-density-optimization/metro_optimizer_dashboard.html) · **Presentation:** [Istanbul_Metro_Network_Optimizer.pptx](Istanbul_Metro_Network_Optimizer.pptx)

**Key result:** at the balanced setting, the optimized timetable runs **4.4% more daily trips** (2,234 vs. 2,139) and cuts estimated passenger waiting time during service hours by **18%**. Most of the gain comes from moving trips toward the busiest lines and hours.

![Dashboard](dashboard_screenshot.png)

## Scope

| | |
|---|---|
| Lines | 10, optimized together: M1–M9 and Marmaray |
| Stations | 208 |
| Data | ~3.4M hourly Istanbulkart tap records, İBB Open Data Portal |
| Baseline | 2,139 daily train trips from the current timetable |
| Decision variable | `x(l,t)`: number of trains on line `l` in hour `t` (integer) |

## Model

**Objective.** Waiting time at every station of every line in every service hour is summed with equal weight, and every train dispatched adds a cost:

$$J = \sum_{l,s,t} W(l,s,t) + \mu \sum_{l,t} x(l,t)$$

**Waiting time.** Passengers arrive uniformly, so the average wait is half the headway. With $x$ trains per hour and $D$ entries at a station:

$$W(l,s,t) = D(l,s,t) \cdot \frac{30}{x(l,t)} \quad \text{passenger-minutes}$$

**Money importance scale.** Planners choose $M \in \{1, \dots, 10\}$, which sets the cost of a train trip:

$$\mu = 0.21 \cdot e^{0.55\,(M - 5)}$$

The scale is calibrated so that $M = 5$ keeps the total number of trips close to today's timetable.

**Constraints**
- Hours with no scheduled service (night closure, 00:00–05:59) stay closed and are left out of the waiting totals.
- Crowding floor: a line-hour never gets fewer trains than its hourly entries ÷ set capacity, unless today's timetable already runs fewer.
- At most 8 trains per hour above the current timetable.

**Solving.** The objective is separable by line and hour, so it splits into independent integer sub-problems. Each is solved exactly by checking every feasible train count.

## Results

Computed by the dashboard against the current timetable (2,139 trips, 5.7M passenger-minutes of waiting on an average day):

| M | μ | Daily trips | Trips vs. baseline | Waiting vs. baseline |
|---|---|---|---|---|
| 1 | 0.023 | 3,466 | +62% | −41% |
| 3 | 0.070 | 3,117 | +46% | −38% |
| 4 | 0.121 | 2,691 | +26% | −31% |
| **5** | **0.210** | **2,234** | **+4.4%** | **−18%** |
| 6 | 0.364 | 1,803 | −16% | +3% |
| 7 | 0.631 | 1,543 | −28% | +24% |
| 10 | 3.285 | 1,461 | −32% | +36% (crowding floor binds) |

**Per line at M = 5**

| Line | Trips (now → optimized) | Waiting |
|---|---|---|
| M2 | 219 → 325 | −34% |
| M5 | 178 → 267 | −34% |
| Marmaray | 221 → 361 | −40% |
| M7 | 176 → 223 | −22% |
| M9 | 96 → 117 | −20% |
| M8 | 100 → 114 | −15% |
| M1 | 337 → 321 | +4% |
| M4 | 386 → 275 | +39% |
| M3 | 270 → 168 | +58% |
| M6 | 156 → 63 | +143% |

Because all passenger-minutes count equally, the model moves trips from lightly used lines (M3, M4, M6) to the busiest ones (M2, M5, Marmaray). Two sensitivity checks with the same model: keeping exactly today's 2,139 trips and only reallocating them cuts waiting by about 14%. If every line also keeps its own daily trip count and trips only move between hours, waiting falls by about 6.5%, with M2 alone improving by 23%.

## Assumptions and limitations

- **Demand** is the average hourly number of turnstile entries per station, pooled over all days (weekdays and weekends, 2022–2025).
- **Waiting** is counted only at the boarding station. Transfers, in-vehicle time and passengers left behind on full trains are not modeled beyond the crowding floor.
- **Uniform arrivals** within each hour; real passengers time their arrival to the schedule at low frequencies, so long headways are penalized more than in reality.
- **Directions and branches are combined.** `x` is trains per hour for the whole line (M1A and M1B together), and the crowding floor ignores direction split and passengers who ride only part of the line.
- **No fleet, crew or depot limits.** Trips can be moved freely between hours and lines, although real lines use different rolling stock that is not interchangeable.
- **Trip cost is an abstract unit** (μ), identical for every line. It is not money.
- **No fairness constraint.** Some lightly used lines get much longer waits; a per-line cap on waiting increases would be needed before real use.
- **Night hours are excluded.** Tap records exist between 00:00 and 05:59 (trains after midnight and weekend night service), but the timetable used has no trains then.

## What changed in v2

An audit of the first dashboard version found two problems that inflated its headline result (−78% waiting with +4% trips):

1. **Waiting formula.** v1 used $W = \frac{60}{2x} \cdot \frac{D}{x-1}$. The extra $\frac{1}{x-1}$ factor is not part of the standard half-headway model. It made waiting fall with the square of frequency, so at 20 trains per hour waiting was understated about 19 times.
2. **Closed hours.** The timetable has no trains between 00:00 and 05:59, but there are tap records in those hours. v1 charged each of those passengers 60 minutes of waiting, which made up 73% of the baseline. The optimizer then "opened" night service, and 91% of the reported improvement came from these hours.

v2 also adds the crowding floor, recalibrates μ for the corrected formula, uses Marmaray's set capacity from the source table (3,000 instead of 1,000) and recomputes the match impact view (see below).

## Dashboard

A single self-contained HTML file (Chart.js), with no server needed. Moving the money importance slider re-runs the optimizer in the browser.

- **Schedule:** optimized hourly train counts for all 10 lines
- **Demand heatmap:** station × hour grid for any line (demand, trains or waiting)
- **Line drill-down:** hourly schedule, waiting change and detail table per line
- **Before vs. after:** baseline vs. optimized waiting time per line
- **Money sensitivity:** waiting vs. trips trade-off across all M values
- **Match impact:** extra trains needed per line around Galatasaray, Fenerbahçe and Beşiktaş home matches, spread over the two hours before kickoff, the kickoff hour and the hour after (15% / 45% / 30% / 10%, an assumed split)

## Data pipeline

| Step | Code | Output |
|---|---|---|
| 1. Merge monthly İBB files with DuckDB, normalize station names (manual map + regex), aggregate duplicates. 4.22M raw rows became 3.46M, and 348 station names merged to 266. | `data_cleaning_aggregation.ipynb` | `rayli_sistem_temiz.csv` (large; Google Drive link in the notebook) |
| 2. Time-dependent station weights | `Progress_Report.ipynb` | `saatlik_durak_agirliklari.csv` |
| 3. Hourly origin–destination (OD) matrix estimation | `estimated_od_matrix_solver.py` | `estimated_hourly_od_matrix.csv` |
| 4. Line capacities and operational effort coefficients | `create_operational_effort_coefficients.py`, `operational_effort_rail_updated.ipynb` | `operational_effort_coefficients.csv` |
| 5. Baseline hourly capacity and load ratios | `create_baseline_hourly_capacity.py`, `create_baseline_load_ratios.py` | `baseline_hourly_capacity.csv`, `baseline_load_ratios.csv` |
| 6. Collect and clean Big Three home-match fixtures | `converting_webscrab_into_csv.ipynb` | `big3_22kasım_24ekim.csv` |
| 7. Station demand change around matches vs. non-match days with the same weekday and hour (−12 h to +12 h) | `match_metro_features.py` | `match_station_offset_features.csv` |
| 8. Extra trains needed per club and line | `match_affects.py` | `kompakt_demand_verisi.csv` |

**OD estimation.** Turnstile data only records entries, so destinations are inferred with a gravity-style model based on diurnal asymmetry. Every origin's row sums to 1 (checked for all 7,112 origin-hours). The OD matrix is part of the pipeline but is not yet used by the dashboard's objective.

**Match days.** v2 of `match_affects.py` sums the *net* change in the four hours around kickoff that the dashboard shows. v1 added up only the positive changes over all 25 offsets, so random station-level noise and unrelated hours counted as extra demand. This roughly tripled the extra-train numbers (for example, 37 instead of 12 extra M2 trains for Galatasaray matches). The demand profile also shows a second surge about two hours after kickoff, which the current four-hour window does not cover.

**Known pipeline issues**
- `create_baseline_load_ratios.py` drops Marmaray because the timetable file spells it `Marmaray` and the demand file `MARMARAY`.
- The match baseline uses all non-match days in 2022–2025, while matches cover Nov 2022 – Oct 2024. This may be why the data shows several thousand extra passengers even 12 hours before and after kickoff.

## Future work

- Fairness constraints so no line's waiting rises beyond a set limit
- Using the OD matrix to compute onboard load and real crowding
- Transfer penalties at busy interchanges such as Yenikapı (M1, M2 and Marmaray)
- Rolling-horizon re-optimization with real-time turnstile data
- Adding match-day demand, including the post-match surge, directly into the objective

## Team

Emir Selim İslam, Atillahan Gözütok, Erdem Hasbek and Huzeyfe Dut – Istanbul Technical University, Artificial Intelligence and Data Engineering.

**My contribution (Emir Selim İslam):**
- Formulated the unified objective function, which combines network-wide passenger waiting time with a money importance penalty on train trips, and researched methods for minimizing it.
- Collected and cleaned the 162 Big Three home-match fixtures with a regex-based parsing pipeline (`converting_webscrab_into_csv.ipynb`). These fixtures feed the dashboard's match impact view.

## License

MIT
