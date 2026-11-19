"""Export simulated dashboard data for a static, self-contained site."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from pipeline_twin.api import demo_payload, energy_result, model, risk_matrix
from pipeline_twin.copilot import passages
from pipeline_twin.simulation import SCENARIOS

FLOWS_KG_S = (40, 60, 80)
DELIVERY_BAR = (40, 45, 55, 70, 80)


def export(output: Path):
    if model("detection") is None or model("maintenance") is None:
        raise RuntimeError("Train both demo models before exporting the Pages site")

    def write(relative_path, content):
        path = output / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(content, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n")

    for scenario in SCENARIOS:
        snapshot = demo_payload(scenario)
        # Recordings have no browser-side inference time.
        snapshot["inference_ms"] = None
        write(f"demo/{scenario}.json", snapshot)
    write("risk.json", risk_matrix())
    write("energy.json", {
        "flows": FLOWS_KG_S, "delivery_pressures": DELIVERY_BAR,
        "cases": {f"{flow}:{pressure}": energy_result(flow, pressure * 1e5, 1)
                  for flow in FLOWS_KG_S for pressure in DELIVERY_BAR},
    })
    # Only repository-authored passages. External ingestion and LLM settings are intentionally absent.
    write("references.json", [asdict(passage) for passage in passages()])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("frontend/public/published"))
    export(parser.parse_args().output)
