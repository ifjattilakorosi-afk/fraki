import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import discord
from discord import app_commands
from discord.ext import commands
import datetime
import random


# =========================================================
# 🌐 RENDER HEALTH SERVER
# =========================================================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Discord bot is online!")

    def log_message(self, format, *args):
        pass


def start_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()


threading.Thread(target=start_web_server, daemon=True).start()


# =========================================================
# ⚙️ DISCORD BEÁLLÍTÁSOK
# =========================================================

intents = discord.Intents.default()
intents.guilds = True
intents.message_content = True
intents.members = True


# =========================================================
# ⏱️ DUTY NYILVÁNTARTÁS
# =========================================================

duty_start_times = {}
duty_total_seconds = {}


# =========================================================
# 🤖 BOT
# =========================================================

class FactionBot(commands.Bot):

    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents
        )

    async def setup_hook(self):
        await self.tree.sync()


bot = FactionBot()


# =========================================================
# 🎉 NYEREMÉNYJÁTÉK
# =========================================================

class GiveawayView(discord.ui.View):

    def __init__(self, prize: str, host: discord.Member):
        super().__init__(timeout=None)

        self.prize = prize
        self.host = host
        self.participants = set()

    # 🎉 JELENTKEZÉS
    @discord.ui.button(
        label="🎉 Jelentkezés (0)",
        style=discord.ButtonStyle.primary,
        custom_id="giveaway_join"
    )
    async def join_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        user_id = interaction.user.id

        if user_id in self.participants:

            self.participants.remove(user_id)

            button.label = (
                f"🎉 Jelentkezés ({len(self.participants)})"
            )

            await interaction.response.edit_message(
                view=self
            )

            await interaction.followup.send(
                "❌ Visszavontad a jelentkezésedet a nyereményjátékra!",
                ephemeral=True
            )

        else:

            self.participants.add(user_id)

            button.label = (
                f"🎉 Jelentkezés ({len(self.participants)})"
            )

            await interaction.response.edit_message(
                view=self
            )

            await interaction.followup.send(
                "🎉 **Sikeresen jelentkeztél a nyereményjátékra!** "
                "Sok szerencsét!",
                ephemeral=True
            )

    # 🎲 SORSOLÁS
    @discord.ui.button(
        label="🎲 Sorsolás",
        style=discord.ButtonStyle.green,
        custom_id="giveaway_roll"
    )
    async def roll_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        leader_role = discord.utils.get(
            interaction.guild.roles,
            name="Leader"
        )

        is_leader = (
            leader_role is not None
            and leader_role in interaction.user.roles
        )

        is_admin = interaction.user.guild_permissions.administrator
        is_owner = interaction.user.id == interaction.guild.owner_id

        if not (is_leader or is_admin or is_owner):

            await interaction.response.send_message(
                "❌ Ezt a gombot csak a **Leader**, admin vagy "
                "szervertulajdonos használhatja!",
                ephemeral=True
            )

            return

        if not self.participants:

            await interaction.response.send_message(
                "⚠️ Nem jelentkezett senki a nyereményjátékra!",
                ephemeral=True
            )

            return

        winner_id = random.choice(
            list(self.participants)
        )

        winner = interaction.guild.get_member(
            winner_id
        )

        # GOMBOK LETILTÁSA
        for child in self.children:
            child.disabled = True

        embed = interaction.message.embeds[0]

        embed.title = "🎉 NYEREMÉNYJÁTÉK VÉGET ÉRT 🎉"
        embed.color = discord.Color.gold()

        embed.add_field(
            name="🏆 Nyertes:",
            value=(
                winner.mention
                if winner
                else f"<@{winner_id}>"
            ),
            inline=False
        )

        await interaction.response.edit_message(
            embed=embed,
            view=self
        )

        winner_mention = (
            winner.mention
            if winner
            else f"<@{winner_id}>"
        )

        await interaction.channel.send(
            f"🎊 **GRATULÁLUNK!** {winner_mention} "
            f"megnyerte a következőt: **{self.prize}**!"
        )


# =========================================================
# ⏱️ DUTY MÉRŐ
# =========================================================

class DutyView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    # 🟢 DUTY BE
    @discord.ui.button(
        label="🟢 Duty Be",
        style=discord.ButtonStyle.green,
        custom_id="duty_be"
    )
    async def duty_be(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        user_id = interaction.user.id

        if user_id in duty_start_times:

            await interaction.response.send_message(
                "⚠️ Már szolgálatban vagy!",
                ephemeral=True
            )

            return

        duty_start_times[user_id] = datetime.datetime.now()

        await interaction.response.send_message(
            "🟢 **Szolgálatba léptél!** "
            "A bot elkezdte mérni az idődet.",
            ephemeral=True
        )

        log_channel = discord.utils.get(
            interaction.guild.text_channels,
            name="📋-szolgálati-napló"
        )

        if log_channel:

            await log_channel.send(
                f"🟢 **{interaction.user.mention}** "
                f"szolgálatba lépett: "
                f"<t:{int(datetime.datetime.now().timestamp())}:F>"
            )

    # 🔴 DUTY KI
    @discord.ui.button(
        label="🔴 Duty Ki",
        style=discord.ButtonStyle.red,
        custom_id="duty_ki"
    )
    async def duty_ki(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        user_id = interaction.user.id

        if user_id not in duty_start_times:

            await interaction.response.send_message(
                "⚠️ Nem vagy szolgálatban!",
                ephemeral=True
            )

            return

        start_time = duty_start_times.pop(
            user_id
        )

        now = datetime.datetime.now()

        session_seconds = int(
            (now - start_time).total_seconds()
        )

        duty_total_seconds[user_id] = (
            duty_total_seconds.get(user_id, 0)
            + session_seconds
        )

        hours, remainder = divmod(
            session_seconds,
            3600
        )

        minutes, seconds = divmod(
            remainder,
            60
        )

        time_str = (
            f"{hours} óra "
            f"{minutes} perc"
        )

        await interaction.response.send_message(
            f"🔴 **Kiléptél a szolgálatból!**\n"
            f"A mostani szolgálatod ideje: "
            f"**{time_str}**",
            ephemeral=True
        )

        log_channel = discord.utils.get(
            interaction.guild.text_channels,
            name="📋-szolgálati-napló"
        )

        if log_channel:

            embed = discord.Embed(
                title="🔴 Duty Leadás",
                description=(
                    f"**Tag:** {interaction.user.mention}\n"
                    f"**Eltöltött idő:** {time_str}\n"
                    f"**Kilépés:** "
                    f"<t:{int(now.timestamp())}:F>"
                ),
                color=discord.Color.red()
            )

            await log_channel.send(
                embed=embed
            )

    # 📊 ÖSSZIDŐ
    @discord.ui.button(
        label="📊 Összidő",
        style=discord.ButtonStyle.blurple,
        custom_id="duty_osszido"
    )
    async def duty_osszido(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        user_id = interaction.user.id

        total_sec = duty_total_seconds.get(
            user_id,
            0
        )

        if user_id in duty_start_times:

            current_session = int(
                (
                    datetime.datetime.now()
                    - duty_start_times[user_id]
                ).total_seconds()
            )

            total_sec += current_session

            status_text = (
                "🟢 *Jelenleg is szolgálatban vagy.*"
            )

        else:

            status_text = (
                "🔴 *Jelenleg nem vagy szolgálatban.*"
            )

        hours, remainder = divmod(
            total_sec,
            3600
        )

        minutes, seconds = divmod(
            remainder,
            60
        )

        embed = discord.Embed(
            title="📊 Szolgálati Idő Statisztika",
            description=(
                f"**Tag:** {interaction.user.mention}\n\n"
                f"**Összesített szolgálati időd:**\n"
                f"⏱️ **{hours} óra "
                f"{minutes} perc "
                f"{seconds} másodperc**\n\n"
                f"{status_text}"
            ),
            color=discord.Color.blue()
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )


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
            await interaction.response.send_message(
                "❌ Ez a gomb csak Discord szerveren használható.",
                ephemeral=True
            )
            return

        leader_role = discord.utils.get(
            guild.roles,
            name="Leader"
        )

        is_leader = (
            leader_role is not None
            and leader_role in interaction.user.roles
        )

        is_admin = interaction.user.guild_permissions.administrator
        is_owner = interaction.user.id == guild.owner_id

        if not (is_leader or is_admin or is_owner):
            await interaction.response.send_message(
                "❌ Ezt csak a **Leader**, admin vagy "
                "a szerver tulajdonosa használhatja!",
                ephemeral=True
            )
            return

        member = guild.get_member(self.member_id)

        if member is None:
            try:
                member = await guild.fetch_member(self.member_id)
            except discord.NotFound:
                await interaction.response.send_message(
                    "❌ Ez a játékos már nincs a szerveren.",
                    ephemeral=True
                )
                return
            except discord.HTTPException:
                await interaction.response.send_message(
                    "❌ Nem sikerült lekérni a játékost. Próbáld újra.",
                    ephemeral=True
                )
                return

        role = discord.utils.get(
            guild.roles,
            name="Frakciótag"
        )

        if role is None:
            await interaction.response.send_message(
                "❌ Nem találom a **Frakciótag** szerepkört!\n\n"
                "Futtasd le először a `/setup_frakcio` parancsot.",
                ephemeral=True
            )
            return

        bot_member = guild.me

        if bot_member is None:
            await interaction.response.send_message(
                "❌ Nem sikerült lekérni a bot jogosultságait.",
                ephemeral=True
            )
            return

        bot_top_role = bot_member.top_role

        if role >= bot_top_role:
            await interaction.response.send_message(
                "❌ **Nem tudom kiosztani a Frakciótag rangot!**\n\n"
                "Discordban menj ide:\n"
                "**Szerverbeállítások → Szerepkörök**\n\n"
                "A bot szerepkörét húzd a **Frakciótag** szerepkör FÖLÉ.\n\n"
                f"🤖 Bot legmagasabb rangja: **{bot_top_role.name}**\n"
                f"🎖️ Kiosztandó rang: **{role.name}**",
                ephemeral=True
            )
            return

        if not bot_member.guild_permissions.manage_roles:
            await interaction.response.send_message(
                "❌ A botnak nincs **Szerepkörök kezelése (Manage Roles)** "
                "jogosultsága!",
                ephemeral=True
            )
            return

        if role in member.roles:
            await interaction.response.send_message(
                f"⚠️ {member.mention} már rendelkezik a **Frakciótag** ranggal.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"⏳ {member.mention} elfogadása folyamatban..."
        )

        try:
            await member.add_roles(
                role,
                reason=f"Frakcióba felvétel - elfogadta: {interaction.user}"
            )

        except discord.Forbidden:
            await interaction.followup.send(
                "❌ **Nem sikerült kiosztani a Frakciótag rangot!**\n\n"
                "Ellenőrizd, hogy:\n"
                "• a botnak van **Szerepkörök kezelése** joga;\n"
                "• a bot szerepköre a **Frakciótag** fölött van."
            )
            return

        except discord.HTTPException as e:
            await interaction.followup.send(
                f"❌ Discord hiba történt a rang kiosztásakor: `{e}`"
            )
            return

        await interaction.followup.send(
            f"✅ **{member.mention} sikeresen fel lett véve a frakcióba!**\n"
            f"👤 Elfogadta: {interaction.user.mention}\n"
            f"🎖️ Megkapta: **{role.name}**"
        )

        belepo_chan = discord.utils.get(
            guild.text_channels,
            name="👋-belépő"
        )

        if belepo_chan:
            welcome_embed = discord.Embed(
                title="👋 ÚJ FRAKCIÓTAG ÉRKEZETT!",
                description=(
                    f"🎉 Üdvözöljük a frakcióban, **{member.display_name}**!\n\n"
                    f"👤 Tag: {member.mention}\n"
                    f"🎖️ Rang: **{role.name}**\n\n"
                    "Örülünk, hogy csatlakoztál hozzánk! "
                    "Jó játékot és jó RP-t kívánunk! 🚀"
                ),
                color=discord.Color.green()
            )
            welcome_embed.set_thumbnail(url=member.display_avatar.url)
            welcome_embed.set_footer(text="Üdvözlünk a frakcióban!")
            welcome_embed.timestamp = datetime.datetime.now()

            await belepo_chan.send(
                content=f"👋 **Üdvözöljük {member.mention}!**",
                embed=welcome_embed
            )

        try:
            await member.send(
                "🎉 **Sikeres felvétel!**\n\n"
                f"A Leader ({interaction.user.display_name}) "
                "elfogadta a jelentkezésedet.\n\n"
                "Most már láthatod a frakció teljes szerverét."
            )
        except discord.Forbidden:
            pass

        waiting_channel = guild.get_channel(self.waiting_channel_id)

        if waiting_channel is not None:
            try:
                await waiting_channel.delete(
                    reason=f"Frakcióba felvett tag: {member}"
                )
            except discord.Forbidden:
                await interaction.followup.send(
                    "⚠️ A tag felvétele sikerült, de a privát várótermet "
                    "nem tudtam törölni.\n\n"
                    "Ellenőrizd a bot **Csatornák kezelése** jogosultságát."
                )
            except (discord.NotFound, discord.HTTPException):
                pass

        self.disabled = True
        self.label = "✅ Elfogadva"

        try:
            await interaction.message.edit(
                view=self.view
            )
        except (discord.NotFound, discord.HTTPException):
            pass


class AcceptView(discord.ui.View):

    def __init__(self, member_id, waiting_channel_id):
        super().__init__(timeout=None)
        self.add_item(
            AcceptButton(
                member_id,
                waiting_channel_id
            )
        )


# =========================================================
# 👤 ÚJ TAG AUTOMATIKUS JELENTKEZÉSE
# =========================================================

@bot.event
async def on_member_join(member: discord.Member):

    guild = member.guild

    waiting_category = discord.utils.get(
        guild.categories,
        name="🚪 VÁRÓTERMEK"
    )

    applications_channel = discord.utils.get(
        guild.text_channels,
        name="📋-jelentkezések"
    )

    leader_role = discord.utils.get(
        guild.roles,
        name="Leader"
    )

    subleader_role = discord.utils.get(
        guild.roles,
        name="Subleader"
    )

    if waiting_category is None or applications_channel is None:
        return

    existing_channel = None

    for channel in waiting_category.text_channels:
        if channel.topic == f"FRAKCIOS_JELENTKEZES:{member.id}":
            existing_channel = channel
            break

    if existing_channel is not None:
        waiting_channel = existing_channel
    else:

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=False
            ),
            member: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True
            )
        }

        if leader_role is not None:
            overwrites[leader_role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_messages=True
            )

        if subleader_role is not None:
            overwrites[subleader_role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_messages=True
            )

        safe_name = (
            "".join(
                c.lower() if c.isalnum() else "-"
                for c in member.display_name
            )
            .strip("-")
        )

        if not safe_name:
            safe_name = "tag"

        safe_name = safe_name[:60]
        channel_name = f"jelentkezés-{safe_name}-{member.id}"

        try:
            waiting_channel = await guild.create_text_channel(
                name=channel_name[:100],
                category=waiting_category,
                topic=f"FRAKCIOS_JELENTKEZES:{member.id}",
                overwrites=overwrites,
                reason=f"Automatikus jelentkezési szoba: {member}"
            )

        except (discord.Forbidden, discord.HTTPException):
            return

        await waiting_channel.send(
            f"👋 **Üdv a szerveren, {member.mention}!**\n\n"
            "Ez a **saját privát jelentkezési szobád**.\n"
            "Itt a vezetőség tud veled beszélni.\n\n"
            "📋 A vezetőség a jelentkezésedet a "
            "**📋-jelentkezések** csatornában tudja elfogadni.\n\n"
            "⏳ Kérlek várj, amíg egy Leader felveszi veled a kapcsolatot."
        )

    embed = discord.Embed(
        title="📥 ÚJ FRAKCIÓJELENTKEZÉS",
        description=(
            f"👤 **Jelentkező:** {member.mention}\n"
            f"🆔 **ID:** `{member.id}`\n"
            f"🔒 **Privát szoba:** {waiting_channel.mention}\n\n"
            "A jelentkezővel a saját privát szobájában tudtok beszélni.\n"
            "Más jelentkező ezt a szobát nem látja.\n\n"
            "Ha elfogadjátok, nyomjátok meg az alábbi gombot."
        ),
        color=discord.Color.blue()
    )

    embed.set_footer(
        text="Automatikus frakciójelentkezés"
    )

    embed.timestamp = datetime.datetime.now()

    try:
        await applications_channel.send(
            embed=embed,
            view=AcceptView(
                member.id,
                waiting_channel.id
            )
        )
    except (discord.Forbidden, discord.HTTPException):
        pass


# =========================================================
# 🔄 RÉGI JELENTKEZÉSI GOMBOK VISSZATÖLTÉSE
# =========================================================

_views_loaded = False


@bot.event
async def on_ready():

    global _views_loaded

    if _views_loaded:
        return

    bot.add_view(DutyView())

    for guild in bot.guilds:

        waiting_category = discord.utils.get(
            guild.categories,
            name="🚪 VÁRÓTERMEK"
        )

        if waiting_category is None:
            continue

        for channel in waiting_category.text_channels:

            if not channel.topic:
                continue

            prefix = "FRAKCIOS_JELENTKEZES:"

            if not channel.topic.startswith(prefix):
                continue

            try:
                member_id = int(
                    channel.topic[len(prefix):]
                )
            except ValueError:
                continue

            try:
                bot.add_view(
                    AcceptView(
                        member_id,
                        channel.id
                    )
                )
            except ValueError:
                pass

    _views_loaded = True

    print(
        f"✅ Bejelentkezve: {bot.user} | "
        f"Régi jelentkezési gombok betöltve."
    )


# =========================================================
# 🎁 /ajandek
# =========================================================

@bot.tree.command(
    name="ajandek",
    description="Nyereményjáték (Giveaway) indítása gombbal"
)
@app_commands.describe(
    nyeremeny="Mi a nyeremény?"
)
async def ajandek(
    interaction: discord.Interaction,
    nyeremeny: str
):

    leader_role = discord.utils.get(
        interaction.guild.roles,
        name="Leader"
    )

    is_leader = (
        leader_role is not None
        and leader_role in interaction.user.roles
    )

    is_admin = interaction.user.guild_permissions.administrator
    is_owner = interaction.user.id == interaction.guild.owner_id

    if not (is_leader or is_admin or is_owner):

        await interaction.response.send_message(
            "❌ Ezt a parancsot csak a "
            "**Leader**, admin vagy szervertulajdonos "
            "használhatja!",
            ephemeral=True
        )

        return

    embed = discord.Embed(
        title="🎁 NYEREMÉNYJÁTÉK! 🎁",
        description=(
            f"**Nyeremény:** {nyeremeny}\n\n"
            "Kattints az alábbi "
            "**🎉 Jelentkezés** gombra "
            "a részvételhez!"
        ),
        color=discord.Color.purple()
    )

    embed.set_footer(
        text=f"Indította: {interaction.user.display_name}"
    )

    embed.timestamp = datetime.datetime.now()

    view = GiveawayView(
        prize=nyeremeny,
        host=interaction.user
    )

    await interaction.response.send_message(
        embed=embed,
        view=view
    )


# =========================================================
# 👑 /remove
# =========================================================

@bot.tree.command(
    name="remove",
    description="MINDEN csatorna, hangcsatorna és kategória törlése"
)
async def remove_all(interaction: discord.Interaction):

    if interaction.user.id != interaction.guild.owner_id:

        await interaction.response.send_message(
            "❌ Ezt kizárólag a **szerver tulajdonosa** használhatja!",
            ephemeral=True
        )

        return

    await interaction.response.send_message(
        "💣 **A szerver összes csatornájának törlése megkezdődött...**",
        ephemeral=True
    )

    guild = interaction.guild

    for channel in list(guild.channels):
        try:
            await channel.delete()
        except Exception:
            pass


# =========================================================
# 🧹 /clear
# =========================================================

@bot.tree.command(
    name="clear",
    description="Üzenetek törlése az adott csatornából"
)
@app_commands.describe(
    mennyiseg="Hány üzenetet töröljön a bot?"
)
async def clear_messages(
    interaction: discord.Interaction,
    mennyiseg: int = 100
):

    leader_role = discord.utils.get(
        interaction.guild.roles,
        name="Leader"
    )

    is_leader = (
        leader_role is not None
        and leader_role in interaction.user.roles
    )

    is_admin = interaction.user.guild_permissions.administrator
    is_owner = interaction.user.id == interaction.guild.owner_id

    if not (is_leader or is_admin or is_owner):

        await interaction.response.send_message(
            "❌ Nincs jogosultságod az üzenetek törléséhez!",
            ephemeral=True
        )

        return

    await interaction.response.defer(ephemeral=True)

    try:
        deleted = await interaction.channel.purge(limit=mennyiseg)

        await interaction.followup.send(
            f"🧹 Sikeresen törölve **{len(deleted)}** üzenet!",
            ephemeral=True
        )

    except Exception as e:
        await interaction.followup.send(
            f"⚠️ Hiba történt a törlés során: {e}",
            ephemeral=True
        )


# =========================================================
# ⚡ /setup_frakcio
# =========================================================

@bot.tree.command(
    name="setup_frakcio",
    description="Teljes, kibővített frakció szerkezet kiépítése"
)
async def setup_frakcio(interaction: discord.Interaction):

    leader_role = discord.utils.get(
        interaction.guild.roles,
        name="Leader"
    )

    is_leader = (
        leader_role is not None
        and leader_role in interaction.user.roles
    )

    is_admin = interaction.user.guild_permissions.administrator
    is_owner = interaction.user.id == interaction.guild.owner_id

    if not (is_leader or is_admin or is_owner):

        await interaction.response.send_message(
            "❌ Ezt a parancsot csak a **Leader**, admin vagy szervertulajdonos használhatja!",
            ephemeral=True
        )

        return

    await interaction.response.defer()

    guild = interaction.guild

    leader = (
        leader_role
        or await guild.create_role(
            name="Leader",
            color=discord.Color.red(),
            permissions=discord.Permissions(administrator=True)
        )
    )

    subleader = (
        discord.utils.get(guild.roles, name="Subleader")
        or await guild.create_role(name="Subleader", color=discord.Color.orange())
    )

    tag = (
        discord.utils.get(guild.roles, name="Frakciótag")
        or await guild.create_role(name="Frakciótag", color=discord.Color.blue())
    )

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

    waiting_overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        leader: discord.PermissionOverwrite(view_channel=True),
        subleader: discord.PermissionOverwrite(view_channel=True)
    }

    cat_varo = discord.utils.get(guild.categories, name="🚪 VÁRÓTERMEK")

    if cat_varo is None:
        cat_varo = await guild.create_category("🚪 VÁRÓTERMEK", overwrites=waiting_overwrites)
    else:
        await cat_varo.edit(overwrites=waiting_overwrites)

    cat_info = await guild.create_category("📌 INFORMÁCIÓK", overwrites=overwrites_hidden)
    await cat_info.create_text_channel("👋-belépő")
    await cat_info.create_text_channel("📢-bejelentések")
    await cat_info.create_text_channel("📜-szabályzat")
    await cat_info.create_text_channel("🎖️-rangok-és-fizetések")
    await cat_info.create_text_channel("📝-minták-és-nyomtatványok")
    await cat_info.create_text_channel("🚗-járműpark-és-kulcsok")
    await cat_info.create_text_channel("❓-gyakori-kérdések")

    cat_ic_elet = await guild.create_category("💼 IC ÉLET", overwrites=overwrites_hidden)
    await cat_ic_elet.create_text_channel("💬-ic-chat")
    await cat_ic_elet.create_text_channel("📸-ic-fotók-és-kamera")
    await cat_ic_elet.create_text_channel("📝-szabadságkérelmek")
    await cat_ic_elet.create_text_channel("📋-ic-ötletek-és-reformok")
    await cat_ic_elet.create_text_channel("📂-ic-adatok")

    cat_ooc = await guild.create_category("💭 OOC ÉLET", overwrites=overwrites_hidden)
    await cat_ooc.create_text_channel("💭-ooc-chat")
    await cat_ooc.create_text_channel("📷-rp-élményképek")
    await cat_ooc.create_text_channel("💡-ötletek-és-javaslatok")
    await cat_ooc.create_text_channel("😂-mémek-és-offtopic")

    cat_ic = await guild.create_category("💼 IC MŰKÖDÉS & DUTY", overwrites=overwrites_hidden)
    duty_chan = await cat_ic.create_text_channel("⏰-duty-mérő")
    await cat_ic.create_text_channel("📋-szolgálati-napló")
    await cat_ic.create_text_channel("📦-frakció-széf-és-raktár")
    await cat_ic.create_text_channel("⚔️-akciók-és-tervek")
    await cat_ic.create_text_channel("🤝-diplomácia")
    await cat_ic.create_text_channel("💰-kassza-és-elszámolás")

    embed_duty = discord.Embed(
        title="⏰ Szolgálati Idő Mérő (Duty)",
        description=(
            "Használd az alábbi gombokat a szolgálatba lépéshez, "
            "kilépéshez és az összidőd ellenőrzéséhez!\n\n"
            "🟢 **Duty Be** - Szolgálat megkezdése\n"
            "🔴 **Duty Ki** - Szolgálat befejezése\n"
            "📊 **Összidő** - Eddigi összesített időd lekérése"
        ),
        color=discord.Color.blue()
    )

    await duty_chan.send(embed=embed_duty, view=DutyView())

    cat_vez = await guild.create_category("🔒 VEZETŐSÉG", overwrites=overwrites_admin)
    await cat_vez.create_text_channel("🔒-vezetőségi-chat")
    await cat_vez.create_text_channel("📋-jelentkezések")
    await cat_vez.create_text_channel("⚠️-figyelmeztetések")
    await cat_vez.create_text_channel("🚫-feketelista")
    await cat_vez.create_text_channel("📑-vezetőségi-jegyzetek")

    cat_voice = await guild.create_category("🔊 HANGCSATORNÁK", overwrites=overwrites_hidden)
    await cat_voice.create_voice_channel("🔊 OOC Beszélgető 1")
    await cat_voice.create_voice_channel("🔊 OOC Beszélgető 2")
    await cat_voice.create_voice_channel("🔊 Rádió 1 [IC / RP]")
    await cat_voice.create_voice_channel("🔊 Rádió 2 [IC / RP]")
    await cat_voice.create_voice_channel("🔊 Akció / Taktikai 1")
    await cat_voice.create_voice_channel("🔊 Akció / Taktikai 2")
    await cat_voice.create_voice_channel("💤 AFK / Inaktív")
    await cat_voice.create_voice_channel("🔒 Vezetőségi Tárgyaló", overwrites=overwrites_admin)

    await interaction.followup.send("✅ **A szerverstruktúra sikeresen létrejött!**")


# =========================================================
# 📢 /bejelentes
# =========================================================

@bot.tree.command(
    name="bejelentes",
    description="Hivatalos bejelentés kiküldése a bejelentések csatornába"
)
@app_commands.describe(
    cim="A bejelentés címe",
    uzenet="A bejelentés szövege"
)
async def bejelentes(
    interaction: discord.Interaction,
    cim: str,
    uzenet: str
):

    leader_role = discord.utils.get(interaction.guild.roles, name="Leader")
    is_leader = leader_role is not None and leader_role in interaction.user.roles
    is_admin = interaction.user.guild_permissions.administrator
    is_owner = interaction.user.id == interaction.guild.owner_id

    if not (is_leader or is_admin or is_owner):
        await interaction.response.send_message(
            "❌ Ezt csak a **Leader**, admin vagy szervertulajdonos használhatja!",
            ephemeral=True
        )
        return

    chan = discord.utils.get(interaction.guild.text_channels, name="📢-bejelentések")

    if chan:
        embed = discord.Embed(
            title=f"📢 {cim}",
            description=uzenet,
            color=discord.Color.red()
        )
        embed.set_footer(text=f"Kiadta: {interaction.user.display_name}")
        embed.timestamp = datetime.datetime.now()

        await chan.send(content="@everyone", embed=embed)
        await interaction.response.send_message("✅ Bejelentés kiküldve!", ephemeral=True)


# =========================================================
# ⚠️ /warn
# =========================================================

@bot.tree.command(
    name="warn",
    description="Figyelmeztetés adása egy tagnak"
)
@app_commands.describe(
    tag="A figyelmeztetett tag",
    indok="A figyelmeztetés indoka"
)
async def warn(
    interaction: discord.Interaction,
    tag: discord.Member,
    indok: str
):

    leader_role = discord.utils.get(interaction.guild.roles, name="Leader")
    is_leader = leader_role is not None and leader_role in interaction.user.roles
    is_admin = interaction.user.guild_permissions.administrator
    is_owner = interaction.user.id == interaction.guild.owner_id

    if not (is_leader or is_admin or is_owner):
        await interaction.response.send_message(
            "❌ Ezt csak a **Leader**, admin vagy szervertulajdonos használhatja!",
            ephemeral=True
        )
        return

    warn_chan = discord.utils.get(interaction.guild.text_channels, name="⚠️-figyelmeztetések")

    if warn_chan:
        embed = discord.Embed(
            title="⚠️ Frakció Figyelmeztetés (Warn)",
            description=(
                f"**Kapta:** {tag.mention}\n"
                f"**Adta:** {interaction.user.mention}\n"
                f"**Indok:** {indok}"
            ),
            color=discord.Color.dark_red()
        )
        embed.timestamp = datetime.datetime.now()

        await warn_chan.send(embed=embed)

        try:
            await tag.send(
                "⚠️ **Figyelmeztetést kaptál a frakcióban!**\n"
                f"**Indok:** {indok}\n"
                f"**Adta:** {interaction.user.name}"
            )
        except Exception:
            pass

        await interaction.response.send_message(f"✅ Figyelmeztetés rögzítve: {tag.mention}", ephemeral=True)


# =========================================================
# 📢 /everyone
# =========================================================

@bot.tree.command(
    name="everyone",
    description="Üzenet kiküldése az összes aktív egyéni váróterembe"
)
@app_commands.describe(uzenet="A kiküldendő üzenet szövege")
async def everyone_cmd(
    interaction: discord.Interaction,
    uzenet: str
):

    leader_role = discord.utils.get(interaction.guild.roles, name="Leader")
    is_leader = leader_role is not None and leader_role in interaction.user.roles
    is_admin = interaction.user.guild_permissions.administrator
    is_owner = interaction.user.id == interaction.guild.owner_id

    if not (is_leader or is_admin or is_owner):
        await interaction.response.send_message(
            "❌ Ezt csak a **Leader**, admin vagy szervertulajdonos használhatja!",
            ephemeral=True
        )
        return

    cat_varo = discord.utils.get(interaction.guild.categories, name="🚪 VÁRÓTERMEK")

    if not cat_varo or not cat_varo.text_channels:
        await interaction.response.send_message(
            "⚠️ Jelenleg nincsenek nyitott egyéni várótermek!",
            ephemeral=True
        )
        return

    sent_count = 0

    for channel in cat_varo.text_channels:
        try:
            await channel.send(
                f"📢 **Leaderi közlemény ({interaction.user.mention}):**\n{uzenet}"
            )
            sent_count += 1
        except Exception:
            pass

    await interaction.response.send_message(
        f"✅ Az üzenet sikeresen kiküldve **{sent_count}** váróterembe!",
        ephemeral=True
    )


# =========================================================
# 🏛️ FRAKCIÓKÉPZŐ PREFIX PARANCSOK (!frakcio ...)
# =========================================================

async def _setup_rendor_logic(ctx: commands.Context):
    guild = ctx.guild
    if guild is None:
        await ctx.send("❌ Ez a parancs csak Discord szerveren használható!")
        return

    if not (ctx.author.guild_permissions.administrator or ctx.author.id == guild.owner_id):
        await ctx.send("❌ Ezt csak admin vagy a szerver tulajdonosa használhatja!")
        return

    role = discord.utils.get(guild.roles, name="🚓 Rendőr") or await guild.create_role(name="🚓 Rendőr", color=discord.Color.blue())
    leader = discord.utils.get(guild.roles, name="🚓 Rendőrség Vezetőség") or await guild.create_role(name="🚓 Rendőrség Vezetőség", color=discord.Color.dark_blue())
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        role: discord.PermissionOverwrite(view_channel=True),
        leader: discord.PermissionOverwrite(view_channel=True)
    }

    category = discord.utils.get(guild.categories, name="🚓 RENDŐRSÉG") or await guild.create_category("🚓 RENDŐRSÉG", overwrites=overwrites)
    channels = [
        ("📻-rádió", "Rendőrségi rádió / IC kommunikáció."),
        ("📜-rádió-szabályzat", "Rádióhasználati és kommunikációs szabályzat."),
        ("📘-rendőrségi-szabályzat", "A rendőrség általános szabályzata."),
        ("🚔-járőr-információk", "Járőrözéshez és szolgálathoz szükséges információk."),
        ("🚨-akciók", "Akciók, üldözések és taktikai műveletek."),
        ("🚗-járműpark", "Rendőrségi járművek, egységek és használatuk."),
        ("🔫-felszerelés", "Felszerelések, fegyverek és szolgálati eszközök."),
        ("📋-feladatok", "Aktuális rendőrségi feladatok."),
        ("⚖️-bírságok-eljárások", "Bírságok és RP eljárások."),
        ("📂-nyomozások", "Nyomozások és ügyek."),
        ("📝-jelentések", "Szolgálati és intézkedési jelentések."),
        ("📢-közlemények", "Vezetőségi közlemények."),
        ("💬-rendőr-ooc", "Rendőrségi OOC beszélgetés.")
    ]

    created = 0
    for name, topic in channels:
        if discord.utils.get(category.text_channels, name=name) is None:
            await category.create_text_channel(name=name, topic=topic)
            created += 1

    await ctx.send(
        f"✅ **Rendőrségi frakció elkészült!**\n"
        f"🚓 Kategória: {category.mention}\n"
        f"🎖️ Rang: **{role.name}**\n"
        f"📁 Új csatornák: **{created}**"
    )


async def _setup_mentos_logic(ctx: commands.Context):
    guild = ctx.guild
    if guild is None:
        await ctx.send("❌ Ez a parancs csak Discord szerveren használható!")
        return

    if not (ctx.author.guild_permissions.administrator or ctx.author.id == guild.owner_id):
        await ctx.send("❌ Ezt csak admin vagy a szerver tulajdonosa használhatja!")
        return

    role = discord.utils.get(guild.roles, name="🚑 Mentős") or await guild.create_role(name="🚑 Mentős", color=discord.Color.red())
    leader = discord.utils.get(guild.roles, name="🚑 Mentőszolgálat Vezetőség") or await guild.create_role(name="🚑 Mentőszolgálat Vezetőség", color=discord.Color.dark_red())
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        role: discord.PermissionOverwrite(view_channel=True),
        leader: discord.PermissionOverwrite(view_channel=True)
    }

    category = discord.utils.get(guild.categories, name="🚑 MENTŐSZOLGÁLAT") or await guild.create_category("🚑 MENTŐSZOLGÁLAT", overwrites=overwrites)
    channels = [
        ("📻-mentős-rádió", "Mentőszolgálati rádió / IC kommunikáció."),
        ("📜-rádió-szabályzat", "Mentős rádiózási és kommunikációs szabályzat."),
        ("📘-mentős-szabályzat", "A mentőszolgálat általános szabályzata."),
        ("🚑-szolgálati-információk", "Szolgálathoz szükséges információk."),
        ("🏥-kórházi-információk", "Kórházi és betegellátási információk."),
        ("🚨-riasztások", "Aktuális riasztások és kivonulások."),
        ("🩺-felszerelés", "Orvosi felszerelések és használatuk."),
        ("🚑-járműpark", "Mentőautók és egyéb szolgálati járművek."),
        ("📋-betegjelentések", "RP beteg- és esetjelentések."),
        ("📝-szolgálati-jelentések", "Szolgálati jelentések."),
        ("📢-közlemények", "Vezetőségi közlemények."),
        ("💬-mentős-ooc", "Mentőszolgálati OOC beszélgetés.")
    ]

    created = 0
    for name, topic in channels:
        if discord.utils.get(category.text_channels, name=name) is None:
            await category.create_text_channel(name=name, topic=topic)
            created += 1

    await ctx.send(
        f"✅ **Mentőszolgálati frakció elkészült!**\n"
        f"🚑 Kategória: {category.mention}\n"
        f"🎖️ Rang: **{role.name}**\n"
        f"📁 Új csatornák: **{created}**"
    )


async def _setup_szerelo_logic(ctx: commands.Context):
    guild = ctx.guild
    if guild is None:
        await ctx.send("❌ Ez a parancs csak Discord szerveren használható!")
        return

    if not (ctx.author.guild_permissions.administrator or ctx.author.id == guild.owner_id):
        await ctx.send("❌ Ezt csak admin vagy a szerver tulajdonosa használhatja!")
        return

    role = discord.utils.get(guild.roles, name="🔧 Szerelő") or await guild.create_role(name="🔧 Szerelő", color=discord.Color.orange())
    leader = discord.utils.get(guild.roles, name="🔧 Szerelő Vezetőség") or await guild.create_role(name="🔧 Szerelő Vezetőség", color=discord.Color.dark_orange())
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        role: discord.PermissionOverwrite(view_channel=True),
        leader: discord.PermissionOverwrite(view_channel=True)
    }

    category = discord.utils.get(guild.categories, name="🔧 SZERELŐ") or await guild.create_category("🔧 SZERELŐ", overwrites=overwrites)
    channels = [
        ("📻-szerelő-rádió", "Szerelő rádió / IC kommunikáció."),
        ("📜-szerelő-szabályzat", "Szerelői és rádiózási szabályzat."),
        ("📘-műhely-szabályzat", "A műhely használatának szabályai."),
        ("💰-szerelő-árlista", "Szerelői szolgáltatások és árlista."),
        ("🔧-munkalapok", "Aktuális szerelési munkalapok."),
        ("🚗-járművek", "Javítandó és elkészült járművek."),
        ("🛠️-alkatrészek", "Alkatrészek és készletinformációk."),
        ("📦-raktár", "Raktár és készlet."),
        ("📋-munkajelentések", "Elvégzett munkák jelentései."),
        ("💵-kassza-elszámolás", "Munkadíjak és kassza elszámolások."),
        ("📢-közlemények", "Vezetőségi közlemények."),
        ("💬-szerelő-ooc", "Szerelői OOC beszélgetés.")
    ]

    created = 0
    for name, topic in channels:
        if discord.utils.get(category.text_channels, name=name) is None:
            await category.create_text_channel(name=name, topic=topic)
            created += 1

    await ctx.send(
        f"✅ **Szerelő frakció elkészült!**\n"
        f"🔧 Kategória: {category.mention}\n"
        f"🎖️ Rang: **{role.name}**\n"
        f"📁 Új csatornák: **{created}**"
    )


# --- Group Parancs (!frakcio ...) ---

@bot.group(name="frakcio", invoke_without_command=True)
async def frakcio_group(ctx: commands.Context):
    await ctx.send(
        "❌ **Használat:**\n"
        "• `!frakcio rendor` - Rendőrségi frakció kiépítése\n"
        "• `!frakcio mentos` - Mentőszolgálati frakció kiépítése\n"
        "• `!frakcio szerelo` - Szerelő frakció kiépítése"
    )


@frakcio_group.command(name="rendor")
async def frakcio_rendor_sub(ctx: commands.Context):
    await _setup_rendor_logic(ctx)


@frakcio_group.command(name="mentos")
async def frakcio_mentos_sub(ctx: commands.Context):
    await _setup_mentos_logic(ctx)


@frakcio_group.command(name="szerelo")
async def frakcio_szerelo_sub(ctx: commands.Context):
    await _setup_szerelo_logic(ctx)


# --- Standalone Parancsok (!frakcio_rendor stb.) ---

@bot.command(name="frakcio_rendor")
async def frakcio_rendor_cmd(ctx: commands.Context):
    await _setup_rendor_logic(ctx)


@bot.command(name="frakcio_mentos")
async def frakcio_mentos_cmd(ctx: commands.Context):
    await _setup_mentos_logic(ctx)


@bot.command(name="frakcio_szerelo")
async def frakcio_szerelo_cmd(ctx: commands.Context):
    await _setup_szerelo_logic(ctx)


# =========================================================
# 🚀 BOT INDÍTÁSA
# =========================================================

bot.run(
    os.environ["DISCORD_TOKEN"]
)
