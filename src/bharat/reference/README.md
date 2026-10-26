# State reference list

`states.csv` is the one list every source must join to.

- `state_code`: Local Government Directory (LGD) state code. Codes 1–35 follow the Census 2011
  numbering; 36 Telangana, 37 Ladakh, 38 Dadra and Nagar Haveli and Daman and Diu.
  Checked against https://lgdirectory.gov.in/globalviewstateforcitizen.do on 26 Oct 2026.
  Sources use their own codes (MoSPI alone has three systems), so matching is always by name.
- `kind`: `state` or `ut` today. Jammu and Kashmir was a state until 30 Oct 2019 and a UT from
  31 Oct 2019; it keeps code 1.
- `valid_from` / `valid_to`: inclusive dates the entity existed. Blank means no limit inside our
  data range. Andhra Pradesh figures before 2 Jun 2014 cover the undivided state.
- `aliases`: name variants seen in sources, separated by `|`. Matching ignores case,
  punctuation and `&` vs `and`, so only real spelling differences need listing.
