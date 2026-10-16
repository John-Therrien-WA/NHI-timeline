# The evidence profile and the corroboration score

What the score is for: to put the stories that many independent people tell, with documents behind them, in the obvious places on the timeline, and the stories one person tells once at the edge, without anyone judging which stories are true. John's rule: "the more corroborated, normalised for the standard of the whole, come to the obvious positions in the project, and things that are similar or corroborate each other overlap."

The score has three layers. The **profile** is the evidence, counted and kept visible. The **score** is one number derived from the profile; it drives the visual (a story's size, brightness and distance from the corridor's centre). The **tier** names the band a story sits in, in words. `pipeline/score.py` is this file as code and writes all three into each story and into `data/scores.json`.

## Tellers and independence

1. **Tellers.** Collect every telling of the story and group them by `teller`. One person is one teller however often, and on however many shows, they tell it.
2. **Independence.** Build the citation graph from `cites` among the story's tellers. Two tellers are independent when neither reaches the other through `cites` within the story and they are not the same person. A teller who reaches another teller of the story is dependent: their telling is a **repetition**, which the page shows as reach, never as weight. Tellers that cite each other in a cycle count once, as the strongest of them.
3. **A teller's kind** is the strongest kind among their tellings, in the fixed order firsthand, official, journalist, secondhand, researcher, host. The order does not move with the institutional-trust knob: a teller who is both a witness and an official counts as a witness at every setting.

## The profile

Every story carries `profile`:

- `independent_tellers`: how many independent tellers the story has.
- `firsthand`, `official_records`, `official_conclusions`, `journalist`, `secondhand`, `researcher`, `host`: the independent tellers counted by their kind; the seven sum to `independent_tellers`. An `official` teller is a record unless every official telling of theirs carries `"official_kind": "conclusion"`.
- `documents`: the distinct documents that are themselves tellings (`"document": id`).
- `credited_documents`: the distinct documents an independent teller credits (`documents` on a telling) that are not already tellings. A document credited only by a dependent teller counts nowhere.
- `repetitions`: the dependent tellers.
- `contradicted`: true when a `contradicts` relation joins the story to another, in either direction. It flags and never reduces; the `contradicts` link stays on the page.
- `strongest_kind`: the strongest kind among the independent tellers.
- `tellers`: the independent tellers' ids. `episodes`: the distinct episode ids among all tellings.

The profile holds everything the attestation needs, so the page recomputes it at any knob value without the pipeline.

## Weights

The research behind each weight is `notes/trust-prior.md`; no published source fixes a number, so the weights set a direction and a rough magnitude, and the knob exposes the one that is most disputed.

| Term | Weight | Grounding |
|---|---|---|
| firsthand | 1.0 | The witness or participant is the anchor every framework (legal hearsay, Vallée's SVP, AP and Reuters sourcing) ranks first. |
| official | 0.8 x trust | Below firsthand because an official summary of testimony depends on its witnesses and the institution's own historian records explanations issued knowing they were false; not far below because law and the Admiralty system treat public records as presumptively trustworthy. |
| journalist | 0.6 | A reporter citing named sources ranks under the source itself in AP and Reuters practice. |
| secondhand | 0.5 | Vallée's firsthand to secondhand ratio of 3:2 puts relayed testimony near two thirds of firsthand; 0.5 stays on the cautious side of it. |
| researcher | 0.25 | A summary without a named source has no anchor of its own in any framework. |
| host | 0.1 | The host's framing is reach, not testimony. |
| a document that is a telling | 0.5 | A document quoted in its own right is evidence beside its teller. |
| a document only credited | 0.25 | Credited by a teller already counted, it adds less than a document quoted directly. |

**Attestation** is the sum of each count times its weight, with both `official_records` and `official_conclusions` at the official weight, plus the two document terms.

## The institutional-trust knob

One multiplier on the official weight, labelled institutional trust, from 0.5 to 1.25, default 1.0. At the default an official teller weighs 0.8; the range moves it between 0.4 and 1.0, so at its top an official teller weighs as much as a witness and never more. Every other weight stays fixed. The pipeline writes the attestation and score at the default; `data/scores.json` and `site/data.json` carry the weights, the knob's default and range, and the median, so the page recomputes every attestation and the median at the reader's setting.

## Score

The corpus median of attestation over all stories is `m`, floored at 0.5. The **score** is attestation over `m`. A story at 1.0 is as well attested as the typical story in the corpus; the scale moves as the corpus grows, so a score is only meaningful beside the corpus's date.

## Tiers

- **well-attested**: at least two independent tellers, and at least one document (a telling or credited), one firsthand teller or one official record.
- **told-by-several**: at least two independent tellers, none of them a witness or a record and no document.
- **told-once**: one independent teller (however often repeated).

The tiers do not depend on the knob or the median, so a story's band is the same at every setting and in every corpus size.

## Overlap

Two stories are linked when they share a document or an event (`related` with `same-event` or `variant`), or when one is marked `corroborates` or `contradicts` the other. A `same-event` pair is drawn as a link; `contradicts` as a dashed link in the warning colour. A shared teller is not a link: one host telling fifty stories would join every story to every other and the lines would be a band. The page counts it instead and shows it in a story's panel as "also told by this teller: N stories" (by teller when the story has several), so the reach of one voice stays visible without being drawn as corroboration.

## What the score is not

- Not truth. A hoax told by twenty independent people scores high, and should: the project maps what is told.
- Not reach. A story repeated by every podcast but sourced to one person scores like one person; the repetitions and the episodes are in the profile, so the difference between corroboration and virality stays visible.
- Not a verdict on a contradiction. A contradicted story keeps its score; the flag and the link say that someone tells it otherwise.

## Open questions

- The record and conclusion split of `official`. The research (FRE 803(8)'s "matter observed" against a conclusion) suggests a record of observation keep a high weight and the knob scale only explanatory conclusions. The profile already counts the two apart; nothing sets `official_kind` yet, so both weigh the same until the extractor or a hand edit marks conclusions.
- Era normalisation. Stories before 1970 have fewer living tellers by nature; there is one corpus-wide median.
- Recanting. A teller who later recants is a `contradicts` link to their own earlier telling, which flags both and changes no weight; whether a recantation should remove the earlier telling's weight is open.
