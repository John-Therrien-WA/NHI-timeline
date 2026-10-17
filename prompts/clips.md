You are reading passages that appear word for word in more than one podcast episode about non-human intelligence. Hosts often cut a clip of another person into an episode: a guest from another of their episodes, a news interview, a hearing, a documentary. A transcript extractor that credits every quote to the episode's guest then credits the clip's words to the wrong person. Your job is to say, for each numbered group below, who actually speaks the shared passage and which episode the recording originally belongs to.

Each group gives the shared words and, for every episode they occur in (an occurrence), the episode's show, title, host, guests and published date, the people the corpus knows in that episode, and the caption text of about a minute before and after the passage. The captions are automatic: names are often misspelled, and a line beginning with `>>` marks a change of speaker. A `>>` at the start or the end of the passage in one episode and not in the other is strong evidence of a cut. So is an introduction in the lines before ("here's what X told me", "listen to this", "as X said on the show"), a passage whose content or voice does not fit the conversation around it, and the host reacting to it afterwards as to something played. In the occurrence where the recording belongs, the passage sits inside a running conversation: the question that leads into it comes before, and the same speaker or the interviewer carries on after it.

The published date does not tell the origin: a host may air a clip from an interview he has recorded but not yet published. That the speaker is a listed guest does not decide it either, since every episode lists its own guest. Judge from the caption text.

Decide one verdict for each group:

- `clip`: the passage is one recording aired more than once. Give the `speaker`, `also_heard` and the `origin`: `#n`, the number of the occurrence the recording belongs to (the conversation it was recorded in), or `outside` when every occurrence replays a recording from outside these episodes (a news interview, a documentary, a hearing, another show).
- `not-a-clip`: the words coincide but each occurrence is said by its own speaker in its own conversation (two people reading out the same document, a stock phrase, a sponsor read). `speaker` and `origin` are null, `also_heard` empty.
- `unclear`: the captions do not let you tell who speaks or where it is from. `speaker` and `origin` are null, `also_heard` empty. Prefer this to a guess.

The `speaker` is the person whose account the passage carries: in an exchange, the person being interviewed, not the interviewer asking the questions. `also_heard` lists every other person whose voice is in the passage (the interviewer of the clip, a second guest); empty when only the speaker is heard. When a person is among "the people the corpus knows" of any occurrence, answer with that id exactly as given (for example `harold-malmgren`), even when you would spell the name differently; otherwise answer with the person's full name as the captions or the titles give it.

<groups>
{groups}
</groups>

Answer with `groups`: one entry per group, in the order of their numbers, each with six fields in this order:

- `group`: the group's number.
- `reason`: one or two sentences naming the evidence (the `>>` marks, the introduction, the conversation around the passage in each occurrence).
- `verdict`: `clip`, `not-a-clip` or `unclear`.
- `speaker`: for a clip, the id or name of the person whose account it is; null otherwise.
- `also_heard`: for a clip, the ids or names of the other people heard in the passage; empty otherwise.
- `origin`: for a clip, `#n` or `outside`; null otherwise.

<example>
{"groups": [{"group": 1, "reason": "In occurrence 2 the host says 'here is what Bo told me' and a >> opens the passage, which breaks off the topic; in occurrence 1 the passage answers the interviewer's question and Bo goes on speaking after it.", "verdict": "clip", "speaker": "bo-fixture", "also_heard": ["dee-fixture"], "origin": "#1"}, {"group": 2, "reason": "Both speakers read out the same sentence of the harbour log, each in their own conversation.", "verdict": "not-a-clip", "speaker": null, "also_heard": [], "origin": null}]}
</example>
