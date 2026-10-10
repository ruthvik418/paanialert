# Indore water contamination: sources

Owner: C. Every number in the video and writeup must trace back to a line here. The replay (`data/replay_indore.jsonl`) follows this timeline and is labelled SIMULATION wherever it appears.

## Facts we use

| Fact | Status | Source |
|---|---|---|
| Bhagirathpura, Indore, December 2025: sewage entered the drinking-water supply | Confirmed | [Wikipedia: 2025 Indore drinking water contamination](https://en.wikipedia.org/wiki/2025_Indore_drinking_water_contamination) |
| Cause: a leak in a water pipeline under a toilet, found by lab tests | Confirmed | [Deccan Herald](https://www.deccanherald.com/india/madhya-pradesh/leakage-in-water-pipeline-under-toilet-in-indores-bhagirathpura-led-to-water-contamination-says-lab-test-3848852) |
| Residents complained of foul, discoloured water before hospitalisations | Confirmed | [Business Today](https://www.businesstoday.in/india/story/indore-water-crisis-how-indias-cleanest-city-was-hit-by-a-deadly-diarrhoea-outbreak-509150-2026-01-02) |
| 32 deaths, about 1,400 people ill | Check the latest figure before recording | Wikipedia (above); confirm against a recent news report |
| Contaminated supply continued until Feb 6, 2026 | Check exact wording | Wikipedia (above) |
| Judicial panel: the deaths were preventable; pipeline tender delays contributed | Confirmed | [DT Next](https://www.dtnext.in/news/national/indore-water-linked-deaths-preventable-pipeline-tender-delays-contributed-to-tragedy-judicial-panel) |
| India's disease surveillance reacts once patients reach health facilities | Background | [IDSP reporting delays (CEGH)](https://www.ceghonline.com/article/S2213-3984(22)00072-0/fulltext) |

## Timeline for the replay

Used by `scripts/replay.py` (see `docs/replay.md`). Approximate dates are marked `~`. Day 0 is the first illness.

| Day | Date | Event | Source |
|---|---|---|---|
| ~−12 | ~15 Dec 2025 | Residents notice foul, discoloured water ("mid-December", approximate) | [Wikipedia: 2025 Indore drinking water contamination](https://en.wikipedia.org/wiki/2025_Indore_drinking_water_contamination) |
| −2 | 25 Dec 2025 | Many households report a bitter taste and strong odour | [Wikipedia: 2025 Indore drinking water contamination](https://en.wikipedia.org/wiki/2025_Indore_drinking_water_contamination) |
| 0 | 27 Dec 2025 | Residents fall ill with vomiting and diarrhoea | [Wikipedia: 2025 Indore drinking water contamination](https://en.wikipedia.org/wiki/2025_Indore_drinking_water_contamination) |
| 2 | 29 Dec 2025 | The mayor confirms at least three deaths | [Wikipedia: 2025 Indore drinking water contamination](https://en.wikipedia.org/wiki/2025_Indore_drinking_water_contamination) |
| | Feb 6, 2026 | Contaminated supply stopped (check exact wording before using) | [Wikipedia: 2025 Indore drinking water contamination](https://en.wikipedia.org/wiki/2025_Indore_drinking_water_contamination) |
| | 1 Oct 2026 | Judicial commission: the contamination "could have been prevented" | [DT Next](https://www.dtnext.in/news/national/indore-water-linked-deaths-preventable-pipeline-tender-delays-contributed-to-tragedy-judicial-panel) |

Not used: when hospitalisations peaked (no dated source yet).
