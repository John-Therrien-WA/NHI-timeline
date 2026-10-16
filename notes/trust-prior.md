# The trust prior: what the research supports

Research note (scout pass, 16 October 2026) behind the `official` weight and the institutional-trust knob in `scoring.md`. The question: can the weight of an institutional source (a government document, an official explanation, an agency summary of testimony) against a firsthand individual witness be grounded in evidence rather than taste, and exposed as a knob without building in a bias. The short answer: no source attaches a numeric prior to "institution versus individual"; every framework separates source reliability from information credibility and leaves the weight to judgment. The anchors below support a direction, not a magnitude.

## Frameworks that separate source reliability from information credibility

- NATO/Admiralty 6x6 (STANAG 2511, now AJP-2.1; text reproduced in the MISP admiralty-scale taxonomy, https://github.com/MISP/misp-taxonomies/blob/master/admiralty-scale/README.md): source A (completely reliable) to E (unreliable), F cannot be judged; information 1 (confirmed by other sources) to 5 (improbable), 6 cannot be judged. No numeric priors; a new source is F by rule. Kelly, Budescu, Dhami and Mandel 2025 (Judgment and Decision Making, https://doaj.org/article/1275b61966214005aca34e254dca4e67) find analysts' trust ratings lean on source reliability more than content credibility.
- ICD 203 (US ODNI analytic standards): source quality described separately from confidence (high, moderate, low) and from likelihood bands. No source-type weights.
- Legal evidence: hearsay rationale names perception, memory, narration and sincerity as the four risks. Public records are admissible under FRE 803(8) (https://www.law.cornell.edu/rules/fre/rule_803) unless circumstances "indicate a lack of trustworthiness", and law-enforcement observations are excluded in criminal cases; the rule distinguishes a "matter observed" from a conclusion. The presumption of regularity for official acts is rebuttable (https://www.lawfaremedia.org/article/history-taxonomy-and-qualified-defense-presumption-regularity).
- Bovens and Hartmann 2003, Bayesian Epistemology (arXiv precursor https://arxiv.org/pdf/cs/0003041): n independent, partially reliable witnesses; confidence rises with number, independence and coherence. Reliability is a free parameter. Independence (screening off) is the operative requirement, which is what the project's `cites` rule implements.
- Journalism: AP's two-source rule for anonymous material, with an exception for a single authoritative figure in a position to know (https://ds.svcs.associatedpress.com/behind-the-news/when-is-it-ok-to-use-anonymous-sources); Reuters requires first-hand knowledge for a single anonymous source. Firsthand participants rank above officials on background; no numbers.

## Base rates for individual witnesses

Honest error dominates fabrication by about an order of magnitude in every corpus found.

- Project Blue Book: 701 of 12,618 reports unidentified, 5.6 percent (https://www.af.mil/About-Us/Fact-Sheets/Display/Article/104590/). Special Report 14 (Battelle 1955, 3,201 cases): 69 percent known, 9 percent insufficient, 22 percent unknown; 35 percent of the best-documented cases unknown against 18 percent of the poorest; 1.5 percent "psychological", hoaxes not broken out (https://www.theblackvault.com/documentarchive/project-blue-book-special-report-14-may-5-1955/).
- GEIPAN (France, 3,188 cases, February 2025): A 26.4, B 39.0, C 31.4, D 2.2 percent; consistency and residual strangeness scored separately (https://geipan.fr/en/stats).
- Hendry 1979 (CUFOS, 1,307 reports): about 89 percent identified (tertiary, https://en.wikipedia.org/wiki/Identification_studies_of_UFOs).
- Eyewitness memory: misidentification in 69 percent of 375 DNA exonerations (Innocence Project, advocacy); high-confidence initial identifications under good conditions about 95 percent accurate (Wixted and Wells 2017, peer reviewed); false-memory implantation about 30 percent in a mega-analysis (Scoboria et al. 2017).
- Lying: confirmed false crime reports about 5 percent (Ferguson and Malouff 2016, https://rune.une.edu.au/web/handle/1959.11/19001; the 2 to 10 percent range is contested on definitions).

## Base rates for institutions

No study gives a rate of official statements later shown false; the literature is catalogues without denominators. Overclassification figures ("50 to 90 percent", https://sgp.fas.org/congress/2016/overclass.pdf) are testimony, not audits, and secrecy is not lying.

- Official admissions, not advocacy: the NSA's Gulf of Tonkin release (https://nsarchive.gwu.edu/NSAEBB/NSAEBB132/press20051201.htm); the Senate Intelligence Committee's 2008 finding that prewar Iraq statements were "not substantiated" (https://www.intelligence.senate.gov/press/senate-intelligence-committee-unveils-final-phase-ii-reports-prewar-iraq-intelligence), with a partisan dissent.
- UFO-specific, from the CIA's own historian (Haines 1997, Studies in Intelligence, https://sgp.fas.org/library/ciaufo.html): the Robertson Panel recommended the National Security Council "debunk UFO reports"; Blue Book "tried to explain away" U-2 sightings and was "careful not to reveal the true cause of the sighting to the public"; "this concealment of CIA interest contributed greatly to later charges of a CIA conspiracy and coverup."
- Roswell: the 8 July 1947 "flying disc" release withdrawn the same day; the 1994 report (Mogul) after a GAO audit; the 1997 "Case Closed" report (https://www.nsa.gov/news-features/declassified-documents/ufo/assets/files/report_af_roswell.pdf).
- AARO's 2024 historical report: critics list factual errors (https://thedebrief.org/aaros-historical-report-a-tale-of-factual-errors-and-old-mistakes-repeated/, journalism); claims of deception beyond those errors rest on advocacy sources only.

## Numeric ratings of anomalous testimony

- Hynek 1972: strangeness and probability axes, single-reporter cases capped at probability 3.
- Vallée 1990 (Confrontations), SVP: source S 0 unknown, 1 known but unproven, 2 reliable secondhand, 3 reliable firsthand; visit V and possible-explanation P 0 to 4. The only published firsthand to secondhand ratio found, 3:2.
- GEIPAN A to D, as above. Galileo Project: instruments only, testimony "not enough for science". Ballester Olmos and Guasp's certainty index: not found online. Schulze-Makuch and Reichhardt 2025 (Universe 11:326): an evidence-quality scale by observer count, imagery and whether a conventional explanation was sought; the levels could not be fetched.

## What the score takes from this

- Firsthand 1.0, official 0.8, journalist 0.6, secondhand 0.5, researcher 0.25, host 0.1. Secondhand rises from 0.4 because Vallée's 3:2 puts it near 0.67 and 0.4 sat below every published anchor. Official sits below firsthand because an official summary of testimony is a dependent teller of those witnesses and because, in this domain, the institution's own historian records explanations issued knowing they were false; it sits not far below because law and the Admiralty system treat institutional records as presumptively trustworthy and the institutional record is anecdotes without a rate.
- The knob is one multiplier on the official weight, labelled institutional trust, range 0.5 to 1.25, default 1.0 (so official moves between 0.4 and 1.0); every other weight stays fixed. `scoring.md` is the specification.
- The refinement that follows FRE 803(8), kept as an open question until something sets it: an official telling is either a record of observation (a radar log, a deck log, a pilot's report in a hearing transcript) or an explanatory conclusion (a weather balloon, a Mogul balloon, "no evidence"); the profile already counts the two apart through `official_kind`, and the knob could then scale conclusions alone.
- Uncertainty: no source supports any specific value. The direction (official at or below firsthand for this corpus) rests on official admissions; the magnitude is judgment, and the knob exists so the reader can move it.
