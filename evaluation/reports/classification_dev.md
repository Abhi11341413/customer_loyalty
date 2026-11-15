# Classification evaluation — dev

As of 2026-11-15. Cases: **200**. Exact segment-set match: **100.0%**. Engagement macro-F1: **1.000**. Severe strategy errors: **0**.

## Engagement axis (multiclass)

```
                    precision    recall  f1-score   support

 INSUFFICIENT_DATA      1.000     1.000     1.000        13
           DORMANT      1.000     1.000     1.000        26
DECLINING_ACTIVITY      1.000     1.000     1.000        23
        CONSISTENT      1.000     1.000     1.000       127
          STANDARD      1.000     1.000     1.000        11

          accuracy                          1.000       200
         macro avg      1.000     1.000     1.000       200
      weighted avg      1.000     1.000     1.000       200
```

| true \ pred | INSUFFICIENT_DATA | DORMANT | DECLINING_ACTIVITY | CONSISTENT | STANDARD |
|---|---|---|---|---|---|
| **INSUFFICIENT_DATA** | 13 | 0 | 0 | 0 | 0 |
| **DORMANT** | 0 | 26 | 0 | 0 | 0 |
| **DECLINING_ACTIVITY** | 0 | 0 | 23 | 0 | 0 |
| **CONSISTENT** | 0 | 0 | 0 | 127 | 0 |
| **STANDARD** | 0 | 0 | 0 | 0 | 11 |


## Qualifier / flag (binary)

**LOYALTY_CANDIDATE**

```
              precision    recall  f1-score   support

          no      1.000     1.000     1.000       137
         yes      1.000     1.000     1.000        63

    accuracy                          1.000       200
   macro avg      1.000     1.000     1.000       200
weighted avg      1.000     1.000     1.000       200
```

**PAYMENT_REMINDER**

```
              precision    recall  f1-score   support

          no      1.000     1.000     1.000       159
         yes      1.000     1.000     1.000        41

    accuracy                          1.000       200
   macro avg      1.000     1.000     1.000       200
weighted avg      1.000     1.000     1.000       200
```

## Strategy-level confusion

| true \ pred | ESCALATE | BILLING_REMINDER | LOYALTY_REWARD | WINBACK | REENGAGEMENT | APPRECIATION | NO_CONTACT |
|---|---|---|---|---|---|---|---|
| **ESCALATE** | 13 | 0 | 0 | 0 | 0 | 0 | 0 |
| **BILLING_REMINDER** | 0 | 41 | 0 | 0 | 0 | 0 | 0 |
| **LOYALTY_REWARD** | 0 | 0 | 32 | 0 | 0 | 0 | 0 |
| **WINBACK** | 0 | 0 | 0 | 26 | 0 | 0 | 0 |
| **REENGAGEMENT** | 0 | 0 | 0 | 0 | 23 | 0 | 0 |
| **APPRECIATION** | 0 | 0 | 0 | 0 | 0 | 54 | 0 |
| **NO_CONTACT** | 0 | 0 | 0 | 0 | 0 | 0 | 11 |


## Mismatches

None.


> Limitations: synthetic labels reflect the intended business definitions (ASSUMPTIONS in segments.yaml); they do not validate the definitions themselves.
