# TermProjectYZV202E
YZV202E 2026 Spring Term Project
# Istanbul Rail Network: Passenger Density Optimization

A data pipeline that estimates hour-by-hour passenger loads on Istanbul's rail network (metro, funicular, Marmaray). It prepares the inputs for an optimization model that schedules trains to keep platforms and trains below a target crowding level, including on football match days. Term project for **YZV202E – Optimization for Data Science** at Istanbul Technical University (Spring 2026), team of four.

## Objective

Optimize dispatch scheduling (headways) so that passenger density on platforms and inside trains stays low and crowds clear quickly. Extra trips are not free, so the model trades crowding against operational effort.

## Data

| Source | What it contains | File |
|---|---|---|
| Istanbul Metropolitan Municipality (İBB) hourly ridership | Monthly hourly turnstile entries per line and station, rail only. 4.22M raw rows were cleaned to 3.46M rows, and 348 station names merged to 266 stations. | `rayli_sistem_temiz.csv` (large; Google Drive link in `data_cleaning_aggregation.ipynb`) |
| Metro Istanbul line data | Vehicle type, set capacity, fleet size, average speed and wagons per set for each line | `istanbul_rayli_sistem_verileri_guncel.csv` |
| Timetables | Number of trips per line and hour | `hourly_metro_train_numbers.csv` |
| Football fixtures | 162 home matches of Galatasaray (75), Fenerbahçe (47) and Beşiktaş (40), Nov 2022 – Oct 2024 | `big3_22kasım_24ekim.csv` |

## Pipeline

| Step | Code | Output |
|---|---|---|
| 1. Merge monthly files with DuckDB, normalize station names (manual map + regex), aggregate duplicates | `data_cleaning_aggregation.ipynb` | `rayli_sistem_temiz.csv` |
| 2. Time-dependent station weights | `Progress_Report.ipynb` | `saatlik_durak_agirliklari.csv` |
| 3. Hourly origin–destination (OD) matrix estimation | `estimated_od_matrix_solver.py` | `estimated_hourly_od_matrix.csv` (169,570 OD pairs, 20 lines) |
| 4. Operational effort coefficients per line | `create_operational_effort_coefficients.py`, `operational_effort_rail_updated.ipynb` | `operational_effort_coefficients.csv` |
| 5. Baseline hourly capacity | `create_baseline_hourly_capacity.py` | `baseline_hourly_capacity.csv` |
| 6. Baseline load ratios (demand ÷ capacity) | `create_baseline_load_ratios.py` | `baseline_load_ratios.csv` (the script writes it as `baseline_load_ratios_no_m1_merge.csv`) |
| 7. Collect and clean match fixtures | `converting_webscrab_into_csv.ipynb` | `big3_22kasım_24ekim.csv` |
| 8. Station demand change around matches (−12 h to +12 h) | `match_metro_features.py` | `match_station_offset_features.csv` |
| 9. Extra demand per club and line, converted to extra trains | `match_affects.py`, `matchCleaner.py` | `kompakt_demand_verisi.csv`, `match_station_offset_with_trains.csv` |

## Method notes

**Station weights.** Each station's share of its line's traffic in a given hour:

$$W_{i,t} = \frac{P_{i,t}}{\sum_{j=1}^{N} P_{j,t}}$$

where $P_{i,t}$ is the number of passengers entering station $i$ in hour $t$, and $N$ is the number of stations on the line.

**OD estimation.** Turnstile data only records entries, so destinations are estimated with a gravity-style model based on diurnal asymmetry. In the morning, destinations are weighted by their evening entry volume, because workplaces that send people home at night attract them in the morning. In the evening the logic is reversed. Every row is normalized so that flow is conserved. Edge cases are handled explicitly: single-station lines, two-station lines and literal `"NAN"` station names.

**Load ratio.** Average hourly demand divided by hourly capacity (trips × set capacity). The baseline average is 0.56, and some line-hours reach 2.06, more than double the scheduled capacity.

**Operational effort.** One additional standard trip equals one unit of normalized operational effort. This is not a monetary cost; passenger load is handled separately through the load ratio.

**Match days.** For every match, station demand from 12 hours before to 12 hours after kickoff is compared with a non-match baseline. Positive extra demand is divided by train capacity, and the result is rounded up from 0.30, which gives the number of additional trains needed per club and line.

## Repository notes

- `Progress_Report.ipynb` documents the objective and the first milestone.
- `optimization project first meeting.pdf` contains the kickoff meeting notes.
- The cleaned ridership file is too large for GitHub. Download it from the Google Drive link in `data_cleaning_aggregation.ipynb` and place it in the repository root before running the scripts.

```bash
pip install pandas numpy duckdb
python create_operational_effort_coefficients.py
python create_baseline_hourly_capacity.py
python create_baseline_load_ratios.py
python estimated_od_matrix_solver.py
python match_metro_features.py
python match_affects.py
```

## Team

Developed by four ITU Artificial Intelligence and Data Engineering students: [@erdemhasbek](https://github.com/erdemhasbek), [@itu-itis24-gozutoka24](https://github.com/itu-itis24-gozutoka24), [@itu-itis24-dut23](https://github.com/itu-itis24-dut23) and [@itu-itis24-islam24](https://github.com/itu-itis24-islam24).

**My contribution (Emir Selim İslam):**
- Collected and cleaned the 162 Big Three home-match fixtures with a regex-based parsing pipeline (`converting_webscrab_into_csv.ipynb`). These fixtures feed the match-day demand features in steps 8 and 9.
- Formulated the cost function that balances passenger crowding (load ratio) against operational effort (extra trips), and researched optimization models to minimize it.

## License

MIT
