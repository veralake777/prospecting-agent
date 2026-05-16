VERTICALS = [
    "attractions","family entertainment centers","amusement parks","trampoline parks","water parks","arcades","laser tag centers","go-kart tracks","climbing gyms","golf courses","golf simulators","mini golf venues","indoor recreation venues"
]
TEMPLATES = [
    "{vertical} near {city} {state}","{vertical} {city} {state}","{vertical} birthday parties {city} {state}","{vertical} book online {city} {state}","{vertical} membership {city} {state}","{vertical} waiver {city} {state}","{vertical} tickets {city} {state}","{vertical} group events {city} {state}"
]

def build_queries(vertical: str, city: str, state: str) -> list[str]:
    return [t.format(vertical=vertical, city=city, state=state) for t in TEMPLATES]
