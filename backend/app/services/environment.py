import requests


def fetch_environment_snapshot(latitude: float, longitude: float):

    response = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": latitude,
            "longitude": longitude,
            "current": ",".join([
                "temperature_2m",
                "relative_humidity_2m",
                "rain",
                "surface_pressure",
                "cloud_cover",
                "wind_speed_10m"
            ])
        },
        timeout=10
    )

    data = response.json()

    current = data.get("current", {})

    return {
        "temperature": current.get("temperature_2m"),
        "humidity": current.get("relative_humidity_2m"),
        "rainfall": current.get("rain"),
        "pressure": current.get("surface_pressure"),
        "cloud_cover": current.get("cloud_cover"),
        "wind_speed": current.get("wind_speed_10m"),
        "weather_source": "open-meteo"
    }