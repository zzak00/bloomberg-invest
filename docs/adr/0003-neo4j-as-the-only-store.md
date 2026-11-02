# Neo4j is the only store

Neo4j Community holds everything the app keeps:
- Organisations and Facts;
- Documents, Sections, Chunks, paragraphs and Cells;
- the vector and full-text indexes;
- Prices;
- Runs and Reviews.

There is no second database. We chose it over PostgreSQL + pgvector, the other option shortlisted in #6. Postgres fits constraints and fact tables best, but we want Cypher open for graph questions beyond the fixed agent tools, and `neo4j-graphrag`'s hybrid retriever. One store also keeps each piece of state in one place, as ADR 0002 requires.

## Consequences

- **Required properties and types:** Community enforces only uniqueness constraints, so the Python store layer checks the rest before writing.
- **Running Cypher written later:** Community has no read-only roles. Such queries run in read transactions after an `EXPLAIN` check that the query only reads, with a timeout and a row limit.
- **Licence:** Community is GPLv3, fine for internal use. A hosted product for others needs a licence review.
- **Adding Postgres later:** possible for a job queue, accounts or price analytics. Facts, Runs and Reviews stay in Neo4j.
