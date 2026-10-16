# Prior art: NHI timelines, case databases, scoring

Research note (scout pass, 16 October 2026). Standing tags: [inst] institutional, [journ] journalism, [enth] enthusiast, [adv] advocacy, [acad] academic. The rating schemes (Hynek, Vallée SVP, GEIPAN A to D, Schulze-Makuch) are in `notes/trust-prior.md`.

## What exists

- Geldreich, "Dataset of the Damned" (https://github.com/richgel999/ufo_data) [enth, the best chronology]: merges Hatch's U (about 18,000 records), Magonia, Eberhart, rr0, Overmeire, Dolan's 2009 appendix, NICAP and more into one JSON and Markdown chronology; each event has date, location, description, type, reference, source dataset and id, and for Hatch rows credibility and strangeness tags. Code Apache 2.0; data per source (Hatch family permission, Beau GFDL, commercial use may need permission). Linear time, no map, no 3D, no teller independence.
- The Black Vault's post-2017 UAP timeline (https://www.theblackvault.com/documentarchive/the-black-vaults-post-2017-uap-ufo-timeline-project) [journ, FOIA]: dated entries with a quote, a source line and a "Problem:" note flagging where accounts contradict (Elizondo, the Times, the Pentagon). The nearest existing thing to "who said what, and does it agree". Not downloadable.
- Snead, Timeline of U.S. Congressional Action on UFOs 2007 to 2024 (https://justinsnead.substack.com/p/timeline-of-us-congressional-action) [enth, careful]: legislation, hearings, testimony, documents; no export.
- Wikipedia, List of reported UFO sightings (https://en.wikipedia.org/wiki/List_of_reported_UFO_sightings) and David Grusch UFO whistleblower claims (https://en.wikipedia.org/wiki/David_Grusch_UFO_whistleblower_claims) [tertiary, CC BY-SA]: the Grusch article groups claims by venue and date, 98 references, no transcript time codes.
- Loren Gross, UFOs: A History (https://sohp.us/collections/ufos-a-history/doc/1947.php) [enth, archival]: month by month 1947 to 1959, sourced to press and Blue Book files.
- Vallée's Magonia catalogue (https://www.rpginc.com/the-magonia-database-a-century-of-ufo-landings-1868-1968-2/), Project 1947 (https://project1947.com/folio/index.htm), rr0.org (https://rr0.org/, GFDL, French), Patrick Gross (https://ufology.patrickgross.org/, 23,000 case pages with citation tags) [enth].
- AARO Historical Record Report Vol. I (https://www.theblackvault.com/documentarchive/report-on-the-historical-record-of-u-s-government-involvement-with-unidentified-anomalous-phenomena-uap-volume-i/) [inst]: 1945 to 2023 as programs, not stories.
- Map based: UFOMAP (https://ufomap.ca) [enth], 746,637 records from NUFORC, UFOCAT, MUFON and others on a 2D map, export only in the paid tier, an undefined "quality score"; Google's WebGL globe experiment (https://experiments.withgoogle.com/ufo-sightings-around-the-world) is 3D but shows cluster centroids of NUFORC, no stories.
- Not found: a Liberation Times, Debrief, UAP Caucus or Sol Foundation timeline; any 3D timeline of the subject.

## Case databases and terms

- NUFORC [enth, the de facto standard]: witness narratives with date, place and shape; the terms forbid scraping and redistribution, data by request (https://github.com/timothyrenner/nuforc_sightings_data); mirrors on Hugging Face carry a warning that the real licence is stricter.
- MUFON CMS [adv]: full reports behind membership.
- The Black Vault [journ, FOIA]: Blue Book, 129,491 pages and 10,000 cases as free PDFs (https://www.theblackvault.com/casefiles/); the CIA collection (https://www.theblackvault.com/documentarchive/ufos-the-central-intelligence-agency-cia-collection/). Government records, public domain.
- CIA Reading Room (https://www.cia.gov/readingroom/collection/ufos-fact-or-fiction) [inst, public domain]; UK National Archives UFO files (https://www.nationalarchives.gov.uk/explore-the-collection/explore-by-time-period/postwar/ufo-reports/) [inst, OGL v3].
- GEIPAN (https://www.cnes-geipan.fr/fr/recherche/cas) [inst]: 3,200 cases with witness PDFs and A to D classes; licence not confirmed.
- UFOCAT [enth, CUFOS]: 300,000 entries, sold, not open. Hatch's U: inside Geldreich.
- uap-knowledge-graph (https://uap-knowledge-graph.onrender.com/uap_deploy/sources) [enth]: 66 sources with a licence column, a crib for terms.
- Isaac Koi [enth]: 25,875 PDFs catalogued (https://isaackoi.com/); a 50,000-video auto-transcript archive on AboveTopSecret, a finding aid for which recordings carry which story.

## Scoring across a corpus, and tellings graphs

Every scheme found classifies one case (Hynek, Vallée, GEIPAN, Hatch, Enigma Labs' proprietary 1 to 100, Schulze-Makuch and Reichhardt 2025, https://www.mdpi.com/2218-1997/11/10/326). Nothing normalises against a corpus or models the independence of tellers. No tellings graph exists: the Black Vault's "Problem:" notes, Wikipedia's by-venue grouping of Grusch's claims and Metabunk's provenance threads (https://metabunk.org/goto/post?id=296323) are the nearest, all prose.

## What this project adds

Verbatim quotes at time codes; explicit teller independence through `cites`; a corpus-normalised score with an evidence profile; a story axis (the same story told across podcasts) instead of a sightings axis; overlap links including contradictions; 3D exploration; open, diffable per-story JSON.

## Candidates for the scrape beyond American Alchemy

1. Geldreich's `ufo_data` JSON: the broadest sourced chronology, licence-tagged per row; gives eras, places and document anchors for the decades before podcasts. Its rows would enter as `researcher` tellings citing the catalogue's reference, never as corroboration on their own.
2. The Black Vault post-2017 timeline: dated, sourced entries and ready-made contradiction flags around AATIP, Elizondo and Grusch, the same tellers the corpus already holds.
3. Koi's transcript archive as a finding aid: which episodes carry a story, then the captions re-pulled through `yt-dlp` so quotes stay verbatim and reachable.
Unresolved: NUFORC, Kaggle, GEIPAN and MUFON terms.
