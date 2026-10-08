import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import datetime
import random

import discord
from discord import app_commands
from discord.ext import commands


# =========================================================
# 🌐 RENDER HEALTH SERVER
# =========================================================

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Discord bot is online!")

    def log_message(self, format, *args):
        pass


def start_web_server():
    try:
        port = int(os.environ.get("PORT", 10000))
        server = HTTPServer(("0.0.0.0", port), HealthHandler)

        print(f"🌐 Render health server elindult a(z) {port} porton.")

        server.serve_forever()

    except Exception as e:
        print(f"❌ Health server hiba: {e}")


threading.Thread(
    target=start_web_server,
    daemon=True
).start()


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

        # A slash parancsok szinkronizálása az on_ready
        # eseményben történik, mert ott már biztosan
        # rendelkezésre állnak a guild-ek.
        print("⚙️ Bot setup_hook lefutott.")


bot = FactionBot()


# =========================================================
# 🔄 ÁLLAPOTOK
# =========================================================

_commands_synced = False
_views_loaded = False


# =========================================================
# 🔐 JOGOSULTSÁG ELLENŐRZÉS
# =========================================================

def has_management_access(interaction: discord.Interaction):

    guild = interaction.guild

    if guild is None:
        return False

    user = interaction.user

    if user.id == guild.owner_id:
        return True

    if user.guild_permissions.administrator:
        return True

    leader_role = discord.utils.get(
        guild.roles,
        name="Leader"
    )

    if leader_role is not None and leader_role in user.roles:
        return True

    return False


def has_admin_access(interaction: discord.Interaction):

    guild = interaction.guild

    if guild is None:
        return False

    user = interaction.user

    return (
        user.id == guild.owner_id
        or user.guild_permissions.administrator
    )


# =========================================================
# 🎉 NYEREMÉNYJÁTÉK
# =========================================================

class GiveawayView(discord.ui.View):

    def __init__(
        self,
        prize: str,
        host: discord.Member
    ):

        super().__init__(timeout=None)

        self.prize = prize
        self.host = host
        self.participants = set()

    # =====================================================
    # 🎉 JELENTKEZÉS
    # =====================================================

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
                "❌ Visszavontad a jelentkezésedet!",
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

    # =====================================================
    # 🎲 SORSOLÁS
    # =====================================================

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

        guild = interaction.guild

        if guild is None:
            await interaction.response.send_message(
                "❌ Ez csak szerveren használható.",
                ephemeral=True
            )
            return

        if not has_management_access(interaction):

            await interaction.response.send_message(
                "❌ Ezt a gombot csak a **Leader**, admin vagy "
                "szervertulajdonos használhatja!",
                ephemeral=True
            )

            return

        if not self.participants:

            await interaction.response.send_message(
                "⚠️ Nem jelentkezett senki!",
                ephemeral=True
            )

            return

        winner_id = random.choice(
            list(self.participants)
        )

        winner = guild.get_member(
            winner_id
        )

        for child in self.children:
            child.disabled = True

        if interaction.message.embeds:

            embed = interaction.message.embeds[0]

        else:

            embed = discord.Embed()

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

        if interaction.channel:

            await interaction.channel.send(
                f"🎊 **GRATULÁLUNK!** {winner_mention} "
                f"megnyerte: **{self.prize}**!"
            )


# =========================================================
# ⏱️ DUTY MÉRŐ
# =========================================================

class DutyView(discord.ui.View):

    def __init__(self):

        super().__init__(timeout=None)

    # =====================================================
    # 🟢 DUTY BE
    # =====================================================

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
            "🟢 **Szolgálatba léptél!**\n"
            "A bot elkezdte mérni az idődet.",
            ephemeral=True
        )

        log_channel = discord.utils.get(
            interaction.guild.text_channels,
            name="📋-szolgálati-napló"
        )

        if log_channel:

            now = datetime.datetime.now()

            await log_channel.send(
                f"🟢 **{interaction.user.mention}** "
                f"szolgálatba lépett: "
                f"<t:{int(now.timestamp())}:F>"
            )

    # =====================================================
    # 🔴 DUTY KI
    # =====================================================

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

        session_seconds = max(
            0,
            int(
                (now - start_time).total_seconds()
            )
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
            f"{minutes} perc "
            f"{seconds} másodperc"
        )

        await interaction.response.send_message(
            f"🔴 **Kiléptél a szolgálatból!**\n\n"
            f"⏱️ A mostani szolgálatod ideje:\n"
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

    # =====================================================
    # 📊 ÖSSZIDŐ
    # =====================================================

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

            current_session = max(
                0,
                int(
                    (
                        datetime.datetime.now()
                        - duty_start_times[user_id]
                    ).total_seconds()
                )
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

    def __init__(
        self,
        member_id,
        waiting_channel_id
    ):

        super().__init__(
            label="✅ Elfogadás (Szerver megnyitása)",
            style=discord.ButtonStyle.green,
            custom_id=(
                f"accept_member:"
                f"{member_id}:"
                f"{waiting_channel_id}"
            )
        )

        self.member_id = member_id
        self.waiting_channel_id = waiting_channel_id

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        guild = interaction.guild

        if guild is None:

            await interaction.response.send_message(
                "❌ Ez csak Discord szerveren használható.",
                ephemeral=True
            )

            return

        if not has_management_access(interaction):

            await interaction.response.send_message(
                "❌ Ezt csak a **Leader**, admin vagy "
                "szervertulajdonos használhatja!",
                ephemeral=True
            )

            return

        member = guild.get_member(
            self.member_id
        )

        if member is None:

            try:

                member = await guild.fetch_member(
                    self.member_id
                )

            except discord.NotFound:

                await interaction.response.send_message(
                    "❌ Ez a játékos már nincs a szerveren.",
                    ephemeral=True
                )

                return

            except discord.HTTPException:

                await interaction.response.send_message(
                    "❌ Nem sikerült lekérni a játékost.",
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
                "❌ Nem sikerült lekérni a bot adatait.",
                ephemeral=True
            )

            return

        if not bot_member.guild_permissions.manage_roles:

            await interaction.response.send_message(
                "❌ A botnak nincs **Szerepkörök kezelése** "
                "jogosultsága!",
                ephemeral=True
            )

            return

        if role >= bot_member.top_role:

            await interaction.response.send_message(
                "❌ **Nem tudom kiosztani a Frakciótag rangot!**\n\n"
                "Menj ide:\n"
                "**Szerverbeállítások → Szerepkörök**\n\n"
                "A bot szerepkörét húzd a "
                "**Frakciótag** szerepkör fölé.",
                ephemeral=True
            )

            return

        if role in member.roles:

            await interaction.response.send_message(
                f"⚠️ {member.mention} már rendelkezik "
                f"a **Frakciótag** ranggal.",
                ephemeral=True
            )

            return

        await interaction.response.send_message(
            f"⏳ {member.mention} elfogadása folyamatban..."
        )

        try:

            await member.add_roles(
                role,
                reason=(
                    f"Frakcióba felvétel - "
                    f"elfogadta: {interaction.user}"
                )
            )

        except discord.Forbidden:

            await interaction.followup.send(
                "❌ Nem sikerült kiosztani a Frakciótag rangot!\n\n"
                "Ellenőrizd a bot jogosultságait és a "
                "szerepkör sorrendjét."
            )

            return

        except discord.HTTPException as e:

            await interaction.followup.send(
                f"❌ Discord hiba történt: `{e}`"
            )

            return

        await interaction.followup.send(
            f"✅ **{member.mention} sikeresen fel lett véve!**\n"
            f"👤 Elfogadta: {interaction.user.mention}\n"
            f"🎖️ Rang: **{role.name}**"
        )

        # =================================================
        # 👋 BELÉPŐ
        # =================================================

        belepo_chan = discord.utils.get(
            guild.text_channels,
            name="👋-belépő"
        )

        if belepo_chan:

            welcome_embed = discord.Embed(
                title="👋 ÚJ FRAKCIÓTAG ÉRKEZETT!",
                description=(
                    f"🎉 Üdvözöljük a frakcióban, "
                    f"**{member.display_name}**!\n\n"
                    f"👤 Tag: {member.mention}\n"
                    f"🎖️ Rang: **{role.name}**\n\n"
                    "Örülünk, hogy csatlakoztál hozzánk!\n"
                    "Jó játékot és jó RP-t kívánunk! 🚀"
                ),
                color=discord.Color.green()
            )

            welcome_embed.set_thumbnail(
                url=member.display_avatar.url
            )

            welcome_embed.set_footer(
                text="Üdvözlünk a frakcióban!"
            )

            welcome_embed.timestamp = datetime.datetime.now()

            await belepo_chan.send(
                content=f"👋 **Üdvözöljük {member.mention}!**",
                embed=welcome_embed
            )

        # =================================================
        # 📩 PRIVÁT ÜZENET
        # =================================================

        try:

            await member.send(
                "🎉 **Sikeres felvétel!**\n\n"
                f"A Leader ({interaction.user.display_name}) "
                "elfogadta a jelentkezésedet.\n\n"
                "Most már láthatod a frakció szerverét."
            )

        except discord.Forbidden:
            pass

        # =================================================
        # 🗑️ VÁRÓTEREM TÖRLÉSE
        # =================================================

        waiting_channel = guild.get_channel(
            self.waiting_channel_id
        )

        if waiting_channel is not None:

            try:

                await waiting_channel.delete(
                    reason=f"Frakcióba felvett tag: {member}"
                )

            except discord.Forbidden:

                await interaction.followup.send(
                    "⚠️ A tag felvétele sikerült, de a "
                    "várótermet nem tudtam törölni."
                )

            except discord.NotFound:
                pass

            except discord.HTTPException:
                pass

        # =================================================
        # 🔘 GOMB LETILTÁSA
        # =================================================

        self.disabled = True
        self.label = "✅ Elfogadva"

        try:

            await interaction.message.edit(
                view=self.view
            )

        except (
            discord.NotFound,
            discord.HTTPException
        ):
            pass


class AcceptView(discord.ui.View):

    def __init__(
        self,
        member_id,
        waiting_channel_id
    ):

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
async def on_member_join(
    member: discord.Member
):

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

    if (
        waiting_category is None
        or applications_channel is None
    ):

        print(
            f"[JELENTKEZÉS] Hiányzik valami: "
            f"{guild.name}"
        )

        return

    existing_channel = None

    for channel in waiting_category.text_channels:

        if channel.topic == (
            f"FRAKCIOS_JELENTKEZES:{member.id}"
        ):

            existing_channel = channel
            break

    if existing_channel is not None:

        waiting_channel = existing_channel

    else:

        overwrites = {

            guild.default_role:
                discord.PermissionOverwrite(
                    view_channel=False
                ),

            member:
                discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    attach_files=True,
                    embed_links=True
                )
        }

        if leader_role is not None:

            overwrites[leader_role] = (
                discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    manage_messages=True
                )
            )

        if subleader_role is not None:

            overwrites[subleader_role] = (
                discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    manage_messages=True
                )
            )

        safe_name = "".join(
            c.lower() if c.isalnum() else "-"
            for c in member.display_name
        ).strip("-")

        if not safe_name:
            safe_name = "tag"

        safe_name = safe_name[:60]

        channel_name = (
            f"jelentkezés-{safe_name}-{member.id}"
        )

        try:

            waiting_channel = (
                await guild.create_text_channel(
                    name=channel_name[:100],
                    category=waiting_category,
                    topic=(
                        f"FRAKCIOS_JELENTKEZES:"
                        f"{member.id}"
                    ),
                    overwrites=overwrites,
                    reason=(
                        f"Automatikus jelentkezési szoba: "
                        f"{member}"
                    )
                )
            )

        except discord.Forbidden:

            print(
                "[JELENTKEZÉS] Nincs jogosultság "
                "csatornát létrehozni."
            )

            return

        except discord.HTTPException as e:

            print(
                f"[JELENTKEZÉS] Discord hiba: {e}"
            )

            return

        try:

            await waiting_channel.send(
                f"👋 **Üdv a szerveren, {member.mention}!**\n\n"
                "Ez a **saját privát jelentkezési szobád**.\n"
                "Itt a vezetőség tud veled beszélni.\n\n"
                "📋 A vezetőség a jelentkezésedet a "
                "**📋-jelentkezések** csatornában tudja elfogadni.\n\n"
                "⏳ Kérlek várj, amíg egy Leader "
                "felveszi veled a kapcsolatot."
            )

        except Exception as e:

            print(
                f"[JELENTKEZÉS] Üzenetküldési hiba: {e}"
            )

    # =====================================================
    # 📋 JELENTKEZÉS A VEZETŐSÉGBEN
    # =====================================================

    embed = discord.Embed(
        title="📥 ÚJ FRAKCIÓJELENTKEZÉS",
        description=(
            f"👤 **Jelentkező:** {member.mention}\n"
            f"🆔 **ID:** `{member.id}`\n"
            f"🔒 **Privát szoba:** "
            f"{waiting_channel.mention}\n\n"
            "A jelentkezővel a saját privát szobájában "
            "tudtok beszélni.\n\n"
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

    except discord.Forbidden:

        print(
            "[JELENTKEZÉS] Nincs jogosultság "
            "a jelentkezési üzenethez."
        )

    except discord.HTTPException as e:

        print(
            f"[JELENTKEZÉS] Discord hiba: {e}"
        )


# =========================================================
# 🔄 SLASH PARANCSOK SZINKRONIZÁLÁSA
# =========================================================

async def sync_guild_commands():

    global _commands_synced

    if _commands_synced:
        return

    if not bot.guilds:

        print(
            "⚠️ Még nincs betöltött Discord szerver."
        )

        return

    success = True

    print(
        f"🔄 Slash parancsok szinkronizálása "
        f"{len(bot.guilds)} szerverre..."
    )

    for guild in bot.guilds:

        try:

            # A globális command tree jelenlegi
            # parancsait átmásoljuk az adott guildre.
            
            
            
            
            
            
            
            bot.tree.copy_global_to(guild=guild)
            await bot.tree.sync(guild=guild)
            )

            synced = await bot.tree.sync(
                guild=guild
            )

            print(
                f"✅ {guild.name} | "
                f"{len(synced)} slash parancs szinkronizálva."
            )

            command_names = [
                command.name
                for command in synced
            ]

            print(
                f"   📋 Parancsok: "
                f"{', '.join(command_names)}"
            )

        except Exception as e:

            success = False

            print(
                f"❌ Slash sync hiba: "
                f"{guild.name} | {e}"
            )

    if success:

        _commands_synced = True

        print(
            "✅ AZ ÖSSZES SLASH PARANCS SZINKRONIZÁLVA!"
        )

    else:

        print(
            "⚠️ Néhány slash parancs szinkronizálása "
            "nem sikerült. Újrapróbálom."
        )


# =========================================================
# 🔄 RÉGI GOMBOK VISSZATÖLTÉSE
# =========================================================

async def load_persistent_views():

    global _views_loaded

    if _views_loaded:
        return

    # Duty gomb
    try:

        bot.add_view(
            DutyView()
        )

        print(
            "✅ DutyView betöltve."
        )

    except Exception as e:

        print(
            f"❌ DutyView hiba: {e}"
        )

    # Jelentkezési gombok
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

            prefix = (
                "FRAKCIOS_JELENTKEZES:"
            )

            if not channel.topic.startswith(
                prefix
            ):
                continue

            try:

                member_id = int(
                    channel.topic[
                        len(prefix):
                    ]
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

                print(
                    f"✅ Jelentkezési gomb betöltve: "
                    f"{channel.name}"
                )

            except Exception as e:

                print(
                    f"⚠️ Gomb betöltési hiba: "
                    f"{channel.name} | {e}"
                )

    _views_loaded = True

    print(
        "✅ Minden tartós gomb betöltve."
    )


# =========================================================
# 🟢 ON READY
# =========================================================

@bot.event
async def on_ready():

    print(
        f"🟢 BEJELENTKEZVE: {bot.user}"
    )

    print(
        f"🆔 Bot ID: {bot.user.id}"
    )

    print(
        f"🌐 Szerverek száma: {len(bot.guilds)}"
    )

    # Slash command sync
    await sync_guild_commands()

    # Persistent views
    await load_persistent_views()

    print(
        "🚀 BOT TELJESEN ELINDULT!"
    )


# =========================================================
# ❌ SLASH PARANCS HIBAKEZELÉS
# =========================================================

@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError
):

    print(
        f"❌ SLASH COMMAND HIBA: "
        f"{type(error).__name__}: {error}"
    )

    message = (
        "❌ Hiba történt a parancs végrehajtásakor.\n"
        "Nézd meg a Render logját a pontos hibáért."
    )

    try:

        if interaction.response.is_done():

            await interaction.followup.send(
                message,
                ephemeral=True
            )

        else:

            await interaction.response.send_message(
                message,
                ephemeral=True
            )

    except Exception as e:

        print(
            f"❌ Hibaüzenet küldési hiba: {e}"
        )


# =========================================================
# 🎁 /ajandek
# =========================================================

@bot.tree.command(
    name="ajandek",
    description="Nyereményjáték indítása"
)
@app_commands.describe(
    nyeremeny="Mi a nyeremény?"
)
async def ajandek(
    interaction: discord.Interaction,
    nyeremeny: str
):

    if not has_management_access(interaction):

        await interaction.response.send_message(
            "❌ Ezt csak a **Leader**, admin vagy "
            "szervertulajdonos használhatja!",
            ephemeral=True
        )

        return

    embed = discord.Embed(
        title="🎁 NYEREMÉNYJÁTÉK! 🎁",
        description=(
            f"**Nyeremény:** {nyeremeny}\n\n"
            "Kattints az alábbi gombra "
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
    description="Minden csatorna törlése"
)
async def remove_all(
    interaction: discord.Interaction
):

    guild = interaction.guild

    if guild is None:
        return

    if interaction.user.id != guild.owner_id:

        await interaction.response.send_message(
            "❌ Ezt kizárólag a szerver tulajdonosa használhatja!",
            ephemeral=True
        )

        return

    await interaction.response.send_message(
        "💣 **A szerver csatornáinak törlése megkezdődött...**",
        ephemeral=True
    )

    for channel in list(guild.channels):

        try:

            await channel.delete()

        except Exception as e:

            print(
                f"⚠️ Csatorna törlési hiba: "
                f"{channel.name} | {e}"
            )


# =========================================================
# 🧹 /clear
# =========================================================

@bot.tree.command(
    name="clear",
    description="Üzenetek törlése"
)
@app_commands.describe(
    mennyiseg="Hány üzenetet töröljön?"
)
async def clear_messages(
    interaction: discord.Interaction,
    mennyiseg: int = 100
):

    if not has_management_access(interaction):

        await interaction.response.send_message(
            "❌ Nincs jogosultságod az üzenetek törléséhez!",
            ephemeral=True
        )

        return

    if mennyiseg < 1:
        mennyiseg = 1

    if mennyiseg > 1000:
        mennyiseg = 1000

    await interaction.response.defer(
        ephemeral=True
    )

    try:

        deleted = await interaction.channel.purge(
            limit=mennyiseg
        )

        await interaction.followup.send(
            f"🧹 Sikeresen törölve "
            f"**{len(deleted)}** üzenet!",
            ephemeral=True
        )

    except Exception as e:

        await interaction.followup.send(
            f"⚠️ Hiba történt: `{e}`",
            ephemeral=True
        )


# =========================================================
# ⚡ /setup_frakcio
# =========================================================

@bot.tree.command(
    name="setup_frakcio",
    description="Teljes frakció Discord struktúra létrehozása"
)
async def setup_frakcio(
    interaction: discord.Interaction
):

    if not has_management_access(interaction):

        await interaction.response.send_message(
            "❌ Ezt csak a **Leader**, admin vagy "
            "szervertulajdonos használhatja!",
            ephemeral=True
        )

        return

    await interaction.response.defer()

    guild = interaction.guild

    if guild is None:
        return

    # =====================================================
    # 🎖️ RANGOK
    # =====================================================

    leader = discord.utils.get(
        guild.roles,
        name="Leader"
    )

    if leader is None:

        leader = await guild.create_role(
            name="Leader",
            color=discord.Color.red(),
            permissions=discord.Permissions(
                administrator=True
            )
        )

    subleader = discord.utils.get(
        guild.roles,
        name="Subleader"
    )

    if subleader is None:

        subleader = await guild.create_role(
            name="Subleader",
            color=discord.Color.orange()
        )

    tag = discord.utils.get(
        guild.roles,
        name="Frakciótag"
    )

    if tag is None:

        tag = await guild.create_role(
            name="Frakciótag",
            color=discord.Color.blue()
        )

    # =====================================================
    # 🔐 JOGOSULTSÁGOK
    # =====================================================

    overwrites_hidden = {

        guild.default_role:
            discord.PermissionOverwrite(
                view_channel=False
            ),

        tag:
            discord.PermissionOverwrite(
                view_channel=True
            ),

        leader:
            discord.PermissionOverwrite(
                view_channel=True
            ),

        subleader:
            discord.PermissionOverwrite(
                view_channel=True
            )
    }

    overwrites_admin = {

        guild.default_role:
            discord.PermissionOverwrite(
                view_channel=False
            ),

        leader:
            discord.PermissionOverwrite(
                view_channel=True
            ),

        subleader:
            discord.PermissionOverwrite(
                view_channel=True
            )
    }

    waiting_overwrites = {

        guild.default_role:
            discord.PermissionOverwrite(
                view_channel=False
            ),

        leader:
            discord.PermissionOverwrite(
                view_channel=True
            ),

        subleader:
            discord.PermissionOverwrite(
                view_channel=True
            )
    }

    # =====================================================
    # 🚪 VÁRÓTERMEK
    # =====================================================

    cat_varo = discord.utils.get(
        guild.categories,
        name="🚪 VÁRÓTERMEK"
    )

    if cat_varo is None:

        cat_varo = await guild.create_category(
            "🚪 VÁRÓTERMEK",
            overwrites=waiting_overwrites
        )

    else:

        await cat_varo.edit(
            overwrites=waiting_overwrites
        )

    # =====================================================
    # 📌 INFORMÁCIÓK
    # =====================================================

    cat_info = await guild.create_category(
        "📌 INFORMÁCIÓK",
        overwrites=overwrites_hidden
    )

    info_channels = [
        "👋-belépő",
        "📢-bejelentések",
        "📜-szabályzat",
        "🎖️-rangok-és-fizetések",
        "📝-minták-és-nyomtatványok",
        "🚗-járműpark-és-kulcsok",
        "❓-gyakori-kérdések"
    ]

    for name in info_channels:

        await cat_info.create_text_channel(
            name
        )

    # =====================================================
    # 💼 IC ÉLET
    # =====================================================

    cat_ic_elet = await guild.create_category(
        "💼 IC ÉLET",
        overwrites=overwrites_hidden
    )

    for name in [
        "💬-ic-chat",
        "📸-ic-fotók-és-kamera",
        "📝-szabadságkérelmek",
        "📋-ic-ötletek-és-reformok",
        "📂-ic-adatok"
    ]:

        await cat_ic_elet.create_text_channel(
            name
        )

    # =====================================================
    # 💭 OOC ÉLET
    # =====================================================

    cat_ooc = await guild.create_category(
        "💭 OOC ÉLET",
        overwrites=overwrites_hidden
    )

    for name in [
        "💭-ooc-chat",
        "📷-rp-élményképek",
        "💡-ötletek-és-javaslatok",
        "😂-mémek-és-offtopic"
    ]:

        await cat_ooc.create_text_channel(
            name
        )

    # =====================================================
    # 💼 IC MŰKÖDÉS & DUTY
    # =====================================================

    cat_ic = await guild.create_category(
        "💼 IC MŰKÖDÉS & DUTY",
        overwrites=overwrites_hidden
    )

    duty_chan = await cat_ic.create_text_channel(
        "⏰-duty-mérő"
    )

    await cat_ic.create_text_channel(
        "📋-szolgálati-napló"
    )

    await cat_ic.create_text_channel(
        "📦-frakció-széf-és-raktár"
    )

    await cat_ic.create_text_channel(
        "⚔️-akciók-és-tervek"
    )

    await cat_ic.create_text_channel(
        "🤝-diplomácia"
    )

    await cat_ic.create_text_channel(
        "💰-kassza-és-elszámolás"
    )

    embed_duty = discord.Embed(
        title="⏰ Szolgálati Idő Mérő",
        description=(
            "Használd az alábbi gombokat!\n\n"
            "🟢 **Duty Be**\n"
            "Szolgálat megkezdése\n\n"
            "🔴 **Duty Ki**\n"
            "Szolgálat befejezése\n\n"
            "📊 **Összidő**\n"
            "Összesített szolgálati idő"
        ),
        color=discord.Color.blue()
    )

    await duty_chan.send(
        embed=embed_duty,
        view=DutyView()
    )

    # =====================================================
    # 🔒 VEZETŐSÉG
    # =====================================================

    cat_vez = await guild.create_category(
        "🔒 VEZETŐSÉG",
        overwrites=overwrites_admin
    )

    for name in [
        "🔒-vezetőségi-chat",
        "📋-jelentkezések",
        "⚠️-figyelmeztetések",
        "🚫-feketelista",
        "📑-vezetőségi-jegyzetek"
    ]:

        await cat_vez.create_text_channel(
            name
        )

    # =====================================================
    # 🔊 HANGCSATORNÁK
    # =====================================================

    cat_voice = await guild.create_category(
        "🔊 HANGCSATORNÁK",
        overwrites=overwrites_hidden
    )

    for name in [
        "🔊 OOC Beszélgető 1",
        "🔊 OOC Beszélgető 2",
        "🔊 Rádió 1 [IC / RP]",
        "🔊 Rádió 2 [IC / RP]",
        "🔊 Akció / Taktikai 1",
        "🔊 Akció / Taktikai 2",
        "💤 AFK / Inaktív"
    ]:

        await cat_voice.create_voice_channel(
            name
        )

    await cat_voice.create_voice_channel(
        "🔒 Vezetőségi Tárgyaló",
        overwrites=overwrites_admin
    )

    await interaction.followup.send(
        "✅ **A teljes frakció szerverstruktúra sikeresen létrejött!**\n\n"
        "🎖️ Leader\n"
        "🎖️ Subleader\n"
        "🎖️ Frakciótag\n"
        "🚪 Várótermek\n"
        "📌 Információk\n"
        "💼 IC élet\n"
        "💭 OOC élet\n"
        "⏰ Duty rendszer\n"
        "🔒 Vezetőség\n"
        "🔊 Hangcsatornák",
        ephemeral=True
    )


# =========================================================
# 📢 /bejelentes
# =========================================================

@bot.tree.command(
    name="bejelentes",
    description="Hivatalos bejelentés küldése"
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

    if not has_management_access(interaction):

        await interaction.response.send_message(
            "❌ Nincs jogosultságod!",
            ephemeral=True
        )

        return

    chan = discord.utils.get(
        interaction.guild.text_channels,
        name="📢-bejelentések"
    )

    if chan is None:

        await interaction.response.send_message(
            "❌ Nem találom a 📢-bejelentések csatornát.",
            ephemeral=True
        )

        return

    embed = discord.Embed(
        title=f"📢 {cim}",
        description=uzenet,
        color=discord.Color.red()
    )

    embed.set_footer(
        text=f"Kiadta: {interaction.user.display_name}"
    )

    embed.timestamp = datetime.datetime.now()

    await chan.send(
        content="@everyone",
        embed=embed
    )

    await interaction.response.send_message(
        "✅ Bejelentés kiküldve!",
        ephemeral=True
    )


# =========================================================
# ⚠️ /warn
# =========================================================

@bot.tree.command(
    name="warn",
    description="Figyelmeztetés adása"
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

    if not has_management_access(interaction):

        await interaction.response.send_message(
            "❌ Nincs jogosultságod!",
            ephemeral=True
        )

        return

    warn_chan = discord.utils.get(
        interaction.guild.text_channels,
        name="⚠️-figyelmeztetések"
    )

    if warn_chan is None:

        await interaction.response.send_message(
            "❌ Nem találom a figyelmeztetések csatornát.",
            ephemeral=True
        )

        return

    embed = discord.Embed(
        title="⚠️ Frakció Figyelmeztetés",
        description=(
            f"**Kapta:** {tag.mention}\n"
            f"**Adta:** {interaction.user.mention}\n"
            f"**Indok:** {indok}"
        ),
        color=discord.Color.dark_red()
    )

    embed.timestamp = datetime.datetime.now()

    await warn_chan.send(
        embed=embed
    )

    try:

        await tag.send(
            "⚠️ **Figyelmeztetést kaptál a frakcióban!**\n"
            f"**Indok:** {indok}\n"
            f"**Adta:** {interaction.user.name}"
        )

    except Exception:
        pass

    await interaction.response.send_message(
        f"✅ Figyelmeztetés rögzítve: {tag.mention}",
        ephemeral=True
    )


# =========================================================
# 📢 /everyone
# =========================================================

@bot.tree.command(
    name="everyone",
    description="Üzenet küldése minden aktív váróterembe"
)
@app_commands.describe(
    uzenet="A kiküldendő üzenet"
)
async def everyone_cmd(
    interaction: discord.Interaction,
    uzenet: str
):

    if not has_management_access(interaction):

        await interaction.response.send_message(
            "❌ Nincs jogosultságod!",
            ephemeral=True
        )

        return

    cat_varo = discord.utils.get(
        interaction.guild.categories,
        name="🚪 VÁRÓTERMEK"
    )

    if (
        cat_varo is None
        or not cat_varo.text_channels
    ):

        await interaction.response.send_message(
            "⚠️ Jelenleg nincsenek nyitott várótermek!",
            ephemeral=True
        )

        return

    sent_count = 0

    for channel in cat_varo.text_channels:

        try:

            await channel.send(
                f"📢 **Leaderi közlemény "
                f"({interaction.user.mention}):**\n"
                f"{uzenet}"
            )

            sent_count += 1

        except Exception:
            pass

    await interaction.response.send_message(
        f"✅ Az üzenet kiküldve "
        f"**{sent_count}** váróterembe!",
        ephemeral=True
    )


# =========================================================
# 🏗️ FRAKCIÓ GENERÁTOR
# =========================================================

async def create_faction_structure(
    interaction: discord.Interaction,
    category_name: str,
    member_role_name: str,
    leader_role_name: str,
    member_color: discord.Color,
    leader_color: discord.Color,
    channels: list,
    success_name: str,
    icon: str
):

    guild = interaction.guild

    if guild is None:
        return

    if not has_admin_access(interaction):

        await interaction.response.send_message(
            "❌ Ezt csak **admin vagy a szerver tulajdonosa** "
            "használhatja!",
            ephemeral=True
        )

        return

    await interaction.response.defer(
        ephemeral=True
    )

    # =====================================================
    # 🎖️ RANG
    # =====================================================

    member_role = discord.utils.get(
        guild.roles,
        name=member_role_name
    )

    if member_role is None:

        member_role = await guild.create_role(
            name=member_role_name,
            color=member_color,
            reason=f"{success_name} frakció létrehozása"
        )

    leader_role = discord.utils.get(
        guild.roles,
        name=leader_role_name
    )

    if leader_role is None:

        leader_role = await guild.create_role(
            name=leader_role_name,
            color=leader_color,
            reason=f"{success_name} vezetőség létrehozása"
        )

    # =====================================================
    # 🔐 JOGOSULTSÁG
    # =====================================================

    overwrites = {

        guild.default_role:
            discord.PermissionOverwrite(
                view_channel=False
            ),

        member_role:
            discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
            ),

        leader_role:
            discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_messages=True
            )
    }

    # =====================================================
    # 📁 KATEGÓRIA
    # =====================================================

    category = discord.utils.get(
        guild.categories,
        name=category_name
    )

    if category is None:

        category = await guild.create_category(
            category_name,
            overwrites=overwrites,
            reason=f"{success_name} frakció létrehozása"
        )

    else:

        await category.edit(
            overwrites=overwrites
        )

    created = 0
    existing = 0

    # =====================================================
    # 📋 CSATORNÁK
    # =====================================================

    for channel_name, topic in channels:

        existing_channel = discord.utils.get(
            category.text_channels,
            name=channel_name
        )

        if existing_channel is not None:

            existing += 1
            continue

        await category.create_text_channel(
            name=channel_name,
            topic=topic,
            reason=f"{success_name} frakció"
        )

        created += 1

    await interaction.followup.send(
        f"{icon} **{success_name} frakció elkészült!**\n\n"
        f"📁 Kategória: {category.mention}\n"
        f"🎖️ Rang: **{member_role.name}**\n"
        f"👑 Vezetőség: **{leader_role.name}**\n"
        f"🆕 Új csatornák: **{created}**\n"
        f"📂 Már létezett: **{existing}**",
        ephemeral=True
    )


# =========================================================
# 🚓 /frakcio_rendor
# =========================================================

@bot.tree.command(
    name="frakcio_rendor",
    description="Rendőrségi frakció teljes Discord szerkezete"
)
async def frakcio_rendor(
    interaction: discord.Interaction
):

    channels = [

        (
            "📻-rádió",
            "Rendőrségi rádió / IC kommunikáció."
        ),

        (
            "📜-rádió-szabályzat",
            "Rádióhasználati és kommunikációs szabályzat."
        ),

        (
            "📘-rendőrségi-szabályzat",
            "A rendőrség általános szabályzata."
        ),

        (
            "🚔-járőr-információk",
            "Járőrözéshez szükséges információk."
        ),

        (
            "🚨-akciók",
            "Akciók, üldözések és taktikai műveletek."
        ),

        (
            "🚗-járműpark",
            "Rendőrségi járművek és egységek."
        ),

        (
            "🔫-felszerelés",
            "Szolgálati felszerelések és eszközök."
        ),

        (
            "📋-feladatok",
            "Aktuális rendőrségi feladatok."
        ),

        (
            "⚖️-bírságok-eljárások",
            "Bírságok és RP eljárások."
        ),

        (
            "📂-nyomozások",
            "Nyomozások és ügyek."
        ),

        (
            "📝-jelentések",
            "Szolgálati és intézkedési jelentések."
        ),

        (
            "📢-közlemények",
            "Vezetőségi közlemények."
        ),

        (
            "💬-rendőr-ooc",
            "Rendőrségi OOC beszélgetés."
        )
    ]

    await create_faction_structure(
        interaction=interaction,
        category_name="🚓 RENDŐRSÉG",
        member_role_name="🚓 Rendőr",
        leader_role_name="🚓 Rendőrség Vezetőség",
        member_color=discord.Color.blue(),
        leader_color=discord.Color.dark_blue(),
        channels=channels,
        success_name="Rendőrségi",
        icon="🚓"
    )


# =========================================================
# 🚑 /frakcio_mentos
# =========================================================

@bot.tree.command(
    name="frakcio_mentos",
    description="Mentőszolgálati frakció teljes Discord szerkezete"
)
async def frakcio_mentos(
    interaction: discord.Interaction
):

    channels = [

        (
            "📻-mentős-rádió",
            "Mentőszolgálati rádió / IC kommunikáció."
        ),

        (
            "📜-rádió-szabályzat",
            "Mentős rádiózási szabályzat."
        ),

        (
            "📘-mentős-szabályzat",
            "A mentőszolgálat általános szabályzata."
        ),

        (
            "🚑-szolgálati-információk",
            "Szolgálathoz szükséges információk."
        ),

        (
            "🏥-kórházi-információk",
            "Kórházi és betegellátási információk."
        ),

        (
            "🚨-riasztások",
            "Aktuális riasztások és kivonulások."
        ),

        (
            "🩺-felszerelés",
            "Orvosi felszerelések."
        ),

        (
            "🚑-járműpark",
            "Mentőautók és szolgálati járművek."
        ),

        (
            "📋-betegjelentések",
            "RP beteg- és esetjelentések."
        ),

        (
            "📝-szolgálati-jelentések",
            "Szolgálati jelentések."
        ),

        (
            "📢-közlemények",
            "Vezetőségi közlemények."
        ),

        (
            "💬-mentős-ooc",
            "Mentőszolgálati OOC beszélgetés."
        )
    ]

    await create_faction_structure(
        interaction=interaction,
        category_name="🚑 MENTŐSZOLGÁLAT",
        member_role_name="🚑 Mentős",
        leader_role_name="🚑 Mentőszolgálat Vezetőség",
        member_color=discord.Color.red(),
        leader_color=discord.Color.dark_red(),
        channels=channels,
        success_name="Mentőszolgálati",
        icon="🚑"
    )


# =========================================================
# 🔧 /frakcio_szerelo
# =========================================================

@bot.tree.command(
    name="frakcio_szerelo",
    description="Szerelő frakció teljes Discord szerkezete"
)
async def frakcio_szerelo(
    interaction: discord.Interaction
):

    channels = [

        (
            "📻-szerelő-rádió",
            "Szerelő rádió / IC kommunikáció."
        ),

        (
            "📜-szerelő-szabályzat",
            "Szerelői és rádiózási szabályzat."
        ),

        (
            "📘-műhely-szabályzat",
            "A műhely használatának szabályai."
        ),

        (
            "💰-szerelő-árlista",
            "Szerelői szolgáltatások és árlista."
        ),

        (
            "🔧-munkalapok",
            "Aktuális szerelési munkalapok."
        ),

        (
            "🚗-járművek",
            "Javítandó és elkészült járművek."
        ),

        (
            "🛠️-alkatrészek",
            "Alkatrészek és készletinformációk."
        ),

        (
            "📦-raktár",
            "Raktár és készlet."
        ),

        (
            "📋-munkajelentések",
            "Elvégzett munkák jelentései."
        ),

        (
            "💵-kassza-elszámolás",
            "Munkadíjak és kassza elszámolások."
        ),

        (
            "📢-közlemények",
            "Vezetőségi közlemények."
        ),

        (
            "💬-szerelő-ooc",
            "Szerelői OOC beszélgetés."
        )
    ]

    await create_faction_structure(
        interaction=interaction,
        category_name="🔧 SZERELŐ",
        member_role_name="🔧 Szerelő",
        leader_role_name="🔧 Szerelő Vezetőség",
        member_color=discord.Color.orange(),
        leader_color=discord.Color.dark_orange(),
        channels=channels,
        success_name="Szerelő",
        icon="🔧"
    )


# =========================================================
# 🚀 BOT INDÍTÁSA
# =========================================================

token = os.environ.get("DISCORD_TOKEN")

if not token:

    print(
        "❌ HIBA: A DISCORD_TOKEN környezeti változó nincs beállítva!"
    )

else:

    print(
        "🚀 Discord bot indítása..."
    )

    bot.run(
        token
    )
