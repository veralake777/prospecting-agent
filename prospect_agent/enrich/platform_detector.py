PLATFORMS = {
    "Roller": ["roller.app"], "FareHarbor": ["fareharbor"], "Peek Pro": ["peek.com"], "Bookeo": ["bookeo"],
    "Xola": ["xola"], "Checkfront": ["checkfront"], "Rock Gym Pro": ["rockgympro", "app.rockgympro.com"],
    "Capitan": ["capitan"], "Aluvii": ["aluvii"], "Party Center Software": ["partycentersoftware"],
    "Smartwaiver": ["smartwaiver"], "WaiverForever": ["waiverforever"], "Club Caddie": ["clubcaddie"], "foreUP": ["foreup"],
    "Lightspeed Golf": ["lightspeed"], "GolfNow": ["golfnow"], "Chronogolf": ["chronogolf"], "Mindbody": ["mindbody"],
    "Club Automation": ["clubautomation"], "EZFacility": ["ezfacility"], "RecDesk": ["recdesk"], "Shopify": ["shopify"],
    "WordPress": ["wp-content"], "Webflow": ["webflow"], "Wix": ["wix"], "Squarespace": ["squarespace"],
}

def detect_platforms(text: str) -> list[dict]:
    s = text.lower()
    out = []
    for name, keys in PLATFORMS.items():
        for k in keys:
            if k.lower() in s:
                out.append({"platform": name, "confidence": 0.9, "evidence": k})
                break
    return out
