Stellarium NEO Flutter GUI design implementation

Based on the current public main branch of:
https://github.com/hotaka-0206/stellarium_neo

Replace these files in stellarium_neo_gui/lib/:
- main.dart
- screens/home_screen.dart
- services/api_service.dart

Implemented:
- Dark astronomy-oriented single-screen UI
- Backend connection indicator (existing /api/status)
- Unified target input field
- Live JPL target resolution using /api/target/inspect
- Orbital elements / RA-Dec mode switch
- Orbit reference date/time + JST/UTC selector
- RA/Dec observer location dialog
- RA/Dec start/end date/time selectors
- Fixed 0.5 s interval display
- Estimated point count
- 12-hour range warning
- Final JPL fetch / Stellarium display action area

Not connected yet:
- Orbital-elements execution endpoint (not present in api/server.py yet)
- Final execution buttons. They currently show a message instead of controlling Stellarium.

No new Flutter package is required.
