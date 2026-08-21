import psycopg2, os, asyncio
from discord_webhook import DiscordWebhook
from spotbot.update import fetch_update_speeds, calculate_next_expected_update
from spotbot.regions import fetch_regions, calculate_expected_delegate
from spotbot.embeds import generate_predicted_embed, generate_replaced_embed, generate_cte_embed
from tenacity import retry, retry_if_exception_type, retry_unless_exception_type, stop_after_delay, wait_exponential
from gql import Client, gql
from gql.transport.websockets import WebsocketsTransport
from gql.transport.exceptions import TransportQueryError

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

@retry(retry=retry_if_exception_type(Exception) & retry_unless_exception_type(TransportQueryError), stop=stop_after_delay(300), wait=wait_exponential())
async def bootstrap_loop(session):
    global regions, minor_speed, major_speed

    print("Starting bootstrap loop subscription")

    async for result in session.subscribe(gql('subscription { bootstrap { after { lastEventId } } }')):
        print(f"Bootstrap: last event ID = {result["bootstrap"]["after"]["lastEventId"]}")
        regions = fetch_regions(conn)
        minor_speed, major_speed = fetch_update_speeds(conn)
        print(f"Minor: {minor_speed} n/sec, major: {major_speed} n/sec")

@retry(retry=retry_if_exception_type(Exception) & retry_unless_exception_type(TransportQueryError), stop=stop_after_delay(300), wait=wait_exponential())
async def region_loop(session):
    global vulnerable_regions, empty_regions

    print("Starting region loop subscription")

    async for result in session.subscribe(gql('subscription { regionChange(regions: []) { after { name delegateName lastupdate residentCount members { name validEndorsementCount } } } }')):
        state = result["regionChange"]["after"]
        if state is None:
            continue

        name = state["name"]
        current_delegate = state["delegateName"]
        expected_delegate, endos = calculate_expected_delegate(current_delegate, state["members"])
        data = regions.get(name)

        # Not in daily dump
        if data is None:
            continue

        status, totalnations = data
        lastupdate = state["lastupdate"]
        nextupdate = calculate_next_expected_update(lastupdate, totalnations, minor_speed, major_speed)
        nation_count = state["residentCount"]

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

async def graphql_connection():
    transport = WebsocketsTransport(url=f"ws://{retina_url}/sub")
    client = Client(transport=transport)

    session = await client.connect_async(reconnecting=True)

    bootstrap_task = asyncio.create_task(bootstrap_loop(session))
    region_task = asyncio.create_task(region_loop(session))

    await asyncio.gather(bootstrap_task, region_task)

    session.close_async()

asyncio.run(graphql_connection())