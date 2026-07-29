from zoneinfo import ZoneInfo
from datetime import datetime, time, timezone, timedelta

def fetch_update_speeds(conn) -> tuple[float, float]:
    cursor = conn.cursor()
    cursor.execute("SELECT lastminorupdate, lastmajorupdate FROM regions_dump ORDER BY updateorder ASC LIMIT 1")
    first_region = cursor.fetchone()
    cursor.execute("SELECT lastminorupdate, lastmajorupdate, totalnations, numnations FROM regions_dump ORDER BY updateorder DESC LIMIT 1")
    last_region = cursor.fetchone()
    cursor.close()

    nations = last_region[2] + last_region[3]

    minor_time = last_region[0] - first_region[0]
    major_time = last_region[1] - first_region[1]

    return (nations / minor_time, nations / major_time)

SERVER_TIMEZONE = ZoneInfo("America/Los_Angeles")
MAJOR_BASE = time(21, 0, 0, tzinfo=SERVER_TIMEZONE)
MINOR_BASE = time(9, 0, 0, tzinfo=SERVER_TIMEZONE)

def calculate_next_expected_update(lastupdate, totalnations, minor_speed, major_speed) -> int:
    dateobj = datetime.fromtimestamp(lastupdate, tz=timezone.utc).astimezone(SERVER_TIMEZONE)

    if dateobj.hour < 9:
        dateobj = datetime.combine(dateobj.date(), MINOR_BASE, tzinfo=SERVER_TIMEZONE) + timedelta(seconds=totalnations / minor_speed)
        return int(dateobj.timestamp())
    elif dateobj.hour < 21:
        dateobj = datetime.combine(dateobj.date(), MAJOR_BASE, tzinfo=SERVER_TIMEZONE) + timedelta(seconds=totalnations / major_speed)
        return int(dateobj.timestamp())
    else:
        dateobj = datetime.combine(dateobj.date(), MINOR_BASE, tzinfo=SERVER_TIMEZONE) + timedelta(days=1, seconds=totalnations / minor_speed)
        return int(dateobj.timestamp())