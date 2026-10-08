# Fixtures

Two tiny, entirely fictional episodes so the whole chain runs offline: `pipeline.check --fixture`
copies this folder to a temporary directory and runs extract (reading `answers/<id>.json` instead
of asking `claude -p`), merge, score, build and the checks on it. Nothing here is a real claim, a
real person, a real show or a real place; the video ids do not exist. `data/` holds the axes, the
two episodes, one document and one hand-written story (the one that contradicts a merged one);
`sources/captions/` the invented caption text; `answers/` the model answers as the prompt's schema
gives them, including one quote that is not verbatim and must be dropped.
