# Data inventory

Full Hagstofa catalogue (1,906 tables): `data/catalog/hagstofa_tables.tsv`
(regenerate with `scripts/crawl_hagstofa_catalog.py`). Fetch any table with
`ubisim.data.hagstofa.fetch(path, selection)`; responses are cached under `data/raw/`.

## Statistics Iceland (PxWeb API)

| Module | Table | Content |
|---|---|---|
| Demography | MAN00101 | Population by sex and age 1841–2026 |
| | MAN09010, MAN09012 | Population projection 2026–2075 |
| | MAN05201, MAN05303 | Fertility, by mother's citizenship |
| | Ibuar > Family (31 tables) | Households and families (child pooling) |
| | Ibuar > Migration (15 tables) | Migration by citizenship |
| Labour | THJ11002 | Employed persons, jobs, hours by industry 1991–2025 |
| | VIN10022 | Register-based employment by industry, age, origin |
| | VIN02001–02005 | Earnings and distribution by occupation, sector, industry |
| | VIN02091/02092/02100 | Labour cost index, hourly labour cost |
| | TEK02001/02003 | Taxable wages by industry and residence |
| | THJ11011 | Labour productivity |
| Income | TEK01001, TEK01006, TEK01007 | Income and distributions by age and sex |
| | THJ09006, THJ09007 | Disposable income, assets and liabilities by percentile |
| | LIF01151 | Poverty threshold, median equivalised disposable income |
| Social | FEL02001, FEL02003, FEL02005 | Old-age and disability pension beneficiaries (to 2022) |
| Public finance | THJ05111 | Main aggregates |
| | THJ05132 | Revenue in detail |
| | THJ05142, THJ05143 | Expenditure by function and by economic type |
| | THJ05161 | Subsidies in detail (agriculture 19.7 bn, 2024) |
| | THJ05165 | Social benefits by function |
| | THJ05181 | Financial assets and liabilities |
| Macro | THJ01102 | GDP and GNI |
| | THJ02103 | Household consumption |
| | THJ07000 | Economic forecast 2025–2031 (baseline) |
| External | UTA06002, UTA06101, UTA06201 | Trade balance, exports and imports by commodity |
| Fisheries | SJA08101, SJA08103, SJA08107, SJA08109 | Operating accounts and profit (resource rent) |
| | SJA09001 | Catch and value by species |
| Agriculture | LAN1101, LAN1105 | Output, results |
| | LAN05001–05008 | Farm accounts by type |
| Firms | FYR08000, FYR08001, FYR08010 | Structural business statistics, financial statements |
| Energy | Umhverfi > Energy (14 tables) | Energy use, to check |

## Other sources (not in PxWeb)

| Need | Source |
|---|---|
| Property values (fasteignamat 2026: 17,300 bn ISK) | HMS |
| Tax parameters (persónuafsláttur 2026: 72,492/month) | Skatturinn |
| Pension-fund assets, contributions, payments | Seðlabanki Íslands |
| TR benefit rules and clawbacks | Tryggingastofnun |
| Electricity use by consumer, smelter contracts | Orkustofnun, Landsvirkjun annual reports |
| Supply-use / input-output tables | Hagstofa (published as files, not PxWeb) — to locate |
| Business demography (births, survival) | Hagstofa / Eurostat — to locate |
| Quota holdings, veiðigjald | Fiskistofa, Skatturinn |
| Foreign wages by occupation (emigration cap) | Eurostat SES, Statistics Norway/Sweden/Denmark |
