"""Generate ROC curve figure for the paper appendix."""
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

RESULTS_DIR = Path("outputs/evaluation_results_emnlp2026")

with open(RESULTS_DIR / "roc_evidence_gate_analysis.json") as f:
    data = json.load(f)

roc = data["roc_curve"]
fprs = [p["fpr"] for p in roc]
tprs = [p["tpr"] for p in roc]
thresholds = [p["threshold"] for p in roc]
precisions = [p["precision"] for p in roc]
recalls = [p["recall"] for p in roc]
f1s = [p["f1"] for p in roc]

fig, axes = plt.subplots(1, 2, figsize=(10, 4.5))

# Left: ROC curve
ax = axes[0]
ax.plot(fprs, tprs, 'b-o', markersize=3, linewidth=1.5, label=f'MEKG (AUC={data["auc_roc"]:.3f})')
ax.plot([0, 1], [0, 1], 'k--', alpha=0.3, label='Random')
# Mark optimal point
opt = data["optimal_threshold"]
opt_idx = next(i for i, p in enumerate(roc) if p["threshold"] == opt["threshold"])
ax.plot(fprs[opt_idx], tprs[opt_idx], 'r*', markersize=15, label=f'Optimal (t={opt["threshold"]})')
ax.set_xlabel('False Positive Rate')
ax.set_ylabel('True Positive Rate')
ax.set_title('ROC Curve: Evidence Gate')
ax.legend(loc='lower right')
ax.grid(True, alpha=0.3)
ax.set_xlim(-0.02, 1.02)
ax.set_ylim(-0.02, 1.02)

# Right: Precision-Recall-F1 vs threshold
ax = axes[1]
ax.plot(thresholds, precisions, 'g-s', markersize=3, linewidth=1.5, label='Precision')
ax.plot(thresholds, recalls, 'b-^', markersize=3, linewidth=1.5, label='Recall')
ax.plot(thresholds, f1s, 'r-o', markersize=3, linewidth=1.5, label='F1')
ax.axvline(x=opt["threshold"], color='gray', linestyle='--', alpha=0.5, label=f'Optimal t={opt["threshold"]}')
ax.set_xlabel('Confidence Threshold')
ax.set_ylabel('Score')
ax.set_title('Precision/Recall/F1 vs. Evidence Gate Threshold')
ax.legend(loc='center right')
ax.grid(True, alpha=0.3)
ax.set_xlim(0, 1)
ax.set_ylim(0, 1.05)

plt.tight_layout()
out_path = Path("paper/roc_evidence_gate.pdf")
plt.savefig(out_path, dpi=150, bbox_inches='tight')
print(f"Saved: {out_path}")

# Also save PNG for preview
plt.savefig(RESULTS_DIR / "roc_evidence_gate.png", dpi=150, bbox_inches='tight')
print(f"Saved PNG preview: {RESULTS_DIR / 'roc_evidence_gate.png'}")
