def fetch_regions(conn) -> dict[str, str]:
    cursor = conn.cursor()
    cursor.execute("SELECT canon_name, delegateauth, governor, totalnations FROM regions_dump")
    result = cursor.fetchall()
    cursor.close()

    regions = {}
    for row in result:
        if row[2] == "0":
            regions[row[0]] = ("Governorless", row[3])
        elif "X" in row[1]:
            regions[row[0]] = ("Executive Delegate", row[3])
        else:
            regions[row[0]] = (None, row[3])

    return regions

def calculate_expected_delegate(current, nations) -> tuple[str | None, int]:
    endorsements = [(n["name"], n["validEndorsementCount"]) for n in nations]

    if len(endorsements) == 0:
        return (None, 0)
    
    current_delegate_endos = 0
    for name, endos in endorsements:
        if name == current:
            current_delegate_endos = endos

    result = sorted(endorsements, key=lambda e:e[1], reverse=True)[0]
    if result[1] == 0:
        return (None, 0)
    
    if current_delegate_endos == result[1]:
        return (current, current_delegate_endos)
    
    return result