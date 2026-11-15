# Classification evaluation — eval

As of 2026-11-15. Cases: **500**. Exact segment-set match: **100.0%**. Engagement macro-F1: **1.000**. Severe strategy errors: **0**.

## Engagement axis (multiclass)

```
                    precision    recall  f1-score   support

 INSUFFICIENT_DATA      1.000     1.000     1.000        30
           DORMANT      1.000     1.000     1.000        41
DECLINING_ACTIVITY      1.000     1.000     1.000        59
        CONSISTENT      1.000     1.000     1.000       329
          STANDARD      1.000     1.000     1.000        41

          accuracy                          1.000       500
         macro avg      1.000     1.000     1.000       500
      weighted avg      1.000     1.000     1.000       500
```

| true \ pred | INSUFFICIENT_DATA | DORMANT | DECLINING_ACTIVITY | CONSISTENT | STANDARD |
|---|---|---|---|---|---|
| **INSUFFICIENT_DATA** | 30 | 0 | 0 | 0 | 0 |
| **DORMANT** | 0 | 41 | 0 | 0 | 0 |
| **DECLINING_ACTIVITY** | 0 | 0 | 59 | 0 | 0 |
| **CONSISTENT** | 0 | 0 | 0 | 329 | 0 |
| **STANDARD** | 0 | 0 | 0 | 0 | 41 |


## Qualifier / flag (binary)

**LOYALTY_CANDIDATE**

```
              precision    recall  f1-score   support

          no      1.000     1.000     1.000       326
         yes      1.000     1.000     1.000       174

    accuracy                          1.000       500
   macro avg      1.000     1.000     1.000       500
weighted avg      1.000     1.000     1.000       500
```

**PAYMENT_REMINDER**

```
              precision    recall  f1-score   support

          no      1.000     1.000     1.000       391
         yes      1.000     1.000     1.000       109

    accuracy                          1.000       500
   macro avg      1.000     1.000     1.000       500
weighted avg      1.000     1.000     1.000       500
```

## Strategy-level confusion

| true \ pred | ESCALATE | BILLING_REMINDER | LOYALTY_REWARD | WINBACK | REENGAGEMENT | APPRECIATION | NO_CONTACT |
|---|---|---|---|---|---|---|---|
| **ESCALATE** | 30 | 0 | 0 | 0 | 0 | 0 | 0 |
| **BILLING_REMINDER** | 0 | 109 | 0 | 0 | 0 | 0 | 0 |
| **LOYALTY_REWARD** | 0 | 0 | 95 | 0 | 0 | 0 | 0 |
| **WINBACK** | 0 | 0 | 0 | 41 | 0 | 0 | 0 |
| **REENGAGEMENT** | 0 | 0 | 0 | 0 | 59 | 0 | 0 |
| **APPRECIATION** | 0 | 0 | 0 | 0 | 0 | 125 | 0 |
| **NO_CONTACT** | 0 | 0 | 0 | 0 | 0 | 0 | 41 |


## Mismatches

None.


> Limitations: synthetic labels reflect the intended business definitions (ASSUMPTIONS in segments.yaml); they do not validate the definitions themselves.
