import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import datetime
import random
import asyncio

import discord
from discord import app_commands
from discord.ext import commands


# =========================================================
# 🌐 RENDER HEALTH SERVER (24/7 MŰKÖDÉSHEZ)
# =========================================================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Faction Bot is Running Perfectly!")

    def log_message(self, format, *args):
        pass


def start_web_server():
    port = int(os.environ.get("PORT", 10000))
    try:
        server = HTTPServer(("0.0.0.0", port), HealthHandler)
        server.serve_forever()
    except Exception as e:
        print(f"[WEB SERVER ERROR] {e}")


threading.Thread(target=start_web_server, daemon=True).start()


# =========================================================
# ⚙️ BOT BEÁLLÍTÁSOK & INTENTEK
# =========================================================

intents = discord.Intents.default()
intents.guilds = True
intents.message_content = True
intents.members = True


# Global nyomonkövető szótárak a Duty-hoz
duty_start_times = {}
duty_total_seconds = {}


class FactionBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None
        )

    async def setup_hook(self):
        # Slash parancsok globális szinkronizálása
        await self.tree.sync()


bot = FactionBot()


# =========================================================
# 💬 JOGOSULTSÁG ELLENŐRZŐ SEGÉDFÜGGVÉNY
# =========================================================

def check_permission(ctx: commands.Context) -> bool:
    if not ctx.guild:
        return False
    leader_role = discord.utils.get(ctx.guild.roles, name="Leader")
    is_leader = leader_role is not None and leader_role in ctx.author.roles
    is_admin = ctx.author.guild_permissions.administrator
    is_owner = ctx.author.id == ctx.guild.owner_id
    return is_leader or is_admin or is_owner


# =========================================================
# 🎉 NYEREMÉNYJÁTÉK VIEW
# =========================================================

class GiveawayView(discord.ui.View):
    def __init__(self, prize: str, host: discord.Member):
        super().__init__(timeout=None)
        self.prize = prize
        self.host = host
        self.participants = set()

    @discord.ui.button(
        label="🎉 Jelentkezés (0)",
        style=discord.ButtonStyle.primary,
        custom_id="giveaway_join"
    )
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id

        if user_id in self.participants:
            self.participants.remove(user_id)
            button.label = f"🎉 Jelentkezés ({len(self.participants)})"
            await interaction.response.edit_message(view=self)
            await interaction.followup.send("❌ Visszavontad a jelentkezésedet!", ephemeral=True)
        else:
            self.participants.add(user_id)
            button.label = f"🎉 Jelentkezés ({len(self.participants)})"
            await interaction.response.edit_message(view=self)
            await interaction.followup.send("🎉 **Sikeresen jelentkeztél a nyereményjátékra!**", ephemeral=True)

    @discord.ui.button(
        label="🎲 Sorsolás",
        style=discord.ButtonStyle.green,
        custom_id="giveaway_roll"
    )
    async def roll_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        leader_role = discord.utils.get(guild.roles, name="Leader")
        is_leader = leader_role is not None and leader_role in interaction.user.roles
        is_admin = interaction.user.guild_permissions.administrator
        is_owner = interaction.user.id == guild.owner_id

        if not (is_leader or is_admin or is_owner):
            await interaction.response.send_message("❌ Ezt csak Leader, admin vagy tulajdonos használhatja!", ephemeral=True)
            return

        if not self.participants:
            await interaction.response.send_message("⚠️ Nem jelentkezett senki a nyereményjátékra!", ephemeral=True)
            return

        winner_id = random.choice(list(self.participants))
        winner = guild.get_member(winner_id)

        for child in self.children:
            child.disabled = True

        embed = interaction.message.embeds[0]
        embed.title = "🎉 NYEREMÉNYJÁTÉK VÉGET ÉRT 🎉"
        embed.color = discord.Color.gold()
        winner_mention = winner.mention if winner else f"<@{winner_id}>"
        embed.add_field(name="🏆 Nyertes:", value=winner_mention, inline=False)

        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.channel.send(f"🎊 **GRATULÁLUNK!** {winner_mention} megnyerte a következőt: **{self.prize}**!")


# =========================================================
# ⏱️ DUTY MÉRŐ VIEW
# =========================================================

class DutyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🟢 Duty Be", style=discord.ButtonStyle.green, custom_id="duty_be")
    async def duty_be(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id

        if user_id in duty_start_times:
            await interaction.response.send_message("⚠️ Már szolgálatban vagy!", ephemeral=True)
            return

        duty_start_times[user_id] = datetime.datetime.now()
        await interaction.response.send_message("🟢 **Szolgálatba léptél!** A bot elkezdte mérni az idődet.", ephemeral=True)

        log_channel = discord.utils.get(interaction.guild.text_channels, name="📋-szolgálati-napló")
        if log_channel:
            await log_channel.send(f"🟢 **{interaction.user.mention}** szolgálatba lépett: <t:{int(datetime.datetime.now().timestamp())}:F>")

    @discord.ui.button(label="🔴 Duty Ki", style=discord.ButtonStyle.red, custom_id="duty_ki")
    async def duty_ki(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id

        if user_id not in duty_start_times:
            await interaction.response.send_message("⚠️ Nem vagy szolgálatban!", ephemeral=True)
            return

        start_time = duty_start_times.pop(user_id)
        now = datetime.datetime.now()
        session_seconds = int((now - start_time).total_seconds())
        duty_total_seconds[user_id] = duty_total_seconds.get(user_id, 0) + session_seconds

        hours, remainder = divmod(session_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        time_str = f"{hours} óra {minutes} perc"

        await interaction.response.send_message(f"🔴 **Kiléptél a szolgálatból!**\nA mostani szolgálatod ideje: **{time_str}**", ephemeral=True)

        log_channel = discord.utils.get(interaction.guild.text_channels, name="📋-szolgálati-napló")
        if log_channel:
            embed = discord.Embed(
                title="🔴 Duty Leadás",
                description=f"**Tag:** {interaction.user.mention}\n**Eltöltött idő:** {time_str}\n**Kilépés:** <t:{int(now.timestamp())}:F>",
                color=discord.Color.red()
            )
            await log_channel.send(embed=embed)

    @discord.ui.button(label="📊 Összidő", style=discord.ButtonStyle.blurple, custom_id="duty_osszido")
    async def duty_osszido(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        total_sec = duty_total_seconds.get(user_id, 0)

        if user_id in duty_start_times:
            current_session = int((datetime.datetime.now() - duty_start_times[user_id]).total_seconds())
            total_sec += current_session
            status_text = "🟢 *Jelenleg is szolgálatban vagy.*"
        else:
            status_text = "🔴 *Jelenleg nem vagy szolgálatban.*"

        hours, remainder = divmod(total_sec, 3600)
        minutes, seconds = divmod(remainder, 60)

        embed = discord.Embed(
            title="📊 Szolgálati Idő Statisztika",
            description=(
                f"**Tag:** {interaction.user.mention}\n\n"
                f"**Összesített szolgálati időd:**\n"
                f"⏱️ **{hours} óra {minutes} perc {seconds} másodperc**\n\n"
                f"{status_text}"
            ),
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


# =========================================================
# 🔘 FRAKCIÓJELENTKEZÉS ELFOGADÁSA
# =========================================================

class AcceptButton(discord.ui.Button):
    def __init__(self, member_id, waiting_channel_id):
        super().__init__(
            label="✅ Elfogadás (Szerver megnyitása)",
            style=discord.ButtonStyle.green,
            custom_id=f"accept_member:{member_id}:{waiting_channel_id}"
        )
        self.member_id = member_id
        self.waiting_channel_id = waiting_channel_id

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("❌ Ez a gomb csak szerveren használható.", ephemeral=True)
            return

        leader_role = discord.utils.get(guild.roles, name="Leader")
        is_leader = leader_role is not None and leader_role in interaction.user.roles
        is_admin = interaction.user.guild_permissions.administrator
        is_owner = interaction.user.id == guild.owner_id

        if not (is_leader or is_admin or is_owner):
            await interaction.response.send_message("❌ Ezt csak Leader, admin vagy tulajdonos használhatja!", ephemeral=True)
            return

        member = guild.get_member(self.member_id)
        if member is None:
            try:
                member = await guild.fetch_member(self.member_id)
            except discord.NotFound:
                await interaction.response.send_message("❌ Ez a játékos már nincs a szerveren.", ephemeral=True)
                return

        role = discord.utils.get(guild.roles, name="Frakciótag")
        if role is None:
            await interaction.response.send_message("❌ Nem találom a **Frakciótag** szerepkört! Hozd létre vagy futtasd a `/setup_frakcio` parancsot.", ephemeral=True)
            return

        if role in member.roles:
            await interaction.response.send_message(f"⚠️ {member.mention} már rendelkezik a **Frakciótag** ranggal.", ephemeral=True)
            return

        await interaction.response.send_message(f"⏳ {member.mention} elfogadása folyamatban...")

        try:
            await member.add_roles(role, reason=f"Frakcióba felvétel - elfogadta: {interaction.user}")
        except Exception as e:
            await interaction.followup.send(f"❌ Hiba a rang kiosztásakor: `{e}`")
            return

        await interaction.followup.send(f"✅ **{member.mention} sikeresen fel lett véve a frakcióba!**")

        belepo_chan = discord.utils.get(guild.text_channels, name="👋-belépő")
        if belepo_chan:
            welcome_embed = discord.Embed(
                title="👋 ÚJ FRAKCIÓTAG ÉRKEZETT!",
                description=f"🎉 Üdvözöljük a frakcióban, **{member.display_name}**!\n\n👤 Tag: {member.mention}\n🎖️ Rang: **{role.name}**",
                color=discord.Color.green()
            )
            await belepo_chan.send(content=f"👋 **Üdvözöljük {member.mention}!**", embed=welcome_embed)

        try:
            await member.send("🎉 **Sikeres felvétel!** A Vezetőség elfogadta a jelentkezésedet.")
        except Exception:
            pass

        waiting_channel = guild.get_channel(self.waiting_channel_id)
        if waiting_channel:
            try:
                await waiting_channel.delete()
            except Exception:
                pass


class AcceptView(discord.ui.View):
    def __init__(self, member_id, waiting_channel_id):
        super().__init__(timeout=None)
        self.add_item(AcceptButton(member_id, waiting_channel_id))


# =========================================================
# 👤 AUTOMATIKUS JELENTKEZÉSI SZOBA BELÉPÉSKOR
# =========================================================

@bot.event
async def on_member_join(member: discord.Member):
    guild = member.guild
    waiting_category = discord.utils.get(guild.categories, name="🚪 VÁRÓTERMEK")
    applications_channel = discord.utils.get(guild.text_channels, name="📋-jelentkezések")
    leader_role = discord.utils.get(guild.roles, name="Leader")
    subleader_role = discord.utils.get(guild.roles, name="Subleader")

    if waiting_category is None or applications_channel is None:
        return

    existing_channel = None
    for channel in waiting_category.text_channels:
        if channel.topic == f"FRAKCIOS_JELENTKEZES:{member.id}":
            existing_channel = channel
            break

    if existing_channel:
        waiting_channel = existing_channel
    else:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        }
        if leader_role:
            overwrites[leader_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_messages=True)
        if subleader_role:
            overwrites[subleader_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_messages=True)

        safe_name = "".join(c.lower() if c.isalnum() else "-" for c in member.display_name).strip("-") or "tag"
        channel_name = f"jelentkezés-{safe_name[:30]}-{member.id}"

        try:
            waiting_channel = await guild.create_text_channel(
                name=channel_name[:100],
                category=waiting_category,
                topic=f"FRAKCIOS_JELENTKEZES:{member.id}",
                overwrites=overwrites
            )
        except Exception as e:
            print(f"[ERROR] Csatorna létrehozása sikertelen: {e}")
            return

        await waiting_channel.send(
            f"👋 **Üdv a szerveren, {member.mention}!**\n"
            "Ez a saját privát jelentkezési szobád. Kérlek várj, amíg a vezetőség felveszi veled a kapcsolatot."
        )

    embed = discord.Embed(
        title="📥 ÚJ FRAKCIÓJELENTKEZÉS",
        description=f"👤 **Jelentkező:** {member.mention}\n🆔 **ID:** `{member.id}`\n🔒 **Privát szoba:** {waiting_channel.mention}",
        color=discord.Color.blue()
    )
    try:
        await applications_channel.send(embed=embed, view=AcceptView(member.id, waiting_channel.id))
    except Exception as e:
        print(f"[ERROR] Jelentkezési üzenet küldése sikertelen: {e}")


@bot.event
async def on_ready():
    bot.add_view(DutyView())
    print(f"✅ Bot elindult mint: {bot.user} | Slash (/) és ! parancsok aktívak!")


# =========================================================
# ⚙️ SEGÉDFÜGGVÉNY FRAKCIÓ CSATORNÁK TÖMEGES LÉTREHOZÁSÁHOZ
# =========================================================

async def build_faction_structure(ctx: commands.Context, category_name: str, role_name: str, leader_role_name: str, role_color: discord.Color, channels_list: list):
    if not check_permission(ctx):
        msg = "❌ Ezt a parancsot csak Leader, admin vagy tulajdonos használhatja!"
        if ctx.interaction:
            await ctx.interaction.response.send_message(msg, ephemeral=True)
        else:
            await ctx.send(msg)
        return

    if ctx.interaction:
        await ctx.interaction.response.defer()

    guild = ctx.guild
    role = discord.utils.get(guild.roles, name=role_name) or await guild.create_role(name=role_name, color=role_color)
    leader_role = discord.utils.get(guild.roles, name=leader_role_name) or await guild.create_role(name=leader_role_name, color=discord.Color.gold())

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        role: discord.PermissionOverwrite(view_channel=True),
        leader_role: discord.PermissionOverwrite(view_channel=True)
    }

    category = discord.utils.get(guild.categories, name=category_name) or await guild.create_category(category_name, overwrites=overwrites)

    created_count = 0
    for ch_name, ch_topic in channels_list:
        if discord.utils.get(category.text_channels, name=ch_name) is None:
            await category.create_text_channel(name=ch_name, topic=ch_topic)
            created_count += 1

    msg = f"✅ **{category_name} frakció szerkezete sikeresen kiépítve!**\n📁 Kategória: {category.mention}\n📄 Új csatornák: **{created_count}**"
    if ctx.interaction:
        await ctx.interaction.followup.send(msg)
    else:
        await ctx.send(msg)


# =========================================================
# 🚓 /frakcio_rendor
# =========================================================

@bot.hybrid_command(name="frakcio_rendor", description="Rendőrségi (LSPD/PD) frakció teljes kiépítése")
async def frakcio_rendor(ctx: commands.Context):
    channels = [
        ("📻-rendőr-rádió", "Rendőrségi rádió / IC kommunikáció"),
        ("📜-rádió-szabályzat", "Rádióhasználati szabályzat és kódok"),
        ("📘-rendőrségi-szabályzat", "Általános rendőrségi szabályzat"),
        ("🚔-járőr-információk", "Járőrözési protokollok és zónák"),
        ("🚨-akciók-és-tervek", "Taktikai műveletek és elfogások"),
        ("🚗-járműpark", "Rendőrségi járművek és kulcsok"),
        ("🔫-felszerelés-és-fegyvertár", "Fegyverek, golyóálló mellények, felszerelés"),
        ("📋-napi-feladatok", "Aktuális elfogatóparancsok és feladatok"),
        ("⚖️-bírságok-és-btk", "Büntető törvénykönyv és bírságok"),
        ("📂-nyomozások-és-akták", "Detektív nyomozati ügyek"),
        ("📝-intézkedési-jelentések", "Hivatalos rendőri jelentések"),
        ("📢-vezetőségi-közlemények", "Vezetőségi hírek és utasítások"),
        ("💬-rendőr-ooc", "OOC kötetlen beszélgető")
    ]
    await build_faction_structure(ctx, "🚓 RENDŐRSÉG", "🚓 Rendőr", "🚓 Rendőrség Vezetőség", discord.Color.blue(), channels)


# =========================================================
# 🚑 /frakcio_mentos
# =========================================================

@bot.hybrid_command(name="frakcio_mentos", description="Mentőszolgálati (EMS) frakció teljes kiépítése")
async def frakcio_mentos(ctx: commands.Context):
    channels = [
        ("📻-mentős-rádió", "Mentőszolgálati rádió és hívások"),
        ("📜-rádió-szabályzat", "Rádiózási protokoll"),
        ("📘-mentős-szabályzat", "Általános egészségügyi szabályzat"),
        ("🚑-szolgálati-információk", "Szolgálati beosztások"),
        ("🏥-kórházi-információk", "Kórházi ellátások és árak"),
        ("🚨-riasztások", "Sürgősségi riasztások"),
        ("🩺-orvosi-felszerelés", "Gyógyszerek és orvosi táska"),
        ("🚑-járműpark-és-helikopter", "Mentőautók és helikopterek"),
        ("📋-betegellátási-jegyzék", "Ellátott betegek naplója"),
        ("📝-szolgálati-jelentések", "Hivatalos mentős jelentések"),
        ("📢-vezetőségi-közlemények", "EMS Vezetőségi közlemények"),
        ("💬-mentős-ooc", "OOC beszélgető")
    ]
    await build_faction_structure(ctx, "🚑 MENTŐSZOLGÁLAT", "🚑 Mentős", "🚑 Mentőszolgálat Vezetőség", discord.Color.red(), channels)


# =========================================================
# 🔧 /frakcio_szerelo
# =========================================================

@bot.hybrid_command(name="frakcio_szerelo", description="Szerelő frakció (Műhely/Fix&Drive) teljes kiépítése")
async def frakcio_szerelo(ctx: commands.Context):
    channels = [
        ("📻-szerelő-rádió", "Szerelő rádió és autómentés"),
        ("📜-szerelő-szabályzat", "Műhely működési szabályzata"),
        ("💰-szerelő-árlista", "Szerelési és vontatási árlista"),
        ("🔧-munkalapok", "Folyamatban lévő szerelések"),
        ("🚗-vontatók-és-járművek", "Szerelő járművek és kulcsok"),
        ("🛠️-alkatrészek-és-tuning", "Alkatrész raktár és árak"),
        ("📦-műhely-raktár", "Raktárkészlet nyilvántartás"),
        ("📋-munkajelentések", "Napi szerelési jelentések"),
        ("💵-kassza-és-elszámolás", "Pénzügyi elszámolások"),
        ("📢-vezetőségi-közlemények", "Szerelő vezetőségi hírek"),
        ("💬-szerelő-ooc", "OOC chat")
    ]
    await build_faction_structure(ctx, "🔧 SZERELŐ MŰHELY", "🔧 Szerelő", "🔧 Szerelő Vezetőség", discord.Color.orange(), channels)


# =========================================================
# 🕶️ /frakcio_mafia
# =========================================================

@bot.hybrid_command(name="frakcio_mafia", description="Maffia / Szervezett bűnözési frakció kiépítése")
async def frakcio_mafia(ctx: commands.Context):
    channels = [
        ("📻-titkos-rádió", "Kódolt rádiócsatorna"),
        ("📜-család-szabályzata", "Omertà és a család szabályai"),
        ("⚔️-akciók-és-rablásertek", "Bankrablássok, túszdrámák és tervek"),
        ("🤝-diplomácia-és-szövetségek", "Más maffiákkal és bandákkal való megállapodások"),
        ("📦-fegyver-és-drograktár", "Illegális raktárkészlet"),
        ("🚗-családi-flotta", "Maffia járművek és kulcsok"),
        ("💰-feketepiac-és-pénzmosás", "Pénzügyek és bevételek"),
        ("📋-megbízások-és-vérdíjak", "Célpontok és megbízások"),
        ("📢-don-utasításai", "Vezetőség és a Don közleményei"),
        ("💬-mafia-ooc", "OOC beszélgető")
    ]
    await build_faction_structure(ctx, "🕶️ MAFFIA", "🕶️ Maffia Tag", "🕶️ Maffia Vezetőség", discord.Color.dark_purple(), channels)


# =========================================================
# 🏙️ /frakcio_banda
# =========================================================

@bot.hybrid_command(name="frakcio_banda", description="Utcai Banda (Gang) frakció kiépítése")
async def frakcio_banda(ctx: commands.Context):
    channels = [
        ("📻-utcai-rádió", "Utcai rádiózás és jelzések"),
        ("📜-hood-szabályok", "Terület és hood szabályzat"),
        ("🔫-területharcok-és-akciók", "Turf war-ok és lövöldözések"),
        ("🚗-banda-autók", "Verdák és lowrider-ek"),
        ("📦-banda-széf", "Közös széf és drogok"),
        ("💰-biznisz-és-eladások", "Utcai üzletek"),
        ("📢-og-üzenetek", "OG-k és vezetők hirdetményei"),
        ("💬-gang-ooc", "OOC beszélgető")
    ]
    await build_faction_structure(ctx, "🏙️ UTCAI BANDA", "🏙️ Banda Tag", "🏙️ Banda OG", discord.Color.dark_gold(), channels)


# =========================================================
# 🏛️ /frakcio_kormany
# =========================================================

@bot.hybrid_command(name="frakcio_kormany", description="Kormány / Városháza frakció kiépítése")
async def frakcio_kormany(ctx: commands.Context):
    channels = [
        ("📻-kormány-rádió", "Hivatalos rádiócsatorna"),
        ("📜-alkotmány-és-törvények", "Városi törvények és rendeletek"),
        ("⚖️-bírósági-ügyek", "Tárgyalások és perek"),
        ("🏢-engedélyek-és-egyéni-vállalkozások", "Cégbejegyzések és engedélyek"),
        ("💰-városi-költségvetés", "Kincstár és adók"),
        ("📢-polgármesteri-közlemények", "Hivatalos városi bejelentések"),
        ("💬-kormány-ooc", "OOC chat")
    ]
    await build_faction_structure(ctx, "🏛️ KORMÁNY ÉS BÍRÓSÁG", "🏛️ Kormánytisztviselő", "🏛️ Kormány Vezetőség", discord.Color.gold(), channels)


# =========================================================
# ⚡ /setup_frakcio (Általános Frakció Struktúra + Duty Mérő)
# =========================================================

@bot.hybrid_command(name="setup_frakcio", description="Teljes alapértelmezett frakció szerkezet kiépítése")
async def setup_frakcio(ctx: commands.Context):
    if not check_permission(ctx):
        await ctx.send("❌ Ezt a parancsot csak Leader, admin vagy tulajdonos használhatja!", ephemeral=True)
        return

    if ctx.interaction:
        await ctx.interaction.response.defer()

    guild = ctx.guild

    leader = discord.utils.get(guild.roles, name="Leader") or await guild.create_role(name="Leader", color=discord.Color.red(), permissions=discord.Permissions(administrator=True))
    subleader = discord.utils.get(guild.roles, name="Subleader") or await guild.create_role(name="Subleader", color=discord.Color.orange())
    tag = discord.utils.get(guild.roles, name="Frakciótag") or await guild.create_role(name="Frakciótag", color=discord.Color.blue())

    overwrites_hidden = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        tag: discord.PermissionOverwrite(view_channel=True),
        leader: discord.PermissionOverwrite(view_channel=True),
        subleader: discord.PermissionOverwrite(view_channel=True)
    }

    overwrites_admin = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        leader: discord.PermissionOverwrite(view_channel=True),
        subleader: discord.PermissionOverwrite(view_channel=True)
    }

    # 🚪 VÁRÓTERMEK
    await guild.create_category("🚪 VÁRÓTERMEK", overwrites=overwrites_admin)

    # 📌 INFORMÁCIÓK
    cat_info = await guild.create_category("📌 INFORMÁCIÓK", overwrites=overwrites_hidden)
    for ch in ["👋-belépő", "📢-bejelentések", "📜-szabályzat", "🎖️-rangok-és-fizetések", "📝-minták-és-nyomtatványok", "🚗-járműpark-és-kulcsok", "❓-gyakori-kérdések"]:
        await cat_info.create_text_channel(ch)

    # 💼 IC ÉLET
    cat_ic_elet = await guild.create_category("💼 IC ÉLET", overwrites=overwrites_hidden)
    for ch in ["💬-ic-chat", "📸-ic-fotók-és-kamera", "📝-szabadságkérelmek", "📋-ic-ötletek-és-reformok", "📂-ic-adatok"]:
        await cat_ic_elet.create_text_channel(ch)

    # 💭 OOC ÉLET
    cat_ooc = await guild.create_category("💭 OOC ÉLET", overwrites=overwrites_hidden)
    for ch in ["💭-ooc-chat", "📷-rp-élményképek", "💡-ötletek-és-javaslatok", "😂-mémek-és-offtopic"]:
        await cat_ooc.create_text_channel(ch)

    # 💼 IC MŰKÖDÉS & DUTY
    cat_ic = await guild.create_category("💼 IC MŰKÖDÉS & DUTY", overwrites=overwrites_hidden)
    duty_chan = await cat_ic.create_text_channel("⏰-duty-mérő")
    for ch in ["📋-szolgálati-napló", "📦-frakció-széf-és-raktár", "⚔️-akciók-és-tervek", "🤝-diplomácia", "💰-kassza-és-elszámolás"]:
        await cat_ic.create_text_channel(ch)

    embed_duty = discord.Embed(
        title="⏰ Szolgálati Idő Mérő (Duty)",
        description="🟢 **Duty Be** - Szolgálat megkezdése\n🔴 **Duty Ki** - Szolgálat befejezése\n📊 **Összidő** - Összesített idő lekérése",
        color=discord.Color.blue()
    )
    await duty_chan.send(embed=embed_duty, view=DutyView())

    # 🔒 VEZETŐSÉG
    cat_vez = await guild.create_category("🔒 VEZETŐSÉG", overwrites=overwrites_admin)
    for ch in ["🔒-vezetőségi-chat", "📋-jelentkezések", "⚠️-figyelmeztetések", "🚫-feketelista", "📑-vezetőségi-jegyzetek"]:
        await cat_vez.create_text_channel(ch)

    # 🔊 HANGCSATORNÁK
    cat_voice = await guild.create_category("🔊 HANGCSATORNÁK", overwrites=overwrites_hidden)
    for vch in ["🔊 OOC Beszélgető 1", "🔊 OOC Beszélgető 2", "🔊 Rádió 1 [IC / RP]", "🔊 Rádió 2 [IC / RP]", "🔊 Akció / Taktikai 1", "💤 AFK / Inaktív"]:
        await cat_voice.create_voice_channel(vch)
    await cat_voice.create_voice_channel("🔒 Vezetőségi Tárgyaló", overwrites=overwrites_admin)

    msg = "✅ **A frakció szerkezete és a duty mérő panel sikeresen elkészült!**"
    if ctx.interaction:
        await ctx.interaction.followup.send(msg)
    else:
        await ctx.send(msg)


# =========================================================
# 📢 /bejelentes
# =========================================================

@bot.hybrid_command(name="bejelentes", description="Hivatalos bejelentés kiküldése")
@app_commands.describe(cim="A bejelentés címe", uzenet="A bejelentés szövege")
async def bejelentes(ctx: commands.Context, cim: str, *, uzenet: str):
    if not check_permission(ctx):
        await ctx.send("❌ Ezt csak Leader, admin vagy tulajdonos használhatja!", ephemeral=True)
        return

    chan = discord.utils.get(ctx.guild.text_channels, name="📢-bejelentések")
    if chan:
        embed = discord.Embed(title=f"📢 {cim}", description=uzenet, color=discord.Color.red())
        embed.set_footer(text=f"Kiadta: {ctx.author.display_name}")
        embed.timestamp = datetime.datetime.now()
        await chan.send(content="@everyone", embed=embed)
        await ctx.send("✅ Bejelentés sikeresen kiküldve!", ephemeral=True)
    else:
        await ctx.send("❌ Nem található a `📢-bejelentések` csatorna!", ephemeral=True)


# =========================================================
# ⚠️ /warn
# =========================================================

@bot.hybrid_command(name="warn", description="Figyelmeztetés adása egy tagnak")
@app_commands.describe(tag="A figyelmeztetett tag", indok="A figyelmeztetés indoka")
async def warn(ctx: commands.Context, tag: discord.Member, *, indok: str):
    if not check_permission(ctx):
        await ctx.send("❌ Ezt csak Leader, admin vagy tulajdonos használhatja!", ephemeral=True)
        return

    warn_chan = discord.utils.get(ctx.guild.text_channels, name="⚠️-figyelmeztetések")
    if warn_chan:
        embed = discord.Embed(
            title="⚠️ Frakció Figyelmeztetés (Warn)",
            description=f"**Kapta:** {tag.mention}\n**Adta:** {ctx.author.mention}\n**Indok:** {indok}",
            color=discord.Color.dark_red()
        )
        embed.timestamp = datetime.datetime.now()
        await warn_chan.send(embed=embed)

        try:
            await tag.send(f"⚠️ **Figyelmeztetést kaptál a frakcióban!**\n**Indok:** {indok}\n**Adta:** {ctx.author.name}")
        except Exception:
            pass

        await ctx.send(f"✅ Figyelmeztetés rögzítve: {tag.mention}", ephemeral=True)


# =========================================================
# 🎁 /ajandek
# =========================================================

@bot.hybrid_command(name="ajandek", description="Nyereményjáték indítása")
@app_commands.describe(nyeremeny="Mi a nyeremény?")
async def ajandek(ctx: commands.Context, *, nyeremeny: str):
    if not check_permission(ctx):
        await ctx.send("❌ Ezt a parancsot csak Leader, admin vagy tulajdonos használhatja!", ephemeral=True)
        return

    embed = discord.Embed(
        title="🎁 NYEREMÉNYJÁTÉK! 🎁",
        description=f"**Nyeremény:** {nyeremeny}\n\nKattints a **🎉 Jelentkezés** gombra a részvételhez!",
        color=discord.Color.purple()
    )
    embed.set_footer(text=f"Indította: {ctx.author.display_name}")
    embed.timestamp = datetime.datetime.now()

    view = GiveawayView(prize=nyeremeny, host=ctx.author)
    await ctx.send(embed=embed, view=view)


# =========================================================
# 🧹 /clear
# =========================================================

@bot.hybrid_command(name="clear", description="Üzenetek törlése a csatornából")
@app_commands.describe(mennyiseg="Hány üzenetet töröljön a bot?")
async def clear_messages(ctx: commands.Context, mennyiseg: int = 100):
    if not check_permission(ctx):
        await ctx.send("❌ Nincs jogosultságod az üzenetek törléséhez!", ephemeral=True)
        return

    if ctx.interaction:
        await ctx.interaction.response.defer(ephemeral=True)

    try:
        deleted = await ctx.channel.purge(limit=mennyiseg)
        msg = f"🧹 Sikeresen törölve **{len(deleted)}** üzenet!"
        if ctx.interaction:
            await ctx.interaction.followup.send(msg, ephemeral=True)
        else:
            await ctx.send(msg, delete_after=5)
    except Exception as e:
        msg = f"⚠️ Hiba történt: {e}"
        if ctx.interaction:
            await ctx.interaction.followup.send(msg, ephemeral=True)
        else:
            await ctx.send(msg)


# =========================================================
# 💣 /remove
# =========================================================

@bot.hybrid_command(name="remove", description="MINDEN csatorna törlése a szerverről")
async def remove_all(ctx: commands.Context):
    if ctx.author.id != ctx.guild.owner_id:
        await ctx.send("❌ Ezt kizárólag a **szerver tulajdonosa** használhatja!", ephemeral=True)
        return

    await ctx.send("💣 **A szerver összes csatornájának törlése megkezdődött...**", ephemeral=True)
    for channel in list(ctx.guild.channels):
        try:
            await channel.delete()
        except Exception:
            pass


# =========================================================
# 📢 /everyone
# =========================================================

@bot.hybrid_command(name="everyone", description="Üzenet kiküldése az összes nyitott váróterembe")
@app_commands.describe(uzenet="A kiküldendő üzenet")
async def everyone_cmd(ctx: commands.Context, *, uzenet: str):
    if not check_permission(ctx):
        await ctx.send("❌ Ezt csak Leader, admin vagy tulajdonos használhatja!", ephemeral=True)
        return

    cat_varo = discord.utils.get(ctx.guild.categories, name="🚪 VÁRÓTERMEK")
    if not cat_varo or not cat_varo.text_channels:
        await ctx.send("⚠️ Jelenleg nincsenek nyitott egyéni várótermek!", ephemeral=True)
        return

    sent_count = 0
    for channel in cat_varo.text_channels:
        try:
            await channel.send(f"📢 **Leaderi közlemény ({ctx.author.mention}):**\n{uzenet}")
            sent_count += 1
        except Exception:
            pass

    await ctx.send(f"✅ Az üzenet kiküldve **{sent_count}** váróterembe!", ephemeral=True)


# =========================================================
# 🚀 BOT INDÍTÁSA
# =========================================================

token = os.environ.get("DISCORD_TOKEN")

if not token:
    print("❌ HIBA: A 'DISCORD_TOKEN' környezeti változó nincs beállítva a Renderen!")
    sys.exit(0)

try:
    bot.run(token)
except discord.errors.PrivilegedIntentsRequired:
    print("❌ HIBA: A Discord Portalon be kell kapcsolnod az INTENT-eket (Server Members & Message Content)!")
except Exception as e:
    print(f"[BOT CRASH PREVENTED] {e}")
