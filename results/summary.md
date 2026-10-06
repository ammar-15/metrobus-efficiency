# Metrobus trunk-and-feeder plan

Generated from the Metrobus GTFS schedule for **2026-10-06** (busiest weekday in the feed).
Today: 22 routes, 943 weekday trips, 916 stops
(grouped into 709 places after merging paired stops across the street).

## Today vs proposed

|  | Today | Proposed | Change |
|---|---|---|---|
| Peak buses in service | 48 | 100 | +52 |
| Weekday revenue hours | 578.5 | 1310.5 | +732 |
| Places with frequent service (≈15 min or better) | 4.7% | 28.1% |  |
| Bus activity at frequent places | 21.4% | 50.5% |  |

Proposed: **3 trunk lines** every 10 min and
**32 feeder loops** every 20 min,
running 18 h per weekday. 84.2% of today's places stay served
by a trunk stop within 400 m or a feeder loop.

## Hubs

1. Village Shopping Centre (521 buses/weekday today)
2. Avalon Mall (479 buses/weekday today)
3. MUN Centre (462 buses/weekday today)
4. Ridge Rd before Gloucester St (246 buses/weekday today)
5. Military Rd at St Thomas Church (193 buses/weekday today)
6. Cornwall Ave after Craigmillar Ave (162 buses/weekday today)
7. Empire Ave opp Kellys Brook Apts (197 buses/weekday today)
8. Torbay Rd at Newfoundland Dr (84 buses/weekday today)
9. Elizabeth Ave before New Cove Rd (95 buses/weekday today)
10. Water St at Convention Centre (163 buses/weekday today)

## Lines

| line | type | from_to | hubs | follows_route | stops | km | run_min | headway_min | buses | weekday_hours |
|---|---|---|---|---|---|---|---|---|---|---|
| T1 | trunk | Military Rd at St Thomas Church → Empire Ave opp Kellys Brook Apts | Military Rd at St Thomas Church, Elizabeth Ave before New Cove Rd, Torbay Rd at Newfoundland Dr, Ridge Rd before Gloucester St, MUN Centre, Avalon Mall, Empire Ave opp Kellys Brook Apts |  | 24 | 13.4 | 39.7 | 10.0 | 9 | 143.0 |
| T2 | trunk | Village Shopping Centre → Empire Ave opp Kellys Brook Apts | Village Shopping Centre, Cornwall Ave after Craigmillar Ave, Water St at Convention Centre, Military Rd at St Thomas Church, Empire Ave opp Kellys Brook Apts |  | 23 | 9.9 | 30.8 | 10.0 | 7 | 110.8 |
| T3 | trunk | Cornwall Ave after Craigmillar Ave → Empire Ave opp Kellys Brook Apts | Cornwall Ave after Craigmillar Ave, Empire Ave opp Kellys Brook Apts |  | 7 | 2.3 | 6.1 | 10.0 | 2 | 22.0 |
| F1 | feeder | Village Shopping Centre → Shoal Bay Rd at Park Ln | Village Shopping Centre | 18 | 48 | 14.8 | 32.0 | 20.0 | 4 | 57.5 |
| F2 | feeder | Village Shopping Centre → Old Placentia Rd after Commonwealth Ave | Village Shopping Centre | 21 | 43 | 11.3 | 31.8 | 20.0 | 4 | 57.2 |
| F3 | feeder | Village Shopping Centre → Clyde Ave before Bruce St | Village Shopping Centre | 22 | 36 | 11.0 | 34.8 | 20.0 | 4 | 62.6 |
| F4 | feeder | Cornwall Ave after Cornwall Cres → Harvey Rd at Longs Hill | Cornwall Ave after Cornwall Cres, Harvey Rd at Longs Hill | 2 | 6 | 2.6 | 7.8 | 20.0 | 1 | 14.1 |
| F5 | feeder | Kings Bridge Rd at Lake Ave → Torbay Road Mall | Kings Bridge Rd at Lake Ave, Torbay Road Mall | 2 | 24 | 5.7 | 19.9 | 20.0 | 3 | 35.8 |
| F6 | feeder | Elizabeth Ave before New Cove Rd → Freshwater Rd before Oxen Pond Rd | Elizabeth Ave before New Cove Rd, Freshwater Rd before Oxen Pond Rd | 2 | 10 | 3.5 | 12.4 | 20.0 | 2 | 22.3 |
| F7 | feeder | Paradise Double Ice Complex → Avalon Mall | Avalon Mall | 30 | 34 | 12.3 | 41.3 | 20.0 | 5 | 74.3 |
| F8 | feeder | Clyde Ave before Bruce St → Village Shopping Centre | Village Shopping Centre | 22 | 31 | 10.3 | 32.8 | 20.0 | 4 | 59.0 |
| F9 | feeder | Village Shopping Centre → Avalon Mall | Village Shopping Centre, Avalon Mall | 19 | 30 | 9.6 | 33.2 | 20.0 | 4 | 59.8 |
| F10 | feeder | Old Placentia Rd after Commonwealth Ave → Village Shopping Centre | Village Shopping Centre | 21 | 29 | 9.3 | 30.3 | 20.0 | 4 | 54.6 |
| F11 | feeder | Stavanger Dr near  Staples → Torbay Road Mall | Torbay Road Mall | 3 | 14 | 4.8 | 20.0 | 20.0 | 3 | 36.0 |
| F12 | feeder | Cornwall Ave after Craigmillar Ave → Village Shopping Centre | Cornwall Ave after Craigmillar Ave, Village Shopping Centre | 3 | 13 | 4.8 | 13.3 | 20.0 | 2 | 24.0 |
| F13 | feeder | Robin Hood Bay Rd near Logy Bay Rd → Elizabeth Ave before New Cove Rd | Elizabeth Ave before New Cove Rd | 9 | 21 | 6.1 | 18.7 | 20.0 | 3 | 33.7 |
| F14 | feeder | Elizabeth Ave before New Cove Rd → Higgins Line before Portugal Cove Rd | Elizabeth Ave before New Cove Rd, Higgins Line before Portugal Cove Rd | 9 | 5 | 1.9 | 5.8 | 20.0 | 1 | 10.4 |
| F15 | feeder | Higgins Line before Portugal Cove Rd → Ridge Rd before Gloucester St | Higgins Line before Portugal Cove Rd, Ridge Rd before Gloucester St | 9 | 4 | 1.6 | 4.0 | 20.0 | 1 | 7.1 |
| F16 | feeder | Ladysmith Dr at Maurice Putt Cres → Thorburn Rd opp Picea Ln | Thorburn Rd opp Picea Ln | 26 | 18 | 7.1 | 18.8 | 20.0 | 3 | 33.8 |
| F17 | feeder | Thorburn Rd opp Picea Ln → MUN Centre | Thorburn Rd opp Picea Ln, MUN Centre | 26 | 6 | 2.4 | 10.9 | 20.0 | 2 | 19.6 |
| F18 | feeder | Great Eastern Ave opp Nonia St → Avalon Mall | Avalon Mall | 16 | 16 | 6.3 | 20.1 | 20.0 | 3 | 36.1 |
| F19 | feeder | Avalon Mall → MUN Centre | Avalon Mall, MUN Centre | 16 | 6 | 3.8 | 15.3 | 20.0 | 2 | 27.6 |
| F20 | feeder | Empire Ave opp Kellys Brook Apts → Topsail Rd at Hazelwood Elem | Empire Ave opp Kellys Brook Apts, Topsail Rd at Hazelwood Elem | 12 | 20 | 5.4 | 19.9 | 20.0 | 3 | 35.9 |
| F21 | feeder | Paradise Double Ice Complex → Avalon Mall | Avalon Mall | 30 | 19 | 11.2 | 27.3 | 20.0 | 4 | 49.1 |
| F22 | feeder | Cuckholds Cove Rd before Maxwell Pl → Military Rd at St Thomas Church | Military Rd at St Thomas Church | 15 | 8 | 2.1 | 7.3 | 20.0 | 1 | 13.2 |
| F23 | feeder | Military Rd at Bannerman Park → Thorburn Rd at Avalon Mall | Military Rd at Bannerman Park, Thorburn Rd at Avalon Mall | 15 | 13 | 5.2 | 21.6 | 20.0 | 3 | 38.9 |
| F24 | feeder | Airport near Arrivals → Newfoundland Dr after Stirling Cres | Newfoundland Dr after Stirling Cres | 14 | 15 | 6.0 | 18.4 | 20.0 | 3 | 33.1 |
| F25 | feeder | Topsail Rd before Road De Luxe → Perlin St before Brookfield Rd | Topsail Rd before Road De Luxe | 6 | 17 | 4.4 | 12.0 | 20.0 | 2 | 21.5 |
| F26 | feeder | Water St after Alexander St → Linegar Ave opp Community Centre | Water St after Alexander St | 11 | 10 | 2.7 | 9.4 | 20.0 | 2 | 17.0 |
| F27 | feeder | Linegar Ave opp Community Centre → Water St at Convention Centre | Water St at Convention Centre | 11 | 6 | 3.0 | 10.0 | 20.0 | 2 | 18.0 |
| F28 | feeder | Stavanger Dr near  Staples → Newfoundland Dr after Stirling Cres | Newfoundland Dr after Stirling Cres | 23 | 8 | 3.1 | 11.7 | 20.0 | 2 | 21.0 |
| F29 | feeder | Signal Hill Rd near Murphys Ln → Military Rd at St Thomas Church | Military Rd at St Thomas Church | 29 | 2 | 1.2 | 5.3 | 20.0 | 1 | 9.5 |
| F30 | feeder | Thorburn Rd opp Picea Ln → Mount Scio Rd opp Easter Seals | Thorburn Rd opp Picea Ln | 29 | 3 | 1.7 | 4.4 | 20.0 | 1 | 7.9 |
| F31 | feeder | Mount Scio Rd opp Easter Seals → Ridge Rd before Gloucester St | Ridge Rd before Gloucester St | 29 | 3 | 2.0 | 6.7 | 20.0 | 1 | 12.0 |
| F32 | feeder | Danny Dr near Marshalls → Village Shopping Centre | Village Shopping Centre | 20 | 5 | 8.0 | 17.8 | 20.0 | 2 | 31.9 |

### Flags
- **T3**: short: could run as an extension of a feeder loop instead
- **F15**: few stops: candidate for on-demand service
- **F18**: few stops: candidate for on-demand service
- **F19**: few stops: candidate for on-demand service
- **F23**: few stops: candidate for on-demand service
- **F27**: few stops: candidate for on-demand service
- **F29**: few stops: candidate for on-demand service
- **F30**: few stops: candidate for on-demand service
- **F31**: few stops: candidate for on-demand service
- **F32**: few stops: candidate for on-demand service

112 places are left without service; see `stops_plan.csv` (status 'walk to nearby stop').

## How to read this

- *Peak buses today* counts trips running at the same moment, a lower bound on today's fleet in service.
- Trunk running times come from today's scheduled times between stops, minus 12 s for every stop
  removed by consolidating to ~400 m spacing. No bus lanes or signal priority are assumed.
- Feeder loops start and end at a hub, so every feeder trip connects to every trunk line at that hub.
- This is a planning sketch from schedule data, not ridership. It shows where frequency could go for a similar
  number of buses; real proposals need boarding counts, street checks and public input.
