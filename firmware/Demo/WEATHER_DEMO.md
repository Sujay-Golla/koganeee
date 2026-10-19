# Kogane: real weather

Updated 2026-10-18. The assistant now requests actual weather from
[Open-Meteo](https://open-meteo.com/), replacing the fixed Toronto demonstration.
Its free service needs no API key or account for this personal, non-commercial
demo. Voice recognition and the task list still run locally.

## Try it

Close the old assistant with **Q**, then run:

```powershell
cd C:\Users\sujay\OneDrive\Documents\koganeee\firmware\base-station
.\.venv\Scripts\python.exe -m kogane_base.tools.demo_assistant --device 3
```

1. Say **Kogane** and wait for **Listening**.
2. Say **Show me the weather today**.
3. **Checking…** appears while the laptop fetches the forecast.
4. The card shows Toronto's current temperature and conditions, today's high
   and low, the provider and the conditions' local update time. The laptop speaks
   the current conditions and today's forecast.

The large **Now** value is current modeled temperature; **Today** is the daily
forecast high/low. These are weather-service estimates, not readings from your
aircraft. A fresh request runs whenever you ask; the card does not update itself
continuously. The laptop needs internet access. Failed, incomplete or outdated
responses show **Weather unavailable**; previous numbers and preset values are
not substituted. Try asking again after restoring internet access.

**W** also fetches real weather, with a **Keyboard** label. **F** toggles fullscreen.
`--preview outputs\cards` only renders static layout previews and does not request
weather. The preview's weather card says **Not loaded**.

For another city, add `--city "Ottawa" --country CA`. The country is a two-letter
code; the city is resolved through the provider, rather than just relabeling
Toronto data. For the FC screen, add `--host 10.0.0.47 --lcd-rotation 180
--lcd-mirror-x` with the current ESP32 IP. No firmware flash is needed.

## Data and verification

Only the city/country lookup and resolved coordinates go to Open-Meteo over
HTTPS. Microphone audio and task contents stay on the laptop. Each request has
a six-second timeout; the first request performs both location and forecast
lookups. Forecast results and source timestamps appear in the local
`outputs\assistant_events.jsonl` activity log.

The actual Toronto request succeeded on 2026-10-18. Twenty-one new checks cover
location parameters, local dates, current-data freshness, missing values, wrong
units, connection failures, background loading, clearing previous values on
failure and offline static previews. The 63 existing voice/task/display checks
also pass. Rendered LCD-size cards were visually checked. Physical LCD reception
still needs the next powered session.

Weather data: [Open-Meteo forecast API](https://open-meteo.com/en/docs),
[geocoding API](https://open-meteo.com/en/docs/geocoding-api),
[terms and attribution](https://open-meteo.com/en/terms). The display credits
Open-Meteo; its data is licensed under CC BY 4.0. The free hosted API is for
non-commercial use.
