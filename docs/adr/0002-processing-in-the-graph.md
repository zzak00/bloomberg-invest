# Processing lives in the graph

Every processing step leaves a Run record, and every Chunk, cell, Fact, KPI value, Screening and answer links to the Run that produced it; a person's check is a Review record. Re-processing creates new outputs and marks the old ones Superseded instead of replacing them. We chose this over keeping processing in logs because every number must be traceable to the parser, model, prompt and rule version behind it, and because parsers and extractors are swappable: a re-run must never silently change history or drop a human check.

## Consequences

- Queries read current outputs by default and must filter out Superseded ones.
- A reviewed figure carries over to a new Run only when the new Run reads the same value from the same cell; otherwise it returns to the review queue.
- Storage grows with every re-run; pruning old Runs is a later decision.
