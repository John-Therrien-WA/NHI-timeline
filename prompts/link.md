You are deciding whether one telling, taken from a podcast about non-human intelligence, tells a story the corpus already holds. The corpus records stories as told, never as true; your job is only to say whether two people are telling the same story.

Decide one of three:

- `same`: the telling claims the same event, program, document, encounter or theory as one of the stories below, at the same grain. A reader who heard both would say "they are telling the same story". Differences in detail (a date a year off, a number, who was present, how sure the teller is) still make it `same`; those differences go into `difference`. The grain must match: a whole program and one incident inside it, a general claim and one specific case of it, a person's career and one event in it are different grains and never `same`; when the telling is broader or narrower than the nearest story, answer `new`.
- `variant`: the telling is about the same event or subject as one of the stories but makes a different core claim about it, so that one account could be right and the other wrong (the same light explained as a flare and as a craft; the same program placed with a different agency in a different decade). Both stay as stories, linked as variants.
- `new`: none of the stories below is this story. A story about a related but distinct event is `new`: a different crash, a different witness's own encounter, a single incident inside a larger program the story only mentions, a general theory beside a specific event.

<telling>
{candidate}
</telling>

<stories>
{stories}
</stories>

Answer with five fields, in this order:

- `reason`: one or two sentences naming what the telling and the chosen story share or do not share (the event, the place, the time, the people). For `new`, say why the nearest story is a different story.
- `story`: the id of the story you judge `same` or `variant`, exactly as given above; null for `new`.
- `grain`: whether the telling's scope matches the chosen story (`same`), is wider than it (`broader`: the whole program, the general claim, the career) or is narrower (`narrower`: one incident inside it, one case of it, one event in it). For `new`, the grain against the nearest story. A `same` at any grain but `same` is not kept.
- `decision`: `same`, `variant` or `new`.
- `difference`: for `same` and `variant`, what this telling adds or says differently from the story's tellings (dates, numbers, who did what, a stronger or weaker claim, a source the story lacks), in one sentence; an empty string when nothing differs and for `new`.

<example>
{"reason": "Both describe the 1958 green light rising from the Harbour of Nowhere; this teller relays it from the witness.", "story": "the-lantern-over-the-harbour-of-nowhere-1958", "grain": "same", "decision": "same", "difference": "Told second hand from Bo Fixture, with no duration given, where the story's witness says it hung for a minute."}
</example>
