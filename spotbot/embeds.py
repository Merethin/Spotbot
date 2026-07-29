from discord_webhook import DiscordEmbed

def generate_predicted_embed(region, native_del, new_del, endos, status, nextupdate):
    description = f"Region: **[{region}](https://www.nationstates.net/region={region})**\n"
    description += f"Status: **{status}**\n"
    description += f"Next Update (Est.): <t:{nextupdate}:R>\n\n"

    if native_del is None:
        description += f"Current delegate: **None**\n"
    else:
        description += f"Current delegate: **[{native_del}](https://www.nationstates.net/nation={native_del})**\n"

    description += f"Incoming delegate: **[{new_del}](https://www.nationstates.net/nation={new_del})** ({endos}e)"

    return DiscordEmbed(title="Delegate Change Incoming", description=description, color="ffa500")

def generate_replaced_embed(region, native_del, new_del, status, lastupdate):
    description = f"Region: **[{region}](https://www.nationstates.net/region={region})**\n"
    description += f"Status: **{status}**\n"
    description += f"Updated: <t:{lastupdate}:R>\n\n"

    if native_del is None:
        description += f"**[{new_del}](https://www.nationstates.net/nation={new_del})** has seized the delegacy"
    else:
        description += f"**[{native_del}](https://www.nationstates.net/nation={native_del})** has been replaced by **[{new_del}](https://www.nationstates.net/nation={new_del})** as delegate"

    return DiscordEmbed(title="Delegate Replaced", description=description, color="ff0000")

def generate_cte_embed(region: str, nextupdate, user_agent):
    name = "%20".join([s.capitalize() for s in region.split("_")])

    description = f"Region: **[{region}](https://www.nationstates.net/region={region})**\n"
    description += f"Next Update (Est.): <t:{nextupdate}:R>\n\n"
    description += f"**[Refound Link](https://www.nationstates.net/page=create_region/template-overall=none?region_name={name}&desc=a&generated_by=Spotbot__by_Merethin__usedBy_{user_agent})**"

    return DiscordEmbed(title="Empty Region", description=description, color="ff0000")