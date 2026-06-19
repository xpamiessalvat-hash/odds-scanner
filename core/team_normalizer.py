import re


TEAM_ALIASES = {

    # MLB

    "new york yankees": "yankees",
    "ny yankees": "yankees",
    "n.y. yankees": "yankees",

    "boston red sox": "red sox",
    "red sox": "red sox",

    "chicago white sox": "white sox",
    "white sox": "white sox",

    "los angeles dodgers": "dodgers",
    "la dodgers": "dodgers",
    "dodgers": "dodgers",

    "san francisco giants": "giants",
    "sf giants": "giants",
    "giants": "giants",

    "st. louis cardinals": "cardinals",
    "st louis cardinals": "cardinals",
    "cardinals": "cardinals",

    "kansas city royals": "royals",
    "royals": "royals",

    "athletics": "athletics",
    "oakland athletics": "athletics",

}
def normalize_team_name(name):

    name = name.lower()

    name = name.replace(".", "")

    name = re.sub(
        r"\s+",
        " ",
        name
    ).strip()

    if name in TEAM_ALIASES:
        return TEAM_ALIASES[name]

    return name