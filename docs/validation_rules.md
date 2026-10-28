# Data Validation & Cleaning Rules

Implemented in `scripts/validate_clean.py` (Raw layer -> Cleaned layer).
Every rejected/corrected row is written, with a reason code, to
`logs/rejected_records.csv`.

## 1. Identifier standardization
All `student_id` values are trimmed of whitespace and upper-cased before
any join or de-duplication, so the same student is recognized
consistently across the roster, academic, attendance, LMS and
assignment sources (this is the "standardize student identifiers across
sources" requirement).

## 2. Duplicate removal
| Table | Natural key | Rule |
|---|---|---|
| student_roster | student_id | Keep first occurrence, reject the rest (`duplicate_student_id`). |
| academic_records | student_id + source_subject | Keep first occurrence (`duplicate_student_subject`). |
| attendance | student_id + semester + month | Keep first occurrence (`duplicate_month_record`). |

## 3. Invalid-value checks
| Table | Rule | Reason code |
|---|---|---|
| academic_records | `G3` (final grade) must be within the UCI dataset's own 0-20 scale | `G3_out_of_range(0-20)` |
| attendance | `classes_attended` cannot exceed `classes_held` | `attended_exceeds_held` |

## 4. Referential integrity
Every row in `academic_records`, `attendance`, `lms_activity` and
`assignments` must reference a `student_id` present in the cleaned
`student_roster`. Orphaned rows (student not in the roster) are
rejected with reason `student_id_not_in_roster`.

## 5. Missing-record handling

**Guiding principle (per the course's missing-data guideline): a NULL
must never be automatically replaced by zero or a guessed value. First
identify WHY it's missing, then decide the treatment based on the cause
and how the feature will be used -- and document it.** This project
distinguishes two genuinely different situations, matching the
guideline's own "situation -> recommended handling" framing:

| Situation | Where it happens | How it's handled |
|---|---|---|
| **Partial gap** -- a student has *some* but not all expected attendance months on file (a single month's ERP upload was skipped) | `validate_clean.py` | Not fabricated. `attendance_pct` is computed from whichever months ARE present; the gap itself is logged to `logs/attendance_completeness_gaps.csv` (student_id -> missing months) so it's traceable, not hidden. |
| **Full gap** -- a source has *no record at all* for a student that semester (e.g. the ERP never sent that student's attendance batch) | `transform_load.py`, building the mart | Detected via a left-join producing NULL. Flagged FIRST (`attendance_data_available` / `lms_data_available` / `assignment_data_available` = `False`, and `data_quality_flag` names the source) BEFORE any fallback value is applied. Only after flagging is a documented fallback used (cohort median for attendance/LMS, 0 for assignment completion), so downstream consumers (dashboard, Part 2 model) always get a numeric value without losing the "this was imputed, not measured" signal. |
| **Missing assignment marks** -- `marks_obtained` is `NULL` whenever `submitted = False` | `validate_clean.py` / source data | This is an *expected*, meaningful absence (you can't have marks for work not submitted) -- analogous to the guideline's "keep the value missing and add a flag" case. It is never rejected, never coerced to 0, and directly lowers `assignment_completion_rate` (a real completion signal, not a data-quality problem). |

The full list of columns this produces (`attendance_data_available`,
`lms_data_available`, `assignment_data_available`, `data_quality_flag`)
is documented in `docs/data_dictionary.md`. As of the current seeded
run, 15 of 1,034 student-subject records carry
`data_quality_flag = "imputed:attendance"` -- a real, inspectable example
of the flag in action, visible in `data/analytical/student_performance_mart.csv`
and the `student_performance_mart` table in the SQLite database.

## 6. Why the raw layer contains "dirty" data at all
Real ERP/LMS/CSV extracts are never perfectly clean. To make validation
and missing-data handling demonstrably do real work (per the brief's
requirement for a genuine "rejected-record or error log", and the
missing-data guideline's requirement to "show which source failed to
provide a value and how the pipeline detected it"), `scripts/ingest.py`
deliberately introduces a small, seeded amount of realistic noise while
copying source files into the raw layer: ~1.5% duplicate roster rows,
~1% duplicate and ~1% out-of-range academic records, ~2% scattered
single-month attendance gaps, and a full-semester attendance sync
failure for ~1.5% of student-semester pairs (this last one is what
produces the "full gap" cases flagged in Section 5). This is clearly
commented in `ingest.py` and disclosed here -- the original UCI source
CSVs in `data/source_files/` are never altered.

## Rejection log schema (`logs/rejected_records.csv`)
Every original column from the source row, plus:
- `_rejected_from_table` -- which cleaned table the row was destined for
- `_rejection_reason` -- one of the reason codes above
- `_rejected_at` -- UTC timestamp of the validation run
