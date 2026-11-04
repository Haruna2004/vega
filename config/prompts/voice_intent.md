A road inspector recorded a voice note at a defect site. Extract structured intent
that changes how urgently the site should be repaired.

- summary: the note in one clean sentence.
- tags: short snake_case tags (e.g. school_crossing, accident_reported, flooding,
  heavy_trucks, market_day, near_hospital, bus_stop, motorcycle_route).
- near_school / near_hospital / near_bus_stop / heavy_traffic: true only if the note says so.
- exposure_multiplier: 1.0 = no change; up to 2.0 when the note reports vulnerable road
  users (children, pedestrians crossing), accidents, or heavy traffic; below 1.0 only if
  the note says the site is rarely used.
- urgency: low | normal | high | immediate.

Style: never use em dashes or en dashes; use commas, colons or full stops.
