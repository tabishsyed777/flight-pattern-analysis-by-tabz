# Example outputs (synthetic sample data)

Three illustrative flights as the dashboard shows them. Not real aircraft.

## `F-8f69b21a` - Hold-like (unusual vs peers) (score 100/100, data confidence: high)

**Why:**

- Heading swept 1816 degrees (about 5.0 full turns) while inside the 50 km area; typical straight-in or vectored arrivals sweep under ~270 degrees.
- 66% of the track passed within 1.5 km of a spot flown at least 3 min earlier, so the path overlaps itself (looping geometry).
- For about 20 min the aircraft made less than 1.5 km of progress toward the airport over 6-minute windows while flying a winding path. Altitude changed by -198 m during that time.
- 10 distinct turning episodes (>1 deg/s), turning 42% of the time observed in the area.
- After this window the track came within 5 km of the airport at low altitude.
- Context: of 4 comparable flights, only 25% look hold-like (peer median score 3), so this is unusual relative to similar traffic - worth a human look, nothing more.
- This is a pattern worth reviewing, not proof of an emergency or wrongdoing. Holding is a routine procedure (traffic spacing, weather, runway changes, training).

**Data-quality notices:**

- No data-quality issues detected by the automatic checks (this is not a guarantee).

## `F-1c4586b2` - Hold-like (common among peers) (score 100/100, data confidence: high)

**Why:**

- Heading swept 1846 degrees (about 5.1 full turns) while inside the 50 km area; typical straight-in or vectored arrivals sweep under ~270 degrees.
- 67% of the track passed within 1.5 km of a spot flown at least 3 min earlier, so the path overlaps itself (looping geometry).
- For about 21 min the aircraft made less than 1.5 km of progress toward the airport over 6-minute windows while flying a winding path. Altitude changed by -312 m during that time.
- 10 distinct turning episodes (>1 deg/s), turning 42% of the time observed in the area.
- After this window the track came within 5 km of the airport at low altitude.
- Context: 3 comparable flights (entry within +/-180 min and +/-90 deg sector) - 33% also look hold-like, so this looks common for that time and approach sector (e.g. traffic flow or weather), not unusual by itself.
- This is a pattern worth reviewing, not proof of an emergency or wrongdoing. Holding is a routine procedure (traffic spacing, weather, runway changes, training).

**Data-quality notices:**

- No data-quality issues detected by the automatic checks (this is not a guarantee).

## `F-e06547ec` - No hold-like pattern (score 11/100, data confidence: high)

**Why:**

- Heading swept 323 degrees (about 0.9 full turns) while inside the 50 km area; typical straight-in or vectored arrivals sweep under ~270 degrees.
- 7% of the track passed within 1.5 km of a spot flown at least 3 min earlier, so the path overlaps itself (looping geometry).
- After this window the track came within 5 km of the airport at low altitude.
- This is a pattern worth reviewing, not proof of an emergency or wrongdoing. Holding is a routine procedure (traffic spacing, weather, runway changes, training).

**Data-quality notices:**

- No data-quality issues detected by the automatic checks (this is not a guarantee).
