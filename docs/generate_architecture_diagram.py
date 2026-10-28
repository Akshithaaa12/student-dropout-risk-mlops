"""
Generates docs/architecture_diagram.png -- the data architecture /
pipeline-flow diagram required by the assignment brief (section 4 &
Part 1 submission package item 5).

Requires the system Graphviz binary (`dot`) in addition to the Python
`graphviz` package:
    macOS:  brew install graphviz
    Ubuntu: sudo apt-get install graphviz

A rendered PNG is already committed at docs/architecture_diagram.png,
so you do NOT need to re-run this before your demo -- only if you want
to change the diagram.
"""

from pathlib import Path
from graphviz import Digraph

OUT_DIR = Path(__file__).resolve().parent

dot = Digraph("architecture", format="png")
dot.attr(rankdir="LR", fontname="Helvetica", fontsize="11", bgcolor="white")
dot.attr("node", fontname="Helvetica", fontsize="10", style="filled")

# Source layer
with dot.subgraph(name="cluster_source") as c:
    c.attr(label="Source Layer", style="rounded", color="#9CA3AF")
    c.node("uci", "UCI Student\nPerformance CSV\n(primary, real, public)", fillcolor="#DBEAFE", shape="box")
    c.node("erp", "College ERP export\n(student roster, simulated)", fillcolor="#DBEAFE", shape="box")
    c.node("att", "Attendance export\n(simulated, ERP-style)", fillcolor="#DBEAFE", shape="box")
    c.node("lms", "LMS activity export\n(simulated, Moodle-style)", fillcolor="#DBEAFE", shape="box")
    c.node("asg", "Assignment submissions\nexport (simulated)", fillcolor="#DBEAFE", shape="box")

# Ingestion / orchestration
with dot.subgraph(name="cluster_ingest") as c:
    c.attr(label="Ingestion & Orchestration", style="rounded", color="#9CA3AF")
    c.node("ingest", "ingest.py\n(extract, log,\nraw copy)", fillcolor="#FEF3C7", shape="box")
    c.node("airflow", "Orchestrator:\nrun_pipeline.py\n(+ Airflow DAG def.)", fillcolor="#FDE68A", shape="box3d")

# Raw / staging / cleaned layers
dot.node("raw", "Raw layer\n(data/raw/*.csv)", fillcolor="#FEE2E2", shape="folder")
dot.node("clean", "validate_clean.py\n(dedupe, validate,\nreject log)", fillcolor="#FEF3C7", shape="box")
dot.node("cleaned", "Cleaned layer\n(data/cleaned/*.csv)", fillcolor="#FEE2E2", shape="folder")

# Transform / analytical / storage
dot.node("transform", "transform_load.py\n(feature engineering:\nattendance %, avg marks,\nassignment completion,\nrisk score)", fillcolor="#FEF3C7", shape="box")
dot.node("analytical", "Analytical layer\n(data/analytical/*.csv)", fillcolor="#FEE2E2", shape="folder")
dot.node("db", "SQLite warehouse\nstudent_performance.db\n(star-schema tables +\nstudent_performance_mart)", fillcolor="#D1FAE5", shape="cylinder")

# Consumption
dot.node("dash", "Streamlit dashboard\n(5 views: attendance vs marks,\npass/fail, dept/semester,\nhigh-risk list, student profile)", fillcolor="#E0E7FF", shape="component")

dot.edge("uci", "ingest")
dot.edge("erp", "ingest")
dot.edge("att", "ingest")
dot.edge("lms", "ingest")
dot.edge("asg", "ingest")
dot.edge("ingest", "raw")
dot.edge("raw", "clean")
dot.edge("clean", "cleaned")
dot.edge("cleaned", "transform")
dot.edge("transform", "analytical")
dot.edge("analytical", "db")
dot.edge("db", "dash")
dot.edge("airflow", "ingest", style="dashed", label="schedules")
dot.edge("airflow", "clean", style="dashed")
dot.edge("airflow", "transform", style="dashed")

dot.render(OUT_DIR / "architecture_diagram", cleanup=True)
print(f"Wrote {OUT_DIR / 'architecture_diagram.png'}")
