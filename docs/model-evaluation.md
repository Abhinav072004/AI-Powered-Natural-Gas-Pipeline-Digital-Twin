# Synthetic detection evaluation

With the locked environment, run `python -m pipeline_twin.simulation dataset --rounds 2 --steps 32` and `python -m pipeline_twin.detection --xgboost`. Install the optional `xgboost` dependency group for the third supervised model. The run produces 20 episodes and 640 samples in each chronological split. Training, selection and scoring use different seeds and whole episodes. The exact [evaluation output](detection-evaluation.json) includes the confusion matrices and per-class scores.

| Held-out model | Leak precision | Leak recall | Leak F1 | Leak ROC-AUC | False leak alerts per normal hour | Episodes missed | Median detection time among hits |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Physics alone | 0.442 | 0.280 | 0.343 | — | 2.63 | 2/4 | 90 s |
| Random Forest | 0.811 | 0.366 | 0.504 | 0.863 | 0.66 | 0/4 | 360 s |
| SVM | 0.850 | 0.415 | 0.557 | 0.882 | 0.44 | 1/4 | 180 s |
| XGBoost | 0.824 | 0.171 | 0.283 | 0.810 | 0.00 | 2/4 | 630 s |

Validation selected Random Forest at a probability threshold of 0.25, with two consecutive candidates and a positive smoothed mass-balance residual required to report a potential leak. Position estimates agreed with the true segment on 80% of the 30 samples localized by this model. Mean midpoint error was 40.6 km because some estimates pointed to distant segments. Isolation Forest, fitted on normal training windows, yielded novelty ROC-AUC of 0.725 on test observations with telemetry.

The held-out leak set is small. Persistent false alarms, intermittent missed samples, and occasional large localization errors remain. Investigate the observations and data quality before accepting a proposed classification or segment. Results describe generated scenarios and require independent validation before use on measured data.

## Maintenance scoring

Run `python -m pipeline_twin.maintenance` to train the failure-window model and reproduce the [maintenance metrics](maintenance-evaluation.json). Training uses 120 generated trajectories and testing uses 40 trajectories with separate seeds. For 1,873 held-out windows, logistic regression attained 0.994 ROC-AUC, 0.947 average precision, and a Brier score of 0.019. The label means the latent condition indicator crosses the synthetic failure threshold within ten samples. The score ranks virtual equipment using a mapped condition indicator. There is no equipment-specific field calibration or remaining-life estimate.
