# Data sources: check of the first 10 datasets

Checked 26 Oct 2026 using official web pages, API specs and a few small unauthenticated API calls.
No sign-ups or keys were used. **Confirmed** = seen on an official page or in a live official API
response that day. **Not confirmed** = could not be seen on an official source (reason given).

## Headline risks

1. **State codes differ between sources, even within MoSPI.** CPI uses Census-2011-style codes
   (no Ladakh; Daman and Diu 25 and Dadra and Nagar Haveli 26 separate). PLFS uses alphabetical
   codes (Andhra Pradesh 1, Ladakh 37, DNH&DD 38). ASI uses Census-style codes but Ladakh 38 and
   DNH&DD 88. **Every source is matched to LGD by state name, never by its own code.**
2. **MoSPI's CPI API stops at December 2025.** It offers base years 2012 and 2010 only. The new
   CPI series (base 2024 = 100, from January 2026, launched 12 Feb 2026) is not in the API and
   cannot be spliced onto the old one.
3. **PLFS changed from July–June years to calendar years.** The API has July–June ("Agriculture
   Year") for 2017-18 to 2023-24 and calendar years 2022 to 2025. No July–June 2024-25 exists.
   The two are kept as separate period types and never mixed in one series.
4. **The RBI Handbook 2024-25 has no state population or literacy table** (182 tables checked by title).
5. **TRAI service areas are not states**, and several cover more than one state.
6. **NPCI and RBI block scripts** (NPCI 403; RBI serves a CAPTCHA). Both are manual downloads.
7. **UPI "unclassified" share varies by month.** The often-quoted 27.5% is Dataful's estimate for
   FY2024-25, not an NPCI figure; Business Standard reported 41.7% for June 2025. The app uses the
   share from each month's NPCI file, never a fixed number.

## 1. NPCI: UPI volume and value by state, monthly

- Pages: https://www.npci.org.in/what-we-do/upi/upi-ecosystem-statistics (as linked by Medianama,
  14 Jul 2025); Dataful cites https://www.npci.org.in/product/upi/product-statistics.
- Access: manual browser download (403 to scripts, including robots.txt).
- Format, columns, licence: **not confirmed**. Press coverage shows state, volume, value and share,
  from at least April 2025.
- Unclassified share: Dataful, https://insights.dataful.in/articles/here-is-how-upi-usage-differs-across-indian-states
  (FY2024-25: about 27.5% of volume, about 26% of value). NPCI labels rows unclassified "when
  location data is not received" (Business Standard).
- Gotcha: press shares for the same state differ (Maharashtra June 2025: 8.8% vs 9.47%), probably
  because of the denominator. Store both "share of classified" and "share of total".

## 2–4. RBI Handbook of Statistics on Indian States 2024-25

- Press release, 11 Dec 2025 (No. 2025-2026/1682): https://rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx?prid=61798
- Table list: https://www.rbi.org.in/Scripts/AnnualPublications.aspx?head=Handbook%20of%20Statistics%20on%20Indian%20States
- Access: manual (CAPTCHA). Each table has XLSX and PDF with the same stem:
  `https://rbidocs.rbi.org.in/rdocs/Publications/DOCs/<stem>.XLSX`.

| Need | Table | XLSX stem |
|---|---|---|
| NSDP per capita, current prices | 19 | 19T_11122025B8CC230E4A34431999B4D6A107707BCA |
| NSDP per capita, constant prices | 20 | 20T_111220252B6EE27737FD4931A99C5A448B7CEC68 |
| GSDP, current prices | 21 | 21T_11122025D994949B48C44B68B4465FBB9ADDFF3D |
| GSDP, constant prices | 22 | 22T_11122025E6BC0CB35180406EAB6E0D49DE51C8E8 |
| NSDP current / constant | 23 / 24 | 23T_11122025142A7C614BA04533BA1EE9EC9BCA7DBB / 24T_111220256149723C25EB468BB1DED32D422521FB |
| SCB offices (branches) | 152 | 152T_1112202512B2BF0FBDB74FF48CF835E2A6B7C592 |
| SCB deposits | 155 | 155T_11122025BC88547570414295AB088FBCF5C90806 |
| SCB credit | 156 | 156T_1112202520771561966C49F1B9C00F56ACF97557 |
| Credit-deposit ratio (sanction / utilisation) | 153 / 154 | 153T_111220255DEA2A2D23744132BFEDD5768D038648 / 154T_111220253A00C718ED584E7C850BBCAC3B2FA18B |

- Columns, base year and year range: **not confirmed** (CAPTCHA); read the headers and footnotes
  after download. Stems contain a hash and change each edition, so the manifest records them.
- Gotchas: SCB tables exclude Regional Rural Banks (Tables 160, 161, 163). Credit by place of
  sanction differs from credit by place of use.

## 3. Population and literacy

Not in the 2024-25 Handbook. Replacement sources (see section D and the design doc):
Census 2011 tables (https://censusindia.gov.in) for literacy, and the official population
projections for population.

## 5. MoSPI API: CPI by state

- Swagger: https://api.mospi.gov.in; spec https://api.mospi.gov.in/layout/swagger_user_cpi.yaml;
  manual https://api.mospi.gov.in/API/CPI%20API%20User%20Manual.pdf; codes https://api.mospi.gov.in/API/CPI%20Metadata.xlsx
- Auth: sign up once (`POST /api/users/usersignup`), log in (`POST /api/login` with `email`,
  `password`) for a token, send it in the `Authorization` header. **The manual says the token lasts
  15 minutes**; refresh on 401. Without a token only 10 records are returned.
- Endpoint: `GET /api/cpi/getCPIIndex` with `base_year` (2012 or 2010), `series` (Current or Back),
  `year`, `month_code`, `state_code` (1–36, 99 All India), `group_code`, `subgroup_code`,
  `sector_code` (1 Rural, 2 Urban, 3 Combined), `page`, `Format` (JSON or CSV).
  The manual writes `/api/getCPIIndex`; the live path is `/api/cpi/...`.
- Fields: `baseyear, year, month, state, sector, group, subgroup, index, inflation, status`
  plus `meta_data {page, totalRecords, totalPages, recordPerPage}`. Values are strings; `index` can be null.
- Groups: 1 Food and beverages, 2 Pan/tobacco, 3 Clothing and footwear, 4 Housing, 5 Fuel and light,
  6 Miscellaneous, 7 Consumer Food Price, 8 General. Housing is urban only.
- Coverage: January 2013 to December 2025 (confirmed live). Terms of use: **not confirmed**.

## 6. MoSPI API: PLFS by state

- Spec: https://api.mospi.gov.in/layout/swagger_user_plfs.yaml (manual and metadata files did not load).
- Endpoint: `GET /api/plfs/getData` with `indicator_code`, `frequency_code`, `year` ("YYYY-YY" or
  "YYYY"), `state_code` (1–38, alphabetical), `gender_code`, `age_code`, `sector_code`,
  `weekly_status_code`, `page`, `Format`, and more.
- Indicators: 1 LFPR, 2 WPR, 3 UR (per cent), 4–8 worker distribution and earnings.
- Fields: `year_type, year, frequency, indicator, state, gender, sector, AgeGroup, weekly_status,
  religion, socialGroup, General_Education, quarter, month, value, unit`.
- Coverage: July–June 2017-18 to 2023-24 (omit `frequency_code`, pass `year=2023-24`);
  calendar years 2022–2025. No state-level quarterly or monthly data returned.
- Full state code list and terms: **not confirmed**.

## 7. MoSPI API: ASI by state

- Spec: https://api.mospi.gov.in/layout/swagger_user_asi.yaml
- Endpoint: `GET /api/asi/getASIData` with `classification_year` (NIC 2008), `sector_code`
  (use Combined), `year`, `indicator_code`, `state_code` (88 = DNH&DD, 99 = All India),
  `nic_code` (99999 = all industries), `nic_type`, `page`, `Format`.
- Key indicators: 1 Number of factories, 15 Total output, 19 Gross value added,
  31 Persons engaged, 32 Workers. Money in **₹ lakh**.
- Fields: `nic_classification, year, state, sector, indicator, nic_code, nic_description, nic_type, value, unit`.
- Coverage: 2008-09 to 2023-24. Full state code list and terms: **not confirmed**.

## 8. NFHS via data.gov.in

- NFHS-5 (2019-21) factsheets: resource `7c568619-b9b4-40bb-b563-68c28c27a6c1`,
  https://data.gov.in/resource/all-india-and-stateut-wise-factsheets-national-family-health-survey-nfhs-5-2019-2021
  (file `NFHS_5_Factsheets_Data.xls`; catalogue says an API exists, to be tested with a key).
- NFHS-3 and NFHS-4 key indicators: resource `c66bdb52-ef4e-4f5a-aa06-b2b5a6e09d3a`,
  https://www.data.gov.in/resource/all-india-level-and-state-wise-key-indicators-nfhs-3-and-nfhs-4
  (CSV, **no API**, manual download).
- API pattern: `https://api.data.gov.in/resource/<id>?api-key=<key>&format=json&limit=<n>&offset=<n>`.
- Fields and licence: **not confirmed** (pages return 403 to scripts; API needs a key).
- Gotchas: indicator wording differs between rounds, so mapping is by hand; bracketed values rest
  on 25–49 cases and `*` means suppressed.

## 9. TRAI: telecom subscribers by service area

- Reports: https://www.trai.gov.in/release-publication/reports/telecom-subscriptions-reports
  (latest seen: data as on August 2026, PR 125/2026, 28 Sep 2026). **PDF only.**
- 22 service areas: Andhra Pradesh, Assam, Bihar, Delhi, Gujarat, Haryana, Himachal Pradesh,
  Jammu & Kashmir, Karnataka, Kerala, Kolkata, Madhya Pradesh, Maharashtra, Mumbai, North East,
  Odisha, Punjab, Rajasthan, Tamil Nadu, UP (East), UP (West), West Bengal.
- TRAI's notes: Andhra Pradesh includes Telangana; Madhya Pradesh includes Chhattisgarh; Bihar
  includes Jharkhand; Maharashtra includes Goa; UP includes Uttarakhand; West Bengal includes Sikkim;
  North East = Arunachal Pradesh, Manipur, Meghalaya, Mizoram, Nagaland, Tripura. Placement of the
  small UTs is **not confirmed**.
- Gotchas: wireless counts include M2M SIMs and fixed wireless; LSA-level broadband is probably only
  in the quarterly Performance Indicators Report (**not confirmed**).

## 10. GST collections by state, monthly

- Page: https://www.gst.gov.in/download/gststatistics; files at
  `https://tutorial.gst.gov.in/offlineutilities/gst_statistics/statewise_GST_collection_<FY>.xlsx`
  (2017-18 to 2026-27). **Scriptable with GET** (HEAD returns 404).
- Sheet `Collections-Statewise`: `State CD`, `State`, then per month a block of CGST, SGST, IGST,
  TOTAL in ₹ crore (two-row header, needs unpivoting). Rows include Daman and Diu and Dadra and
  Nagar Haveli separately, Ladakh, "Other Territory" and "OIDAR".
- Gotchas: provisional figures; collection by state of registration, not consumption.
- Licence: **not confirmed**.

## A. LGD state codes

From https://lgdirectory.gov.in/globalviewstateforcitizen.do (36 states and UTs). They match
`src/bharat/reference/states.csv`: Telangana 36, Ladakh 37, Dadra and Nagar Haveli and Daman and
Diu 38; 25 and 26 are the former separate UTs. One manual look at the page is still advised,
because it was read through a summarising fetch.

## B. dbt MetricFlow with DuckDB

Open source under Apache-2.0 from metricflow 0.209.0. `dbt-metricflow` 0.15.0 (10 Sep 2026) has a
`dbt-duckdb` extra and needs dbt-core >=1.11,<1.13. dbt-duckdb 1.11.0 is current. **Confirmed** (PyPI).

## C. LLM providers

- Gemini: OpenAI-compatible base URL `https://generativelanguage.googleapis.com/v1beta/openai/`
  (beta). The pricing page lists free use for models including `gemini-3.8-flash` and
  `gemini-3.5-flash-lite`. Free-tier content may be used to improve Google's products.
- Groq: base URL `https://api.groq.com/openai/v1`. Production models include
  `openai/gpt-oss-120b` and `llama-3.3-70b-versatile`.
- Not confirmed for either: free-tier rate-limit numbers (only shown in your account) and an
  explicit "no card" statement (implied by both billing pages).

## D. Official population projections

- "Population Projections for India and States 2011–2036", Technical Group, National Commission on
  Population (MoHFW). The November 2019 version is confirmed:
  https://nhm.gov.in/New_Updates_2018/Report_Population_Projection_2019.pdf (PDF; annual by state;
  Table 11 = population on 1 July).
- A revised July 2020 version is listed on MoHFW's reports page but the site was unreachable.
  Prefer it if it can be downloaded by hand.
- Gotchas: PDF tables need extraction; J&K shown as a UT (Ladakh treatment not confirmed).
