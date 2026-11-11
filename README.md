# AquaGuard 3.0

En lokal instrumentpanel för övervakning av utvalda vattenvärden i akvarier. Python-backenden tar emot mätningar som JSON via serieport, tillgängliggör dem genom API och WebSocket och visar analyser i instrumentpanelen. Den kan även skapa rapporter med en lokal Ollama-modell.

> **Observera:** `arduino/AquaGuard_3_0.ino` är för närvarande tom (0 byte). Lägg till firmware som hanterar sensorerna och skickar data i formatet nedan innan hela systemet används.

## Funktioner

- Instrumentpanel med aktuella mätvärden och en graf över TDS-historiken.
- Kommunikation mellan backend och enheten via USB/serieport.
- REST API, WebSocket-anslutning, statistik, korrelationer och avvikelsedetektering.
- Valfria AI-rapporter som genereras lokalt med Ollama.

## Krav

- Windows 10/11.
- Python 3.10 eller senare.
- Arduino/enhet ansluten via serieport (när firmware har lagts till).
- Valfritt: Ollama och modellen `qwen2.5:3b`.

## Kom igång i Windows

1. Klona repot och gå till projektmappen:

   ```powershell
   git clone <URL_TILL_REPO>
   cd aquaguard2
   ```

2. Skapa och aktivera en virtuell miljö (rekommenderas):

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. Installera beroenden:

   ```powershell
   python -m pip install -r requirements.txt
   ```

4. Anslut enheten och ange rätt serieport och överföringshastighet i `backend/config.py`. Standardinställningarna är `COM4` och `115200` baud.

5. Starta backend från projektets rotmapp:

   ```powershell
   python -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8080
   ```

   Du kan också starta `start.bat`; skriptet installerar beroenden och startar servern.

6. Öppna [http://127.0.0.1:8080](http://127.0.0.1:8080).

Mäthistoriken lagras i processens minne (högst 600 prover) och försvinner när backend startas om.

## Dataformat från enheten

Backend förväntar sig en komplett JSON-rad per mätning, avslutad med en radbrytning. Mätvärden måste vara tal eller `null`, och `type` måste vara `measurement`.

```json
{
  "type": "measurement",
  "device": "aquaguard-1",
  "turbidity_raw": 512,
  "turbidity_voltage": 2.5,
  "turbidity_ntu_approx": 20.0,
  "tds_raw": 420,
  "tds_voltage": 2.05,
  "tds_ppm_est": 180.0,
  "mq135_raw": 350,
  "mq135_voltage": 1.71,
  "water_temp_c": 25.0
}
```

Följande mätfält krävs: `turbidity_raw`, `turbidity_voltage`, `turbidity_ntu_approx`, `tds_raw`, `tds_voltage`, `tds_ppm_est`, `mq135_raw`, `mq135_voltage` och `water_temp_c`. Fältet `device` är valfritt.

## Ollama (valfritt)

Installera och starta Ollama, hämta modellen `qwen2.5:3b` och kontrollera inställningarna `OLLAMA_URL` och `OLLAMA_MODEL` i `backend/config.py`. Instrumentpanelen och övriga API-funktioner kan fortfarande användas utan Ollama, men AI-rapporter kan då inte skapas.

## API

| Slutpunkt | Beskrivning |
| --- | --- |
| `GET /api/status` | Status för serieanslutning och AI samt antal prover |
| `GET /api/latest` | Senaste mätningen |
| `GET /api/history?limit=120` | De senaste mätningarna |
| `GET /api/analysis` | Statistik, korrelationer, avvikelser och varningar |
| `GET /api/ai-status` | Kontrollerar tillgängligheten för Ollama och modellen |
| `POST /api/llm-report` | Skapar en AI-rapport |
| `WS /ws` | Instrumentpanelens livedata, skickas varje sekund |

## Begränsningar och tolkning

- TDS är en uppskattning som kräver kalibrering, och NTU-värdet är ungefärligt.
- MQ-135 ger en rå signal/spänning; det är inte en direkt ppm-mätning.
- Vattentemperaturen anges manuellt.
- Systemet mäter bland annat inte pH, ammoniak, nitrit eller nitrat.
- Använd inte dessa data som enda grund för att bedöma vattnets säkerhet eller djurens välbefinnande. Kontrollera resultaten med kalibrerade mätare och lämpliga tester.

## Projektstruktur

```text
arduino/      enhetens firmware
backend/      FastAPI, konfiguration och mätanalys
dashboard/    webbgränssnitt
requirements.txt
start.bat
```

