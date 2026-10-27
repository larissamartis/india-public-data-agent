# Hand checks of gold answers

The design asks for at least 20% of gold answers to be checked by hand against the original source files, not against the warehouse.
That is at least 24 of the 118 questions with a gold answer.
Tick each one here with the date and what was compared.

How to check one: open the source file named in `dim_source` (the RBI Excel table, the GST
workbook for that year, the population PDF page, the TRAI PDF annexure), find the figure, and
do any arithmetic yourself. Mark it **match** if it agrees with `eval/REVIEW.md` within the
question's tolerance, otherwise **differs** with a note; differences are fixed before the
benchmark is frozen.

| id | checked on | compared with | result | note |
|---|---|---|---|---|
| D003 | 2026-10-27 | RBI Table 21 (21T_…XLSX), sheet 2, Maharashtra 2023-24: 40,55,84,723 lakh = 40,55,847.23 crore | match | checked by reading the cell |
| D069 | 2026-10-27 | RBI Table 21, Odisha 2013-14: 2,96,47,538 lakh = 2,96,475.38 crore | match | |
| D073 | 2026-10-27 | RBI Table 21, Jammu & Kashmir* 2016-17: 1,24,84,800 lakh = 1,24,848 crore | match | footnote: includes Ladakh |
| D004 | 2026-10-27 | RBI Table 19, Bihar 2023-24: 62,201 | match | |
| D060 | 2026-10-27 | RBI Table 20, Uttar Pradesh 2020-21: 40,959 (one point of the series) | match | |
| D005 | 2026-10-27 | RBI Table 152, Uttar Pradesh 2025: 19,436 | match | |
| D062 | 2026-10-27 | RBI Table 152, Bihar 2005: 3,646 (one point of the series) | match | |
| T040 | 2026-10-27 | RBI Table 152, Dadra & Nagar Haveli* 2024: 108 | match | footnote: includes Daman and Diu from 2020 |
| D006 | 2026-10-27 | RBI Table 155, Delhi 2025: 20,71,013 | match | |
| D074 | 2026-10-27 | RBI Table 155, Dadra & Nagar Haveli* 2023: 14,188 | match | merged UT |
| D059 | 2026-10-27 | RBI Table 155, Kerala 2015: 3,28,399 (one point of the series) | match | |
| D026 | 2026-10-27 | RBI Table 155, Kerala 2025 8,94,855 minus 2015 3,28,399 = 5,66,456 | match | arithmetic done by hand |
| D007 | 2026-10-27 | RBI Table 156, Karnataka 2024: 12,38,986 | match | |
| D008 | 2026-10-27 | Population PDF p88, Rajasthan 2026: Persons 83,879 thousand | match | |
| D009 | 2026-10-27 | Population PDF p92, Kerala 2030: Females 19,024 thousand | match | |
| D012 | 2026-10-27 | Population PDF p86, India 2025: Persons 14,15,156 thousand | match | |
| D043 | 2026-10-27 | Population PDF p87, Haryana 2026: Male 16,583, Females 14,826; 14,826 / 16,583 x 1000 = 894.05 | match | |
| D070 | 2026-10-27 | Population PDF p97, Puducherry 2020: Persons 1,549 thousand | match | |
| T024 | 2026-10-27 | Population PDF p90 Odisha 2030 (20,989 M, 23,975 F = 1,142.26); p97 Puducherry 2030 (899 M, 1,034 F = 1,150.17); p92 Kerala 2030 (17,606 M, 19,024 F = 1,080.54) | match | Odisha figure is as printed in the report but far from Census 2011 (979) |
| D044 | 2026-10-27 | Population PDF p96 2026: Daman and Diu 555 M, 179 F = 322.52; Dadra and Nagar Haveli 531 M, 327 F = 615.82. 2011 row (249 / 351) confirms column order | match (2 of 3) | Ladakh (3rd) not yet seen in the PDF text; figures as printed but far from Census 2011 |
| D010 | 2026-10-27 | TRAI PR 140/2026 p20 Annexure II, Kerala Sept-26 operators 99,36,960 + 1 + 1,28,70,954 + 91,04,578 + 1,13,71,687 = 4,32,84,180 | match | summed by hand |
| T007 | 2026-10-27 | TRAI Annexure II, Mumbai Aug-26 total 4,07,73,114 | match | |
| T011 | 2026-10-27 | TRAI Annexure II Sept-26 operator sums: Himachal 95,04,254; North East 1,35,64,401; J&K 1,43,61,534 | match | |
| D029 | 2026-10-27 | TRAI Annexure II Delhi: Sept 7,94,40,979 (summed) minus Aug 7,83,65,095 = 10,75,884 | match | |
| T019 | 2026-10-27 | TRAI Annexure II Bihar: Sept 10,96,03,873 (summed) minus Aug 10,92,74,677 = 3,29,196 | match | |
| D018 | 2026-10-27 | TRAI Annexure II Sept-26 sums: Bihar 10,96,03,873; Maharashtra 10,53,98,354; Andhra Pradesh 8,97,51,742; Madhya Pradesh 8,80,51,240 | match (4 of 5) | UP (East) row not in the text seen |

Checked by the project assistant on 2026-10-27, reading the original files directly: RBI cells
from the Excel XML, and PDF text from the cross-check job (`python -m bharat.eval.crosscheck`)
and the earlier page previews. 24 answers fully checked, 2 partly; no differences found.
GST answers (D001, T001) are not yet checked against the GST workbook.
