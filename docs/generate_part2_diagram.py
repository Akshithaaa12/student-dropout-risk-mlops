"""Part 2 architecture diagram -> docs/architecture_part2.png (needs system Graphviz)."""
from pathlib import Path
import graphviz

out = Path(__file__).resolve().parent / "architecture_part2"
g = graphviz.Digraph("part2", format="png")
g.attr(rankdir="TB", dpi="170", fontname="Helvetica", nodesep="0.5", ranksep="0.45")
g.attr("node", shape="box", style="rounded,filled", fontname="Helvetica", fontsize="11", color="#44546A")

g.node("p1", "Part 1 pipeline\ningest > validate/clean > load\n(mart + cleaned records)", fillcolor="#D9E2F3")
g.node("ds", "mlops/dataset.py\nleak-free ML dataset\n(data/ml + SQLite table)", fillcolor="#E2EFDA")
g.node("tr", "mlops/train.py\nLR / RF / GB / SVM / XGBoost\n5-fold CV, SHAP", fillcolor="#E2EFDA")
g.node("ml", "MLflow\ntracking + registry\nalias: champion", fillcolor="#FFF2CC")
g.node("bn", "models/\nchampion.joblib\nreference_stats.json", fillcolor="#FFF2CC")
g.node("api", "FastAPI service\n/predict  /predict/batch\nDocker container", fillcolor="#FCE4D6")
g.node("lg", "logs/\nprediction_log.csv", fillcolor="#EDEDED")
g.node("mo", "mlops/monitoring.py\nPSI + KS drift\nretrain triggers T1-T4", fillcolor="#FCE4D6")
g.node("dg", "Streamlit dashboard\nview 6: predictions,\nmetrics, drift", fillcolor="#D9E2F3")
g.node("af", "Airflow DAG\n(6 tasks, defined,\nnot run live)", fillcolor="#EDEDED", style="rounded,filled,dashed")

g.edge("p1", "ds"); g.edge("ds", "tr"); g.edge("tr", "ml", label=" log + register")
g.edge("tr", "bn", label=" export"); g.edge("bn", "api"); g.edge("ml", "api", style="dashed", label=" optional load")
g.edge("api", "lg", label=" every request"); g.edge("lg", "mo"); g.edge("bn", "mo", style="dashed", label=" reference")
g.edge("mo", "tr", label=" retrain if triggered", color="#C00000", fontcolor="#C00000")
g.edge("bn", "dg", style="dashed"); g.edge("mo", "dg", style="dashed")
g.edge("af", "p1", style="dotted", arrowhead="none")
g.render(out, cleanup=True)
print("wrote", out.with_suffix(".png"))
