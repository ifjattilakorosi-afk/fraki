import os
import discord
from discord import app_commands
from discord.ext import commands
import datetime
import random

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

# 🔘 ELFOGADÁS GOMB A JELENTKEZÉSEKHEZ
class AcceptView(discord.ui.View):
    def __init__(self, member_id, waiting_channel_id):
        super().__init__(timeout=None)
        self.member_id = member_id
        self.waiting_channel_id = waiting_channel_id

    @discord.ui.button(label="✅ Elfogadás (Szerver megnyitása)", style=discord.ButtonStyle.green)
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        leader_role = discord.utils.get(interaction.guild.roles, name="Leader")
        
        if (not leader_role or leader_role not in interaction.user.roles) and not interaction.user.guild_permissions.administrator and interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message("❌ Ezt csak a **Leader** ranggal rendelkező személyek tehetik meg!", ephemeral=True)
            return

        guild = interaction.guild
        member = guild.get_member(self.member_id)
        role = discord.utils.get(guild.roles, name="Frakciótag")

        if member and role:
            await member.add_roles(role)
            try:
                await member.send("🎉 **Sikeres felvétel!** A Leader elfogadta a jelentkezésedet, most már láthatod a frakció teljes szerverét!")
            except discord.Forbidden:
                pass

        waiting_channel = guild.get_channel(self.waiting_channel_id)
        if waiting_channel:
            await waiting_channel.delete()

        await interaction.response.edit_message(
            content=f"✅ **{member.mention if member else 'A játékos'}** el lett fogadva {interaction.user.mention} által! A privát váróterme törölve lett.",
            embed=None,
            view=None
        )

@bot.event
async def on_ready():
    print(f"✅ Bot elindult mint: {bot.user}")

# 🚪 ÚJ TAG BELÉPÉSE: EGYÉNI VÁRÓTEREM
@bot.event
async def on_member_join(member):
    guild = member.guild
    cat_varo = discord.utils.get(guild.categories, name="🚪 VÁRÓTERMEK") or await guild.create_category("🚪 VÁRÓTERMEK")
    leader_role = discord.utils.get(guild.roles, name="Leader")

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        member: discord.PermissionOverwrite(view_channel=True, send_messages=True),
    }
    if leader_role:
        overwrites[leader_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

    chan_name = f"váró-{member.name}".lower().replace(" ", "-")
    user_chan = await guild.create_text_channel(chan_name, category=cat_varo, overwrites=overwrites)

    await user_chan.send(f"Üdvözlünk {member.mention}! Ez a te privát várótermed. Kérlek várj türelemmel, amíg a Leader felveszi veled a kapcsolatot!")

    app_chan = discord.utils.get(guild.text_channels, name="📋-jelentkezések")
    if app_chan:
        embed = discord.Embed(
            title="🔔 Új tag várakozik!",
            description=f"**Tag:** {member.mention}\n**Privát váróterme:** {user_chan.mention}",
            color=discord.Color.gold()
        )
        await app_chan.send(embed=embed, view=AcceptView(member.id, user_chan.id))

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
