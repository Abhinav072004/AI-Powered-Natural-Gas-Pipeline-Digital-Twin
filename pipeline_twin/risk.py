"""Educational risk scoring with configurable likelihood/severity thresholds."""

HAZARDS = {
    "potential leakage", "abnormal pressure", "equipment failure", "third-party excavation",
    "pipeline intrusion", "environmental exposure", "isolation assessment", "data quality",
}
LEVELS = ((4, "low"), (9, "medium"), (15, "high"), (25, "critical"))
RESPONSES = {
    "low": "Record the observation and monitor the trend.",
    "medium": "Cross-check the measurements and record an engineering investigation.",
    "high": "Escalate promptly to the authorized duty engineer and follow the applicable site procedure.",
    "critical": "Refer immediately to the site's approved emergency response procedures and authorized personnel.",
}


def assess(hazard: str, probability: int, severity: int, thresholds=LEVELS) -> dict:
    if hazard not in HAZARDS or probability not in range(1, 6) or severity not in range(1, 6):
        raise ValueError("Select a known hazard and likelihood and consequence scores from 1 to 5")
    score = probability * severity
    level = next(name for ceiling, name in thresholds if score <= ceiling)
    return {"hazard": hazard, "probability": probability, "severity": severity, "score": score,
            "level": level, "response": RESPONSES[level]}
