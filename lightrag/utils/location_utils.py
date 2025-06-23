import requests


def get_location_info(place_name: str) -> dict:
    """Look up detailed location info from Nominatim."""
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": place_name,
        "format": "json",
        "addressdetails": 1,
        "limit": 1,
    }

    try:
        response = requests.get(
            url, params=params, headers={"User-Agent": "geo-locator-script"}
        )
        response.raise_for_status()
        data = response.json()
        if not data:
            return {"error": f"Aucune donnée trouvée pour '{place_name}'."}
        location = data[0]
        address = location.get("address", {})
        lieu = (
            address.get("city")
            or address.get("town")
            or address.get("village")
            or address.get("hamlet")
            or address.get("locality")
            or address.get("neighbourhood")
            or place_name
        )
        result = {
            "lieu": lieu,
            "pays": address.get("country"),
            "code_pays": address.get("country_code"),
            "region": address.get("state"),
            "province": address.get("county") or address.get("region"),
            "departement": address.get("municipality") or address.get("district"),
            "commune": address.get("city_district") or address.get("suburb"),
            "latitude": location.get("lat"),
            "longitude": location.get("lon"),
            "osm_type": location.get("type"),
            "importance": location.get("importance"),
        }
        return result
    except requests.RequestException as e:
        return {"error": f"Erreur de requête : {str(e)}"}
