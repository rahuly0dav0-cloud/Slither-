# SAS2PY/samples/

Synthetic **inputs to the agent** — nothing here is imported by the engine.
Point a conversion at any `sas/*.sas` file (paste it into the Convert page, or
use `scripts/run_sample0X.py`).

## `sas/` — programs to convert

| file | focus / edge cases |
|------|--------------------|
| `01_data_engineering_merge_means.sas` | DATA-step clean → sort → merge → PROC MEANS |
| `02_data_engineering_complex.sas`     | multi-step data engineering |
| `03_end_to_end_glmselect.sas`         | full pipeline into PROC GLMSELECT (LASSO/stepwise) |
| `04_macro_scoring.sas`                | **`%MACRO` defined + called in the middle**, `%DO`/`%IF`, `CALL SYMPUTX`, macro vars |
| `05_proc_sql_joins.sas`              | PROC SQL: multi-table joins, subqueries, `CASE`, `GROUP BY/HAVING`, `UNION` |
| `06_transpose_arrays_retain.sas`     | PROC TRANSPOSE (wide↔long), `ARRAY`, `RETAIN`, `FIRST./LAST.`, PROC FORMAT |
| `07_large_feature_pipeline.sas`      | **~1000-line** feature-engineering pipeline (context-length stress test) |
| `08_datetime_reporting.sas`          | dates (`INTNX`/`INTCK`), PROC FREQ/MEANS/TABULATE, formats, running totals |

## `oracle/` — dummy-data + ground-truth generators

Self-contained SAS that **inlines its own dummy input data** and runs the same
pipeline, exporting every table to CSV. Run one in a real SAS session to
(re)produce the QC baseline for the matching sample. Each `oracle_0X_*.sas`
header names the sample it corresponds to. No external data or libraries needed.

## Relationship to `data/ground_truth/`

```
oracle/oracle_0X_*.sas   --run in SAS-->   data/ground_truth/0X/*.csv
                                                    │
sas/0X_*.sas          --converted by agent-->   Python output
                                                    │
                                      QC compares the two, cell by cell
```

`data/ground_truth/` holds committed baseline CSVs so the QC gate runs without a
SAS license. Only regenerate them (via `oracle/`) if a sample program changes.
