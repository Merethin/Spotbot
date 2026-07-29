import sseclient, psycopg2, requests, os, json
from discord_webhook import DiscordWebhook
from spotbot.update import fetch_update_speeds, calculate_next_expected_update
from spotbot.regions import fetch_regions, calculate_expected_delegate
from spotbot.embeds import generate_predicted_embed, generate_replaced_embed, generate_cte_embed

def create_sse_feed(url):
    res = requests.get(url, stream=True)
    yield from sseclient.SSEClient(res).events()

db_url = os.getenv("DATABASE_URL")
conn = psycopg2.connect(db_url)
conn.autocommit = True

vulnerable_regions = {}
empty_regions = {}
regions = fetch_regions(conn)
minor_speed, major_speed = fetch_update_speeds(conn)
print(f"Minor: {minor_speed} n/sec, major: {major_speed} n/sec")

retina_url = os.getenv("RETINA_URL")
webhook_url = os.getenv("WEBHOOK_URL")
cte_webhook_url = os.getenv("CTE_WEBHOOK_URL")
user_agent = os.getenv("NS_USER_AGENT")

def mark_vulnerable(name, current_delegate, expected_delegate, endos, status, nextupdate):
    global vulnerable_regions, webhook_url

    webhook = DiscordWebhook(url=webhook_url)
    webhook.add_embed(generate_predicted_embed(name, current_delegate, expected_delegate, endos, status, nextupdate))
    webhook.execute()

    vulnerable_regions[name] = {
        "delegate": current_delegate,
        "webhook": webhook
    }

def mark_empty(name, nextupdate, user_agent):
    global empty_regions, cte_webhook_url

    webhook = DiscordWebhook(url=cte_webhook_url)
    webhook.add_embed(generate_cte_embed(name, nextupdate, user_agent))
    webhook.execute()

    empty_regions[name] = webhook

def update_vulnerable(webhook, name, current_delegate, expected_delegate, endos, status, nextupdate):
    webhook.remove_embeds()
    webhook.add_embed(generate_predicted_embed(name, current_delegate, expected_delegate, endos, status, nextupdate))
    webhook.edit()

def mark_replaced(webhook, name, native_delegate, current_delegate, status, lastupdate):
    global vulnerable_regions

    webhook.remove_embeds()
    webhook.add_embed(generate_replaced_embed(name, native_delegate, current_delegate, status, lastupdate))
    webhook.edit()
    
    del vulnerable_regions[name]

# Main loop
for event in create_sse_feed(f"{retina_url}/sse/world"):
    obj = json.loads(event.data)
    if obj["category"] == "rtboot":
        regions = fetch_regions(conn)
        minor_speed, major_speed = fetch_update_speeds(conn)
        print(f"Minor: {minor_speed} n/sec, major: {major_speed} n/sec")
        continue

    # Process each region in the event
    for name, state in obj["state"].items():
        current_delegate = state["delegate"]
        expected_delegate, endos = calculate_expected_delegate(current_delegate, state["nations"])
        data = regions.get(name)

        # Not in daily dump
        if data is None:
            continue

        status, totalnations = data
        lastupdate = state["last_update"]
        nextupdate = calculate_next_expected_update(lastupdate, totalnations, minor_speed, major_speed)
        nation_count = state["total_nations"]

        print(f"Processing: region={name} ({nation_count}n), native={current_delegate}, incoming={expected_delegate} ({endos}e)")

        if nation_count == 0:
            if name not in empty_regions:
                mark_empty(name, nextupdate, user_agent)
        else:
            if name in empty_regions:
                webhook = empty_regions[name]
                webhook.delete()
                del empty_regions[name]

        # Not a vulnerable region (Executive / Governorless)
        if status is None:
            continue

        if name not in vulnerable_regions:
            if expected_delegate is None or current_delegate == expected_delegate:
                continue

            print(f"Marking {name} as vulnerable")

            mark_vulnerable(name, current_delegate, expected_delegate, endos, status, nextupdate)
        else:
            native_delegate = vulnerable_regions[name]["delegate"]
            webhook = vulnerable_regions[name]["webhook"]

            if native_delegate != current_delegate:
                if current_delegate is not None:
                    print(f"Marking {name} as replaced")

                    mark_replaced(webhook, name, native_delegate, current_delegate, status, lastupdate)
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

            update_vulnerable(webhook, name, current_delegate, expected_delegate, endos, status, nextupdate)