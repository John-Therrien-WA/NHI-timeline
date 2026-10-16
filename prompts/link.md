You are deciding, for each telling of a numbered group taken from a podcast about non-human intelligence, whether it tells a story the corpus already holds. The corpus records stories as told, never as true; your job is only to say whether two people are telling the same story.

Decide one of three for each telling:

- `same`: the telling claims the same event, program, document, encounter or theory as one of the stories below, at the same grain. A reader who heard both would say "they are telling the same story". Differences in detail (a date a year off, a number, who was present, how sure the teller is) still make it `same`; those differences go into `difference`. The grain must match: a whole program and one incident inside it, a general claim and one specific case of it, a person's career and one event in it are different grains and never `same`; when the telling is broader or narrower than the nearest story, answer `new`.
- `variant`: the telling is about the same event or subject as one of the stories but makes a different core claim about it, so that one account could be right and the other wrong (the same light explained as a flare and as a craft; the same program placed with a different agency in a different decade). Both stay as stories, linked as variants.
- `new`: none of the stories below is this story. A story about a related but distinct event is `new`: a different crash, a different witness's own encounter, a single incident inside a larger program the story only mentions, a general theory beside a specific event.

The tellings of a group come in the order they were told, often from one episode, so a later telling may tell again a story an earlier telling of the group begins. A telling may therefore be `same` as, or a `variant` of, an earlier telling of the group (one with a lower number), named `#` and its number (`#2`), by the same rules as a story below. Decide each telling on its own: tellings of one group are not the same story merely for being told together.

<tellings>
{candidates}
</tellings>

<stories>
{stories}
</stories>

Answer with `decisions`: one entry per telling, in the order of their numbers, each with six fields in this order:

- `candidate`: the telling's number.
- `reason`: one or two sentences naming what the telling and the chosen story share or do not share (the event, the place, the time, the people). For `new`, say why the nearest story is a different story.
- `story`: the id of the story you judge `same` or `variant`, exactly as given above, or `#n` for an earlier telling of the group; null for `new`.
- `grain`: whether the telling's scope matches the chosen story (`same`), is wider than it (`broader`: the whole program, the general claim, the career) or is narrower (`narrower`: one incident inside it, one case of it, one event in it). For `new`, the grain against the nearest story. A `same` at any grain but `same` is not kept.
- `decision`: `same`, `variant` or `new`.
- `difference`: for `same` and `variant`, what this telling adds or says differently from the story's tellings (dates, numbers, who did what, a stronger or weaker claim, a source the story lacks), in one sentence; an empty string when nothing differs and for `new`.

<example>
{"decisions": [{"candidate": 1, "reason": "Both describe the 1958 green light rising from the Harbour of Nowhere; this teller relays it from the witness.", "story": "the-lantern-over-the-harbour-of-nowhere-1958", "grain": "same", "decision": "same", "difference": "Told second hand from Bo Fixture, with no duration given, where the story's witness says it hung for a minute."}, {"candidate": 2, "reason": "The pilot boat crew seen that night in the harbour is a different event from the lantern; no story below is about the crew.", "story": null, "grain": "same", "decision": "new", "difference": ""}, {"candidate": 3, "reason": "The same crew on the pilot boat that telling 2 describes, now told by the boat's captain.", "story": "#2", "grain": "same", "decision": "same", "difference": "Names the captain and puts the crew at four."}]}
</example>
