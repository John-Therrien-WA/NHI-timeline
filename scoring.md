# The corroboration score

What the score is for: to put the stories that many independent people tell, with documents behind them, in the obvious places on the timeline, and the stories one person tells once at the edge, without anyone judging which stories are true. John's rule: "the more corroborated, normalised for the standard of the whole, come to the obvious positions in the project, and things that are similar or corroborate each other overlap."

## The rule

1. **Tellers.** Collect every telling of the story. Group tellings by `teller`; one person is one teller however often they tell it.
2. **Independence.** Build the citation graph from `cites`. Two tellers are independent when neither is reachable from the other through `cites` within the story. A teller who cites another teller of the same story adds nothing of their own; their telling still counts as a *repetition*, which the page shows as reach, never as weight.
3. **Weights by kind** (the strongest kind among a teller's tellings): `firsthand` 1.0, `official` 1.0, `journalist` 0.6, `secondhand` 0.4, `researcher` 0.25, `host` 0.1.
4. **Documents.** Each independent document in the tellings adds 0.5 (a document cited by a teller who is already counted adds 0.25).
5. **Attestation** = the sum of the independent tellers' weights plus the document terms.
6. **Normalisation.** The corpus median of attestation over all stories is `m` (at least 0.5). The **score** = attestation / `m`. A story at 1.0 is as well attested as the typical story in the corpus; the scale moves as the corpus grows, so a score is only meaningful beside the corpus's date.
7. **Overlap.** Two stories are linked when they share a teller, a document, or an event (`related` with `same-event` or `variant`), or when one is marked `corroborates` or `contradicts` the other. A `same-event` pair is drawn as one dot with two rings; `contradicts` as a link in the warning colour.

## What the score is not

- Not truth. A hoax told by twenty independent people scores high, and should: the project maps what is told.
- Not reach. A story repeated by every podcast but sourced to one person scores like one person; the page shows the repetitions as a halo so the difference between corroboration and virality is visible.

## Open questions

- Whether `official` should outweigh `firsthand` when the document is itself a summary of testimony (currently equal).
- How to treat a teller who later recants (currently a `contradicts` link to their own earlier telling, no weight change).
- Whether era-level normalisation is needed (stories before 1970 have fewer living tellers by nature); currently one corpus-wide median.
