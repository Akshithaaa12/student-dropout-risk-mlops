# Dataset Sources & Access Instructions

Per the assignment's dataset rule: *"Use only free, legally accessible,
public, institutional, or instructor-approved datasets. Include the
source name and access instructions in the report."*

## 1. Primary source (real, public): UCI Student Performance Dataset
- **What it is**: demographic, academic and behavioural attributes for
  Portuguese secondary-school students in two subjects (Math and
  Portuguese language), including three periods of grades (G1, G2, G3
  on a 0-20 scale), study time, past failures, absences, family
  background, internet access, etc. 33 attributes, 395 (Math) + 649
  (Portuguese) student records.
- **Origin**: P. Cortez and A. Silva, "Using Data Mining to Predict
  Secondary School Student Performance", UCI Machine Learning
  Repository (dataset id 320), CC BY 4.0 license.
- **Suggested use in the brief**: listed explicitly as the "Primary
  historical dataset".
- **How it was obtained for this project**: the direct UCI archive host
  was not reachable from this network, so the identical, publicly
  mirrored CSV files (`student-mat.csv`, `student-por.csv`, unmodified,
  semicolon-delimited, same 33 columns) were retrieved from a public
  GitHub mirror:
  `https://github.com/KunjalJethwani/StudentPerformance`
  (raw files: `.../main/student-mat.csv`, `.../main/student-por.csv`).
  Row/column counts and value ranges were spot-checked against the
  documented UCI schema after download.
- **Local copy**: `data/source_files/academic/student-mat.csv`,
  `student-por.csv` (as retrieved, byte-for-byte).
- **To re-obtain independently**: the dataset is also directly
  browsable at the UCI Machine Learning Repository, "Student
  Performance" (dataset id 320), and mirrored on Kaggle as
  "Student Performance Data Set" (`dskagglemt/student-performance-data-set`).

## 2. Supplementary sources (simulated, for multi-source pipeline demonstration)
The brief lists "College ERP exports" and "LMS exports" as optional
enrichment/institutional sources. Since this is an individual student
project without access to a real college ERP or LMS export, and the
brief explicitly forbids uploading "private, personally identifiable,
or confidential data", three supplementary sources were **synthetically
generated** (seeded/reproducible, documented in
`scripts/generate_synthetic_sources.py`) with realistic statistical
relationships to the real UCI attributes, rather than left out
entirely or faked with real institutional data:

| Simulated source | Represents | Generated file |
|---|---|---|
| College ERP roster export | `student_id`, `department`, `semester` enrichment | `data/source_files/academic/student_roster.csv` |
| ERP attendance export | Monthly attendance | `data/source_files/attendance/attendance_export.csv` |
| LMS activity export | Weekly Moodle-style engagement | `data/source_files/lms/lms_activity_export.csv` |
| Assignment submissions export | Per-assignment submission/marks | `data/source_files/assignments/assignment_submissions.csv` |

No real names, government IDs, contact details or any other personally
identifiable information appear anywhere in this project -- students are
identified only by a synthetic `student_id`.

## Access instructions (to regenerate everything from scratch)
```bash
# 1. (Already done once) fetch the two real UCI CSVs into
#    data/source_files/academic/ -- already included in this repo.

# 2. Generate the supplementary sources
python scripts/generate_synthetic_sources.py

# 3. Run the full pipeline (ingest -> validate/clean -> transform/load)
python scripts/run_pipeline.py

# 4. Launch the dashboard
streamlit run dashboard/app.py
```
