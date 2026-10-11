# Indore water contamination: sources

Every number we quote (README, video, submission) must trace back to a line here. The replay (`data/replay_indore.jsonl`) follows this timeline and is labelled SIMULATION wherever it appears. Checked on 11 Oct 2026.

## Facts we use

| Fact | Source |
|---|---|
| Bhagirathpura, Indore, December 2025: sewage entered the drinking-water supply | [Wikipedia: 2025 Indore drinking water contamination](https://en.wikipedia.org/wiki/2025_Indore_drinking_water_contamination) |
| Cause: a leak in the main pipeline under a toilet, confirmed by lab tests | [Deccan Herald](https://www.deccanherald.com/india/madhya-pradesh/leakage-in-water-pipeline-under-toilet-in-indores-bhagirathpura-led-to-water-contamination-says-lab-test-3848852) |
| Dozens died: the Health Department was told of 35 deaths in Bhagirathpura by 12 Feb 2026, "of which 22 were considered possibly related to the contaminated drinking water" | Judicial commission's report, via [DT Next, 1 Oct 2026](https://www.dtnext.in/news/national/indore-water-linked-deaths-preventable-pipeline-tender-delays-contributed-to-tragedy-judicial-panel) |
| About 1,400 people fell ill | [Wikipedia](https://en.wikipedia.org/wiki/2025_Indore_drinking_water_contamination) (infobox: 1,400 injuries) |
| The tragedy "could have been prevented had the pipeline replacement work been completed on time" | One-member judicial commission (former MP High Court judge Sushil Kumar Gupta), via [DT Next, 1 Oct 2026](https://www.dtnext.in/news/national/indore-water-linked-deaths-preventable-pipeline-tender-delays-contributed-to-tragedy-judicial-panel) |
| Residents had complained about contaminated water for several days and no action was taken | [NHRC press release](https://nhrc.nic.in/media/press-release/nhrc,-india-takes-suo-motu-cognizance-of-the-reported-death-of-7-persons-after-consuming-contaminated-water-being-supplied-in-the-bhagirathpura-area-of-indore-district,-madhya-pradesh:-over-40-people-hospitalised) |
| India's disease surveillance reacts once patients reach health facilities | Background: [IDSP reporting delays (CEGH)](https://www.ceghonline.com/article/S2213-3984(22)00072-0/fulltext) |

Earlier figures (for example "32 deaths till 20 Feb 2026" in Wikipedia's infobox, or "23 deaths" in January reports) were counts at the time; use the commission's figures above.

## Timeline for the replay

Used by `scripts/replay.py` (see `docs/replay.md`). Approximate dates are marked `~`. Day 0 is the first illness.

| Day | Date | Event | Source |
|---|---|---|---|
| ~−12 | ~mid-Dec 2025 | Residents complain of foul-smelling water ("nearly 15 days" before 1 Jan 2026) | [Free Press Journal, 1 Jan 2026](https://www.freepressjournal.in/indore/mp-news-bhagirathpura-turns-into-a-death-zone); [NHRC](https://nhrc.nic.in/media/press-release/nhrc,-india-takes-suo-motu-cognizance-of-the-reported-death-of-7-persons-after-consuming-contaminated-water-being-supplied-in-the-bhagirathpura-area-of-indore-district,-madhya-pradesh:-over-40-people-hospitalised) |
| −2 | 25 Dec 2025 | Residents complain that the water supplied that day had an unusual smell (local councillor Kamal Baghela); a bitter taste is also reported in late December | [Deccan Herald](https://www.deccanherald.com/india/madhya-pradesh/indore-water-contamination-residents-claim-8-deaths-authorities-confirm-three-3847112) |
| 0 | 27 Dec 2025 | First cases of illness: vomiting, diarrhoea, dehydration | [Wikipedia](https://en.wikipedia.org/wiki/2025_Indore_drinking_water_contamination) |
| 2 | 29 Dec 2025 | Indore's mayor confirms at least three deaths | [Wikipedia](https://en.wikipedia.org/wiki/2025_Indore_drinking_water_contamination), citing Dainik Bhaskar, 30 Dec 2025 |
| | 1 Oct 2026 | Judicial commission: it "could have been prevented" | [DT Next](https://www.dtnext.in/news/national/indore-water-linked-deaths-preventable-pipeline-tender-delays-contributed-to-tragedy-judicial-panel) |

Not used: when hospitalisations peaked, or when the contaminated supply stopped (no dated source we could confirm). Sources disagree on the date of the first death (21, 26 or 29 Dec); we use the first official confirmation.
