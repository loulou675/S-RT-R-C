# v73r17 broad-material head

This seven-class ONNX classifier is one part of the local v73r35 cascade. It
does not independently decide every fallback result: its scores are combined
with the exact-destination probabilities, the v73r15 destination router, the
single-vs-mixed head, and generic detector evidence.

## Outputs

- `plastic`
- `metal`
- `paper_cardboard`
- `organic`
- `glass`
- `electronic_battery`
- `mixed_uncertain`

The paired mixed head outputs `single_material` or `mixed_material`. The
destination head outputs the six disposal destinations plus
`mixed_uncertain`.

## Runtime safeguards

The runtime applies thresholds for organic and electronic results, requires
multi-head agreement for mixed-material results, permits a small reviewed set
of generic detector identity overrides, and sends unsupported or conflicting
cases to feedback. Exact-item pair minimums additionally veto several common
harmful assumptions.

## Evaluation status

The policy passes the minimum known-item held-out limits (195/242 correct and
21 harmful) and scored 78 helpful to 11 harmful on six consumed unsupported
development sets. Its final time-bounded independent evaluation scored 10
helpful, 5 harmful, and 9 feedback results.

That 2.00:1 independent helpful-to-harmful ratio misses the original 4:1 gate.
The shortfall is accepted for local MVP integration only. This cascade remains
experimental and must retain feedback and rollback paths.

## Limitations

Appearance alone cannot reliably determine cleanliness, coatings, hidden
layers, contamination, sharps, pressurisation, or local acceptance rules.
Detector identity is closed-set and cannot prove that an unsupported object is
a supported exact item. The app must keep visible material-only caveats and a
feedback path for uncertain cases.
