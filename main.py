import asyncio
import datetime
import json
import os
import itertools
import random
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
from flask import Flask
from threading import Thread

# ==========================================
# 1. AYARLAR VE BAŞLANGIÇ YAPILANDIRMASI
# ==========================================

load_dotenv()
TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

VERI_DOSYASI = "ekonomi.json"
YASAKLI_KELIMELER = ["annesiz", "orospuçocuğu", "oç", "oe"]
TETIKLEYICI_KANAL = "➕ | Oda Oluştur"
DEVAM_EDEN_AVIATORLER = set()
GECERLI_MESLEKLER = ["police", "pilot", "doctor"]

# Rich Presence Durum Döngüsü
richie_rich_durumlari = itertools.cycle([
    "Rulet Oynuyor 🎰",
    "Blackjack Oynuyor 🃏",
    "Aviator Oynuyor ✈️"
])


# ==========================================
# 2. DOSYA TABANLI EKONOMİ & VERİ YÖNETİMİ
# ==========================================

def verileri_yukle():
    if os.path.exists(VERI_DOSYASI):
        try:
            with open(VERI_DOSYASI, "r", encoding="utf-8") as f:
                veriler = json.load(f)
                
                coinler = {int(k): v["bakiye"] for k, v in veriler.items() if "bakiye" in v}
                sureler = {}
                meslekler_veri = {}
                seviye_veri = {}
                
                for k, v in veriler.items():
                    user_id_str = str(k)
                    user_id_int = int(k)
                    
                    if v.get("son_gunluk"):
                        sureler[user_id_int] = datetime.datetime.fromisoformat(v["son_gunluk"])
                    
                    if v.get("meslek_bilgi"):
                        meslekler_veri[user_id_str] = v["meslek_bilgi"]
                        
                    # Seviye ve Görev Verileri
                    seviye_veri[user_id_str] = {
                        "xp": v.get("xp", 0),
                        "level": v.get("level", 1),
                        "gunluk_level": v.get("gunluk_level", 0),
                        "son_sifirlama": v.get("son_sifirlama", str(datetime.date.today())),
                        "gorevler": v.get("gorevler", {"mesaj": 0, "polis": 0, "ses": 0, "gonder": 0, "rulet": 0})
                    }
                        
                return coinler, sureler, meslekler_veri, seviye_veri
        except Exception as e:
            print(f"⚠️ Veri yüklenirken hata oluştu: {e}")
            
    return {}, {}, {}, {}


def verileri_kaydet():
    veriler = {}
    tum_idler = set(
        list(COINLER.keys()) + 
        [int(k) for k in GUNLUK_SURELER.keys()] + 
        [int(k) for k in MESLEKLER_VERI.keys() if str(k).isdigit()] +
        [int(k) for k in SEVIYE_VERI.keys() if str(k).isdigit()]
    )
    
    for user_id in tum_idler:
        user_id_str = str(user_id)
        veriler[user_id_str] = {
            "bakiye": COINLER.get(user_id, 0),
            "son_gunluk": GUNLUK_SURELER[user_id].isoformat() if user_id in GUNLUK_SURELER else None,
            "meslek_bilgi": MESLEKLER_VERI.get(user_id_str, {}),
            "xp": SEVIYE_VERI.get(user_id_str, {}).get("xp", 0),
            "level": SEVIYE_VERI.get(user_id_str, {}).get("level", 1),
            "gunluk_level": SEVIYE_VERI.get(user_id_str, {}).get("gunluk_level", 0),
            "son_sifirlama": SEVIYE_VERI.get(user_id_str, {}).get("son_sifirlama", str(datetime.date.today())),
            "gorevler": SEVIYE_VERI.get(user_id_str, {}).get("gorevler", {"mesaj": 0, "polis": 0, "ses": 0, "gonder": 0, "rulet": 0})
        }

    with open(VERI_DOSYASI, "w", encoding="utf-8") as f:
        json.dump(veriler, f, ensure_ascii=False, indent=4)


# Belleğe verileri alma
COINLER, GUNLUK_SURELER, MESLEKLER_VERI, SEVIYE_VERI = verileri_yukle()


def bakiye_al(user_id):
    if user_id not in COINLER:
        COINLER[user_id] = 500
        verileri_kaydet()
    return COINLER[user_id]


def kullanici_veri_al(user_id):
    user_id_str = str(user_id)
    bugun = str(datetime.date.today())
    if user_id_str not in SEVIYE_VERI:
        SEVIYE_VERI[user_id_str] = {
            "xp": 0, "level": 1, "gunluk_level": 0, "son_sifirlama": bugun,
            "gorevler": {"mesaj": 0, "polis": 0, "ses": 0, "gonder": 0, "rulet": 0}
        }
    else:
        if SEVIYE_VERI[user_id_str].get("son_sifirlama") != bugun:
            SEVIYE_VERI[user_id_str]["son_sifirlama"] = bugun
            SEVIYE_VERI[user_id_str]["gunluk_level"] = 0
            SEVIYE_VERI[user_id_str]["gorevler"] = {"mesaj": 0, "polis": 0, "ses": 0, "gonder": 0, "rulet": 0}
    return SEVIYE_VERI[user_id_str]


# ==========================================
# 3. TASKS & BOT EVENTS (ETKİNLİKLER)
# ==========================================

@tasks.loop(minutes=10)
async def durumu_guncelle():
    yeni_durum = next(richie_rich_durumlari)
    await bot.change_presence(activity=discord.Game(name=yeni_durum))


@bot.event
async def on_ready():
    print(f"✅ {bot.user.name} olarak başarıyla giriş yapıldı!")
    bot.add_view(OdaYonimView())
    if not durumu_guncelle.is_running():
        durumu_guncelle.start()


async def xp_ekle(message, miktar):
    veri = kullanici_veri_al(message.author.id)
    
    # Günlük level sınırı kontrolü (Günlük 5 level limitine ulaşıldıysa XP artışını tamamen durdur)
    if veri["gunluk_level"] >= 5:
        return

    veri["xp"] += miktar
    
    while veri["xp"] >= 100:
        if veri["gunluk_level"] >= 5:
            veri["xp"] = 100
            break
            
        veri["xp"] -= 100
        veri["level"] += 1
        veri["gunluk_level"] += 1
        yeni_level = veri["level"]
        
        odul_mesaji = ""
        if yeni_level in [5, 15, 25, 35, 45]:
            bakiye_al(message.author.id)
            COINLER[message.author.id] += 1000
            odul_mesaji = "🎁 **Level Reward / Seviye Ödülü:** Mystery Box opened (`1,000 Coin`)!"
        else:
            bakiye_al(message.author.id)
            COINLER[message.author.id] += 500
            odul_mesaji = "💰 **Level Reward / Seviye Ödülü:** `+500 Coin` added!"

        # İngilizce Seviye Rolleri Otomatik Atama
        rutbe_rolleri = {10: "Copper", 20: "Silver", 30: "Gold", 40: "Emerald", 50: "Diamond"}
        if yeni_level in rutbe_rolleri:
            rol_adi = rutbe_rolleri[yeni_level]
            rol = discord.utils.get(message.guild.roles, name=rol_adi)
            if rol and rol not in message.author.roles:
                try:
                    await message.author.add_roles(rol)
                    odul_mesaji += f"\n🏆 **Rank Up:** `{rol_adi}` role assigned!"
                except Exception as e:
                    print(f"Rol verme hatası: {e}")

        verileri_kaydet()
        
        embed = discord.Embed(
            title="🚀 LEVEL UP! / SEVIYE ATLADINIZ!",
            description=f"Congratulations {message.author.mention}, you reached **Level {yeni_level}**!\n\nTebrikler, **{yeni_level}. Seviye** oldunuz!\n\n{odul_mesaji}",
            color=discord.Color.gold()
        )
        await message.channel.send(embed=embed)


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    mesaj_icerik = message.content.lower()

    # 1. Küfür Filtresi
    for kelime in YASAKLI_KELIMELER:
        if kelime in mesaj_icerik:
            try:
                await message.delete()
                sure = datetime.timedelta(minutes=1)
                await message.author.timeout(sure, reason="Yasaklı kelime (küfür) kullanımı.")
                await message.author.send(
                    f"⚠️ Merhaba **{message.author.name}**, sunucumuzda uygunsuz kelimeler "
                    f"kullanmamalısınız. Bu sebeple **1 dakika** mutelendiniz."
                )

                mod_kanal = discord.utils.get(message.guild.text_channels, name="bot-moderasyon")
                if mod_kanal:
                    embed = discord.Embed(
                        title="🚨 Otomatik Mute Logu",
                        color=discord.Color.orange(),
                        timestamp=datetime.datetime.now(),
                    )
                    embed.add_field(name="Ceza Alan Üye", value=f"{message.author.mention} (`{message.author.id}`)", inline=False)
                    embed.add_field(name="Sebep", value="Yasaklı Kelime Kullanımı", inline=False)
                    embed.add_field(name="Süre", value="1 Dakika", inline=False)
                    await mod_kanal.send(embed=embed)
            except Exception as e:
                print(f"Küfür filtresi hatası: {e}")
            return

    # 2. Kurallar Yönlendirmesi
    kural_anahtar_kelimeleri = ["kural", "kurallar", "sunucu kuralları", "yasak", "cezalar"]
    if any(k in mesaj_icerik for k in kural_anahtar_kelimeleri):
        kurallar_kanali = discord.utils.get(message.guild.text_channels, name="📝kurallar")
        if kurallar_kanali:
            await message.reply(f"📜 Sunucu kuralları için {kurallar_kanali.mention} kanalını ziyaret edebilirsiniz!")

    # 3. Genel Sohbet XP ve Görev Takibi
    if message.channel.name == "💬genel-sohbet":
        await xp_ekle(message, 20)
        veri = kullanici_veri_al(message.author.id)
        if veri["gorevler"]["mesaj"] < 10:
            veri["gorevler"]["mesaj"] += 1
            if veri["gorevler"]["mesaj"] == 10:
                veri["xp"] += 100
                await message.channel.send(f"✅ {message.author.mention}, **Genel Sohbet Görevi / General Chat Quest** tamamlandı! `+100 XP` kazandın.")
            verileri_kaydet()

    await bot.process_commands(message)


@bot.event
async def on_voice_state_update(member, before, after):
    if after.channel and after.channel.name == TETIKLEYICI_KANAL:
        guild = member.guild
        kategori = after.channel.category
        oda_adi = f"🔊 | {member.name}'in Odası"

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(connect=True),
            member: discord.PermissionOverwrite(
                manage_channels=True, move_members=True, connect=True, speak=True
            ),
        }

        try:
            yeni_kanal = await guild.create_voice_channel(name=oda_adi, category=kategori, overwrites=overwrites)
            await member.move_to(yeni_kanal)
        except Exception as e:
            print(f"Özel oda oluşturulurken hata: {e}")

    if before.channel and before.channel != after.channel:
        if before.channel.name.startswith("🔊 |") and len(before.channel.members) == 0:
            try:
                await before.channel.delete()
            except Exception as e:
                print(f"Boş özel oda silinirken hata: {e}")


@bot.event
async def on_member_join(member):
    rol_adi = "Member"
    rol = discord.utils.get(member.guild.roles, name=rol_adi)
    if rol:
        try:
            await member.add_roles(rol, reason="Sunucuya katıldığı için otomatik rol verildi.")
        except Exception as e:
            print(f"❌ Otomatik rol hatası: {e}")

    kanal = discord.utils.get(member.guild.text_channels, name="bot-moderasyon")
    if kanal:
        await kanal.send(f"📥 **{member.mention}** ({member.name}) sunucuya katıldı! '{rol_adi}' rolü verildi.")


@bot.event
async def on_member_remove(member):
    kanal = discord.utils.get(member.guild.text_channels, name="bot-moderasyon")
    if kanal:
        await kanal.send(f"📤 **{member.name}** sunucudan ayrıldı.")


# ==========================================
# 4. ÖZEL ODA YÖNETİMİ & SEVİYE SİSTEMİ
# ==========================================

class OdaIsimModal(discord.ui.Modal, title="Oda İsmini Değiştir"):
    yeni_isim = discord.ui.TextInput(
        label="Yeni Oda İsmi",
        placeholder="Örn: Sohbet Odası",
        max_length=30,
    )

    async def on_submit(self, interaction: discord.Interaction):
        kanal = interaction.user.voice.channel if interaction.user.voice else None
        if not kanal or not kanal.name.startswith("🔊 |"):
            await interaction.response.send_message("❌ Aktif bir özel odada değilsin!", ephemeral=True)
            return

        await kanal.edit(name=f"🔊 | {self.yeni_isim.value}")
        await interaction.response.send_message(f"✏️ Oda adı **{self.yeni_isim.value}** yapıldı!", ephemeral=True)


class OdaYonimView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Odayı Kilitle", style=discord.ButtonStyle.danger, custom_id="oda_kilit_kalici_id")
    async def kilit_buton(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("❌ Ses odasında olmalısın!", ephemeral=True)
            return
        kanal = interaction.user.voice.channel
        if not kanal.name.startswith("🔊 |"):
            await interaction.response.send_message("❌ Burası kişisel bir özel oda değil!", ephemeral=True)
            return

        await kanal.set_permissions(interaction.guild.default_role, connect=False)
        await interaction.response.send_message(f"🔒 **{kanal.name}** kilitlendi!", ephemeral=True)

    @discord.ui.button(label="Odayı Aç", style=discord.ButtonStyle.success, custom_id="oda_ac_kalici_id")
    async def ac_buton(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("❌ Ses odasında olmalısın!", ephemeral=True)
            return
        kanal = interaction.user.voice.channel
        if not kanal.name.startswith("🔊 |"):
            await interaction.response.send_message("❌ Burası kişisel bir özel oda değil!", ephemeral=True)
            return

        await kanal.set_permissions(interaction.guild.default_role, connect=True)
        await interaction.response.send_message(f"🔓 **{kanal.name}** erişime açıldı!", ephemeral=True)

    @discord.ui.button(label="İsim Değiştir", style=discord.ButtonStyle.primary, custom_id="oda_isim_kalici_id")
    async def isim_buton(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("❌ Ses odasında olmalısın!", ephemeral=True)
            return
        kanal = interaction.user.voice.channel
        if not kanal.name.startswith("🔊 |"):
            await interaction.response.send_message("❌ Burası kişisel bir özel oda değil!", ephemeral=True)
            return

        await interaction.response.send_modal(OdaIsimModal())


@bot.command(name="odapanel", description="Oda yönetim panelini gönderir.")
@commands.has_permissions(administrator=True)
async def odapanel(ctx):
    embed = discord.Embed(
        title="🎛️ Özel Oda Yönetim Paneli",
        description="Odanızı kilitlemek, açmak veya ismini değiştirmek için aşağıdaki butonları kullanabilirsiniz.",
        color=discord.Color.blurple(),
    )
    await ctx.send(embed=embed, view=OdaYonimView())
    await ctx.message.delete()


@bot.command(name="level", aliases=["seviye"])
async def seviye_paneli(ctx):
    veri = kullanici_veri_al(ctx.author.id)
    lvl = veri["level"]
    xp = veri["xp"]
    
    dolu_blok = int(xp // 10)
    bos_blok = 10 - dolu_blok
    bar = "🟩" * dolu_blok + "⬛" * bos_blok
    
    rutbe = "Rookie"
    if lvl >= 50: rutbe = "💎 Diamond"
    elif lvl >= 40: rutbe = "💚 Emerald"
    elif lvl >= 30: rutbe = "💛 Gold"
    elif lvl >= 20: rutbe = "🤍 Silver"
    elif lvl >= 10: rutbe = "🧡 Copper"

    embed = discord.Embed(
        title="📊 LEVEL & PROGRESS SYSTEM / SEVIYE SİSTEMİ",
        description=f"**Player / Oyuncu:** {ctx.author.mention}\n**Rank / Rütbe:** `{rutbe}`",
        color=discord.Color.blurple()
    )
    
    embed.add_field(
        name="📈 Progress / İlerleme",
        value=f"Level: **{lvl}** | XP: `{xp}/100`\n[{bar}] {xp}%",
        inline=False
    )
    
    embed.add_field(
        name="🎁 Rewards / Ödüller",
        value="• Her Level: `500 Coin`\n• Level 5, 15, 25, 35, 45: `Mystery Box` 🎁\n• Rol Ödülleri: `Copper`, `Silver`, `Gold`, `Emerald`, `Diamond`",
        inline=False
    )
    
    gorevler = veri["gorevler"]
    embed.add_field(
        name="📋 Daily Quests / Günlük Görevler (24s)",
        value=(
            f"1️⃣ Sohbet 10 Mesaj: `{gorevler.get('mesaj', 0)}/10` (+100 XP)\n"
            f"2️⃣ Polis 5 İşlem: `{gorevler.get('polis', 0)}/5` (+100 XP)\n"
            f"3️⃣ Ses 15 Dakika: `{gorevler.get('ses', 0)}/15` (+100 XP)\n"
            f"4️⃣ 1000 Coin Gönder: `{gorevler.get('gonder', 0)}/1` (+100 XP)\n"
            f"5️⃣ Rulet Min 1000 Bahis: `{gorevler.get('rulet', 0)}/1` (+100 XP)"
        ),
        inline=False
    )
    
    embed.set_footer(text="Günlük maksimum 5 level sınırı aktiftir. / Daily max 5 level limit active.")
    await ctx.send(embed=embed)


# ==========================================
# 5. EKONOMİ & CÜZDAN KOMUTLARI
# ==========================================

@bot.command(name="cüzdan", aliases=["bakiye", "wallet", "balance"], description="Cüzdanınızı gösterir.")
async def cuzdan(ctx):
    bakiye = bakiye_al(ctx.author.id)
    embed = discord.Embed(
        title=f"💰 {ctx.author.name}'s Wallet",
        description=f"Total Balance: **{bakiye:,} Coin** 🪙",
        color=discord.Color.gold(),
    )
    await ctx.send(embed=embed)


@bot.command(name="günlük", aliases=["daily"], description="Günlük coin ödülü alırsınız.")
async def gunluk(ctx):
    user_id = ctx.author.id
    simdi = datetime.datetime.now()

    if user_id in GUNLUK_SURELER:
        gecen_sure = simdi - GUNLUK_SURELER[user_id]
        if gecen_sure.total_seconds() < 86400:
            kalan_saniye = 86400 - int(gecen_sure.total_seconds())
            kalan_saat = kalan_saniye // 3600
            kalan_dakika = (kalan_saniye % 3600) // 60
            await ctx.send(
                f"⏳ You already claimed your daily reward!\n"
                f"Remaining time: **{kalan_saat} hours {kalan_dakika} minutes** ⏰"
            )
            return

    bakiye_al(user_id)
    COINLER[user_id] += 200
    GUNLUK_SURELER[user_id] = simdi
    verileri_kaydet()

    await ctx.send(
        f"🎁 Daily reward of **200 Coins** added!\n"
        f"New balance: **{COINLER[user_id]:,} Coin** 🪙"
    )


@bot.command(name="top", aliases=["cüzdansıralama"], description="En zengin ilk 5 kişiyi gösterir.")
async def top(ctx):
    if not COINLER:
        await ctx.send("❌ No registered wallets found!")
        return

    sirali_liste = sorted(COINLER.items(), key=lambda item: item[1], reverse=True)

    embed = discord.Embed(
        title="🏆 Rich List (Top 5)",
        description="Top 5 richest wallet holders:",
        color=discord.Color.gold(),
    )

    medyalar = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]

    for i, (user_id, bakiye) in enumerate(sirali_liste[:5]):
        kullanici = ctx.guild.get_member(user_id)
        isim = kullanici.name if kullanici else f"Unknown User (`{user_id}`)"
        embed.add_field(name=f"{medyalar[i]} {isim}", value=f"Balance: **{bakiye:,} Coin** 🪙", inline=False)

    await ctx.send(embed=embed)


@bot.command(name="paraekle", aliases=["addcoins", "givemoney"], description="Kullanıcıya coin ekler.")
@commands.has_permissions(administrator=True)
async def paraekle(ctx, kullanici: discord.Member, miktar: int):
    if miktar <= 0:
        await ctx.send("❌ You must enter an amount greater than 0!")
        return

    user_id = kullanici.id
    bakiye_al(user_id)
    COINLER[user_id] += miktar
    verileri_kaydet()

    await ctx.send(
        f"✅ Added **{miktar:,} Coins** to **{kullanici.name}**!\n"
        f"New balance: **{COINLER[user_id]:,} Coin** 🪙"
    )


@bot.command(name="parasil", aliases=["removecoins", "takemoney"], description="Kullanıcıdan coin siler.")
@commands.has_permissions(administrator=True)
async def parasil(ctx, kullanici: discord.Member, miktar: int):
    if miktar <= 0:
        await ctx.send("❌ You must enter an amount greater than 0!")
        return

    user_id = kullanici.id
    mevcut_bakiye = bakiye_al(user_id)
    COINLER[user_id] = max(0, mevcut_bakiye - miktar)
    verileri_kaydet()

    await ctx.send(
        f"✅ Removed **{miktar:,} Coins** from **{kullanici.name}**!\n"
        f"New balance: **{COINLER[user_id]:,} Coin** 🪙"
    )


@bot.command(name="gönder", aliases=["send", "transfer"], description="Coin transfer eder.")
async def gonder(ctx, hedef: discord.Member, miktar: int):
    kanal_adi = ctx.channel.name.lower()
    if not any(k in kanal_adi for k in ["komutlar", "rulet", "blackjack", "commands"]):
        await ctx.send("❌ You can only use this command in command/gamble channels!")
        return

    if miktar <= 0:
        await ctx.send("❌ You must enter an amount greater than 0!")
        return

    if hedef.id == ctx.author.id:
        await ctx.send("❌ You cannot send coins to yourself!")
        return

    if hedef.bot:
        await ctx.send("❌ You cannot send coins to bots!")
        return

    gonderen_id = ctx.author.id
    hedef_id = hedef.id
    gonderen_bakiye = bakiye_al(gonderen_id)

    if gonderen_bakiye < miktar:
        await ctx.send(f"❌ Not enough coins! Your balance: **{gonderen_bakiye:,} Coin** 🪙")
        return

    COINLER[gonderen_id] -= miktar
    bakiye_al(hedef_id)
    COINLER[hedef_id] += miktar
    verileri_kaydet()

    # Görev İlerlemesi (Gönderim Görevi)
    veri = kullanici_veri_al(gonderen_id)
    if miktar >= 1000 and veri["gorevler"]["gonder"] < 1:
        veri["gorevler"]["gonder"] += 1
        veri["xp"] += 100
        await ctx.send(f"✅ {ctx.author.mention}, **Money Transfer Quest** completed! `+100 XP` earned.")
        verileri_kaydet()

    embed = discord.Embed(
        title="💸 Transfer Successful",
        description=f"**{ctx.author.mention}** -> **{hedef.mention}**\nSuccessfully transferred **{miktar:,} Coins**! 🪙",
        color=discord.Color.green(),
    )
    embed.add_field(name="New Balance", value=f"**{COINLER[gonderen_id]:,} Coin**", inline=True)
    await ctx.send(embed=embed)


# ==========================================
# 6. MARKET & KİŞİYE ÖZEL RENK SİSTEMİ
# ==========================================

MARKET_ESYALARI = {
    "1": {"tip": "rol", "isim": "💎 Millionaire Role", "rol": "Millionaire", "fiyat": 25000},
    "2": {"tip": "rol", "isim": "🎩 Billionaire Role", "rol": "Billionaire", "fiyat": 50000}, 
    "3": {"tip": "ozel_renk", "isim": "🎨 Custom Color Privilege", "fiyat": 75000},
    "4": {"tip": "kasa", "isim": "🎁 Mystery Box (750-1250 Coins)", "fiyat": 1000},
}


@bot.command(name="market", aliases=["shop"], description="Market ürünlerini listeler.")
async def market(ctx):
    embed = discord.Embed(
        title="🛒 Server Market",
        description=(
            "You can purchase special roles, custom color perks, or mystery boxes!\n"
            "To buy: `!buy <item_no>` or `!satınal <item_no>`"
        ),
        color=discord.Color.gold(),
    )

    for id, esya in MARKET_ESYALARI.items():
        if esya["tip"] == "rol":
            detay = f"Type: **Special Role**\nPrice: **{esya['fiyat']:,} Coin** 🪙"
        elif esya["tip"] == "ozel_renk":
            detay = f"Type: **Custom Color** (`!colour <hex>`)\nPrice: **{esya['fiyat']:,} Coin** 🪙"
        else:
            detay = f"Type: **Mystery Box** (750-1250 Coin Reward)\nPrice: **{esya['fiyat']:,} Coin** 🪙"

        embed.add_field(name=f"[{id}] {esya['isim']}", value=detay, inline=False)

    await ctx.send(embed=embed)


@bot.command(name="satınal", aliases=["buy"], description="Marketten ürün satın alır.")
async def satinal(ctx, urun_id: str):
    if urun_id not in MARKET_ESYALARI:
        await ctx.send("❌ Invalid item ID! To view shop: `!market`")
        return

    esya = MARKET_ESYALARI[urun_id]
    user_id = ctx.author.id
    bakiye = bakiye_al(user_id)

    if bakiye < esya["fiyat"]:
        await ctx.send(f"❌ Not enough coins! Required: **{esya['fiyat']:,} Coin**, You have: **{bakiye:,} Coin** 🪙")
        return

    if esya["tip"] == "rol":
        rol = discord.utils.get(ctx.guild.roles, name=esya["rol"])
        if not rol:
            await ctx.send(f"⚠️ Role **{esya['rol']}** not found on server!")
            return

        if rol in ctx.author.roles:
            await ctx.send("❌ You already have this role!")
            return

        try:
            COINLER[user_id] -= esya["fiyat"]
            verileri_kaydet()
            await ctx.author.add_roles(rol)
            await ctx.send(f"🎉 Congrats! Purchased **{esya['isim']}** for **{esya['fiyat']:,} Coins**!")
        except Exception as e:
            await ctx.send(f"❌ Error adding role: {e}")

    elif esya["tip"] == "ozel_renk":
        rol_adi = f"Renk | {ctx.author.name}"
        mevcut_rol = discord.utils.get(ctx.author.roles, name=rol_adi)
        if mevcut_rol:
            await ctx.send("❌ You already have a custom color role! Use `!colour <hex>` to change.")
            return

        try:
            COINLER[user_id] -= esya["fiyat"]
            verileri_kaydet()

            yeni_rol = await ctx.guild.create_role(name=rol_adi, reason=f"Custom color for {ctx.author}.")
            await ctx.author.add_roles(yeni_rol)
            await ctx.send(
                f"🎉 Congrats! Purchased Custom Color privilege!\n"
                f"✨ **{rol_adi}** role created. Use `!colour #HEXCODE` to change your color!"
            )
        except Exception as e:
            await ctx.send(f"❌ Error: {e}")

    elif esya["tip"] == "kasa":
        try:
            COINLER[user_id] -= esya["fiyat"]
            kasa_mesaj = await ctx.send(f"🎁 **{ctx.author.mention}** is opening the Mystery Box... 📦✨")
            await asyncio.sleep(1.5)

            kazanc = random.randint(750, 1250)
            COINLER[user_id] += kazanc
            verileri_kaydet()

            fark = kazanc - esya["fiyat"]
            durum_metni = f"Profit! 🎉 (+{fark})" if fark > 0 else (f"Loss... 😅 ({fark})" if fark < 0 else "Breakeven! 🔄")

            embed = discord.Embed(
                title="🎁 Mystery Box Opened!",
                description=(
                    f"💰 **Reward:** `+{kazanc:,} Coin`\n"
                    f"📊 **Status:** {durum_metni}\n"
                    f"🪙 **Current Balance:** **{COINLER[user_id]:,} Coin**"
                ),
                color=discord.Color.purple(),
            )
            await kasa_mesaj.edit(content=None, embed=embed)
        except Exception as e:
            await ctx.send(f"❌ Error opening box: {e}")


@bot.command(name="renk", aliases=["colour", "color"], description="Renk rolünün rengini değiştirir.")
async def renk_degistir(ctx, hex_kodu: str):
    hedef_rol = next((rol for rol in ctx.author.roles if rol.name.startswith("Renk | ")), None)

    if not hedef_rol:
        await ctx.send("❌ You don't have a custom color role! Buy from shop: `!market`")
        return

    hex_kodu = hex_kodu.strip()
    if not hex_kodu.startswith("#"):
        hex_kodu = "#" + hex_kodu

    try:
        temiz_kod = hex_kodu.replace("#", "")
        renk_degeri = int(temiz_kod, 16)
        await hedef_rol.edit(color=discord.Color(renk_degeri), reason=f"{ctx.author} updated color.")
        await ctx.send(f"🎨 Success! Color updated to **{hex_kodu}**!")
    except ValueError:
        await ctx.send("❌ Invalid hex code! Ex: `!colour #ff0000`")
    except Exception as e:
        await ctx.send(f"❌ Error: {e}")


# ==========================================
# 7. KUMAR SİSTEMLERİ (RULET, BJ, AVIATOR)
# ==========================================

@bot.command(name="rulet", description="Rulet oynarsın.")
async def rulet(ctx, renk: str, miktar: int):
    if "rulet" not in ctx.channel.name.lower():
        await ctx.send("❌ You can only use this command in the **🎰rulet** channel!")
        return

    renk = renk.lower()
    if renk not in ["kırmızı", "siyah", "yeşil"]:
        await ctx.send("❌ Invalid color! Options: `kırmızı`, `siyah`, `yeşil`")
        return

    if miktar <= 0:
        await ctx.send("❌ You must enter an amount greater than 0!")
        return

    user_id = ctx.author.id
    bakiye = bakiye_al(user_id)

    if bakiye < miktar:
        await ctx.send(f"❌ Not enough coins! Your balance: **{bakiye:,} Coin** 🪙")
        return

    # Görev İlerlemesi (Rulet Görevi)
    veri = kullanici_veri_al(user_id)
    if miktar >= 1000 and veri["gorevler"]["rulet"] < 1:
        veri["gorevler"]["rulet"] += 1
        veri["xp"] += 100
        await ctx.send(f"✅ {ctx.author.mention}, **Roulette Quest** completed! `+100 XP` earned.")

    animasyon_embed = discord.Embed(
        title="🎰 Roulette Wheel Spinning...",
        description="Wheel is spinning... 🔄",
        color=discord.Color.blurple(),
    )
    mesaj = await ctx.send(embed=animasyon_embed)

    for adim in ["🔴 Red...", "⚫ Black...", "🟢 Green...", "🔴 Red...", "⚫ Black..."]:
        animasyon_embed.description = f"Wheel is spinning fast: **{adim}** 🎲"
        await mesaj.edit(embed=animasyon_embed)
        await asyncio.sleep(0.6)

    sonuclar = ["kırmızı"] * 47 + ["siyah"] * 47 + ["yeşil"] * 6
    gelen_renk = random.choice(sonuclar)

    embed = discord.Embed()
    if gelen_renk == renk:
        if gelen_renk == "yeşil":
            kazanc = miktar * 14
            COINLER[user_id] += kazanc - miktar
            embed.color = discord.Color.green()
            embed.title = "🎉 AMAZING! GREEN HIT!"
            embed.description = f"🟢 Green hit! You won **{kazanc:,} Coins**! 🚀\nNew balance: **{COINLER[user_id]:,} Coin**"
        else:
            kazanc = miktar * 2
            COINLER[user_id] += kazanc - miktar
            embed.color = discord.Color.gold()
            embed.title = "✨ YOU WON!"
            embed.description = f"**{gelen_renk.capitalize()}** hit! You won **{kazanc:,} Coins**! 💰\nNew balance: **{COINLER[user_id]:,} Coin**"
    else:
        COINLER[user_id] -= miktar
        embed.color = discord.Color.red()
        embed.title = "💸 YOU LOST!"
        embed.description = f"**{gelen_renk.capitalize()}** hit. You lost **{miktar:,} Coins**... 🤡\nNew balance: **{COINLER[user_id]:,} Coin**"

    verileri_kaydet()
    await mesaj.edit(embed=embed)


# --- BLACKJACK (21) ---
class BlackjackView(discord.ui.View):
    def __init__(self, ctx, miktar, oy_kartlar, bot_kartlar, deste):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.miktar = miktar
        self.oy_kartlar = oy_kartlar
        self.bot_kartlar = bot_kartlar
        self.deste = deste

    def kart_toplam(self, kartlar):
        toplam = sum(kartlar)
        as_sayisi = kartlar.count(11)
        while toplam > 21 and as_sayisi > 0:
            toplam -= 10
            as_sayisi -= 1
        return toplam

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary, custom_id="bj_hit")
    async def hit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("❌ This is not your game!", ephemeral=True)
            return

        await interaction.response.defer()
        self.oy_kartlar.append(self.deste.pop())
        oy_toplam = self.kart_toplam(self.oy_kartlar)

        if oy_toplam > 21:
            COINLER[self.ctx.author.id] -= self.miktar
            verileri_kaydet()

            embed = discord.Embed(
                title="💥 BUSTED! (Over 21)",
                description=f"Your Cards: {self.oy_kartlar} (Total: **{oy_toplam}**)\nYou lost **{self.miktar:,} Coins**! 💸",
                color=discord.Color.red(),
            )
            self.stop()
            await interaction.message.edit(embed=embed, view=None)
        else:
            embed = discord.Embed(
                title="🃏 Blackjack (21)",
                description=f"**Your Cards:** {self.oy_kartlar} (Total: **{oy_toplam}**)\n**Bot's Open Card:** [{self.bot_kartlar[0]}, ?]",
                color=discord.Color.blue(),
            )
            await interaction.message.edit(embed=embed, view=self)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.success, custom_id="bj_stand")
    async def stand_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("❌ This is not your game!", ephemeral=True)
            return

        await interaction.response.defer()
        while self.kart_toplam(self.bot_kartlar) < 17:
            self.bot_kartlar.append(self.deste.pop())

        oy_toplam = self.kart_toplam(self.oy_kartlar)
        bot_toplam = self.kart_toplam(self.bot_kartlar)
        user_id = self.ctx.author.id
        embed = discord.Embed(title="🃏 Blackjack Result")

        if bot_toplam > 21 or oy_toplam > bot_toplam:
            COINLER[user_id] += self.miktar
            embed.color = discord.Color.green()
            embed.title = "🎉 YOU WON!"
            embed.description = (
                f"**Your Cards:** {self.oy_kartlar} (Total: **{oy_toplam}**)\n"
                f"**Bot's Cards:** {self.bot_kartlar} (Total: **{bot_toplam}**)\n\n"
                f"You won **+{self.miktar:,} Coins**! 💰"
            )
        elif oy_toplam < bot_toplam:
            COINLER[user_id] -= self.miktar
            embed.color = discord.Color.red()
            embed.title = "💸 YOU LOST!"
            embed.description = (
                f"**Your Cards:** {self.oy_kartlar} (Total: **{oy_toplam}**)\n"
                f"**Bot's Cards:** {self.bot_kartlar} (Total: **{bot_toplam}**)\n\n"
                f"You lost **-{self.miktar:,} Coins**! 🤡"
            )
        else:
            embed.color = discord.Color.gold()
            embed.title = "🤝 TIE!"
            embed.description = (
                f"**Your Cards:** {self.oy_kartlar} (Total: **{oy_toplam}**)\n"
                f"**Bot's Cards:** {self.bot_kartlar} (Total: **{bot_toplam}**)\n\n"
                f"Coins refunded."
            )

        verileri_kaydet()
        self.stop()
        await interaction.message.edit(embed=embed, view=None)


@bot.command(name="blackjack", aliases=["bj", "21"], description="Blackjack oynarsın.")
async def blackjack(ctx, miktar: int):
    if "blackjack" not in ctx.channel.name.lower():
        await ctx.send("❌ You can only use this command in the **🃏blackjack** channel!")
        return

    if miktar <= 0:
        await ctx.send("❌ You must enter a valid bet amount!")
        return

    user_id = ctx.author.id
    bakiye = bakiye_al(user_id)

    if bakiye < miktar:
        await ctx.send(f"❌ Not enough coins! Your balance: **{bakiye:,} Coin** 🪙")
        return

    deste = [2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 10, 10, 11] * 4
    random.shuffle(deste)

    oy_kartlar = [deste.pop(), deste.pop()]
    bot_kartlar = [deste.pop(), deste.pop()]

    view = BlackjackView(ctx, miktar, oy_kartlar, bot_kartlar, deste)
    embed = discord.Embed(
        title="🃏 Blackjack (21)",
        description=(
            f"**Your Cards:** {oy_kartlar} (Total: **{view.kart_toplam(oy_kartlar)}**)\n"
            f"**Bot's Open Card:** [{bot_kartlar[0]}, ?]\n\n"
            f"Do you want to Hit or Stand?"
        ),
        color=discord.Color.blue(),
    )
    await ctx.send(embed=embed, view=view)


# --- AVIATOR ---
@bot.command(name="aviator")
async def aviator(ctx, miktar: int = None):
    izin_verilen_kanal = "✈️aviator"
    if ctx.channel.name != izin_verilen_kanal:
        await ctx.send(f"❌ This command can only be used in **#{izin_verilen_kanal}**!", delete_after=5)
        return

    user_id = ctx.author.id
    MAKS_BAHIS = 10000

    if miktar is None or miktar <= 0:
        await ctx.send("❌ Please enter a valid amount! Ex: `!aviator 100`")
        return

    if miktar > MAKS_BAHIS:
        await ctx.send(f"⚠️ Maximum bet is **{MAKS_BAHIS:,} Coins**.")
        return

    bakiye = bakiye_al(user_id)
    if bakiye < miktar:
        await ctx.send(f"❌ Not enough coins! Wallet: **{bakiye:,} Coin**")
        return

    if user_id in DEVAM_EDEN_AVIATORLER:
        await ctx.send("❌ You already have an active game!")
        return

    COINLER[user_id] -= miktar
    verileri_kaydet()
    DEVAM_EDEN_AVIATORLER.add(user_id)

    carpan = 1.00
    patlama_noktasi = round(random.uniform(1.05, 3.80), 2)
    kazandi_mi = False

    class AviatorView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=30)
            self.value = False

        @discord.ui.button(label="💸 CASH OUT!", style=discord.ButtonStyle.green, emoji="🚀")
        async def parayi_cek(self, interaction: discord.Interaction, button: discord.ui.Button):
            nonlocal kazandi_mi
            if interaction.user.id != user_id:
                await interaction.response.send_message("❌ This is not your game!", ephemeral=True)
                return

            if not kazandi_mi:
                kazandi_mi = True
                self.value = True
                for child in self.children:
                    child.disabled = True
                await interaction.response.edit_message(view=self)
                self.stop()

    view = AviatorView()
    embed = discord.Embed(
        title="✈️ AVIATOR - Flight Simulation",
        description=(
            "🚀 **Plane taking off...**\n\n"
            "```text\n 1.00x | ✈️ . . . . . . . . . . .\n       | ─────────────────────────\n```\n"
            f"**Bet:** {miktar:,} Coin\n📈 **Multiplier:** `{carpan:.2f}x`"
        ),
        color=discord.Color.gold()
    )
    mesaj = await ctx.send(embed=embed, view=view)

    try:
        while not view.value and carpan < patlama_noktasi:
            await asyncio.sleep(1.0)
            if kazandi_mi:
                break

            carpan += round(random.uniform(0.03, 0.18), 2)
            if carpan >= patlama_noktasi:
                carpan = patlama_noktasi
                break

            oran = min(int((carpan - 1.0) / 2.8 * 10), 9)
            bosluk = " . " * oran
            kalan_bosluk = " . " * (9 - oran)

            embed.description = (
                f"✈️ **Plane climbing higher!**\n\n"
                f"```text\n {carpan:.2f}x |{bosluk}✈️{kalan_bosluk}\n       | ─────────────────────────\n```\n"
                f"**Bet:** {miktar:,} Coin\n📈 **Multiplier:** `{carpan:.2f}x`"
            )
            await mesaj.edit(embed=embed, view=view)

        if kazandi_mi:
            kazanc = int(miktar * carpan)
            COINLER[user_id] += kazanc
            verileri_kaydet()

            embed.title = "🎉 SUCCESSFUL CASH OUT!"
            embed.color = discord.Color.green()
            embed.description = (
                f"You cashed out in time!\n\n"
                f"✨ **Multiplier:** `{carpan:.2f}x`\n"
                f"💰 **Won:** **+{kazanc:,} Coin**\n"
                f"🏦 **New Wallet:** `{COINLER[user_id]:,} Coin`"
            )
            await mesaj.edit(embed=embed, view=None)
        else:
            verileri_kaydet()
            embed.title = "💥 PLANE CRASHED (BOOM)!"
            embed.color = discord.Color.red()
            embed.description = (
                f"Plane flew away at `{patlama_noktasi}x`.\n\n"
                f"```text\n 💥 BOOM! | ✈️💨 (Disappeared)\n```\n"
                f"💸 **Lost:** `{miktar:,} Coin`\n"
                f"🏦 **Remaining Wallet:** `{COINLER[user_id]:,} Coin`"
            )
            await mesaj.edit(embed=embed, view=None)

    except Exception as e:
        print(f"Aviator error: {e}")
    finally:
        DEVAM_EDEN_AVIATORLER.discard(user_id)


# ==========================================
# 8. MESLEK SİSTEMİ (SEVİYE KISITLAMALI)
# ==========================================

async def kanal_kontrol(ctx):
    if "meslekler" not in ctx.channel.name.lower() and "jobs" not in ctx.channel.name.lower():
        await ctx.send("❌ You can only use this command in the **🥼meslekler / 💼jobs** channel!")
        return False
    return True


@bot.command(name="meslekler", aliases=["jobs"], description="Meslekleri listeler.")
async def meslekler_komut(ctx):
    if not await kanal_kontrol(ctx):
        return

    embed = discord.Embed(
        title="🥼 Server Jobs Panel / Sunucu Meslekler Paneli",
        description=(
            "**TR:** Güncel meslekler, gereksinimler ve oranlar:\n"
            "* Seçmek için: `!meslekseç <police/pilot/doctor>`\n"
            "* İstifa: `!istifa` (Cooldown kaldırılmıştır)\n\n"
            "**EN:** Updated jobs and requirements:\n"
            "* Choose: `!joinjob <police/pilot/doctor>`\n"
            "* Resign: `!quitjob` (No cooldown)"
        ),
        color=discord.Color.blue(),
    )
    embed.add_field(name="👮 Police", value="Her seviye. (Kazan: +550 | Kaybet: -250)", inline=False)
    embed.add_field(name="✈️ Pilot", value="Min **Level 10**. (Kazan: +1,750 | Kaybet: 10 Dakika Yasak)", inline=False)
    embed.add_field(name="👨‍⚕️ Doctor", value="Min **Level 20**. (Kazan: +2,500 | Kaybet: -750 Coin)", inline=False)
    await ctx.send(embed=embed)


@bot.command(name="meslekseç", aliases=["joinjob"], description="Mesleğe girer.")
async def mesleksec(ctx, *, meslek_adi: str):
    if not await kanal_kontrol(ctx):
        return

    meslek_adi = meslek_adi.lower()
    veri = kullanici_veri_al(ctx.author.id)
    kullanici_level = veri["level"]

    if meslek_adi not in GECERLI_MESLEKLER:
        await ctx.send("❌ Invalid job! Options: `police`, `pilot`, `doctor`")
        return

    # Seviye Kısıtlamaları
    if meslek_adi == "pilot" and kullanici_level < 10:
        await ctx.send(f"❌ You must be at least **Level 10** to choose Pilot! (Current: {kullanici_level})")
        return
    if meslek_adi == "doctor" and kullanici_level < 20:
        await ctx.send(f"❌ You must be at least **Level 20** to choose Doctor! (Current: {kullanici_level})")
        return

    rol_mapping = {"police": "Police", "doctor": "Doctor", "pilot": "Pilot"}
    rol_ismi = rol_mapping.get(meslek_adi, meslek_adi.capitalize())
    hedef_rol = discord.utils.get(ctx.guild.roles, name=rol_ismi)

    if not hedef_rol:
        await ctx.send(f"⚠️ Role **{rol_ismi}** not found on server!")
        return

    for diger_meslek in GECERLI_MESLEKLER:
        diger_rol_ismi = rol_mapping.get(diger_meslek, diger_meslek.capitalize())
        diger_rol = discord.utils.get(ctx.guild.roles, name=diger_rol_ismi)
        if diger_rol and diger_rol in ctx.author.roles:
            try:
                await ctx.author.remove_roles(diger_rol)
            except Exception as e:
                print(f"Old role removal error: {e}")

    try:
        await ctx.author.add_roles(hedef_rol)
    except Exception as e:
        await ctx.send(f"❌ Could not assign role: {e}")
        return

    user_id_str = str(ctx.author.id)
    if user_id_str not in MESLEKLER_VERI:
        MESLEKLER_VERI[user_id_str] = {}

    MESLEKLER_VERI[user_id_str]["meslek"] = meslek_adi
    MESLEKLER_VERI[user_id_str]["cezali"] = False
    verileri_kaydet()

    await ctx.send(f"🎉 Congrats! You are now a **{rol_ismi}**!")


@bot.command(name="istifa", aliases=["quitjob"], description="Meslekten ayrılır.")
async def istifa_komut(ctx):
    if not await kanal_kontrol(ctx):
        return

    user_id_str = str(ctx.author.id)
    if user_id_str not in MESLEKLER_VERI or not MESLEKLER_VERI[user_id_str].get("meslek"):
        await ctx.send("❌ You don't have an active job!")
        return

    rol_mapping = {"police": "Police", "doctor": "Doctor", "pilot": "Pilot"}
    for meslek in GECERLI_MESLEKLER:
        rol_ismi = rol_mapping.get(meslek, meslek.capitalize())
        rol = discord.utils.get(ctx.guild.roles, name=rol_ismi)
        if rol and rol in ctx.author.roles:
            try:
                await ctx.author.remove_roles(rol)
            except Exception as e:
                print(f"Resign role removal error: {e}")

    MESLEKLER_VERI[user_id_str]["meslek"] = None
    MESLEKLER_VERI[user_id_str]["cezali"] = False
    verileri_kaydet()

    await ctx.send(f"💼 **{ctx.author.mention}** successfully resigned.")


@bot.command(name="polis", aliases=["police"], description="Polis görevi.")
async def polis_komut(ctx):
    if not await kanal_kontrol(ctx):
        return

    user_id_str = str(ctx.author.id)
    if user_id_str not in MESLEKLER_VERI or MESLEKLER_VERI[user_id_str].get("meslek") != "police":
        await ctx.send("❌ You are not a police officer! Use `!joinjob police`")
        return

    simdiki_zaman = datetime.datetime.now().timestamp()
    son_polis_islem = MESLEKLER_VERI[user_id_str].get("son_polis_islem", 0)
    cooldown_suresi = 180

    if simdiki_zaman - son_polis_islem < cooldown_suresi:
        kalan = int(cooldown_suresi - (simdiki_zaman - son_polis_islem))
        await ctx.send(f"⏳ Cooldown remaining: **{kalan // 60} minutes {kalan % 60} seconds**")
        return

    MESLEKLER_VERI[user_id_str]["son_polis_islem"] = simdiki_zaman
    verileri_kaydet()
    bakiye_al(ctx.author.id)

    # Görev İlerlemesi (Polis Görevi)
    veri = kullanici_veri_al(ctx.author.id)
    if veri["gorevler"]["polis"] < 5:
        veri["gorevler"]["polis"] += 1
        if veri["gorevler"]["polis"] == 5:
            veri["xp"] += 100
            await ctx.send(f"✅ {ctx.author.mention}, **Police Quest** completed! `+100 XP` earned.")
        verileri_kaydet()

    if random.choice([True, False]):
        COINLER[ctx.author.id] += 550
        verileri_kaydet()
        embed = discord.Embed(
            title="🚨 Criminal Caught!",
            description=f"**{ctx.author.mention}** caught the criminal!\n🎉 **+550 Coin** | Balance: **{COINLER[ctx.author.id]:,} Coin**",
            color=discord.Color.green(),
        )
    else:
        COINLER[ctx.author.id] = max(0, COINLER[ctx.author.id] - 250)
        verileri_kaydet()
        embed = discord.Embed(
            title="🏃 Criminal Escaped!",
            description=f"**{ctx.author.mention}** lost the suspect!\n💸 **-250 Coin** | Balance: **{COINLER[ctx.author.id]:,} Coin**",
            color=discord.Color.red(),
        )
    await ctx.send(embed=embed)


@bot.command(name="doktor", aliases=["doctor"], description="Doktor görevi.")
async def doktor_komut(ctx):
    if not await kanal_kontrol(ctx):
        return

    user_id_str = str(ctx.author.id)
    if user_id_str not in MESLEKLER_VERI or MESLEKLER_VERI[user_id_str].get("meslek") != "doctor":
        await ctx.send("❌ You are not a doctor! Use `!joinjob doctor`")
        return

    simdiki_zaman = datetime.datetime.now().timestamp()
    son_doktor_islem = MESLEKLER_VERI[user_id_str].get("son_doktor_islem", 0)
    cooldown_suresi = 180

    if simdiki_zaman - son_doktor_islem < cooldown_suresi:
        kalan = int(cooldown_suresi - (simdiki_zaman - son_doktor_islem))
        await ctx.send(f"⏳ Cooldown remaining: **{kalan // 60} minutes {kalan % 60} seconds**")
        return

    MESLEKLER_VERI[user_id_str]["son_doktor_islem"] = simdiki_zaman
    verileri_kaydet()
    bakiye_al(ctx.author.id)

    if random.choice([True, False]):
        COINLER[ctx.author.id] += 2500
        verileri_kaydet()
        embed = discord.Embed(
            title="🏥 Successful Surgery!",
            description=f"**{ctx.author.mention}** saved the patient!\n🎉 **+2,500 Coin** | Balance: **{COINLER[ctx.author.id]:,} Coin**",
            color=discord.Color.green(),
        )
    else:
        COINLER[ctx.author.id] = max(0, COINLER[ctx.author.id] - 750)
        verileri_kaydet()
        embed = discord.Embed(
            title="💔 Failed Surgery!",
            description=f"**{ctx.author.mention}** lost the patient.\n💸 **-750 Coin** | Balance: **{COINLER[ctx.author.id]:,} Coin**",
            color=discord.Color.red(),
        )
    await ctx.send(embed=embed)


@bot.command(name="pilot", description="Pilot görevi.")
async def pilot_komut(ctx):
    if not await kanal_kontrol(ctx):
        return

    user_id_str = str(ctx.author.id)
    if user_id_str not in MESLEKLER_VERI or MESLEKLER_VERI[user_id_str].get("meslek") != "pilot":
        await ctx.send("❌ You are not a pilot! Use `!joinjob pilot`")
        return

    simdiki_zaman = datetime.datetime.now().timestamp()
    son_islem = MESLEKLER_VERI[user_id_str].get("son_islem", 0)

    yasak_suresi = 600 if MESLEKLER_VERI[user_id_str].get("cezali", False) else 0
    if yasak_suresi > 0 and simdiki_zaman - son_islem < yasak_suresi:
        kalan = int(yasak_suresi - (simdiki_zaman - son_islem))
        await ctx.send(f"⏳ Flight ban active! Remaining: **{kalan // 60} minutes {kalan % 60} seconds**")
        return

    son_pilot_islem = MESLEKLER_VERI[user_id_str].get("son_pilot_islem", 0)
    cooldown_suresi = 180
    if simdiki_zaman - son_pilot_islem < cooldown_suresi:
        kalan = int(cooldown_suresi - (simdiki_zaman - son_pilot_islem))
        await ctx.send(f"⏳ Maintenance cooldown: **{kalan // 60} minutes {kalan % 60} seconds**")
        return

    MESLEKLER_VERI[user_id_str]["son_pilot_islem"] = simdiki_zaman
    MESLEKLER_VERI[user_id_str]["cezali"] = False
    MESLEKLER_VERI[user_id_str]["son_islem"] = simdiki_zaman
    bakiye_al(ctx.author.id)

    if random.choice([True, False]):
        COINLER[ctx.author.id] += 1750
        verileri_kaydet()
        embed = discord.Embed(
            title="✈️ Safe Flight!",
            description=f"**{ctx.author.mention}** completed the flight successfully!\n🎉 **+1,750 Coin** | Balance: **{COINLER[ctx.author.id]:,} Coin**",
            color=discord.Color.green(),
        )
    else:
        MESLEKLER_VERI[user_id_str]["cezali"] = True
        MESLEKLER_VERI[user_id_str]["son_islem"] = simdiki_zaman
        verileri_kaydet()
        embed = discord.Embed(
            title="⚠️ Flight Cancelled!",
            description=f"**{ctx.author.mention}** encountered bad weather conditions!\n🚫 Received a **10-minute flight ban**!",
            color=discord.Color.red(),
        )
    await ctx.send(embed=embed)


# ==========================================
# 9. MODERASYON KOMUTLARI
# ==========================================

def sure_hesapla(sayi: int, birim: str):
    birim = birim.lower()
    if birim in ["saniye", "s"]:
        return sayi
    elif birim in ["dakika", "d"]:
        return sayi * 60
    elif birim in ["saat", "h"]:
        return sayi * 3600
    elif birim in ["gün", "g"]:
        return sayi * 86400
    return None


@bot.command(name="mute", description="Kullanıcıyı mutelar.")
@commands.has_permissions(moderate_members=True)
async def mute(ctx, kullanici: discord.Member, sayi: int, birim: str):
    toplam_saniye = sure_hesapla(sayi, birim)
    if not toplam_saniye:
        await ctx.send("❌ Invalid time unit! (`s`, `d`, `h`, `g`)")
        return

    sure = datetime.timedelta(seconds=toplam_saniye)
    try:
        await kullanici.timeout(sure, reason=f"{ctx.author} muted.")
        await ctx.send(f"🔒 **{kullanici.mention}** successfully muted for **{sayi} {birim}**!")
    except Exception as e:
        await ctx.send(f"Error: {e}")


@bot.command(name="unmute", description="Mute kaldırır.")
@commands.has_permissions(moderate_members=True)
async def unmute(ctx, kullanici: discord.Member):
    try:
        await kullanici.timeout(None, reason=f"{ctx.author} unmuted.")
        await ctx.send(f"🔊 Mute removed for **{kullanici.mention}**!")
    except Exception as e:
        await ctx.send(f"Error: {e}")


@bot.command(name="ban", description="Kullanıcıyı banlar.")
@commands.has_permissions(ban_members=True)
async def ban(ctx, kullanici: discord.Member, *, sebep: str = "Not specified"):
    try:
        await kullanici.ban(reason=sebep)
        await ctx.send(f"🔨 **{kullanici.name}** banned! Reason: {sebep}")
    except Exception as e:
        await ctx.send(f"Error: {e}")


@bot.command(name="kick", description="Kullanıcıyı atar.")
@commands.has_permissions(kick_members=True)
async def kick(ctx, kullanici: discord.Member, *, sebep: str = "Not specified"):
    try:
        await kullanici.kick(reason=sebep)
        await ctx.send(f"👢 **{kullanici.name}** kicked! Reason: {sebep}")
    except Exception as e:
        await ctx.send(f"Error: {e}")


@bot.command(name="unban", description="ID ile ban kaldırır.")
@commands.has_permissions(ban_members=True)
async def unban(ctx, user_id: str):
    if not user_id.isdigit():
        await ctx.send("❌ Please enter a valid User ID!")
        return

    try:
        user = await bot.fetch_user(int(user_id))
        await ctx.guild.unban(user)
        await ctx.send(f"🔓 Unbanned **{user.name}**!")
    except Exception as e:
        await ctx.send(f"Error: {e}")


@bot.command(name="odayaçek", aliases=["çek"], description="Kullanıcıyı odanıza çeker.")
async def odayacek(ctx, kullanici: discord.Member):
    if not ctx.author.guild_permissions.move_members:
        await ctx.send("❌ You don't have **Move Members** permission!")
        return

    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("❌ You are not in a voice channel!")
        return

    if not kullanici.voice or not kullanici.voice.channel:
        await ctx.send(f"❌ **{kullanici.name}** is not in a voice channel!")
        return

    hedef_kanal = ctx.author.voice.channel
    try:
        await kullanici.move_to(hedef_kanal, reason=f"{ctx.author} pulled user.")
        await ctx.send(f"🎯 **{kullanici.mention}** moved to **{hedef_kanal.name}**!")
    except Exception as e:
        await ctx.send(f"Error: {e}")


@bot.command(name="sil", description="Mesaj siler.")
@commands.has_permissions(manage_messages=True)
async def sil(ctx, sayi: int):
    if sayi <= 0:
        await ctx.send("❌ Enter a number greater than 0!")
        return

    silinen = await ctx.channel.purge(limit=sayi + 1)
    mesaj = await ctx.send(f"🧹 Successfully deleted **{len(silinen) - 1}** messages!")
    await asyncio.sleep(3)
    await mesaj.delete()


@bot.command(name="kapat", description="Kanalı kilitler.")
@commands.has_permissions(manage_channels=True)
async def kapat(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
    await ctx.send(f"🔒 **{ctx.channel.name}** locked!")


@bot.command(name="aç", description="Kanal kilidini açar.")
@commands.has_permissions(manage_channels=True)
async def ac(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=True)
    await ctx.send(f"🔓 **{ctx.channel.name}** unlocked for messages!")


@bot.command(name="slowmode", description="Yavaş mod ayarlar.")
@commands.has_permissions(manage_channels=True)
async def slowmode(ctx, saniye: int = 0):
    try:
        await ctx.channel.edit(slowmode_delay=saniye)
        if saniye == 0:
            await ctx.send("⏱️ Slowmode removed.")
        else:
            await ctx.send(f"⏱️ Slowmode set to **{saniye}** seconds!")
    except Exception as e:
        await ctx.send(f"Error: {e}")


# ==========================================
# 10. WEB KEEP-ALIVE SUNUCUSU & BOT BAŞLATMA
# ==========================================

app = Flask('')

@app.route('/')
def home():
    return "Bot aktif ve 7/24 çalışıyor!"

def run_web():
    app.run(host='0.0.0.0', port=8080)

def web_sunucusunu_baslat():
    t = Thread(target=run_web)
    t.start()


if __name__ == '__main__':
    web_sunucusunu_baslat()
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ HATA: .env dosyasında TOKEN bulunamadı!")
