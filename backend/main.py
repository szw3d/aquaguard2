
import json
import threading
import time
import asyncio

from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import requests
import serial

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from config import (
    SERIAL_PORT,
    BAUD_RATE,
    OLLAMA_URL,
    OLLAMA_MODEL,
    HISTORY_LIMIT
)

from analytics import analyze


# ============================================================
# AQUAGUARD 3.0 – PROGRAMKONFIGURATION
# ============================================================

app = FastAPI(
    title="AquaGuard 3.0",
    description="Intelligent system för akvarieövervakning",
    version="3.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)


# ============================================================
# GLOBALT TILLSTÅND
# ============================================================

history = deque(maxlen=HISTORY_LIMIT)

lock = threading.Lock()

serial_status = {
    "connected": False,
    "port": SERIAL_PORT,
    "error": None,
    "last_seen": None
}

ai_status = {
    "available": None,
    "model": OLLAMA_MODEL,
    "last_generation": None,
    "last_error": None,
    "generation_time": None
}

DASHBOARD = (
    Path(__file__).resolve().parent.parent
    / "dashboard"
    / "index.html"
)


# ============================================================
# DATANORMALISERING
# ============================================================

def normalize(payload):

    if not isinstance(payload, dict):
        return None

    if payload.get("type") != "measurement":
        return None

    fields = [
        "turbidity_raw",
        "turbidity_voltage",
        "turbidity_ntu_approx",
        "tds_raw",
        "tds_voltage",
        "tds_ppm_est",
        "mq135_raw",
        "mq135_voltage",
        "water_temp_c"
    ]

    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "device": payload.get("device", "unknown")
    }

    for field in fields:

        value = payload.get(field)

        if value is None:
            row[field] = None

        elif isinstance(value, (int, float)) and not isinstance(value, bool):

            row[field] = float(value)

        else:
            return None

    return row


# ============================================================
# SERIEKOMMUNIKATION
# ============================================================

def serial_worker():

    while True:

        try:

            with serial.Serial(
                SERIAL_PORT,
                BAUD_RATE,
                timeout=1
            ) as connection:

                with lock:

                    serial_status["connected"] = True
                    serial_status["error"] = None

                print(f"[SERIEPORT] Ansluten: {SERIAL_PORT}")

                while True:

                    line = connection.readline().decode(
                        "utf-8",
                        errors="ignore"
                    ).strip()

                    if not line:
                        continue

                    try:

                        payload = json.loads(line)

                        measurement = normalize(payload)

                        if measurement:

                            with lock:

                                history.append(measurement)

                                serial_status["last_seen"] = (
                                    measurement["timestamp"]
                                )

                    except (
                        json.JSONDecodeError,
                        TypeError,
                        ValueError
                    ):

                        continue

        except Exception as error:

            with lock:

                serial_status["connected"] = False
                serial_status["error"] = str(error)

            print(f"[SERIEPORTFEL] {error}")

            time.sleep(3)


# ============================================================
# UPPSTART
# ============================================================

@app.on_event("startup")
def startup():

    thread = threading.Thread(
        target=serial_worker,
        daemon=True
    )

    thread.start()

    print("[AQUAGUARD] Systemet har startats")
    print(f"[AQUAGUARD] Serieport: {SERIAL_PORT}")
    print(f"[AQUAGUARD] AI-modell: {OLLAMA_MODEL}")


# ============================================================
# INSTRUMENTPANEL
# ============================================================

@app.get("/")
def dashboard():

    if DASHBOARD.exists():

        return FileResponse(DASHBOARD)

    return {
        "error": "Instrumentpanelens fil kunde inte hittas",
        "expected_path": str(DASHBOARD)
    }


# ============================================================
# API-STATUS
# ============================================================

@app.get("/api/status")
def get_status():

    with lock:

        return {
            "serial": dict(serial_status),
            "ai": dict(ai_status),
            "samples": len(history),
            "model": OLLAMA_MODEL
        }


# ============================================================
# SENASTE MÄTNING
# ============================================================

@app.get("/api/latest")
def get_latest():

    with lock:

        return history[-1] if history else {}


# ============================================================
# MÄTHISTORIK
# ============================================================

@app.get("/api/history")
def get_history(limit: int = 120):

    with lock:

        limit = max(1, min(limit, HISTORY_LIMIT))

        return list(history)[-limit:]


# ============================================================
# ANALYSFUNKTION
# ============================================================

@app.get("/api/analysis")
def get_analysis():

    with lock:

        rows = list(history)

    return analyze(rows)


# ============================================================
# ANSLUTNINGSTEST FÖR OLLAMA
# ============================================================

@app.get("/api/ai-status")
def get_ai_status():

    try:

        response = requests.get(
            OLLAMA_URL.replace("/api/chat", "/api/tags"),
            timeout=(5, 15)
        )

        response.raise_for_status()

        models = response.json().get("models", [])

        available_models = [
            model.get("name")
            for model in models
        ]

        model_available = OLLAMA_MODEL in available_models

        with lock:

            ai_status["available"] = True
            ai_status["last_error"] = None

        return {
            "connected": True,
            "model": OLLAMA_MODEL,
            "model_available": model_available,
            "available_models": available_models
        }

    except Exception as error:

        with lock:

            ai_status["available"] = False
            ai_status["last_error"] = str(error)

        return {
            "connected": False,
            "model": OLLAMA_MODEL,
            "error": str(error)
        }


# ============================================================
# AQUAGUARDS AI-ANALYS
# ============================================================

@app.post("/api/llm-report")
def generate_llm_report():

    # Hämta de senaste mätningarna

    with lock:

        rows = list(history)[-60:]

    if not rows:

        return {
            "report": (
                "Det finns inga mätdata. "
                "Kontrollera Arduino och COM-anslutningen."
            )
        }

    # Kör analysfunktionen

    analysis = analyze(rows)

    # Förbered data för språkmodellen

    prompt_data = {

        "latest_measurement": rows[-1],

        "statistics": analysis.get(
            "stats", {}
        ),

        "correlations": analysis.get(
            "correlations", {}
        ),

        "anomalies": analysis.get(
            "anomalies", []
        ),

        "warnings": analysis.get(
            "warnings", []
        ),

        "measurement_count": len(rows)

    }

    # Systeminstruktioner

    system_prompt = """
    Du är huvudanalytiker för AquaGuard 3.0.
Du skriver en detaljerad teknisk rapport baserad på sensordata.

VIKTIG SPRÅKREGEL:
Skriv hela svaret på svenska. Använd inte polska eller andra språk.
Tekniska parameternamn och enheter får behållas i standardform.

ANALYSREGLER:
- Hitta aldrig på eller lägg till mätvärden.
- Skilj tydligt mellan mätvärden, beräkningar, hypoteser och rekommendationer.
- MQ-135 mäter en rå sensorsignal; spänning eller ADC-värde är inte en ppm-mätning.
- TDS är en uppskattning och kräver kalibrering.
- NTU är ett ungefärligt värde tills sensorn har kalibrerats.
- Vattentemperaturen anges manuellt och mäts inte automatiskt.
- Bedöm inte akvariets säkerhet enbart utifrån tillgängliga sensorer.
- Anta inte fiskart, akvariets storlek eller filtreringstyp om uppgifterna saknas.
- Ange exakt vilken information som saknas.
- Presentera inte universella riktvärden som säkra för alla akvarier.
- Beskriv inte korrelation som bevis för att en parameter orsakar en förändring i en annan.

Skriv en utförlig rapport med följande struktur:

1. SAMMANFATTNING
De viktigaste slutsatserna i 3–5 konkreta punkter.

2. AKTUELLT LÄGE
Beskriv varje tillgänglig parameter: senaste värde, enhet, betydelse och mätbegränsningar.

3. TRENDANALYS
Jämför de senaste uppgifterna med medelvärde, median, minimum, maximum och standardavvikelse.
Beskriv förändringens riktning och om den är stor i förhållande till den normala spridningen.
Dra inga slutsatser om trender om antalet prover är otillräckligt.

4. SAMBAND MELLAN PARAMETRAR
Beskriv tillgängliga korrelationer, vad de kan antyda och vad som inte kan fastställas utifrån dem.

5. AVVIKELSER OCH VARNINGAR
Lista upptäckta avvikelser och varningar. Förklara deras möjliga betydelse och säkerhetsnivå.
Om inga avvikelser har upptäckts i de analyserade uppgifterna ska du säga det.

6. BEGRÄNSNINGAR OCH DATAKVALITET
Ta upp kalibrering, manuellt angiven temperatur, avsaknad av pH-, ammoniak-, nitrit- och nitratmätningar samt MQ-135:s begränsningar.

7. REKOMMENDATIONER
Prioritera åtgärderna. Skilj mellan vad som kan göras direkt och vilka ytterligare mätningar som behövs för att bekräfta hypoteser.

8. SLUTSATS
Sammanfatta vad som är känt, vad som är okänt och vilka data som bör samlas in härnäst.

Undvik vaga råd som ”övervaka vattnet” utan att förklara exakt vad som ska mätas och varför.
Upprepa inte samma information i flera avsnitt.
Var utförlig, men basera allt enbart på de data som har skickats.
"""

    start_time = time.time()

    try:

        # Begäran till Ollama

        response = requests.post(

            OLLAMA_URL,

            json={

                "model": OLLAMA_MODEL,

                "stream": False,

                "messages": [

                    {
                        "role": "system",
                        "content": system_prompt
                    },

                    {
                        "role": "user",
                        "content": json.dumps(
                            prompt_data,
                            ensure_ascii=False,
                            allow_nan=False
                        )
                    }

                ],

                "options": {

                    "temperature": 0.1,

                    "num_predict": 900,

                    "num_ctx": 4096

                }

            },

            timeout=(10, 300)

        )

        response.raise_for_status()

        result = response.json()

        report = result.get(
            "message", {}
        ).get(
            "content", ""
        ).strip()

        generation_time = round(
            time.time() - start_time,
            2
        )

        if not report:

            report = "Ollama-modellen returnerade en tom rapport."

        # Uppdatera AI-status

        with lock:

            ai_status["available"] = True

            ai_status["last_generation"] = (
                datetime.now(timezone.utc).isoformat()
            )

            ai_status["last_error"] = None

            ai_status["generation_time"] = generation_time

        print(
            f"[AI] Rapport skapad på {generation_time} s"
        )

        return {

            "report": report,

            "model": OLLAMA_MODEL,

            "analysis": analysis,

            "generation": {

                "generation_time_seconds": generation_time,

                "total_duration": result.get(
                    "total_duration"
                ),

                "load_duration": result.get(
                    "load_duration"
                ),

                "prompt_eval_duration": result.get(
                    "prompt_eval_duration"
                ),

                "eval_duration": result.get(
                    "eval_duration"
                ),

                "eval_count": result.get(
                    "eval_count"
                )

            }

        }

    except requests.exceptions.ConnectTimeout:

        error_message = (
            "Tidsgränsen för anslutning till Ollama överskreds."
        )

    except requests.exceptions.ReadTimeout:

        error_message = (
            "Ollama överskred tidsgränsen för generering. "
            "Försök igen eller minska antalet token."
        )

    except requests.exceptions.ConnectionError:

        error_message = (
            "Det gick inte att ansluta till Ollama. "
            "Kontrollera tjänsten på 127.0.0.1:11434."
        )

    except requests.exceptions.HTTPError as error:

        error_message = f"HTTP-fel från Ollama: {error}"

    except Exception as error:

        error_message = f"Oväntat AI-fel: {error}"

    generation_time = round(
        time.time() - start_time,
        2
    )

    with lock:

        ai_status["available"] = False
        ai_status["last_error"] = error_message
        ai_status["generation_time"] = generation_time

    print(f"[AI-FEL] {error_message}")

    return {

        "report": error_message,

        "model": OLLAMA_MODEL,

        "analysis": analysis

    }


# ============================================================
# WEBSOCKET – INSTRUMENTPANEL I REALTID
# ============================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):

    await websocket.accept()

    print("[WEBSOCKET] Instrumentpanelen är ansluten")

    try:

        while True:

            with lock:

                rows = list(history)[-120:]

                status = dict(serial_status)

                ai = dict(ai_status)

            current_analysis = analyze(rows)

            await websocket.send_json({

                "latest": rows[-1] if rows else {},

                "history": rows,

                "analysis": current_analysis,

                "status": status,

                "ai": ai

            })

            await asyncio.sleep(1)

    except WebSocketDisconnect:

        print("[WEBSOCKET] Instrumentpanelen har kopplats från")

    except Exception as error:

        print(f"[WEBSOCKET-FEL] {error}")
