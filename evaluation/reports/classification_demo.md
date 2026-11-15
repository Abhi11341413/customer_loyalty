# Classification evaluation — demo

As of 2026-11-15. Cases: **10**. Exact segment-set match: **100.0%**. Engagement macro-F1: **0.600**. Severe strategy errors: **0**.

## Engagement axis (multiclass)

```
                    precision    recall  f1-score   support

 INSUFFICIENT_DATA      0.000     0.000     0.000         0
           DORMANT      1.000     1.000     1.000         1
DECLINING_ACTIVITY      1.000     1.000     1.000         2
        CONSISTENT      1.000     1.000     1.000         7
          STANDARD      0.000     0.000     0.000         0

          accuracy                          1.000        10
         macro avg      0.600     0.600     0.600        10
      weighted avg      1.000     1.000     1.000        10
```

| true \ pred | INSUFFICIENT_DATA | DORMANT | DECLINING_ACTIVITY | CONSISTENT | STANDARD |
|---|---|---|---|---|---|
| **INSUFFICIENT_DATA** | 0 | 0 | 0 | 0 | 0 |
| **DORMANT** | 0 | 1 | 0 | 0 | 0 |
| **DECLINING_ACTIVITY** | 0 | 0 | 2 | 0 | 0 |
| **CONSISTENT** | 0 | 0 | 0 | 7 | 0 |
| **STANDARD** | 0 | 0 | 0 | 0 | 0 |


## Qualifier / flag (binary)

**LOYALTY_CANDIDATE**

```
              precision    recall  f1-score   support

          no      1.000     1.000     1.000         7
         yes      1.000     1.000     1.000         3

    accuracy                          1.000        10
   macro avg      1.000     1.000     1.000        10
weighted avg      1.000     1.000     1.000        10
```

**PAYMENT_REMINDER**

```
              precision    recall  f1-score   support

          no      1.000     1.000     1.000         7
         yes      1.000     1.000     1.000         3

    accuracy                          1.000        10
   macro avg      1.000     1.000     1.000        10
weighted avg      1.000     1.000     1.000        10
```

## Strategy-level confusion

| true \ pred | ESCALATE | BILLING_REMINDER | LOYALTY_REWARD | WINBACK | REENGAGEMENT | APPRECIATION | NO_CONTACT |
|---|---|---|---|---|---|---|---|
| **ESCALATE** | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| **BILLING_REMINDER** | 0 | 3 | 0 | 0 | 0 | 0 | 0 |
| **LOYALTY_REWARD** | 0 | 0 | 2 | 0 | 0 | 0 | 0 |
| **WINBACK** | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| **REENGAGEMENT** | 0 | 0 | 0 | 0 | 2 | 0 | 0 |
| **APPRECIATION** | 0 | 0 | 0 | 0 | 0 | 2 | 0 |
| **NO_CONTACT** | 0 | 0 | 0 | 0 | 0 | 0 | 0 |


## Mismatches

None.


> Limitations: synthetic labels reflect the intended business definitions (ASSUMPTIONS in segments.yaml); they do not validate the definitions themselves.
