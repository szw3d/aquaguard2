import math
from statistics import mean, median, pstdev

METRICS = [
    "tds_ppm_est",
    "turbidity_ntu_approx",
    "water_temp_c",
    "mq135_voltage"
]


def valid_values(values):
    return [
        float(v)
        for v in values
        if isinstance(v, (int, float))
        and math.isfinite(v)
    ]


def calculate_statistics(history):
    result = {}

    for metric in METRICS:
        values = valid_values([
            row.get(metric) for row in history
        ])

        if not values:
            result[metric] = None
            continue

        result[metric] = {
            "mean": round(mean(values), 2),
            "median": round(median(values), 2),
            "min": round(min(values), 2),
            "max": round(max(values), 2),
            "stddev": round(
                pstdev(values) if len(values) > 1 else 0,
                2
            ),
            "count": len(values)
        }

    return result


def pearson_correlation(x_values, y_values):
    pairs = [
        (x, y)
        for x, y in zip(x_values, y_values)
        if isinstance(x, (int, float))
        and isinstance(y, (int, float))
        and math.isfinite(x)
        and math.isfinite(y)
    ]

    if len(pairs) < 5:
        return None

    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]

    mx = mean(xs)
    my = mean(ys)

    numerator = sum(
        (x - mx) * (y - my)
        for x, y in pairs
    )

    denominator = math.sqrt(
        sum((x - mx) ** 2 for x in xs) *
        sum((y - my) ** 2 for y in ys)
    )

    if denominator == 0:
        return None

    return round(numerator / denominator, 3)


def detect_anomalies(history):
    anomalies = []

    for metric in METRICS:
        values = valid_values([
            row.get(metric)
            for row in history[-60:]
        ])

        if len(values) < 8:
            continue

        med = median(values)

        deviations = [
            abs(value - med)
            for value in values
        ]

        mad = median(deviations)

        if mad == 0:
            continue

        current = values[-1]

        robust_z = (
            0.6745 * (current - med) / mad
        )

        if abs(robust_z) >= 3.5:
            anomalies.append({
                "metric": metric,
                "value": round(current, 2),
                "robust_z": round(robust_z, 2),
                "message": (
                    f"Ovanlig förändring upptäckt för {metric}"
                )
            })

    return anomalies


def analyze(history):
    if not history:
        return {
            "stats": {},
            "correlations": {},
            "anomalies": [],
            "warnings": ["Väntar på sensordata"]
        }

    latest = history[-1]

    warnings = [
        "TDS är ett uppskattat värde och kräver kalibrering.",
        "Grumlighet i NTU är ungefärlig och kräver kalibrering.",
        "MQ-135-spänningen är inte en ppm-mätning.",
        "Vattentemperaturen anges manuellt."
    ]

    if latest.get("turbidity_ntu_approx") is None:
        warnings.append(
            "Grumligheten ligger utanför det stödda uppskattningsintervallet."
        )

    if latest.get("tds_ppm_est", 0) > 500:
        warnings.append(
            "Förhöjt uppskattat TDS-värde. Kontrollera med en kalibrerad mätare."
        )

    correlations = {
        "tds_vs_turbidity": pearson_correlation(
            [r.get("tds_ppm_est") for r in history],
            [r.get("turbidity_ntu_approx") for r in history]
        ),
        "tds_vs_temperature": pearson_correlation(
            [r.get("tds_ppm_est") for r in history],
            [r.get("water_temp_c") for r in history]
        ),
        "mq135_vs_temperature": pearson_correlation(
            [r.get("mq135_voltage") for r in history],
            [r.get("water_temp_c") for r in history]
        )
    }

    return {
        "stats": calculate_statistics(history),
        "correlations": correlations,
        "anomalies": detect_anomalies(history),
        "warnings": warnings
    }