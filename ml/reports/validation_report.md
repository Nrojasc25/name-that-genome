# Validation-only calibration and confidence selection

Calibration fit rows: 1768. Separate policy-selection rows: 1768.
Fitted temperature: 1.034627. Retained: False. Active temperature: 1.000000.
Probability kind: uncalibrated. Confidence rule accepted: False.

## Calibration checks

- log_loss_improves: False
- brier_nonworse: True
- ece_nonworse: True

Warm single-variant p95: 0.168 ms.
No test or gene-challenge predictions were read. Temperature scaling preserves argmax, so it cannot repair poor Likely pathogenic recall.
Calibration is retained only when the independent validation-selection subset passes all predeclared checks. The fitted temperature is not refitted afterward.
Low confidence is a separate flag. Every row retains its original five-class argmax prediction.
