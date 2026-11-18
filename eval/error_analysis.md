# Error analysis

Every incorrect answer, labelled by where it went wrong.

## Full agent – dev (16 of 73 wrong)

- refuse instead of answer at plan: 8
- refuse instead of answer at coverage: 2
- clarify instead of answer at plan: 2
- error instead of answer at sql: 1
- error instead of answer at plan: 1
- missing caveat: 1
- error instead of refuse at plan: 1

| id | type | expected | got | label | missing caveats |
|---|---|---|---|---|---|
| D006 | single_fact | answer | refuse | refuse instead of answer at plan |  |
| D013 | single_fact | answer | refuse | refuse instead of answer at plan | provisional |
| D024 | change_over_time | answer | refuse | refuse instead of answer at plan | provisional |
| D033 | change_over_time | answer | refuse | refuse instead of answer at coverage | provisional |
| D036 | change_over_time | answer | refuse | refuse instead of answer at plan | provisional |
| D051 | combining_sources | answer | refuse | refuse instead of answer at plan |  |
| D052 | combining_sources | answer | refuse | refuse instead of answer at coverage |  |
| D054 | combining_sources | answer | refuse | refuse instead of answer at plan | provisional |
| D063 | groups | answer | refuse | refuse instead of answer at plan | provisional |
| D065 | groups | answer | clarify | clarify instead of answer at plan | recompute |
| D066 | groups | answer | error | error instead of answer at sql | recompute, projection |
| D067 | groups | answer | error | error instead of answer at plan |  |
| D068 | groups | answer | clarify | clarify instead of answer at plan |  |
| D074 | matching_trap | answer | refuse | refuse instead of answer at plan | dnh_merged |
| D077 | matching_trap | refuse | refuse | missing caveat | service_area |
| D086 | cannot_answer | refuse | error | error instead of refuse at plan |  |

## Agent without metrics layer – dev (40 of 77 wrong)

- missing caveat: 18
- refuse instead of answer at plan: 11
- error instead of answer at sql: 4
- clarify instead of answer at plan: 3
- error instead of answer at plan: 2
- wrong values at answer: 1
- error instead of clarify at plan: 1

| id | type | expected | got | label | missing caveats |
|---|---|---|---|---|---|
| D001 | single_fact | answer | answer | missing caveat | provisional |
| D002 | single_fact | answer | refuse | refuse instead of answer at plan | provisional |
| D008 | single_fact | answer | refuse | refuse instead of answer at plan |  |
| D009 | single_fact | answer | refuse | refuse instead of answer at plan |  |
| D012 | single_fact | answer | refuse | refuse instead of answer at plan |  |
| D013 | single_fact | answer | answer | missing caveat | provisional |
| D014 | ranking | answer | answer | missing caveat | provisional |
| D019 | ranking | answer | error | error instead of answer at plan | projection |
| D024 | change_over_time | answer | answer | missing caveat | provisional |
| D028 | change_over_time | answer | refuse | refuse instead of answer at plan | projection |
| D033 | change_over_time | answer | error | error instead of answer at sql | provisional |
| D035 | change_over_time | answer | refuse | refuse instead of answer at plan |  |
| D036 | change_over_time | answer | answer | wrong values at answer | provisional |
| D039 | scaled_comparison | answer | answer | missing caveat | projection |
| D040 | scaled_comparison | answer | error | error instead of answer at sql | projection |
| D041 | scaled_comparison | answer | answer | missing caveat | provisional, projection |
| D043 | scaled_comparison | answer | error | error instead of answer at plan | projection |
| D044 | scaled_comparison | answer | refuse | refuse instead of answer at plan |  |
| D046 | scaled_comparison | answer | answer | missing caveat | projection |
| D047 | combining_sources | answer | answer | missing caveat | provisional |
| D048 | combining_sources | answer | answer | missing caveat | provisional |
| D050 | combining_sources | answer | answer | missing caveat | projection |
| D051 | combining_sources | answer | error | error instead of answer at sql | service_area, projection |
| D052 | combining_sources | answer | error | error instead of answer at sql | projection |
| D054 | combining_sources | answer | answer | missing caveat | provisional, projection |
| D055 | combining_sources | answer | answer | missing caveat | provisional, projection |
| D056 | combining_sources | answer | answer | missing caveat | projection |
| D057 | trend | answer | answer | missing caveat | provisional |
| D058 | trend | answer | refuse | refuse instead of answer at plan |  |
| D061 | trend | answer | answer | missing caveat | provisional |
| D063 | groups | answer | refuse | refuse instead of answer at plan | provisional |
| D064 | groups | answer | refuse | refuse instead of answer at plan |  |
| D065 | groups | answer | answer | missing caveat | recompute |
| D066 | groups | answer | answer | missing caveat | recompute, projection |
| D067 | groups | answer | clarify | clarify instead of answer at plan |  |
| D068 | groups | answer | clarify | clarify instead of answer at plan |  |
| D069 | matching_trap | answer | clarify | clarify instead of answer at plan |  |
| D070 | matching_trap | answer | refuse | refuse instead of answer at plan | projection |
| D077 | matching_trap | refuse | refuse | missing caveat | service_area |
| D099 | unclear | clarify | error | error instead of clarify at plan |  |

## Plain LLM (no data) – dev (87 of 100 wrong)

- refuse instead of answer: 56
- wrong values: 20
- answer instead of refuse: 9
- missing caveat: 2

| id | type | expected | got | label | missing caveats |
|---|---|---|---|---|---|
| D001 | single_fact | answer | refuse | refuse instead of answer | provisional |
| D002 | single_fact | answer | refuse | refuse instead of answer | provisional |
| D003 | single_fact | answer | answer | wrong values |  |
| D004 | single_fact | answer | refuse | refuse instead of answer |  |
| D005 | single_fact | answer | refuse | refuse instead of answer |  |
| D006 | single_fact | answer | refuse | refuse instead of answer |  |
| D007 | single_fact | answer | answer | wrong values |  |
| D008 | single_fact | answer | answer | wrong values |  |
| D009 | single_fact | answer | answer | wrong values |  |
| D010 | single_fact | answer | refuse | refuse instead of answer | service_area |
| D011 | single_fact | answer | refuse | refuse instead of answer |  |
| D012 | single_fact | answer | answer | wrong values |  |
| D013 | single_fact | answer | refuse | refuse instead of answer | provisional |
| D014 | ranking | answer | refuse | refuse instead of answer | provisional |
| D015 | ranking | answer | answer | wrong values |  |
| D016 | ranking | answer | answer | wrong values |  |
| D017 | ranking | answer | refuse | refuse instead of answer |  |
| D018 | ranking | answer | refuse | refuse instead of answer | service_area |
| D019 | ranking | answer | answer | wrong values |  |
| D020 | ranking | answer | refuse | refuse instead of answer |  |
| D021 | ranking | answer | answer | wrong values |  |
| D022 | ranking | answer | answer | wrong values |  |
| D023 | ranking | answer | answer | wrong values |  |
| D024 | change_over_time | answer | refuse | refuse instead of answer | provisional |
| D025 | change_over_time | answer | refuse | refuse instead of answer |  |
| D026 | change_over_time | answer | refuse | refuse instead of answer |  |
| D027 | change_over_time | answer | refuse | refuse instead of answer |  |
| D028 | change_over_time | answer | answer | wrong values |  |
| D029 | change_over_time | answer | refuse | refuse instead of answer | service_area |
| D030 | change_over_time | answer | answer | wrong values |  |
| D031 | change_over_time | answer | refuse | refuse instead of answer |  |
| D032 | change_over_time | answer | refuse | refuse instead of answer |  |
| D033 | change_over_time | answer | refuse | refuse instead of answer | provisional |
| D034 | change_over_time | answer | refuse | refuse instead of answer |  |
| D035 | change_over_time | answer | answer | wrong values |  |
| D036 | change_over_time | answer | refuse | refuse instead of answer | provisional |
| D037 | scaled_comparison | answer | refuse | refuse instead of answer |  |
| D038 | scaled_comparison | answer | refuse | refuse instead of answer |  |
| D039 | scaled_comparison | answer | refuse | refuse instead of answer | projection |
| D040 | scaled_comparison | answer | refuse | refuse instead of answer | projection |
| D041 | scaled_comparison | answer | refuse | refuse instead of answer | provisional, projection |
| D042 | scaled_comparison | answer | refuse | refuse instead of answer |  |
| D043 | scaled_comparison | answer | refuse | refuse instead of answer |  |
| D044 | scaled_comparison | answer | refuse | refuse instead of answer |  |
| D045 | scaled_comparison | answer | refuse | refuse instead of answer |  |
| D046 | scaled_comparison | answer | refuse | refuse instead of answer | projection |
| D047 | combining_sources | answer | answer | wrong values | provisional |
| D048 | combining_sources | answer | refuse | refuse instead of answer | provisional |
| D049 | combining_sources | answer | refuse | refuse instead of answer |  |
| D050 | combining_sources | answer | refuse | refuse instead of answer | projection |
| D051 | combining_sources | answer | refuse | refuse instead of answer | service_area |
| D052 | combining_sources | answer | refuse | refuse instead of answer | projection |
| D053 | combining_sources | answer | refuse | refuse instead of answer |  |
| D054 | combining_sources | answer | refuse | refuse instead of answer | provisional, projection |
| D055 | combining_sources | answer | refuse | refuse instead of answer | provisional |
| D056 | combining_sources | answer | refuse | refuse instead of answer |  |
| D057 | trend | answer | refuse | refuse instead of answer | provisional |
| D058 | trend | answer | answer | wrong values |  |
| D059 | trend | answer | refuse | refuse instead of answer |  |
| D060 | trend | answer | refuse | refuse instead of answer |  |
| D061 | trend | answer | refuse | refuse instead of answer | provisional |
| D062 | trend | answer | refuse | refuse instead of answer |  |
| D063 | groups | answer | refuse | refuse instead of answer | provisional |
| D064 | groups | answer | answer | wrong values |  |
| D065 | groups | answer | refuse | refuse instead of answer | recompute |
| D066 | groups | answer | refuse | refuse instead of answer | recompute, projection |
| D067 | groups | answer | refuse | refuse instead of answer |  |
| D068 | groups | answer | refuse | refuse instead of answer |  |
| D069 | matching_trap | answer | answer | wrong values |  |
| D070 | matching_trap | answer | answer | wrong values |  |
| D071 | matching_trap | answer | refuse | refuse instead of answer |  |
| D073 | matching_trap | answer | answer | wrong values | ladakh_in_jk |
| D074 | matching_trap | answer | refuse | refuse instead of answer | dnh_merged |
| D075 | matching_trap | answer | refuse | refuse instead of answer |  |
| D076 | matching_trap | refuse | refuse | missing caveat | state_formed |
| D077 | matching_trap | refuse | refuse | missing caveat | service_area |
| D080 | cannot_answer | refuse | answer | answer instead of refuse |  |
| D085 | cannot_answer | refuse | answer | answer instead of refuse |  |
| D089 | cannot_answer | refuse | answer | answer instead of refuse |  |
| D090 | cannot_answer | refuse | answer | answer instead of refuse |  |
| D091 | cannot_answer | refuse | answer | answer instead of refuse |  |
| D092 | causal_trap | answer | refuse | refuse instead of answer | projection |
| D093 | causal_trap | refuse | answer | answer instead of refuse |  |
| D094 | causal_trap | answer | refuse | refuse instead of answer | provisional, projection |
| D095 | causal_trap | refuse | answer | answer instead of refuse |  |
| D096 | causal_trap | refuse | answer | answer instead of refuse |  |
| D097 | causal_trap | refuse | answer | answer instead of refuse | service_area |

