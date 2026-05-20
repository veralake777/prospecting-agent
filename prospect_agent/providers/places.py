from __future__ import annotations

import httpx

from prospect_agent.config import PRIORITY_MARKETS
from prospect_agent.config import Settings
from prospect_agent.providers.search import is_direct_business_url, normalize_url


CITY_COORDS = {
    ("Atlanta", "GA"): (33.7490, -84.3880),
    ("Savannah", "GA"): (32.0809, -81.0912),
    ("Augusta", "GA"): (33.4735, -82.0105),
    ("Athens", "GA"): (33.9519, -83.3576),
    ("Marietta", "GA"): (33.9526, -84.5499),
    ("Orlando", "FL"): (28.5383, -81.3792),
    ("Tampa", "FL"): (27.9506, -82.4572),
    ("Miami", "FL"): (25.7617, -80.1918),
    ("Jacksonville", "FL"): (30.3322, -81.6557),
    ("Fort Lauderdale", "FL"): (26.1224, -80.1373),
    ("Houston", "TX"): (29.7604, -95.3698),
    ("Dallas", "TX"): (32.7767, -96.7970),
    ("Austin", "TX"): (30.2672, -97.7431),
    ("San Antonio", "TX"): (29.4241, -98.4936),
    ("Fort Worth", "TX"): (32.7555, -97.3308),
    ("Charlotte", "NC"): (35.2271, -80.8431),
    ("Raleigh", "NC"): (35.7796, -78.6382),
    ("Durham", "NC"): (35.9940, -78.8986),
    ("Greensboro", "NC"): (36.0726, -79.7920),
    ("Wilmington", "NC"): (34.2257, -77.9447),
    ("Charleston", "SC"): (32.7765, -79.9311),
    ("Columbia", "SC"): (34.0007, -81.0348),
    ("Greenville", "SC"): (34.8526, -82.3940),
    ("Myrtle Beach", "SC"): (33.6891, -78.8867),
    ("Spartanburg", "SC"): (34.9496, -81.9320),
    ("Nashville", "TN"): (36.1627, -86.7816),
    ("Memphis", "TN"): (35.1495, -90.0490),
    ("Knoxville", "TN"): (35.9606, -83.9207),
    ("Chattanooga", "TN"): (35.0456, -85.3097),
    ("Franklin", "TN"): (35.9251, -86.8689),
    ("Birmingham", "AL"): (33.5186, -86.8104),
    ("Huntsville", "AL"): (34.7304, -86.5861),
    ("Montgomery", "AL"): (32.3792, -86.3077),
    ("Mobile", "AL"): (30.6954, -88.0399),
    ("Tuscaloosa", "AL"): (33.2098, -87.5692),
    ("Phoenix", "AZ"): (33.4484, -112.0740),
    ("Scottsdale", "AZ"): (33.4942, -111.9261),
    ("Tucson", "AZ"): (32.2226, -110.9747),
    ("Mesa", "AZ"): (33.4152, -111.8315),
    ("Tempe", "AZ"): (33.4255, -111.9400),
    ("Denver", "CO"): (39.7392, -104.9903),
    ("Colorado Springs", "CO"): (38.8339, -104.8214),
    ("Boulder", "CO"): (40.0150, -105.2705),
    ("Aurora", "CO"): (39.7294, -104.8319),
    ("Fort Collins", "CO"): (40.5853, -105.0844),
    ("Los Angeles", "CA"): (34.0522, -118.2437),
    ("San Diego", "CA"): (32.7157, -117.1611),
    ("San Jose", "CA"): (37.3382, -121.8863),
    ("Sacramento", "CA"): (38.5816, -121.4944),
    ("Anaheim", "CA"): (33.8366, -117.9143),
    ("New York", "NY"): (40.7128, -74.0060),
    ("Buffalo", "NY"): (42.8864, -78.8784),
    ("Rochester", "NY"): (43.1566, -77.6088),
    ("Albany", "NY"): (42.6526, -73.7562),
    ("Syracuse", "NY"): (43.0481, -76.1474),
    ("Newark", "NJ"): (40.7357, -74.1724),
    ("Jersey City", "NJ"): (40.7178, -74.0431),
    ("Paterson", "NJ"): (40.9168, -74.1718),
    ("Edison", "NJ"): (40.5187, -74.4121),
    ("Trenton", "NJ"): (40.2206, -74.7597),
    ("Philadelphia", "PA"): (39.9526, -75.1652),
    ("Pittsburgh", "PA"): (40.4406, -79.9959),
    ("Allentown", "PA"): (40.6084, -75.4902),
    ("Harrisburg", "PA"): (40.2732, -76.8867),
    ("Erie", "PA"): (42.1292, -80.0851),
    ("Columbus", "OH"): (39.9612, -82.9988),
    ("Cleveland", "OH"): (41.4993, -81.6944),
    ("Cincinnati", "OH"): (39.1031, -84.5120),
    ("Toledo", "OH"): (41.6528, -83.5379),
    ("Akron", "OH"): (41.0814, -81.5190),
    ("Chicago", "IL"): (41.8781, -87.6298),
    ("Aurora", "IL"): (41.7606, -88.3201),
    ("Naperville", "IL"): (41.7508, -88.1535),
    ("Peoria", "IL"): (40.6936, -89.5890),
    ("Rockford", "IL"): (42.2711, -89.0940),
}

OSM_SELECTORS = {
    "amusement": [(("tourism", "theme_park"),), (("leisure", "trampoline_park"),), (("leisure", "miniature_golf"),), (("leisure", "water_park"),)],
    "arcade": [(("leisure", "amusement_arcade"),), (("amenity", "amusement_arcade"),)],
    "attractions": [(("tourism", "theme_park"),), (("leisure", "trampoline_park"),), (("leisure", "miniature_golf"),), (("leisure", "water_park"),), (("sport", "climbing"),), (("leisure", "golf_course"),)],
    "climbing": [(("sport", "climbing"),), (("leisure", "sports_centre"), ("sport", "climbing"))],
    "family": [(("leisure", "trampoline_park"),), (("leisure", "miniature_golf"),), (("leisure", "water_park"),), (("leisure", "amusement_arcade"),), (("amenity", "amusement_arcade"),), (("tourism", "theme_park"),), (("leisure", "bowling_alley"),), (("leisure", "escape_game"),)],
    "go kart": [(("sport", "karting"),), (("leisure", "track"), ("sport", "karting"))],
    "golf": [(("leisure", "golf_course"),)],
    "golf simulator": [(("sport", "golf"),), (("leisure", "sports_centre"), ("sport", "golf"))],
    "indoor recreation": [(("leisure", "trampoline_park"),), (("sport", "climbing"),), (("leisure", "sports_centre"),), (("leisure", "amusement_arcade"),), (("amenity", "amusement_arcade"),), (("leisure", "bowling_alley"),), (("leisure", "escape_game"),)],
    "laser tag": [(("sport", "laser_tag"),), (("leisure", "laser_tag"),)],
    "mini golf": [(("leisure", "miniature_golf"),)],
    "trampoline": [(("leisure", "trampoline_park"),)],
    "water park": [(("leisure", "water_park"),)],
}


class PlacesProvider:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()
        self._google_text_searches_used = 0
        self._google_details_used = 0

    def search(self, query: str) -> list[dict]:
        provider = self.settings.places_provider.strip().lower()
        if provider in {"", "stub", "manual"}:
            return []
        if provider in {"free", "osm", "openstreetmap"}:
            return self._overpass_search(query) or self._openstreetmap_search(query)
        if provider in {"google", "google_places"} and self.settings.places_api_key:
            return self._google_places_search(query)
        return []

    def _overpass_search(self, query: str) -> list[dict]:
        market = self._market_from_query(query)
        selectors = self._selectors_for_query(query)
        if not market or not selectors:
            return []

        city, state = market
        try:
            timeout = httpx.Timeout(self.settings.discovery_http_timeout_seconds + 4, connect=3.0)
            with httpx.Client(timeout=timeout, headers={"User-Agent": self.settings.user_agent}) as client:
                response = client.post(
                    "https://overpass-api.de/api/interpreter",
                    data={"data": self._overpass_query(city, state, selectors)},
                )
                response.raise_for_status()
        except httpx.HTTPError:
            return []

        try:
            elements = response.json().get("elements", [])
        except ValueError:
            return []
        return self._overpass_candidates(elements, city, state)[:8]

    def _overpass_query(self, city: str, state: str, selectors: list[tuple[tuple[str, str], ...]]) -> str:
        coords = CITY_COORDS.get((city, state))
        clauses = []
        for selector in selectors:
            filters = "".join(f'["{key}"="{value}"]' for key, value in selector)
            if coords:
                lat, lon = coords
                radius = max(10000, int(self.settings.osm_search_radius_meters))
                clauses.append(f"nwr(around:{radius},{lat},{lon}){filters};")
            else:
                clauses.append(f"nwr{filters}(area.searchArea);")

        if coords:
            return "[out:json][timeout:15];\n(\n  " + "\n  ".join(clauses) + "\n);\nout tags center 80;"
        return (
            f'[out:json][timeout:15];\narea["name"="{city}"]["boundary"="administrative"]->.searchArea;\n(\n  '
            + "\n  ".join(clauses)
            + "\n);\nout tags center 80;"
        )

    def _overpass_candidates(self, elements: list[dict], city: str, state: str) -> list[dict]:
        candidates = []
        seen_ids = set()
        for element in elements:
            tags = element.get("tags") or {}
            name = tags.get("name", "")
            if not name:
                continue
            source_id = f"osm:{element.get('type')}:{element.get('id')}"
            if source_id in seen_ids:
                continue
            seen_ids.add(source_id)
            website = normalize_url(tags.get("website") or tags.get("contact:website") or tags.get("url") or "")
            phone = tags.get("phone") or tags.get("contact:phone") or ""
            if website and not is_direct_business_url(website):
                website = ""
            center = element.get("center") or {}
            candidates.append(
                {
                    "name": name,
                    "website_url": website,
                    "source_url": f"https://www.openstreetmap.org/{element.get('type')}/{element.get('id')}",
                    "phone": phone,
                    "address": self._format_osm_address(tags),
                    "city": city,
                    "state": state,
                    "postal_code": tags.get("addr:postcode", ""),
                    "country": tags.get("addr:country", ""),
                    "latitude": element.get("lat") or center.get("lat", ""),
                    "longitude": element.get("lon") or center.get("lon", ""),
                    "source_id": source_id,
                    "category": " ".join(str(tags.get(key, "")) for key in ("leisure", "sport", "tourism", "amenity", "attraction")),
                    "snippet": " ".join(str(tags.get(key, "")) for key in ("description", "operator", "brand")),
                    "source_kind": "place",
                }
            )
        return candidates

    def _openstreetmap_search(self, query: str) -> list[dict]:
        try:
            timeout = httpx.Timeout(self.settings.discovery_http_timeout_seconds, connect=3.0)
            with httpx.Client(timeout=timeout, headers={"User-Agent": self.settings.user_agent}) as client:
                response = client.get(
                    "https://nominatim.openstreetmap.org/search",
                    params={"q": query, "format": "jsonv2", "addressdetails": 1, "extratags": 1, "limit": 10},
                )
                response.raise_for_status()
        except httpx.HTTPError:
            return []

        candidates: list[dict] = []
        for item in response.json():
            address = item.get("address") or {}
            tags = item.get("extratags") or {}
            website = normalize_url(tags.get("website") or tags.get("contact:website") or tags.get("url") or "")
            phone = tags.get("phone") or tags.get("contact:phone") or ""
            if website and not is_direct_business_url(website):
                website = ""
            osm_type = {"N": "node", "W": "way", "R": "relation"}.get(str(item.get("osm_type", "")).upper(), "node")
            osm_id = item.get("osm_id", "")
            candidates.append(
                {
                    "name": item.get("name") or item.get("display_name", "").split(",", 1)[0],
                    "website_url": website,
                    "source_url": f"https://www.openstreetmap.org/{osm_type}/{osm_id}" if osm_id else "",
                    "phone": phone,
                    "address": address.get("road", ""),
                    "city": address.get("city") or address.get("town") or address.get("village") or "",
                    "state": address.get("state", ""),
                    "postal_code": address.get("postcode", ""),
                    "country": address.get("country_code", "").upper(),
                    "latitude": item.get("lat", ""),
                    "longitude": item.get("lon", ""),
                    "source_id": f"osm:{osm_type}:{osm_id}" if osm_id else "",
                    "category": f"{item.get('category', '')} {item.get('type', '')}",
                    "snippet": tags.get("description", ""),
                    "source_kind": "place",
                }
            )
            if len(candidates) >= 5:
                break
        return candidates

    @staticmethod
    def _format_osm_address(tags: dict) -> str:
        return " ".join(
            part
            for part in (
                tags.get("addr:housenumber", ""),
                tags.get("addr:street", ""),
            )
            if part
        )

    @staticmethod
    def _market_from_query(query: str) -> tuple[str, str] | None:
        lowered = f" {query.lower()} "
        for state, cities in PRIORITY_MARKETS.items():
            for city in cities:
                if f" {city.lower()} {state.lower()} " in lowered:
                    return city, state
        return None

    @staticmethod
    def _selectors_for_query(query: str) -> list[tuple[tuple[str, str], ...]]:
        lowered = query.lower()
        for key in ("golf simulator", "mini golf", "water park", "laser tag", "go kart", "indoor recreation"):
            if key in lowered:
                return OSM_SELECTORS[key]
        for key in ("trampoline", "climbing", "arcade", "amusement", "family", "golf", "attractions"):
            if key in lowered:
                return OSM_SELECTORS[key]
        return []

    def _google_places_search(self, query: str) -> list[dict]:
        if self._google_text_searches_used >= max(0, self.settings.google_places_max_text_searches_per_run):
            return []
        self._google_text_searches_used += 1
        market = self._market_from_query(query)
        city, state = market if market else ("", "")
        try:
            timeout = httpx.Timeout(self.settings.discovery_http_timeout_seconds, connect=3.0)
            with httpx.Client(timeout=timeout) as client:
                search_response = client.post(
                    "https://places.googleapis.com/v1/places:searchText",
                    headers={
                        "Content-Type": "application/json",
                        "X-Goog-Api-Key": self.settings.places_api_key,
                        "X-Goog-FieldMask": ",".join(
                            [
                                "places.id",
                                "places.displayName",
                                "places.formattedAddress",
                                "places.location",
                                "places.types",
                                "places.primaryType",
                                "places.googleMapsUri",
                            ]
                        ),
                    },
                    json={
                        "textQuery": query,
                        "pageSize": max(1, min(20, int(self.settings.google_places_text_search_page_size))),
                    },
                )
                search_response.raise_for_status()
                search_data = search_response.json()
                candidates = []
                for result in search_data.get("places", []):
                    place_id = result.get("id", "")
                    detail = self._google_place_details(client, place_id) if place_id else {}
                    candidates.append(self._google_candidate_from_place(result, detail, city, state))
                return candidates
        except httpx.HTTPError:
            return []

    def _google_place_details(self, client: httpx.Client, place_id: str) -> dict:
        if self._google_details_used >= max(0, self.settings.google_places_max_details_per_run):
            return {}
        self._google_details_used += 1
        response = client.get(
            f"https://places.googleapis.com/v1/places/{place_id}",
            headers={
                "X-Goog-Api-Key": self.settings.places_api_key,
                "X-Goog-FieldMask": "id,nationalPhoneNumber,internationalPhoneNumber,websiteUri,googleMapsUri,rating,userRatingCount",
            },
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _google_candidate_from_place(place: dict, detail: dict, city: str, state: str) -> dict:
        location = place.get("location") or {}
        display_name = place.get("displayName") or {}
        website = normalize_url(detail.get("websiteUri", ""))
        if website and not is_direct_business_url(website):
            website = ""
        return {
            "name": display_name.get("text", ""),
            "website_url": website,
            "source_url": detail.get("googleMapsUri") or place.get("googleMapsUri", ""),
            "phone": detail.get("nationalPhoneNumber") or detail.get("internationalPhoneNumber") or "",
            "address": place.get("formattedAddress", ""),
            "city": city,
            "state": state,
            "postal_code": "",
            "country": "US" if state else "",
            "latitude": location.get("latitude", ""),
            "longitude": location.get("longitude", ""),
            "google_place_id": place.get("id", ""),
            "google_rating": detail.get("rating", ""),
            "google_review_count": detail.get("userRatingCount", ""),
            "category": " ".join(str(value) for value in [place.get("primaryType", ""), *(place.get("types") or [])] if value),
            "snippet": "",
            "source_kind": "place",
        }

    @staticmethod
    def _google_address_components(components: list[dict]) -> dict:
        out = {}
        for component in components:
            types = set(component.get("types", []))
            if "locality" in types or "postal_town" in types:
                out["city"] = component.get("long_name", "")
            elif "administrative_area_level_1" in types:
                out["state"] = component.get("short_name", "")
            elif "postal_code" in types:
                out["postal_code"] = component.get("long_name", "")
            elif "country" in types:
                out["country"] = component.get("short_name", "")
        return out
