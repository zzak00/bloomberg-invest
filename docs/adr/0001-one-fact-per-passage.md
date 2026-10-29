# One Fact per Passage

A Fact is one statement from one Passage, never a merged record with several sources. When two filings state the same thing, they are two Facts with the same key; agreement and Conflict fall out of grouping by that key, and both values stay visible with their own citations. We chose this over one fact with a list of sources because filings often disagree by date or basis, and a merged record would hide which source said what.

## Consequences

- The store interface is built around Facts (with period or as-of date, basis, recorded time and Passage), not edges, so either graph store from #6 can hold it.
- The value shown for a key is picked at read time: a human-reviewed value, else the latest as-of date, else the annual report over the issuer page.
