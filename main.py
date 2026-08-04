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
                
                for k, v in veriler.items():
                    user_id_str = str(k)
                    user_id_int = int(k)
                    
                    if v.get("son_gunluk"):
                        sureler[user_id_int] = datetime.datetime.fromisoformat(v["son_gunluk"])
                    
                    if v.get("meslek_bilgi"):
                        meslekler_veri[user_id_str] = v["meslek_bilgi"]
                        
                return coinler, sureler, meslekler_veri
        except Exception as e:
            print(f"⚠️ Veri yüklenirken hata oluştu: {e}")
            
    return {}, {}, {}


def verileri_kaydet():
    veriler = {}
    tum_idler = set(
        list(COINLER.keys()) + 
        [int(k) for k in GUNLUK_SURELER.keys()] + 
        [int(k) for k in MESLEKLER_VERI.keys() if str(k).isdigit()]
    )
    
    for user_id in tum_idler:
        user_id_str = str(user_id)
        veriler[user_id_str] = {
            "bakiye": COINLER.get(user_id, 0),
            "son_gunluk": None,
            "meslek_bilgi": MESLEKLER_VERI.get(user_id_str, {})
        }
        
        if user_id in GUNLUK_SURELER:
            veriler[user_id_str]["son_gunluk"] = GUNLUK_SURELER[user_id].isoformat()

    with open(VERI_DOSYASI, "w", encoding="utf-8") as f:
        json.dump(veriler, f, ensure_ascii=False, indent=4)


# Belleğe verileri alma
COINLER, GUNLUK_SURELER, MESLEKLER_VERI = verileri_yukle()


def bakiye_al(user_id):
    if user_id not in COINLER:
        COINLER[user_id] = 500
        verileri_kaydet()
    return COINLER[user_id]


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

    await bot.process_commands(message)


@bot.event
async def on_voice_state_update(member, before, after):
    # Özel Oda Oluşturma
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

    # Boş Özel Odaları Silme
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
# 4. ÖZEL ODA YÖNETİM ARAYÜZÜ (VIEWS)
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


# ==========================================
# 5. EKONOMİ & CÜZDAN KOMUTLARI
# ==========================================

@bot.command(name="cüzdan", aliases=["bakiye", "wallet", "balance"], description="Cüzdanınızı gösterir.")
async def cuzdan(ctx):
    bakiye = bakiye_al(ctx.author.id)
    embed = discord.Embed(
        title=f"💰 {ctx.author.name}'s Wallet / Cüzdanı",
        description=f"Toplam Bakiye / Total Balance: **{bakiye:,} Coin** 🪙",
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
                f"⏳ Günlük ödülünü zaten almışsın! / You already claimed your daily reward!\n"
                f"Kalan süre / Remaining time: **{kalan_saat} saat {kalan_dakika} dakika** ⏰"
            )
            return

    bakiye_al(user_id)
    COINLER[user_id] += 200
    GUNLUK_SURELER[user_id] = simdi
    verileri_kaydet()

    await ctx.send(
        f"🎁 Günlük ödülün olan **200 Coin** eklendi! / Daily reward added!\n"
        f"Yeni bakiye / New balance: **{COINLER[user_id]:,} Coin** 🪙"
    )


@bot.command(name="top", aliases=["cüzdansıralama"], description="En zengin ilk 5 kişiyi gösterir.")
async def top(ctx):
    if not COINLER:
        await ctx.send("❌ Kayıtlı cüzdan bulunamadı!")
        return

    sirali_liste = sorted(COINLER.items(), key=lambda item: item[1], reverse=True)

    embed = discord.Embed(
        title="🏆 Sunucu Zenginler Listesi (Top 5)",
        description="En yüksek bakiyeye sahip ilk 5 üye:",
        color=discord.Color.gold(),
    )

    medyalar = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]

    for i, (user_id, bakiye) in enumerate(sirali_liste[:5]):
        kullanici = ctx.guild.get_member(user_id)
        isim = kullanici.name if kullanici else f"Bilinmeyen Üye (`{user_id}`)"
        embed.add_field(name=f"{medyalar[i]} {isim}", value=f"Bakiye: **{bakiye:,} Coin** 🪙", inline=False)

    await ctx.send(embed=embed)


@bot.command(name="paraekle", aliases=["addcoins", "givemoney"], description="Kullanıcıya coin ekler.")
@commands.has_permissions(administrator=True)
async def paraekle(ctx, kullanici: discord.Member, miktar: int):
    if miktar <= 0:
        await ctx.send("❌ 0'dan büyük bir miktar girmelisin!")
        return

    user_id = kullanici.id
    bakiye_al(user_id)
    COINLER[user_id] += miktar
    verileri_kaydet()

    await ctx.send(
        f"✅ **{kullanici.name}** kullanıcısına **{miktar:,} Coin** eklendi!\n"
        f"Yeni bakiyesi: **{COINLER[user_id]:,} Coin** 🪙"
    )


@bot.command(name="parasil", aliases=["removecoins", "takemoney"], description="Kullanıcıdan coin siler.")
@commands.has_permissions(administrator=True)
async def parasil(ctx, kullanici: discord.Member, miktar: int):
    if miktar <= 0:
        await ctx.send("❌ 0'dan büyük bir miktar girmelisin!")
        return

    user_id = kullanici.id
    mevcut_bakiye = bakiye_al(user_id)
    COINLER[user_id] = max(0, mevcut_bakiye - miktar)
    verileri_kaydet()

    await ctx.send(
        f"✅ **{kullanici.name}** kullanıcısının cüzdanından **{miktar:,} Coin** silindi!\n"
        f"Yeni bakiyesi: **{COINLER[user_id]:,} Coin** 🪙"
    )


@bot.command(name="gönder", aliases=["send", "transfer"], description="Coin transfer eder.")
async def gonder(ctx, hedef: discord.Member, miktar: int):
    kanal_adi = ctx.channel.name.lower()
    if not any(k in kanal_adi for k in ["komutlar", "rulet", "blackjack", "commands"]):
        await ctx.send("❌ Bu komutu sadece belirlenen komut/kumar kanallarında kullanabilirsin!")
        return

    if miktar <= 0:
        await ctx.send("❌ 0'dan büyük miktar girmelisin!")
        return

    if hedef.id == ctx.author.id:
        await ctx.send("❌ Kendine coin gönderemezsin!")
        return

    if hedef.bot:
        await ctx.send("❌ Botlara coin gönderemezsin!")
        return

    gonderen_id = ctx.author.id
    hedef_id = hedef.id
    gonderen_bakiye = bakiye_al(gonderen_id)

    if gonderen_bakiye < miktar:
        await ctx.send(f"❌ Yeterli coinin yok! Bakiyen: **{gonderen_bakiye:,} Coin** 🪙")
        return

    COINLER[gonderen_id] -= miktar
    bakiye_al(hedef_id)
    COINLER[hedef_id] += miktar
    verileri_kaydet()

    embed = discord.Embed(
        title="💸 Coin Transferi Başarılı / Transfer Successful",
        description=f"**{ctx.author.mention}** -> **{hedef.mention}**\n**{miktar:,} Coin** başarıyla aktarıldı! 🪙",
        color=discord.Color.green(),
    )
    embed.add_field(name="Yeni Bakiyen / New Balance", value=f"**{COINLER[gonderen_id]:,} Coin**", inline=True)
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
        title="🛒 Server Market / Sunucu Marketi",
        description=(
            "**TR:** Coinlerinizle özel rol, renk yetkisi veya gizemli kasa satın alabilirsiniz!\n"
            "Satın almak için: `!satınal <ürün_no>` veya `!buy <ürün_no>`\n\n"
            "**EN:** Purchase special roles, custom colors, or mystery boxes with coins!\n"
            "To buy: `!buy <item_no>`"
        ),
        color=discord.Color.gold(),
    )

    for id, esya in MARKET_ESYALARI.items():
        if esya["tip"] == "rol":
            detay = f"Tür / Type: **Special Role**\nFiyat / Price: **{esya['fiyat']:,} Coin** 🪙"
        elif esya["tip"] == "ozel_renk":
            detay = f"Tür / Type: **Custom Color** (`!colour <hex>`)\nFiyat / Price: **{esya['fiyat']:,} Coin** 🪙"
        else:
            detay = f"Tür / Type: **Mystery Box** (750-1250 Coin Reward)\nFiyat / Price: **{esya['fiyat']:,} Coin** 🪙"

        embed.add_field(name=f"[{id}] {esya['isim']}", value=detay, inline=False)

    await ctx.send(embed=embed)


@bot.command(name="satınal", aliases=["buy"], description="Marketten ürün satın alır.")
async def satinal(ctx, urun_id: str):
    if urun_id not in MARKET_ESYALARI:
        await ctx.send("❌ Geçersiz ürün ID'si! Görmek için: `!market`")
        return

    esya = MARKET_ESYALARI[urun_id]
    user_id = ctx.author.id
    bakiye = bakiye_al(user_id)

    if bakiye < esya["fiyat"]:
        await ctx.send(f"❌ Yeterli coinin yok! Gerekli: **{esya['fiyat']:,} Coin**, Sende olan: **{bakiye:,} Coin** 🪙")
        return

    # 1. Standart Rol
    if esya["tip"] == "rol":
        rol = discord.utils.get(ctx.guild.roles, name=esya["rol"])
        if not rol:
            await ctx.send(f"⚠️ Sunucuda **{esya['rol']}** isimli rol bulunamadı! Yetkililere ulaşın.")
            return

        if rol in ctx.author.roles:
            await ctx.send("❌ Bu role zaten sahipsin!")
            return

        try:
            COINLER[user_id] -= esya["fiyat"]
            verileri_kaydet()
            await ctx.author.add_roles(rol)
            await ctx.send(f"🎉 Tebrikler! **{esya['fiyat']:,} Coin** ödeyerek **{esya['isim']}** rolünü satın aldın!")
        except Exception as e:
            await ctx.send(f"❌ Rol verilirken hata oluştu: {e}")

    # 2. Özel Renk (En altta oluşturulur)
    elif esya["tip"] == "ozel_renk":
        rol_adi = f"Renk | {ctx.author.name}"
        mevcut_rol = discord.utils.get(ctx.author.roles, name=rol_adi)
        if mevcut_rol:
            await ctx.send("❌ Zaten renk rolün var! Değiştirmek için: `!colour <hex>`")
            return

        try:
            COINLER[user_id] -= esya["fiyat"]
            verileri_kaydet()

            yeni_rol = await ctx.guild.create_role(name=rol_adi, reason=f"{ctx.author} için renk rolü.")
            await ctx.author.add_roles(yeni_rol)
            await ctx.send(
                f"🎉 Tebrikler! **{esya['fiyat']:,} Coin** ödeyerek renk hakkı aldın!\n"
                f"✨ **{rol_adi}** rolün oluşturuldu. `!colour #HEXKODU` yazarak rengini ayarla!"
            )
        except discord.Forbidden:
            await ctx.send("❌ Botun yetkisi yetersiz!")
        except Exception as e:
            await ctx.send(f"❌ Hata: {e}")

    # 3. Şans Kasası
    elif esya["tip"] == "kasa":
        try:
            COINLER[user_id] -= esya["fiyat"]
            kasa_mesaj = await ctx.send(f"🎁 **{ctx.author.mention}**, Gizemli Kasa'yı açıyor... 📦✨")
            await asyncio.sleep(1.5)

            kazanc = random.randint(750, 1250)
            COINLER[user_id] += kazanc
            verileri_kaydet()

            fark = kazanc - esya["fiyat"]
            durum_metni = f"Kâr! 🎉 (+{fark})" if fark > 0 else (f"Zarar... 😅 ({fark})" if fark < 0 else "Nötr! 🔄")

            embed = discord.Embed(
                title="🎁 Gizemli Kasa Açıldı!",
                description=(
                    f"💰 **Ödül:** `+{kazanc:,} Coin`\n"
                    f"📊 **Durum:** {durum_metni}\n"
                    f"🪙 **Güncel Bakiye:** **{COINLER[user_id]:,} Coin**"
                ),
                color=discord.Color.purple(),
            )
            await kasa_mesaj.edit(content=None, embed=embed)
        except Exception as e:
            await ctx.send(f"❌ Kasa açılırken hata: {e}")


@bot.command(name="renk", aliases=["colour", "color"], description="Renk rolünün rengini değiştirir.")
async def renk_degistir(ctx, hex_kodu: str):
    hedef_rol = next((rol for rol in ctx.author.roles if rol.name.startswith("Renk | ")), None)

    if not hedef_rol:
        await ctx.send("❌ Renk rolün yok! Marketten almak için: `!market`")
        return

    hex_kodu = hex_kodu.strip()
    if not hex_kodu.startswith("#"):
        hex_kodu = "#" + hex_kodu

    try:
        temiz_kod = hex_kodu.replace("#", "")
        renk_degeri = int(temiz_kod, 16)
        await hedef_rol.edit(color=discord.Color(renk_degeri), reason=f"{ctx.author} rengini güncelledi.")
        await ctx.send(f"🎨 Başarılı! Rengin **{hex_kodu}** olarak güncellendi!")
    except ValueError:
        await ctx.send("❌ Geçersiz hex kodu! Örn: `!colour #ff0000`")
    except Exception as e:
        await ctx.send(f"❌ Hata: {e}")


# ==========================================
# 7. KUMAR SİSTEMLERİ (RULET, BJ, AVIATOR)
# ==========================================

@bot.command(name="rulet", description="Rulet oynarsın.")
async def rulet(ctx, renk: str, miktar: int):
    if "rulet" not in ctx.channel.name.lower():
        await ctx.send("❌ Bu komut sadece **🎰rulet** kanalında kullanılabilir!")
        return

    renk = renk.lower()
    if renk not in ["kırmızı", "siyah", "yeşil"]:
        await ctx.send("❌ Geçersiz renk! Seçenekler: `kırmızı`, `siyah`, `yeşil`")
        return

    if miktar <= 0:
        await ctx.send("❌ 0'dan büyük miktar girmelisin!")
        return

    user_id = ctx.author.id
    bakiye = bakiye_al(user_id)

    if bakiye < miktar:
        await ctx.send(f"❌ Yeterli coinin yok! Bakiyen: **{bakiye:,} Coin** 🪙")
        return

    # Ses efekti kontrolü
    vc = ctx.guild.voice_client
    if ctx.author.voice and ctx.author.voice.channel:
        ses_kanali = ctx.author.voice.channel
        if vc is None:
            try:
                vc = await ses_kanali.connect()
            except Exception as e:
                print(f"Ses kanalına bağlanma hatası: {e}")

    ses_dosyasi_yolu = "rulet_sesi.m4a"
    if vc and os.path.exists(ses_dosyasi_yolu):
        try:
            source = discord.FFmpegPCMAudio(ses_dosyasi_yolu, options="-vn")
            def ses_bitti(error):
                fut = asyncio.run_coroutine_threadsafe(vc.disconnect(), bot.loop)
                try:
                    fut.result()
                except Exception as e:
                    print(f"Çıkış hatası: {e}")

            if not vc.is_playing():
                vc.play(source, after=ses_bitti)
        except Exception as e:
            print(f"Ses oynatma hatası: {e}")

    animasyon_embed = discord.Embed(
        title="🎰 Rulet Çarkı Dönüyor...",
        description="Top dönüyor... 🔄",
        color=discord.Color.blurple(),
    )
    mesaj = await ctx.send(embed=animasyon_embed)

    for adim in ["🔴 Kırmızı...", "⚫ Siyah...", "🟢 Yeşil...", "🔴 Kırmızı...", "⚫ Siyah..."]:
        animasyon_embed.description = f"Top hızla dönüyor: **{adim}** 🎲"
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
            embed.title = "🎉 İNANILMAZ! YEŞİL GELDİ!"
            embed.description = f"🟢 Yeşil çıktı! **{kazanc:,} Coin** kazandın! 🚀\nGüncel bakiye: **{COINLER[user_id]:,} Coin**"
        else:
            kazanc = miktar * 2
            COINLER[user_id] += kazanc - miktar
            embed.color = discord.Color.gold()
            embed.title = "✨ KAZANDIN!"
            embed.description = f"**{gelen_renk.capitalize()}** çıktı! **{kazanc:,} Coin** kazandın! 💰\nGüncel bakiye: **{COINLER[user_id]:,} Coin**"
    else:
        COINLER[user_id] -= miktar
        embed.color = discord.Color.red()
        embed.title = "💸 KAYBETTİN!"
        embed.description = f"**{gelen_renk.capitalize()}** çıktı. **{miktar:,} Coin** kaybettin... 🤡\nGüncel bakiye: **{COINLER[user_id]:,} Coin**"

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

    @discord.ui.button(label="Kart Çek (Hit)", style=discord.ButtonStyle.primary, custom_id="bj_hit")
    async def hit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("❌ Bu oyunu sen başlatmadın!", ephemeral=True)
            return

        await interaction.response.defer()
        self.oy_kartlar.append(self.deste.pop())
        oy_toplam = self.kart_toplam(self.oy_kartlar)

        if oy_toplam > 21:
            COINLER[self.ctx.author.id] -= self.miktar
            verileri_kaydet()

            embed = discord.Embed(
                title="💥 PATLADIN! (21'i Geçtin)",
                description=f"Kartların: {self.oy_kartlar} (Toplam: **{oy_toplam}**)\n**{self.miktar:,} Coin** kaybettin! 💸",
                color=discord.Color.red(),
            )
            self.stop()
            await interaction.message.edit(embed=embed, view=None)
        else:
            embed = discord.Embed(
                title="🃏 Blackjack (21)",
                description=f"**Kartların:** {self.oy_kartlar} (Toplam: **{oy_toplam}**)\n**Botun Açık Kartı:** [{self.bot_kartlar[0]}, ?]",
                color=discord.Color.blue(),
            )
            await interaction.message.edit(embed=embed, view=self)

    @discord.ui.button(label="Dur (Stand)", style=discord.ButtonStyle.success, custom_id="bj_stand")
    async def stand_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("❌ Bu oyunu sen başlatmadın!", ephemeral=True)
            return

        await interaction.response.defer()
        while self.kart_toplam(self.bot_kartlar) < 17:
            self.bot_kartlar.append(self.deste.pop())

        oy_toplam = self.kart_toplam(self.oy_kartlar)
        bot_toplam = self.kart_toplam(self.bot_kartlar)
        user_id = self.ctx.author.id
        embed = discord.Embed(title="🃏 Blackjack Sonucu")

        if bot_toplam > 21 or oy_toplam > bot_toplam:
            COINLER[user_id] += self.miktar
            embed.color = discord.Color.green()
            embed.title = "🎉 KAZANDIN!"
            embed.description = (
                f"**Kartların:** {self.oy_kartlar} (Toplam: **{oy_toplam}**)\n"
                f"**Botun Kartları:** {self.bot_kartlar} (Toplam: **{bot_toplam}**)\n\n"
                f"**+{self.miktar:,} Coin** kazandın! 💰"
            )
        elif oy_toplam < bot_toplam:
            COINLER[user_id] -= self.miktar
            embed.color = discord.Color.red()
            embed.title = "💸 KAYBETTİN!"
            embed.description = (
                f"**Kartların:** {self.oy_kartlar} (Toplam: **{oy_toplam}**)\n"
                f"**Botun Kartları:** {self.bot_kartlar} (Toplam: **{bot_toplam}**)\n\n"
                f"**-{self.miktar:,} Coin** kaybettin! 🤡"
            )
        else:
            embed.color = discord.Color.gold()
            embed.title = "🤝 BERABERE!"
            embed.description = (
                f"**Kartların:** {self.oy_kartlar} (Toplam: **{oy_toplam}**)\n"
                f"**Botun Kartları:** {self.bot_kartlar} (Toplam: **{bot_toplam}**)\n\n"
                f"Coin iade edildi."
            )

        verileri_kaydet()
        self.stop()
        await interaction.message.edit(embed=embed, view=None)


@bot.command(name="blackjack", aliases=["bj", "21"], description="Blackjack oynarsın.")
async def blackjack(ctx, miktar: int):
    if "blackjack" not in ctx.channel.name.lower():
        await ctx.send("❌ Bu komut sadece **🃏blackjack** kanalında kullanılabilir!")
        return

    if miktar <= 0:
        await ctx.send("❌ 0'dan büyük bahis girmelisin!")
        return

    user_id = ctx.author.id
    bakiye = bakiye_al(user_id)

    if bakiye < miktar:
        await ctx.send(f"❌ Yeterli coinin yok! Bakiyen: **{bakiye:,} Coin** 🪙")
        return

    deste = [2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 10, 10, 11] * 4
    random.shuffle(deste)

    oy_kartlar = [deste.pop(), deste.pop()]
    bot_kartlar = [deste.pop(), deste.pop()]

    view = BlackjackView(ctx, miktar, oy_kartlar, bot_kartlar, deste)
    embed = discord.Embed(
        title="🃏 Blackjack (21)",
        description=(
            f"**Kartların:** {oy_kartlar} (Toplam: **{view.kart_toplam(oy_kartlar)}**)\n"
            f"**Botun Açık Kartı:** [{bot_kartlar[0]}, ?]\n\n"
            f"Kart çekmek mi istersin, durmak mı?"
        ),
        color=discord.Color.blue(),
    )
    await ctx.send(embed=embed, view=view)


# --- AVIATOR ---
@bot.command(name="aviator")
async def aviator(ctx, miktar: int = None):
    izin_verilen_kanal = "✈️aviator"
    if ctx.channel.name != izin_verilen_kanal:
        await ctx.send(f"❌ Bu komut sadece **#{izin_verilen_kanal}** kanalında kullanılabilir!", delete_after=5)
        return

    user_id = ctx.author.id
    MAKS_BAHIS = 10000

    if miktar is None or miktar <= 0:
        await ctx.send("❌ Lütfen geçerli miktar gir! Örn: `!aviator 100`")
        return

    if miktar > MAKS_BAHIS:
        await ctx.send(f"⚠️ Maksimum bahis **{MAKS_BAHIS:,} Coin** kadardır.")
        return

    bakiye = bakiye_al(user_id)
    if bakiye < miktar:
        await ctx.send(f"❌ Yeterli coinin yok! Cüzdan: **{bakiye:,} Coin**")
        return

    if user_id in DEVAM_EDEN_AVIATORLER:
        await ctx.send("❌ Zaten devam eden bir oyunun var!")
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

        @discord.ui.button(label="💸 PARAYI ÇEK!", style=discord.ButtonStyle.green, emoji="🚀")
        async def parayi_cek(self, interaction: discord.Interaction, button: discord.ui.Button):
            nonlocal kazandi_mi
            if interaction.user.id != user_id:
                await interaction.response.send_message("❌ Bu oyun senin değil!", ephemeral=True)
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
        title="✈️ AVIATOR - Uçuş Simülasyonu",
        description=(
            "🚀 **Uçak kalkış yapıyor...**\n\n"
            "```text\n 1.00x | ✈️ . . . . . . . . . . .\n       | ─────────────────────────\n```\n"
            f"**Bahis:** {miktar:,} Coin\n📈 **Anlık Çarpan:** `{carpan:.2f}x`"
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
                f"✈️ **Uçak tırmanmaya devam ediyor!**\n\n"
                f"```text\n {carpan:.2f}x |{bosluk}✈️{kalan_bosluk}\n       | ─────────────────────────\n```\n"
                f"**Bahis:** {miktar:,} Coin\n📈 **Anlık Çarpan:** `{carpan:.2f}x`"
            )
            await mesaj.edit(embed=embed, view=view)

        if kazandi_mi:
            kazanc = int(miktar * carpan)
            COINLER[user_id] += kazanc
            verileri_kaydet()

            embed.title = "🎉 BAŞARILI TAHLİYE!"
            embed.color = discord.Color.green()
            embed.description = (
                f"Parayı zamanında çektin!\n\n"
                f"✨ **Çarpan:** `{carpan:.2f}x`\n"
                f"💰 **Kazanılan:** **+{kazanc:,} Coin**\n"
                f"🏦 **Yeni Cüzdan:** `{COINLER[user_id]:,} Coin`"
            )
            await mesaj.edit(embed=embed, view=None)
        else:
            verileri_kaydet()
            embed.title = "💥 UÇAK KAÇTI (BOOM)!"
            embed.color = discord.Color.red()
            embed.description = (
                f"Uçak `{patlama_noktasi}x` oranında gözden kayboldu.\n\n"
                f"```text\n 💥 BOOM! | ✈️💨 (Gözden kayboldu)\n```\n"
                f"💸 **Kaybedilen:** `{miktar:,} Coin`\n"
                f"🏦 **Kalan Cüzdan:** `{COINLER[user_id]:,} Coin`"
            )
            await mesaj.edit(embed=embed, view=None)

    except Exception as e:
        print(f"Aviator hatası: {e}")
    finally:
        DEVAM_EDEN_AVIATORLER.discard(user_id)


# ==========================================
# 8. MESLEK SİSTEMİ (GLOBAL)
# ==========================================

GECERLI_MESLEKLER = ["police", "pilot", "doctor"]

async def kanal_kontrol(ctx):
    if "meslekler" not in ctx.channel.name.lower() and "jobs" not in ctx.channel.name.lower():
        await ctx.send("❌ Bu komutu sadece **🥼meslekler / 💼jobs** kanalında kullanabilirsin!")
        return False
    return True


@bot.command(name="meslekler", aliases=["jobs"], description="Meslekleri listeler.")
async def meslekler_komut(ctx):
    if not await kanal_kontrol(ctx):
        return

    embed = discord.Embed(
        title="🥼 Sunucu Meslekler Paneli 2.0 / Server Jobs Panel 2.0",
        description=(
            "**TR:** Güncellenen meslek oranları:\n"
            "* Meslek seçmek için: `!meslekseç <police/pilot/doctor>` veya `!joinjob`\n"
            "* Bekleme süresi: **3 dakika**\n"
            "* İstifa: `!istifa` veya `!quitjob`\n\n"
            "**EN:** Updated job system:\n"
            "* Choose job: `!joinjob <police/pilot/doctor>`\n"
            "* Cooldown: **3 minutes**\n"
            "* Resign: `!quitjob`"
        ),
        color=discord.Color.blue(),
    )
    embed.add_field(name="👮 Police / Polis", value="`!police` veya `!polis` (Kazan: +550 | Kaybet: -250)", inline=False)
    embed.add_field(name="👨‍⚕️ Doctor / Doktor", value="`!doctor` veya `!doktor` (Kazan: +1,000 | Kaybet: -%5 Cüzdan)", inline=False)
    embed.add_field(name="✈️ Pilot", value="`!pilot` (Kazan: +1,000 | Kaybet: 10 Dk Uçuş Yasağı)", inline=False)
    await ctx.send(embed=embed)


@bot.command(name="meslekseç", aliases=["joinjob"], description="Mesleğe girer.")
async def mesleksec(ctx, *, meslek_adi: str):
    if not await kanal_kontrol(ctx):
        return

    meslek_adi = meslek_adi.lower()
    user_id = str(ctx.author.id)

    if meslek_adi not in GECERLI_MESLEKLER:
        await ctx.send("❌ Geçersiz meslek! Seçenekler: `police`, `pilot`, `doctor`")
        return

    simdiki_zaman = datetime.datetime.now().timestamp()

    if user_id in MESLEKLER_VERI:
        son_degisim = MESLEKLER_VERI[user_id].get("son_degisim", 0)
        gecen_sure = simdiki_zaman - son_degisim
        if gecen_sure < 86400:
            kalan_sure = int(86400 - gecen_sure)
            saat = kalan_sure // 3600
            dakika = (kalan_sure % 3600) // 60
            await ctx.send(f"⏳ Yeni meslek değiştirmek için **{saat} saat {dakika} dakika** beklemelisin!")
            return

    rol_mapping = {"police": "Police", "doctor": "Doctor", "pilot": "Pilot"}
    rol_ismi = rol_mapping.get(meslek_adi, meslek_adi.capitalize())
    hedef_rol = discord.utils.get(ctx.guild.roles, name=rol_ismi)

    if not hedef_rol:
        await ctx.send(f"⚠️ Sunucuda **{rol_ismi}** isimli rol bulunamadı!")
        return

    # Eski Rolleri Temizle
    for diger_meslek in GECERLI_MESLEKLER:
        diger_rol_ismi = rol_mapping.get(diger_meslek, diger_meslek.capitalize())
        diger_rol = discord.utils.get(ctx.guild.roles, name=diger_rol_ismi)
        if diger_rol and diger_rol in ctx.author.roles:
            try:
                await ctx.author.remove_roles(diger_rol)
            except Exception as e:
                print(f"Eski rol silme hatası: {e}")

    try:
        await ctx.author.add_roles(hedef_rol)
    except Exception as e:
        await ctx.send(f"❌ Rol verilemedi: {e}")
        return

    if user_id not in MESLEKLER_VERI:
        MESLEKLER_VERI[user_id] = {}

    MESLEKLER_VERI[user_id]["meslek"] = meslek_adi
    MESLEKLER_VERI[user_id]["son_degisim"] = simdiki_zaman
    MESLEKLER_VERI[user_id]["cezali"] = False
    verileri_kaydet()

    await ctx.send(f"🎉 Tebrikler! Başarıyla **{rol_ismi}** oldun!")


@bot.command(name="istifa", aliases=["quitjob"], description="Meslekten ayrılır.")
async def istifa_komut(ctx):
    if not await kanal_kontrol(ctx):
        return

    user_id = str(ctx.author.id)
    if user_id not in MESLEKLER_VERI or not MESLEKLER_VERI[user_id].get("meslek"):
        await ctx.send("❌ Zaten bir mesleğin yok!")
        return

    rol_mapping = {"police": "Police", "doctor": "Doctor", "pilot": "Pilot"}
    for meslek in GECERLI_MESLEKLER:
        rol_ismi = rol_mapping.get(meslek, meslek.capitalize())
        rol = discord.utils.get(ctx.guild.roles, name=rol_ismi)
        if rol and rol in ctx.author.roles:
            try:
                await ctx.author.remove_roles(rol)
            except Exception as e:
                print(f"İstifa rol silme hatası: {e}")

    MESLEKLER_VERI[user_id]["meslek"] = None
    MESLEKLER_VERI[user_id]["cezali"] = False
    verileri_kaydet()

    await ctx.send(f"💼 **{ctx.author.mention}** başarıyla istifa etti. 24 saat bekleme süresi başladı.")


@bot.command(name="polis", aliases=["police"], description="Polis görevi.")
async def polis_komut(ctx):
    if not await kanal_kontrol(ctx):
        return

    user_id = str(ctx.author.id)
    if user_id not in MESLEKLER_VERI or MESLEKLER_VERI[user_id].get("meslek") != "police":
        await ctx.send("❌ Polis değilsin! Olmak için: `!joinjob police`")
        return

    simdiki_zaman = datetime.datetime.now().timestamp()
    son_polis_islem = MESLEKLER_VERI[user_id].get("son_polis_islem", 0)
    cooldown_suresi = 180

    if simdiki_zaman - son_polis_islem < cooldown_suresi:
        kalan = int(cooldown_suresi - (simdiki_zaman - son_polis_islem))
        await ctx.send(f"⏳ Beklemelisin: **{kalan // 60} dakika {kalan % 60} saniye**")
        return

    MESLEKLER_VERI[user_id]["son_polis_islem"] = simdiki_zaman
    verileri_kaydet()
    bakiye_al(int(user_id))

    if random.choice([True, False]):
        COINLER[int(user_id)] += 550
        verileri_kaydet()
        embed = discord.Embed(
            title="🚨 Suçlu Yakalandı!",
            description=f"**{ctx.author.mention}** suçluyu yakaladı!\n🎉 **+550 Coin** | Bakiye: **{COINLER[int(user_id)]:,} Coin**",
            color=discord.Color.green(),
        )
    else:
        COINLER[int(user_id)] = max(0, COINLER[int(user_id)] - 250)
        verileri_kaydet()
        embed = discord.Embed(
            title="🏃 Suçlu Kaçtı!",
            description=f"**{ctx.author.mention}** suçluyu elinden kaçırdı!\n💸 **-250 Coin** | Bakiye: **{COINLER[int(user_id)]:,} Coin**",
            color=discord.Color.red(),
        )
    await ctx.send(embed=embed)


@bot.command(name="doktor", aliases=["doctor"], description="Doktor görevi.")
async def doktor_komut(ctx):
    if not await kanal_kontrol(ctx):
        return

    user_id = str(ctx.author.id)
    if user_id not in MESLEKLER_VERI or MESLEKLER_VERI[user_id].get("meslek") != "doctor":
        await ctx.send("❌ Doktor değilsin! Olmak için: `!joinjob doctor`")
        return

    simdiki_zaman = datetime.datetime.now().timestamp()
    son_doktor_islem = MESLEKLER_VERI[user_id].get("son_doktor_islem", 0)
    cooldown_suresi = 180

    if simdiki_zaman - son_doktor_islem < cooldown_suresi:
        kalan = int(cooldown_suresi - (simdiki_zaman - son_doktor_islem))
        await ctx.send(f"⏳ Beklemelisin: **{kalan // 60} dakika {kalan % 60} saniye**")
        return

    MESLEKLER_VERI[user_id]["son_doktor_islem"] = simdiki_zaman
    verileri_kaydet()
    bakiye_al(int(user_id))

    if random.choice([True, False]):
        COINLER[int(user_id)] += 1000
        verileri_kaydet()
        embed = discord.Embed(
            title="🏥 Başarılı Ameliyat!",
            description=f"**{ctx.author.mention}** hastayı kurtardı!\n🎉 **+1,000 Coin** | Bakiye: **{COINLER[int(user_id)]:,} Coin**",
            color=discord.Color.green(),
        )
    else:
        mevcut_bakiye = COINLER[int(user_id)]
        kesinti = int(mevcut_bakiye * 0.05)
        COINLER[int(user_id)] = max(0, mevcut_bakiye - kesinti)
        verileri_kaydet()
        embed = discord.Embed(
            title="💔 Başarısız Ameliyat!",
            description=f"**{ctx.author.mention}** ameliyatı tamamlayamadı.\n💸 **-%5 Kesinti (-{kesinti:,} Coin)** | Bakiye: **{COINLER[int(user_id)]:,} Coin**",
            color=discord.Color.red(),
        )
    await ctx.send(embed=embed)


@bot.command(name="pilot", description="Pilot görevi.")
async def pilot_komut(ctx):
    if not await kanal_kontrol(ctx):
        return

    user_id = str(ctx.author.id)
    if user_id not in MESLEKLER_VERI or MESLEKLER_VERI[user_id].get("meslek") != "pilot":
        await ctx.send("❌ Pilot değilsin! Olmak için: `!joinjob pilot`")
        return

    simdiki_zaman = datetime.datetime.now().timestamp()
    son_islem = MESLEKLER_VERI[user_id].get("son_islem", 0)

    yasak_suresi = 600 if MESLEKLER_VERI[user_id].get("cezali", False) else 0
    if yasak_suresi > 0 and simdiki_zaman - son_islem < yasak_suresi:
        kalan = int(yasak_suresi - (simdiki_zaman - son_islem))
        await ctx.send(f"⏳ Uçuş yasağın devam ediyor! Kalan: **{kalan // 60} dakika {kalan % 60} saniye**")
        return

    son_pilot_islem = MESLEKLER_VERI[user_id].get("son_pilot_islem", 0)
    cooldown_suresi = 180
    if simdiki_zaman - son_pilot_islem < cooldown_suresi:
        kalan = int(cooldown_suresi - (simdiki_zaman - son_pilot_islem))
        await ctx.send(f"⏳ Bakım süresi bekleniyor: **{kalan // 60} dakika {kalan % 60} saniye**")
        return

    MESLEKLER_VERI[user_id]["son_pilot_islem"] = simdiki_zaman
    MESLEKLER_VERI[user_id]["cezali"] = False
    MESLEKLER_VERI[user_id]["son_islem"] = simdiki_zaman
    bakiye_al(int(user_id))

    if random.choice([True, False]):
        COINLER[int(user_id)] += 1000
        verileri_kaydet()
        embed = discord.Embed(
            title="✈️ Güvenli Uçuş!",
            description=f"**{ctx.author.mention}** uçuşu başarıyla tamamladı!\n🎉 **+1,000 Coin** | Bakiye: **{COINLER[int(user_id)]:,} Coin**",
            color=discord.Color.green(),
        )
    else:
        MESLEKLER_VERI[user_id]["cezali"] = True
        MESLEKLER_VERI[user_id]["son_islem"] = simdiki_zaman
        verileri_kaydet()
        embed = discord.Embed(
            title="⚠️ Uçuş İptali!",
            description=f"**{ctx.author.mention}** tehlikeli hava koşullarıyla karşılaştı!\n🚫 **10 dakika uçuş yasağı** aldın!",
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
        await ctx.send("❌ Geçersiz süre birimi! (`s`, `d`, `h`, `g`)")
        return

    sure = datetime.timedelta(seconds=toplam_saniye)
    try:
        await kullanici.timeout(sure, reason=f"{ctx.author} tarafından mutelendi.")
        await ctx.send(f"🔒 **{kullanici.mention}** başarıyla **{sayi} {birim}** süreyle mutelendi!")

        mod_kanal = discord.utils.get(ctx.guild.text_channels, name="bot-moderasyon")
        if mod_kanal:
            embed = discord.Embed(title="🔒 Mute Atıldı", color=discord.Color.red(), timestamp=datetime.datetime.now())
            embed.add_field(name="Üye", value=f"{kullanici.mention} (`{kullanici.id}`)", inline=False)
            embed.add_field(name="Yetkili", value=f"{ctx.author.mention}", inline=False)
            embed.add_field(name="Süre", value=f"{sayi} {birim}", inline=False)
            await mod_kanal.send(embed=embed)
    except Exception as e:
        await ctx.send(f"Hata: {e}")


@bot.command(name="unmute", description="Mute kaldırır.")
@commands.has_permissions(moderate_members=True)
async def unmute(ctx, kullanici: discord.Member):
    try:
        await kullanici.timeout(None, reason=f"{ctx.author} tarafından kaldırıldı.")
        await ctx.send(f"🔊 **{kullanici.mention}** adlı kullanıcının mutesi kaldırıldı!")
    except Exception as e:
        await ctx.send(f"Hata: {e}")


@bot.command(name="ban", description="Kullanıcıyı banlar.")
@commands.has_permissions(ban_members=True)
async def ban(ctx, kullanici: discord.Member, *, sebep: str = "Belirtilmedi"):
    try:
        await kullanici.ban(reason=sebep)
        await ctx.send(f"🔨 **{kullanici.name}** banlandı! Sebep: {sebep}")
    except Exception as e:
        await ctx.send(f"Hata: {e}")


@bot.command(name="kick", description="Kullanıcıyı atar.")
@commands.has_permissions(kick_members=True)
async def kick(ctx, kullanici: discord.Member, *, sebep: str = "Belirtilmedi"):
    try:
        await kullanici.kick(reason=sebep)
        await ctx.send(f"👢 **{kullanici.name}** atıldı! Sebep: {sebep}")
    except Exception as e:
        await ctx.send(f"Hata: {e}")


@bot.command(name="unban", description="ID ile ban kaldırır.")
@commands.has_permissions(ban_members=True)
async def unban(ctx, user_id: str):
    if not user_id.isdigit():
        await ctx.send("❌ Geçerli bir Kullanıcı ID'si girin!")
        return

    try:
        user = await bot.fetch_user(int(user_id))
        await ctx.guild.unban(user)
        await ctx.send(f"🔓 **{user.name}** yasağı kaldırıldı!")
    except Exception as e:
        await ctx.send(f"Hata: {e}")


@bot.command(name="odayaçek", aliases=["çek"], description="Kullanıcıyı odanıza çeker.")
async def odayacek(ctx, kullanici: discord.Member):
    if not ctx.author.guild_permissions.move_members:
        await ctx.send("❌ **Üyeleri Taşı** yetkin yok!")
        return

    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("❌ Bir ses kanalında değilsin!")
        return

    if not kullanici.voice or not kullanici.voice.channel:
        await ctx.send(f"❌ **{kullanici.name}** ses kanalında değil!")
        return

    hedef_kanal = ctx.author.voice.channel
    try:
        await kullanici.move_to(hedef_kanal, reason=f"{ctx.author} tarafından çekildi.")
        await ctx.send(f"🎯 **{kullanici.mention}** -> **{hedef_kanal.name}** kanalına çekildi!")
    except Exception as e:
        await ctx.send(f"Hata: {e}")


@bot.command(name="sil", description="Mesaj siler.")
@commands.has_permissions(manage_messages=True)
async def sil(ctx, sayi: int):
    if sayi <= 0:
        await ctx.send("❌ 0'dan büyük bir sayı girmelisin!")
        return

    silinen = await ctx.channel.purge(limit=sayi + 1)
    mesaj = await ctx.send(f"🧹 **{len(silinen) - 1}** adet mesaj silindi!")
    await asyncio.sleep(3)
    await mesaj.delete()


@bot.command(name="kapat", description="Kanalı kilitler.")
@commands.has_permissions(manage_channels=True)
async def kapat(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
    await ctx.send(f"🔒 **{ctx.channel.name}** kilitlendi!")


@bot.command(name="aç", description="Kanal kilidini açar.")
@commands.has_permissions(manage_channels=True)
async def ac(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=True)
    await ctx.send(f"🔓 **{ctx.channel.name}** mesajlara açıldı!")


@bot.command(name="slowmode", description="Yavaş mod ayarlar.")
@commands.has_permissions(manage_channels=True)
async def slowmode(ctx, saniye: int = 0):
    try:
        await ctx.channel.edit(slowmode_delay=saniye)
        if saniye == 0:
            await ctx.send("⏱️ Yavaş mod kaldırıldı.")
        else:
            await ctx.send(f"⏱️ Yavaş mod **{saniye}** saniye yapıldı!")
    except Exception as e:
        await ctx.send(f"Hata: {e}")


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
