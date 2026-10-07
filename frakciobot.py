import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import discord
from discord import app_commands
from discord.ext import commands
import datetime
import random

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

intents = discord.Intents.default()
intents.guilds = True
intents.message_content = True
intents.members = True

# Duty nyilvántartás (memóriában)
duty_start_times = {}   # Akkor fut, ha valaki duty-ban van: {user_id: datetime}
duty_total_seconds = {} # Összegyűjtött másodpercek: {user_id: seconds}

class FactionBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()

bot = FactionBot()

# 🎉 NYEREMÉNYJÁTÉK (GIVEAWAY) NÉZET ÉS GOMBOK
class GiveawayView(discord.ui.View):
    def __init__(self, prize: str, host: discord.Member):
        super().__init__(timeout=None)
        self.prize = prize
        self.host = host
        self.participants = set()

    # 🎉 Jelentkezés gomb
    @discord.ui.button(label="🎉 Jelentkezés (0)", style=discord.ButtonStyle.primary, custom_id="giveaway_join")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        
        if user_id in self.participants:
            self.participants.remove(user_id)
            button.label = f"🎉 Jelentkezés ({len(self.participants)})"
            await interaction.response.edit_message(view=self)
            await interaction.followup.send("❌ Visszavontad a jelentkezésedet a nyereményjátékra!", ephemeral=True)
        else:
            self.participants.add(user_id)
            button.label = f"🎉 Jelentkezés ({len(self.participants)})"
            await interaction.response.edit_message(view=self)
            await interaction.followup.send("🎉 **Sikeresen jelentkeztél a nyereményjátékra!** Sok szerencsét!", ephemeral=True)

    # 🎲 Sorsolás gomb (Csak Leadernek)
    @discord.ui.button(label="🎲 Sorsolás", style=discord.ButtonStyle.green, custom_id="giveaway_roll")
    async def roll_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        leader_role = discord.utils.get(interaction.guild.roles, name="Leader")
        is_leader = (leader_role and leader_role in interaction.user.roles) or interaction.user.guild_permissions.administrator or interaction.user.id == interaction.guild.owner_id
        
        if not is_leader:
            await interaction.response.send_message("❌ Ezt a gombot csak a **Leader** / Szervertulajdonos használhatja a sorsoláshoz!", ephemeral=True)
            return

        if not self.participants:
            await interaction.response.send_message("⚠️ Nem jelentkezett senki a nyereményjátékra, így nem lehet sorsolni!", ephemeral=True)
            return

        winner_id = random.choice(list(self.participants))
        winner = interaction.guild.get_member(winner_id)

        # Gombok letiltása a sorsolás után
        for child in self.children:
            child.disabled = True

        embed = interaction.message.embeds[0]
        embed.title = "🎉 NYEREMÉNYJÁTÉK VÉGET ÉRT 🎉"
        embed.color = discord.Color.gold()
        embed.add_field(name="🏆 Nyertes:", value=winner.mention if winner else f"<@{winner_id}>", inline=False)

        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.channel.send(f"🎊 **GRATULÁLUNK!** {winner.mention if winner else f'<@{winner_id}>'} megnyerte a következőt: **{self.prize}**!")

# ⏱️ DUTY MÉRŐ GOMBOK
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

        await interaction.response.send_message(f"🔴 **Kiléptél a szolgálatból!** A mostani szolgálatod ideje: **{time_str}**", ephemeral=True)

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
            description=f"**Tag:** {interaction.user.mention}\n\n**Összesített szolgálati időd:**\n⏱️ **{hours} óra {minutes} perc {seconds} másodperc**\n\n{status_text}",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

```python
# 🔘 ELFOGADÁS GOMB A JELENTKEZÉSEKHEZ
class AcceptView(discord.ui.View):
    def __init__(self, member_id, waiting_channel_id):
        super().__init__(timeout=None)
        self.member_id = member_id
        self.waiting_channel_id = waiting_channel_id

    @discord.ui.button(
        label="✅ Elfogadás (Szerver megnyitása)",
        style=discord.ButtonStyle.green,
        custom_id="accept_member"
    )
    async def accept_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        guild = interaction.guild

        if guild is None:
            await interaction.response.send_message(
                "❌ Ez a gomb csak Discord szerveren használható.",
                ephemeral=True
            )
            return

        # Csak Leader / Admin / Szervertulajdonos használhatja
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
                "❌ Ezt csak a **Leader**, admin vagy a szerver tulajdonosa használhatja!",
                ephemeral=True
            )
            return

        # Megkeressük a jelentkező tagot
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

        # Megkeressük a Frakciótag rangot
        role = discord.utils.get(
            guild.roles,
            name="Frakciótag"
        )

        if role is None:
            await interaction.response.send_message(
                "❌ Nem találom a **Frakciótag** szerepkört!\n"
                "Hozd létre Discordon, vagy futtasd le újra a `/setup_frakcio` parancsot.",
                ephemeral=True
            )
            return

        # A bot saját legmagasabb szerepköre
        bot_member = guild.me

        if bot_member is None:
            await interaction.response.send_message(
                "❌ Nem sikerült lekérni a bot jogosultságait.",
                ephemeral=True
            )
            return

        bot_top_role = bot_member.top_role

        # Ellenőrizzük a szerepkör-hierarchiát
        if role >= bot_top_role:
            await interaction.response.send_message(
                "❌ **Nem tudom kiosztani a Frakciótag rangot!**\n\n"
                "Discordban menj ide:\n"
                "**Szerverbeállítások → Szerepkörök**\n\n"
                "A bot szerepkörét húzd a **Frakciótag** szerepkör FÖLÉ.\n\n"
                f"Bot legmagasabb rangja: **{bot_top_role.name}**\n"
                f"Kiosztandó rang: **{role.name}**",
                ephemeral=True
            )
            return

        # Ellenőrizzük, hogy a botnak van-e Manage Roles joga
        if not bot_member.guild_permissions.manage_roles:
            await interaction.response.send_message(
                "❌ A botnak nincs **Szerepkörök kezelése (Manage Roles)** jogosultsága!",
                ephemeral=True
            )
            return

        # Ha már megvan a rang
        if role in member.roles:
            await interaction.response.send_message(
                f"⚠️ {member.mention} már rendelkezik a **Frakciótag** ranggal.",
                ephemeral=True
            )
            return

        # Először válaszolunk az interactionre
        # Így akkor sem lesz Unknown Message,
        # ha az eredeti jelentkezési üzenet közben megváltozott.
        await interaction.response.send_message(
            f"⏳ {member.mention} elfogadása folyamatban..."
        )

        # Rang kiosztása
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

        # Sikeres felvétel
        await interaction.followup.send(
            f"✅ **{member.mention} sikeresen fel lett véve a frakcióba!**\n"
            f"👤 Elfogadta: {interaction.user.mention}\n"
            f"🎖️ Megkapta: **{role.name}**"
        )

        # Privát üzenet a tagnak
        try:
            await member.send(
                "🎉 **Sikeres felvétel!**\n\n"
                f"A Leader ({interaction.user.display_name}) elfogadta "
                "a jelentkezésedet.\n"
                "Most már láthatod a frakció teljes szerverét."
            )
        except discord.Forbidden:
            # Ha a játékosnál tiltva vannak a DM-ek,
            # attól még a felvétel sikeres.
            pass

        # Váróterem törlése
        waiting_channel = guild.get_channel(self.waiting_channel_id)

        if waiting_channel is not None:
            try:
                await waiting_channel.delete(
                    reason=f"Frakcióba felvett tag: {member}"
                )
            except discord.Forbidden:
                await interaction.followup.send(
                    "⚠️ A tag felvétele sikerült, de a privát várótermet "
                    "nem tudtam törölni. A botnak nincs megfelelő "
                    "csatornakezelési jogosultsága."
                )
            except discord.NotFound:
                # Már törölve lett, nincs probléma.
                pass
            except discord.HTTPException:
                pass

        # A gomb kikapcsolása
        button.disabled = True
        button.label = "✅ Elfogadva"

        try:
            await interaction.message.edit(view=self)
        except (discord.NotFound, discord.HTTPException):
            # Ha az eredeti jelentkezési üzenet már nem létezik,
            # nem állítjuk le emiatt a folyamatot.
            pass
```
```python
# 🔘 ELFOGADÁS GOMB A JELENTKEZÉSEKHEZ
class AcceptView(discord.ui.View):
    def __init__(self, member_id, waiting_channel_id):
        super().__init__(timeout=None)
        self.member_id = member_id
        self.waiting_channel_id = waiting_channel_id

    @discord.ui.button(
        label="✅ Elfogadás (Szerver megnyitása)",
        style=discord.ButtonStyle.green,
        custom_id="accept_member"
    )
    async def accept_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        guild = interaction.guild

        if guild is None:
            await interaction.response.send_message(
                "❌ Ez a gomb csak Discord szerveren használható.",
                ephemeral=True
            )
            return

        # Csak Leader / Admin / Szervertulajdonos használhatja
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
                "❌ Ezt csak a **Leader**, admin vagy a szerver tulajdonosa használhatja!",
                ephemeral=True
            )
            return

        # Megkeressük a jelentkező tagot
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

        # Megkeressük a Frakciótag rangot
        role = discord.utils.get(
            guild.roles,
            name="Frakciótag"
        )

        if role is None:
            await interaction.response.send_message(
                "❌ Nem találom a **Frakciótag** szerepkört!\n"
                "Hozd létre Discordon, vagy futtasd le újra a `/setup_frakcio` parancsot.",
                ephemeral=True
            )
            return

        # A bot saját legmagasabb szerepköre
        bot_member = guild.me

        if bot_member is None:
            await interaction.response.send_message(
                "❌ Nem sikerült lekérni a bot jogosultságait.",
                ephemeral=True
            )
            return

        bot_top_role = bot_member.top_role

        # Ellenőrizzük a szerepkör-hierarchiát
        if role >= bot_top_role:
            await interaction.response.send_message(
                "❌ **Nem tudom kiosztani a Frakciótag rangot!**\n\n"
                "Discordban menj ide:\n"
                "**Szerverbeállítások → Szerepkörök**\n\n"
                "A bot szerepkörét húzd a **Frakciótag** szerepkör FÖLÉ.\n\n"
                f"Bot legmagasabb rangja: **{bot_top_role.name}**\n"
                f"Kiosztandó rang: **{role.name}**",
                ephemeral=True
            )
            return

        # Ellenőrizzük, hogy a botnak van-e Manage Roles joga
        if not bot_member.guild_permissions.manage_roles:
            await interaction.response.send_message(
                "❌ A botnak nincs **Szerepkörök kezelése (Manage Roles)** jogosultsága!",
                ephemeral=True
            )
            return

        # Ha már megvan a rang
        if role in member.roles:
            await interaction.response.send_message(
                f"⚠️ {member.mention} már rendelkezik a **Frakciótag** ranggal.",
                ephemeral=True
            )
            return

        # Először válaszolunk az interactionre
        # Így akkor sem lesz Unknown Message,
        # ha az eredeti jelentkezési üzenet közben megváltozott.
        await interaction.response.send_message(
            f"⏳ {member.mention} elfogadása folyamatban..."
        )

        # Rang kiosztása
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

        # Sikeres felvétel
        await interaction.followup.send(
            f"✅ **{member.mention} sikeresen fel lett véve a frakcióba!**\n"
            f"👤 Elfogadta: {interaction.user.mention}\n"
            f"🎖️ Megkapta: **{role.name}**"
        )

        # Privát üzenet a tagnak
        try:
            await member.send(
                "🎉 **Sikeres felvétel!**\n\n"
                f"A Leader ({interaction.user.display_name}) elfogadta "
                "a jelentkezésedet.\n"
                "Most már láthatod a frakció teljes szerverét."
            )
        except discord.Forbidden:
            # Ha a játékosnál tiltva vannak a DM-ek,
            # attól még a felvétel sikeres.
            pass

        # Váróterem törlése
        waiting_channel = guild.get_channel(self.waiting_channel_id)

        if waiting_channel is not None:
            try:
                await waiting_channel.delete(
                    reason=f"Frakcióba felvett tag: {member}"
                )
            except discord.Forbidden:
                await interaction.followup.send(
                    "⚠️ A tag felvétele sikerült, de a privát várótermet "
                    "nem tudtam törölni. A botnak nincs megfelelő "
                    "csatornakezelési jogosultsága."
                )
            except discord.NotFound:
                # Már törölve lett, nincs probléma.
                pass
            except discord.HTTPException:
                pass

        # A gomb kikapcsolása
        button.disabled = True
        button.label = "✅ Elfogadva"

        try:
            await interaction.message.edit(view=self)
        except (discord.NotFound, discord.HTTPException):
            # Ha az eredeti jelentkezési üzenet már nem létezik,
            # nem állítjuk le emiatt a folyamatot.
            pass
```


# 🎁 /ajandek (NYEREMÉNYJÁTÉK PARANCS)
@bot.tree.command(name="ajandek", description="Nyereményjáték (Giveaway) indítása gombbal")
@app_commands.describe(nyeremeny="Mi a nyeremény? (Pl. VIP rang, $100.000, Fegyver)")
async def ajandek(interaction: discord.Interaction, nyeremeny: str):
    leader_role = discord.utils.get(interaction.guild.roles, name="Leader")
    if (not leader_role or leader_role not in interaction.user.roles) and not interaction.user.guild_permissions.administrator and interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("❌ Ezt a parancsot csak a **Leader** / Szervertulajdonos használhatja!", ephemeral=True)
        return

    embed = discord.Embed(
        title="🎁 NYEREMÉNYJÁTÉK! 🎁",
        description=f"**Nyeremény:** {nyeremeny}\n\nKattints az alábbi **🎉 Jelentkezés** gombra a részvételhez!",
        color=discord.Color.purple()
    )
    embed.set_footer(text=f"Indította: {interaction.user.display_name}")
    embed.timestamp = datetime.datetime.now()

    view = GiveawayView(prize=nyeremeny, host=interaction.user)
    await interaction.response.send_message(embed=embed, view=view)

# 👑 /remove (CSAK A SZERVER TULAJDONOSA/KÉSZÍTŐJE HASZNÁLHATJA)
@bot.tree.command(name="remove", description="MINDEN csatorna, hangcsatorna és kategória törlése (Csak Szervertulajdonosnak)")
async def remove_all(interaction: discord.Interaction):
    if interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("❌ Ezt a parancsot **kizárólag a szerver tulajdonosa (készítője)** használhatja!", ephemeral=True)
        return

    await interaction.response.send_message("💣 **A szerver összes csatornájának törlése megkezdődött...**", ephemeral=True)

    guild = interaction.guild
    for channel in list(guild.channels):
        try:
            await channel.delete()
        except Exception:
            pass

# 🧹 /clear (Üzenetek törlése)
@bot.tree.command(name="clear", description="Üzenetek törlése az adott csatornából")
@app_commands.describe(mennyiseg="Hány üzenetet töröljön a bot? (Alapértelmezett: 100)")
async def clear_messages(interaction: discord.Interaction, mennyiseg: int = 100):
    leader_role = discord.utils.get(interaction.guild.roles, name="Leader")
    
    if (not leader_role or leader_role not in interaction.user.roles) and not interaction.user.guild_permissions.administrator and interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("❌ Nincs jogosultságod az üzenetek törléséhez!", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    
    try:
        deleted = await interaction.channel.purge(limit=mennyiseg)
        await interaction.followup.send(f"🧹 Sikeresen törölve **{len(deleted)}** üzenet!", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"⚠️ Hiba történt a törlés során: {e}", ephemeral=True)

# ⚡ /setup_frakcio
@bot.tree.command(name="setup_frakcio", description="Teljes, kibővített frakció szerkezet kiépítése")
async def setup_frakcio(interaction: discord.Interaction):
    leader_role = discord.utils.get(interaction.guild.roles, name="Leader")
    
    if (not leader_role or leader_role not in interaction.user.roles) and not interaction.user.guild_permissions.administrator and interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("❌ Ezt a parancsot csak a **Leader** ranggal rendelkező személyek használhatják!", ephemeral=True)
        return

    await interaction.response.defer()
    guild = interaction.guild

    leader = leader_role or await guild.create_role(name="Leader", color=discord.Color.red(), permissions=discord.Permissions(administrator=True))
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

    await guild.create_category("🚪 VÁRÓTERMEK")

    # 1. INFORMÁCIÓK
    cat_info = await guild.create_category("📌 INFORMÁCIÓK", overwrites=overwrites_hidden)
    await cat_info.create_text_channel("📢-bejelentések")
    await cat_info.create_text_channel("📜-szabályzat")
    await cat_info.create_text_channel("🎖️-rangok-és-fizetések")
    await cat_info.create_text_channel("📝-minták-és-nyomtatványok")
    await cat_info.create_text_channel("🚗-járműpark-és-kulcsok")
    await cat_info.create_text_channel("❓-gyakori-kérdések")

    # 2. IC ÉLET
    cat_ic_elet = await guild.create_category("💼 IC ÉLET", overwrites=overwrites_hidden)
    await cat_ic_elet.create_text_channel("💬-ic-chat")
    await cat_ic_elet.create_text_channel("📸-ic-fotók-és-kamera")
    await cat_ic_elet.create_text_channel("📝-szabadságkérelmek")
    await cat_ic_elet.create_text_channel("📋-ic-ötletek-és-reformok")
    await cat_ic_elet.create_text_channel("📂-ic-adatok")

    # 3. OOC ÉLET
    cat_ooc = await guild.create_category("💭 OOC ÉLET", overwrites=overwrites_hidden)
    await cat_ooc.create_text_channel("💭-ooc-chat")
    await cat_ooc.create_text_channel("📷-rp-élményképek")
    await cat_ooc.create_text_channel("💡-ötletek-és-javaslatok")
    await cat_ooc.create_text_channel("😂-mémek-és-offtopic")

    # 4. IC MŰKÖDÉS & DUTY
    cat_ic = await guild.create_category("💼 IC MŰKÖDÉS & DUTY", overwrites=overwrites_hidden)
    duty_chan = await cat_ic.create_text_channel("⏰-duty-mérő")
    await cat_ic.create_text_channel("📋-szolgálati-napló")
    await cat_ic.create_text_channel("📦-frakció-széf-és-raktár")
    await cat_ic.create_text_channel("⚔️-akciók-és-tervek")
    await cat_ic.create_text_channel("🤝-diplomácia")
    await cat_ic.create_text_channel("💰-kassza-és-elszámolás")

    embed_duty = discord.Embed(
        title="⏰ Szolgálati Idő Mérő (Duty)",
        description="Használd az alábbi gombokat a szolgálatba lépéshez, kilépéshez és az összidőd ellenőrzéséhez!\n\n🟢 **Duty Be** - Szolgálat megkezdése\n🔴 **Duty Ki** - Szolgálat befejezése\n📊 **Összidő** - Eddigi összesített időd lekérése",
        color=discord.Color.blue()
    )
    await duty_chan.send(embed=embed_duty, view=DutyView())

    # 5. VEZETŐSÉG (Privát)
    cat_vez = await guild.create_category("🔒 VEZETŐSÉG", overwrites=overwrites_admin)
    await cat_vez.create_text_channel("🔒-vezetőségi-chat")
    await cat_vez.create_text_channel("📋-jelentkezések")
    await cat_vez.create_text_channel("⚠️-figyelmeztetések")
    await cat_vez.create_text_channel("🚫-feketelista")
    await cat_vez.create_text_channel("📑-vezetőségi-jegyzetek")

    # 6. HANGCSATORNÁK
    cat_voice = await guild.create_category("🔊 HANGCSATORNÁK", overwrites=overwrites_hidden)
    await cat_voice.create_voice_channel("🔊 OOC Beszélgető 1")
    await cat_voice.create_voice_channel("🔊 OOC Beszélgető 2")
    await cat_voice.create_voice_channel("🔊 Rádió 1 [IC / RP]")
    await cat_voice.create_voice_channel("🔊 Rádió 2 [IC / RP]")
    await cat_voice.create_voice_channel("🔊 Akció / Taktikai 1")
    await cat_voice.create_voice_channel("🔊 Akció / Taktikai 2")
    await cat_voice.create_voice_channel("💤 AFK / Inaktív")
    await cat_voice.create_voice_channel("🔒 Vezetőségi Tárgyaló", overwrites=overwrites_admin)

    await interaction.followup.send("✅ A szerverstruktúra sikeresen frissítve az új csatornákkal!")

# ⚡ /bejelentes
@bot.tree.command(name="bejelentes", description="Hivatalos bejelentés kiküldése a bejelentések csatornába")
@app_commands.describe(cim="A bejelentés címe", uzenet="A bejelentés szövege")
async def bejelentes(interaction: discord.Interaction, cim: str, uzenet: str):
    leader_role = discord.utils.get(interaction.guild.roles, name="Leader")
    if (not leader_role or leader_role not in interaction.user.roles) and not interaction.user.guild_permissions.administrator and interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("❌ Ezt csak a **Leader** használhatja!", ephemeral=True)
        return

    chan = discord.utils.get(interaction.guild.text_channels, name="📢-bejelentések")
    if chan:
        embed = discord.Embed(title=f"📢 {cim}", description=uzenet, color=discord.Color.red())
        embed.set_footer(text=f"Kiadta: {interaction.user.display_name}")
        embed.timestamp = datetime.datetime.now()
        await chan.send(content="@everyone", embed=embed)
        await interaction.response.send_message("✅ Bejelentés kiküldve!", ephemeral=True)

# ⚡ /warn
@bot.tree.command(name="warn", description="Figyelmeztetés (Warn) adása egy tagnak")
@app_commands.describe(tag="A figyelmeztetett tag", indok="A figyelmeztetés indoka")
async def warn(interaction: discord.Interaction, tag: discord.Member, indok: str):
    leader_role = discord.utils.get(interaction.guild.roles, name="Leader")
    if (not leader_role or leader_role not in interaction.user.roles) and not interaction.user.guild_permissions.administrator and interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("❌ Ezt csak a **Leader** használhatja!", ephemeral=True)
        return

    warn_chan = discord.utils.get(interaction.guild.text_channels, name="⚠️-figyelmeztetések")
    if warn_chan:
        embed = discord.Embed(
            title="⚠️ Frakció Figyelmeztetés (Warn)",
            description=f"**Kaptat:** {tag.mention}\n**Adta:** {interaction.user.mention}\n**Indok:** {indok}",
            color=discord.Color.dark_red()
        )
        embed.timestamp = datetime.datetime.now()
        await warn_chan.send(embed=embed)
        
        try:
            await tag.send(f"⚠️ **Figyelmeztetést (Warn) kaptál a frakcióban!**\n**Indok:** {indok}\n**Adta:** {interaction.user.name}")
        except Exception:
            pass

        await interaction.response.send_message(f"✅ Figyelmeztetés rögzítve neki: {tag.mention}", ephemeral=True)

# ⚡ /everyone
@bot.tree.command(name="everyone", description="Üzenet kiküldése az összes aktív egyéni váróterembe")
@app_commands.describe(uzenet="A kiküldendő üzenet szövege")
async def everyone_cmd(interaction: discord.Interaction, uzenet: str):
    leader_role = discord.utils.get(interaction.guild.roles, name="Leader")
    if (not leader_role or leader_role not in interaction.user.roles) and not interaction.user.guild_permissions.administrator and interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("❌ Ezt csak a **Leader** használhatja!", ephemeral=True)
        return

    cat_varo = discord.utils.get(interaction.guild.categories, name="🚪 VÁRÓTERMEK")
    if not cat_varo or not cat_varo.text_channels:
        await interaction.response.send_message("⚠️ Jelenleg nincsenek nyitott egyéni várótermek!", ephemeral=True)
        return

    sent_count = 0
    for channel in cat_varo.text_channels:
        try:
            await channel.send(f"📢 **Leaderi közlemény ({interaction.user.mention}):**\n{uzenet}")
            sent_count += 1
        except Exception:
            pass

    await interaction.response.send_message(f"✅ Az üzenet sikeresen kiküldve **{sent_count}** váróterembe!", ephemeral=True)

bot.run(os.environ["DISCORD_TOKEN"])
