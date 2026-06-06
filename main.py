import sseclient, psycopg2, requests, os, json
from discord_webhook import DiscordWebhook, DiscordEmbed

def create_sse_feed(url):
    res = requests.get(url, stream=True)
    yield from sseclient.SSEClient(res).events()

def calculate_expected_delegate(current, nations) -> tuple[str | None, int]:
    members = set([n["name"] for n in nations])
    endorsements = [(n["name"], len(set(n["endorsements"]).intersection(members))) for n in nations]
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
        return (current_delegate, current_delegate_endos)
    return result

def fetch_regions(cursor) -> dict[str, str]:
    cursor.execute("SELECT canon_name, delegateauth, governor FROM regions_dump")
    result = cursor.fetchall()

    regions = {}
    for row in result:
        if row[2] == "0":
            regions[row[0]] = "Governorless"
        elif "X" in row[1]:
            regions[row[0]] = "Executive Delegate"

    return regions

def generate_predicted_embed(region, native_del, new_del, endos, status):
    description = f"Region: **[{region}](https://www.nationstates.net/region={region})**\n"
    description += f"Status: **{status}**\n\n"

    if native_del is None:
        description += f"Current delegate: **None**\n"
    else:
        description += f"Current delegate: **[{native_del}](https://www.nationstates.net/nation={native_del})**\n"

    description += f"Incoming delegate: **[{new_del}](https://www.nationstates.net/nation={new_del})** ({endos}e)"

    return DiscordEmbed(title="Delegate Change Incoming", description=description, color="ffa500")

def generate_replaced_embed(region, native_del, new_del, status):
    description = f"Region: **[{region}](https://www.nationstates.net/region={region})**\n"
    description += f"Status: **{status}**\n\n"

    if native_del is None:
        description += f"**[{new_del}](https://www.nationstates.net/nation={new_del})** has seized the delegacy"
    else:
        description += f"**[{native_del}](https://www.nationstates.net/nation={native_del})** has been replaced by **[{new_del}](https://www.nationstates.net/nation={new_del})** as delegate"

    return DiscordEmbed(title="Delegate Replaced", description=description, color="ff0000")

db_url = os.getenv("DATABASE_URL")
conn = psycopg2.connect(db_url)
cursor = conn.cursor()

vulnerable_regions = {}
regions = fetch_regions(cursor)

retina_url = os.getenv("RETINA_URL")
webhook_url = os.getenv("WEBHOOK_URL")
for event in create_sse_feed(f"{retina_url}/sse/wadmit+wresign+wkick+ncte+wendo+wunendo+move+ndel+rdel+ldel+rtboot/world"):
    obj = json.loads(event.data)
    if obj["category"] == "rtboot":
        regions = fetch_regions(cursor)
        continue
    for name, state in obj["state"].items():
        current_delegate = state["delegate"]
        expected_delegate, endos = calculate_expected_delegate(current_delegate, state["nations"])
        status = regions.get(name)

        print(f"Processing: region={name}, native={current_delegate}, incoming={expected_delegate} ({endos}e)")

        if name not in vulnerable_regions:
            if expected_delegate is None or current_delegate == expected_delegate:
                continue

            if status is None:
                continue

            print(f"Marking {name} as vulnerable")

            webhook = DiscordWebhook(url=webhook_url)
            webhook.add_embed(generate_predicted_embed(name, current_delegate, expected_delegate, endos, status))
            webhook.execute()

            vulnerable_regions[name] = {
                "delegate": current_delegate,
                "webhook": webhook
            }
        else:
            native_delegate = vulnerable_regions[name]["delegate"]
            webhook = vulnerable_regions[name]["webhook"]

            if native_delegate != current_delegate:
                if current_delegate is not None:
                    print(f"Marking {name} as replaced")

                    webhook.remove_embeds()
                    webhook.add_embed(generate_replaced_embed(name, native_delegate, current_delegate, status))
                    webhook.edit()

                    del vulnerable_regions[name]
                    continue
                else:
                    print(f"Marking {name} as delegacy lost")

                    webhook.delete()
                    del vulnerable_regions[name]
                    continue

            if expected_delegate is None or current_delegate == expected_delegate:
                print(f"Marking {name} as no longer vulnerable")
                webhook.delete()
                del vulnerable_regions[name]
                continue

            webhook.remove_embeds()
            webhook.add_embed(generate_predicted_embed(name, current_delegate, expected_delegate, endos, status))
            webhook.edit()