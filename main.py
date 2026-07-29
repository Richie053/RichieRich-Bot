import asyncio
import datetime
import json
import os
import itertools
import random
import discord
from discord.ext import commands
import yt_dlp
from dotenv import load_dotenv
from discord.ext import tasks

# --- ÇEVRE DEĞİŞKENLERİ (ENV) ---
load_dotenv()
TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

# --- DOSYA TABANLI EKONOMİ VE MESLEK SİSTEMİ ---
VERI_DOSYASI = "ekonomi.json"

def verileri_yukle():
    if os.path.exists(VERI_DOSYASI):
        with open(VERI_DOSYASI, "r", encoding="utf-8") as f:
            veriler = json.load(f)
            
            coinler = {int(k): v["bakiye"] for k, v in veriler.items() if "bakiye" in v}
            sureler = {}
            meslekler_veri = {}
            
            for k, v in veriler.items():
                user_id_str = str(k)
                user_id_int = int(k)
                
                # Günlük süre yükleme
                if v.get("son_gunluk"):
                    sureler[user_id_int] = datetime.datetime.fromisoformat(v["son_gunluk"])
                
                # Meslek verilerini yükleme (String ID olarak tutuyoruz)
                if v.get("meslek_bilgi"):
                    meslekler_veri[user_id_str] = v["meslek_bilgi"]
                    
            return coinler, sureler, meslekler_veri
            
    return {}, {}, {}


def verileri_kaydet():
    veriler = {}
    
    # Tüm kullanıcı ID'lerini birleştirip ortak bir JSON yapısı oluşturuyoruz
    tum_idler = set(list(COINLER.keys()) + [int(k) for k in GUNLUK_SURELER.keys()] + [int(k) for k in MESLEKLER_VERI.keys() if str(k).isdigit()])
    
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


# Verileri yükle (Artık MESLEKLER_VERI de dosyadan okunuyor!)
COINLER, GUNLUK_SURELER, MESLEKLER_VERI = verileri_yukle()


@bot.event
async def on_ready():
    print(f"{bot.user.name} olarak giriş yapıldı ve bot aktif!")
    bot.add_view(OdaYonimView())


# --- EVENT (OLAY) SİSTEMLERİ ---

# --- YASAKLI KELİME FİLTRESİ VE KURAL YÖNLENDİRME ---
YASAKLI_KELIMELER = [
    "annesiz",
    "orospuçocuğu",
    "oç",
    "oe",
]


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    mesaj_icerik = message.content.lower()

    # 1. Yasaklı Kelime Filtresi
    for kelime in YASAKLI_KELIMELER:
        if kelime in mesaj_icerik:
            try:
                await message.delete()
                sure = datetime.timedelta(minutes=1)
                await message.author.timeout(
                    sure,
                    reason="Yasaklı kelime (küfür) kullandığı için otomatik mute.",
                )
                await message.author.send(
                    f"⚠️ Merhaba **{message.author.name}**, sunucumuzda bu tür kelimeleri"
                    " kullanmamalısınız! Bu yüzden **1 dakika** süreyle"
                    " mutelendiniz."
                )

                mod_kanal = discord.utils.get(
                    message.guild.text_channels, name="bot-moderasyon"
                )
                if mod_kanal:
                    embed = discord.Embed(
                        title="🚨 Otomatik Mute Logu",
                        color=discord.Color.orange(),
                        timestamp=datetime.datetime.now(),
                    )
                    embed.add_field(
                        name="Ceza Alan Üye",
                        value=f"{message.author.mention} (`{message.author.id}`)",
                        inline=False,
                    )
                    embed.add_field(
                        name="Sebep",
                        value="Yasaklı Kelime Kullanımı",
                        inline=False,
                    )
                    embed.add_field(name="Süre", value="1 Dakika", inline=False)
                    await mod_kanal.send(embed=embed)

            except Exception as e:
                print(f"Küfür filtresi hatası: {e}")
            return

    # 2. Kurallar Kanalına Yönlendirme Kontrolü
    kural_anahtar_kelimeleri = [
        "kural",
        "kurallar",
        "sunucu kuralları",
        "yasak",
        "cezalar",
    ]
    if any(k in mesaj_icerik for k in kural_anahtar_kelimeleri):
        kurallar_kanali = discord.utils.get(
            message.guild.text_channels, name="📝kurallar"
        )
        if kurallar_kanali:
            await message.reply(
                f"📜 Sunucu kuralları hakkında bilgi almak için lütfen"
                f" {kurallar_kanali.mention} kanalını ziyaret edebilirsin!"
            )

    await bot.process_commands(message)


# --- ÖZEL ODA SİSTEMİ ---
TETIKLEYICI_KANAL = "➕ | Oda Oluştur"


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
            yeni_kanal = await guild.create_voice_channel(
                name=oda_adi, category=kategori, overwrites=overwrites
            )
            await member.move_to(yeni_kanal)
        except Exception as e:
            print(f"Özel oda oluşturulurken hata: {e}")

    if before.channel and before.channel != after.channel:
        if before.channel.name.startswith("🔊 |") and len(
            before.channel.members
        ) == 0:
            try:
                await before.channel.delete()
            except Exception as e:
                print(f"Boş özel oda silinirken hata: {e}")


# --- OTOMATİK ROL VE GİRİŞ-ÇIKIŞ ---
@bot.event
async def on_member_join(member):
    rol_adi = "Üye"
    rol = discord.utils.get(member.guild.roles, name=rol_adi)

    if rol:
        try:
            await member.add_roles(
                rol, reason="Sunucuya yeni katıldığı için otomatik rol verildi."
            )
        except Exception as e:
            print(f"❌ Rol verilirken hata oluştu: {e}")

    kanal_adi = "bot-moderasyon"
    kanal = discord.utils.get(member.guild.text_channels, name=kanal_adi)

    if kanal:
        await kanal.send(
            f"📥 **{member.mention}** ({member.name}) sunucuya katıldı! Otomatik"
            f" '{rol_adi}' rolü verildi."
        )


@bot.event
async def on_member_remove(member):
    kanal_adi = "bot-moderasyon"
    kanal = discord.utils.get(member.guild.text_channels, name=kanal_adi)

    if kanal:
        await kanal.send(f"📤 **{member.name}** sunucudan ayrıldı.")


# --- BUTONLU ODA KONTROL ARAYÜZÜ (MODAL & PERSISTENT VIEW) ---

class OdaIsimModal(discord.ui.Modal, title="Oda İsmini Değiştir"):
    yeni_isim = discord.ui.TextInput(
        label="Yeni Oda İsmi",
        placeholder="Örn: Şantiyeciler Mekanı",
        max_length=30,
    )

    async def on_submit(self, interaction: discord.Interaction):
        kanal = interaction.user.voice.channel
        if not kanal or not kanal.name.startswith("🔊 |"):
            await interaction.response.send_message(
                "❌ Aktif bir özel odan bulunmuyor!", ephemeral=True
            )
            return

        await kanal.edit(name=f"🔊 | {self.yeni_isim.value}")
        await interaction.response.send_message(
            f"✏️ Odanın adı **{self.yeni_isim.value}** olarak değiştirildi!",
            ephemeral=True,
        )


class OdaYonimView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Odayı Kilitle",
        style=discord.ButtonStyle.danger,
        custom_id="oda_kilit_kalici_id",
    )
    async def kilit_buton(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message(
                "❌ Önce kendi ses odanda olmalısın!", ephemeral=True
            )
            return
        kanal = interaction.user.voice.channel
        if not kanal.name.startswith("🔊 |"):
            await interaction.response.send_message(
                "❌ Burası kişisel bir özel oda değil!", ephemeral=True
            )
            return

        await kanal.set_permissions(interaction.guild.default_role, connect=False)
        await interaction.response.send_message(
            f"🔒 **{kanal.name}** odası kilitlendi!", ephemeral=True
        )

    @discord.ui.button(
        label="Odayı Aç",
        style=discord.ButtonStyle.success,
        custom_id="oda_ac_kalici_id",
    )
    async def ac_buton(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message(
                "❌ Önce kendi ses odanda olmalısın!", ephemeral=True
            )
            return
        kanal = interaction.user.voice.channel
        if not kanal.name.startswith("🔊 |"):
            await interaction.response.send_message(
                "❌ Burası kişisel bir özel oda değil!", ephemeral=True
            )
            return

        await kanal.set_permissions(interaction.guild.default_role, connect=True)
        await interaction.response.send_message(
            f"🔓 **{kanal.name}** odası yeniden açıldı!", ephemeral=True
        )

    @discord.ui.button(
        label="İsim Değiştir",
        style=discord.ButtonStyle.primary,
        custom_id="oda_isim_kalici_id",
    )
    async def isim_buton(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message(
                "❌ Önce kendi ses odanda olmalısın!", ephemeral=True
            )
            return
        kanal = interaction.user.voice.channel
        if not kanal.name.startswith("🔊 |"):
            await interaction.response.send_message(
                "❌ Burası kişisel bir özel oda değil!", ephemeral=True
            )
            return

        await interaction.response.send_modal(OdaIsimModal())


@bot.command(name="odapanel", description="Butonlu oda yönetim panelini kurar.")
@commands.has_permissions(administrator=True)
async def odapanel(ctx):
    embed = discord.Embed(
        title="🎛️ Özel Oda Yönetim Paneli",
        description=(
            "Aşağıdaki butonları kullanarak ses odanızı kilitleyebilir, tekrar"
            " açabilir veya ismini değiştirebilirsiniz!\n\n*(Not: İşlem"
            " yapabilmek için kendi ses odanızda olmanız gerekir.)*"
        ),
        color=discord.Color.blurple(),
    )
    await ctx.send(embed=embed, view=OdaYonimView())
    await ctx.message.delete()


# --- EKONOMİ, MARKET VE KUMAR SİSTEMLERİ ---
def bakiye_al(user_id):
    if user_id not in COINLER:
        COINLER[user_id] = 500
        verileri_kaydet()
    return COINLER[user_id]


@bot.command(
    name="cüzdan",
    aliases=["bakiye"],
    description="Cüzdanındaki coin miktarını gösterir.",
)
async def cuzdan(ctx):
    bakiye = bakiye_al(ctx.author.id)
    embed = discord.Embed(
        title=f"💰 {ctx.author.name} Kişisinin Cüzdanı",
        description=f"Toplam Bakiyen: **{bakiye} Coin** 🪙",
        color=discord.Color.gold(),
    )
    await ctx.send(embed=embed)


@bot.command(
    name="günlük", description="Her gün 200 ücretsiz coin hediyeni alırsın."
)
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
                f"⏳ Hey uyanık! Günlük ödülünü zaten almışsın. Tekrar alabilmek"
                f" için **{kalan_saat} saat {kalan_dakika} dakika** beklemelisin! ⏰"
            )
            return

    bakiye_al(user_id)
    COINLER[user_id] += 200
    GUNLUK_SURELER[user_id] = simdi
    verileri_kaydet()

    await ctx.send(
        f"🎁 Günlük ödülün olan **200 Coin** cüzdanına eklendi! Yeni"
        f" bakiyen: **{COINLER[user_id]} Coin** 🪙"
    )


# --- TOP VE CÜZDAN SIRALAMA KOMUTU ---
@bot.command(
    name="top",
    aliases=["cüzdansıralama"],
    description="Sunucudaki en zengin ilk 5 kişiyi gösterir.",
)
async def top(ctx):
    if not COINLER:
        await ctx.send("❌ Henüz kayıtlı cüzdan bulunmuyor!")
        return

    sirali_liste = sorted(COINLER.items(), key=lambda item: item[1], reverse=True)

    embed = discord.Embed(
        title="🏆 Sunucu Zenginler Listesi (Top 5)",
        description="Sunucumuzun en zengin ilk 5 cüzdan sahibi aşağıdadır:",
        color=discord.Color.gold(),
    )

    medyalar = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]

    for i, (user_id, bakiye) in enumerate(sirali_liste[:5]):
        kullanici = ctx.guild.get_member(user_id)
        if kullanici:
            isim = kullanici.name
        else:
            isim = f"Bilinmeyen Üye (`{user_id}`)"

        embed.add_field(
            name=f"{medyalar[i]} {isim}",
            value=f"Bakiye: **{bakiye} Coin** 🪙",
            inline=False,
        )

    await ctx.send(embed=embed)


# --- PARA EKLEME KOMUTU (YETKİLİ) ---
@bot.command(
    name="paraekle",
    description="Belirtilen kullanıcıya cüzdan bakiyesi ekler.",
)
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
        f"✅ **{kullanici.name}** adlı kullanıcının cüzdanına **{miktar} Coin**"
        f" eklendi! Yeni bakiyesi: **{COINLER[user_id]} Coin** 🪙"
    )


# --- COİN GÖNDERME SİSTEMİ (!gönder) ---
@bot.command(
    name="gönder",
    description="Belirtilen kullanıcıya cüzdanından coin transfer edersin.",
)
async def gonder(ctx, hedef: discord.Member, miktar: int):
    kanal_adi = ctx.channel.name.lower()
    if not any(k in kanal_adi for k in ["komutlar", "rulet", "blackjack"]):
        await ctx.send(
            "❌ Bu komutu sadece **📈komutlar**, **🎰rulet** veya"
            " **🃏blackjack** kanallarında kullanabilirsin!"
        )
        return

    if miktar <= 0:
        await ctx.send("❌ 0'dan büyük bir miktar girmelisin!")
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
        await ctx.send(
            f"❌ Yeterli coinin yok! Güncel bakiyen: **{gonderen_bakiye} Coin**"
            " 🪙"
        )
        return

    COINLER[gonderen_id] -= miktar
    bakiye_al(hedef_id)
    COINLER[hedef_id] += miktar
    verileri_kaydet()

    embed = discord.Embed(
        title="💸 Coin Transferi Başarılı",
        description=(
            f"**{ctx.author.mention}**, **{hedef.mention}** adlı kullanıcıya"
            f" başarıyla **{miktar} Coin** gönderdi! 🪙"
        ),
        color=discord.Color.green(),
    )
    embed.add_field(
        name="Yeni Bakiyen",
        value=f"**{COINLER[gonderen_id]} Coin**",
        inline=True,
    )
    await ctx.send(embed=embed)


# --- MARKET & KİŞİYE ÖZEL RENK SİSTEMİ ---

MARKET_ESYALARI = {
    "1": {"tip": "rol", "isim": "💎 Zengin Rolü", "rol": "Zengin", "fiyat": 25000},
    "2": {"tip": "rol", "isim": "🎩 Milyarder Rolü", "rol": "Milyarder", "fiyat": 50000},
    "3": {"tip": "ozel_renk", "isim": "🎨 Kişiye Özel Renk", "fiyat": 75000},
    "4": {"tip": "kasa", "isim": "🎁 Gizemli Kasa (750-1250 Coin)", "fiyat": 1000},
}


@bot.command(name="market", description="Satın alınabilir rolleri, renkleri ve kasaları listeler.")
async def market(ctx):
    embed = discord.Embed(
        title="🛒 Sunucu Marketi",
        description=(
            "Kazandığın coinler ile aşağıdaki özel rolleri, kişiye özel renk yetkisini veya şans kasalarını satın alabilirsin!\n"
            "Satın almak için: `!satınal <ürün_no>`"
        ),
        color=discord.Color.gold(),
    )

    for id, esya in MARKET_ESYALARI.items():
        if esya["tip"] == "rol":
            detay = f"Tür: **Özel Rol**\nFiyat: **{esya['fiyat']} Coin** 🪙"
        elif esya["tip"] == "ozel_renk":
            detay = f"Tür: **Kişiye Özel Renk** (Sadece sana özel rol açılır, `!renk <kod>` ile değiştirirsin)\nFiyat: **{esya['fiyat']} Coin** 🪙"
        else:
            detay = f"Tür: **Şans Kutusu**\nİçerik: **750 - 1250 Coin Şansı!**\nFiyat: **{esya['fiyat']} Coin** 🪙"

        embed.add_field(
            name=f"[{id}] {esya['isim']}",
            value=detay,
            inline=False,
        )

    await ctx.send(embed=embed)


@bot.command(name="satınal", description="Marketten belirtilen ID ile ürün satın alır.")
async def satinal(ctx, urun_id: str):
    if urun_id not in MARKET_ESYALARI:
        await ctx.send("❌ Geçersiz ürün ID'si! Mağazayı görmek için: `!market`")
        return

    esya = MARKET_ESYALARI[urun_id]
    user_id = ctx.author.id
    
    if 'bakiye_al' in globals():
        bakiye = bakiye_al(user_id)
    else:
        if 'COINLER' not in globals():
            global COINLER
            COINLER = {}
        bakiye = COINLER.get(user_id, 0)

    if bakiye < esya["fiyat"]:
        await ctx.send(
            f"❌ Yeterli coinin yok! İhtiyacın olan: **{esya['fiyat']} Coin**, "
            f"Sende olan: **{bakiye} Coin** 🪙"
        )
        return

    # --- DURUM 1: STANDART ROL ---
    if esya["tip"] == "rol":
        rol = discord.utils.get(ctx.guild.roles, name=esya["rol"])
        if not rol:
            await ctx.send(f"⚠️ Sunucuda **{esya['rol']}** isimli rol bulunamadı! Lütfen bir yetkiliye bildirin.")
            return

        if rol in ctx.author.roles:
            await ctx.send("❌ Bu role zaten sahipsin!")
            return

        try:
            COINLER[user_id] -= esya["fiyat"]
            if 'verileri_kaydet' in globals(): verileri_kaydet()
            await ctx.author.add_roles(rol)
            await ctx.send(f"🎉 Tebrikler! **{esya['fiyat']} Coin** ödeyerek **{esya['isim']}** rolünü satın aldın!")
        except Exception as e:
            await ctx.send(f"❌ Rol verilirken bir hata oluştu: {e}")

    # --- DURUM 2: KİŞİYE ÖZEL RENK ---
    elif esya["tip"] == "ozel_renk":
        rol_adi = f"Renk | {ctx.author.name}"
        
        mevcut_rol = discord.utils.get(ctx.author.roles, name=rol_adi)
        if mevcut_rol:
            await ctx.send("❌ Zaten kişiye özel renk rolüne sahipsin! Rengini değiştirmek için `!renk <kod>` komutunu kullanabilirsin.")
            return

        try:
            COINLER[user_id] -= esya["fiyat"]
            if 'verileri_kaydet' in globals(): verileri_kaydet()

            yeni_rol = await ctx.guild.create_role(
                name=rol_adi, 
                reason=f"{ctx.author} için kişiye özel renk rolü."
            )
            
            bot_rolu = ctx.guild.me.top_role
            hedef_pozisyon = max(1, bot_rolu.position - 1)
            
            await yeni_rol.edit(position=hedef_pozisyon)
            await ctx.author.add_roles(yeni_rol)
            
            await ctx.send(f"🎉 Tebrikler! **{esya['fiyat']} Coin** ödeyerek Kişiye Özel Renk hakkını satın aldın!\n✨ Sana özel **{rol_adi}** rolü oluşturuldu ve yukarı yerleştirildi.\nArtık `!renk #HEXKODU` yazarak isminin rengini dilediğin gibi değiştirebilirsin!")
            
        except discord.Forbidden:
            await ctx.send("❌ Hata: Botun yetkisi yetmiyor! Lütfen Discord'da **Sunucu Ayarları > Roller** kısmından botun rolünü en üstteki yetkili rollerin hemen altına taşı.")
        except Exception as e:
            await ctx.send(f"❌ Kişiye özel renk rolü oluşturulurken beklenmeyen bir hata oluştu: {e}")
            
    # --- DURUM 3: GİZEMLİ KASA ---
    elif esya["tip"] == "kasa":
        try:
            COINLER[user_id] -= esya["fiyat"]
            
            kasa_mesaj = await ctx.send(f"🎁 **{ctx.author.mention}**, Gizemli Kasa'yı satın aldı ve açıyor... Kasa açılıyor, içindekiler aranıyor 📦✨")
            await asyncio.sleep(1.5)
            
            kazanc = random.randint(750, 1250)
            COINLER[user_id] += kazanc
            
            if 'verileri_kaydet' in globals(): verileri_kaydet()

            fark = kazanc - esya["fiyat"]
            if fark > 0:
                durum_metni = f"Kâr ettin! 🎉 (+{fark} Coin kazanç)"
            elif fark < 0:
                durum_metni = f"Zarar ettin... Şansına küs! 😅 ({fark} Coin)"
            else:
                durum_metni = f"Paranı aynen geri aldın! 🔄"

            embed = discord.Embed(
                title="🎁 Gizemli Kasa Açıldı!",
                description=(
                    f"**{ctx.author.mention}** kasayı dikkatlice açtı ve içinden çıkan ödülü aldı!\n\n"
                    f"💰 **Çıkan Ödül:** `+{kazanc} Coin`\n"
                    f"📊 **Durum:** {durum_metni}\n"
                    f"🪙 **Güncel Bakiye:** **{COINLER[user_id]} Coin**"
                ),
                color=discord.Color.purple(),
            )
            await kasa_mesaj.edit(content=None, embed=embed)

        except Exception as e:
            await ctx.send(f"❌ Kasa açılırken bir hata oluştu: {e}")


@bot.command(name="renk", description="Kişiye özel renk rolünün rengini değiştirir.")
async def renk_degistir(ctx, hex_kodu: str):
    hedef_rol = None
    for rol in ctx.author.roles:
        if rol.name.startswith("Renk | "):
            hedef_rol = rol
            break

    if not hedef_rol:
        await ctx.send("❌ Üzerinde kişiye özel bir renk rolü bulunamadı! Marketten satın almak için: `!market`")
        return

    hex_kodu = hex_kodu.strip()
    if not hex_kodu.startswith("#"):
        hex_kodu = "#" + hex_kodu

    try:
        temiz_kod = hex_kodu.replace("#", "")
        renk_degeri = int(temiz_kod, 16)
        yeni_renk = discord.Color(renk_degeri)

        await hedef_rol.edit(color=yeni_renk, reason=f"{ctx.author} kendi rengini güncelledi.")
        
        await ctx.send(f"🎨 Harika! Kişiye özel renk rolünün rengi başarıyla **{hex_kodu}** olarak güncellendi!")
    except ValueError:
        await ctx.send("❌ Geçersiz renk kodu! Lütfen geçerli bir Hex kodu gir (Örn: `!renk #ff0000`)")
    except Exception as e:
        await ctx.send(f"❌ Renk değiştirilirken bir hata oluştu: {e}")


# --- KUMAR SİSTEMLERİ (RULET & BLACKJACK & AVIATOR) ---

@bot.command(
    name="rulet",
    description="Rulet oynarsın. Kullanım: !rulet <kırmızı/siyah/yeşil> <miktar>",
)
async def rulet(ctx, renk: str, miktar: int):
    if "rulet" not in ctx.channel.name.lower():
        await ctx.send("❌ Bu komutu sadece **🎰rulet** kanalında kullanabilirsin!")
        return

    renk = renk.lower()
    if renk not in ["kırmızı", "siyah", "yeşil"]:
        await ctx.send(
            "❌ Geçersiz renk! Seçebileceğin renkler: `kırmızı`, `siyah`, `yeşil`"
        )
        return

    if miktar <= 0:
        await ctx.send("❌ 0'dan büyük bir miktar girmelisin!")
        return

    user_id = ctx.author.id
    bakiye = bakiye_al(user_id)

    if bakiye < miktar:
        await ctx.send(
            f"❌ Yeterli coinin yok! Güncel bakiyen: **{bakiye} Coin** 🪙"
        )
        return

    vc = ctx.guild.voice_client
    if ctx.author.voice and ctx.author.voice.channel:
        ses_kanali = ctx.author.voice.channel
        if vc is None:
            vc = await ses_kanali.connect()
        elif not vc.is_playing():
            await vc.move_to(ses_kanali)

    ses_dosyasi_yolu = "rulet_sesi.m4a"

    if vc and os.path.exists(ses_dosyasi_yolu):
        try:
            ffmpeg_options = {"options": "-vn"}
            source = discord.FFmpegPCMAudio(ses_dosyasi_yolu, **ffmpeg_options)

            def ses_bitti(error):
                coro = vc.disconnect()
                fut = asyncio.run_coroutine_threadsafe(coro, bot.loop)
                try:
                    fut.result()
                except Exception as e:
                    print(f"Kanaldan çıkış hatası: {e}")

            if not vc.is_playing():
                vc.play(source, after=ses_bitti)
        except Exception as e:
            print(f"🚨 SES ÇALMA HATASI: {e}")

    animasyon_embed = discord.Embed(
        title="🎰 Rulet Çarkı Dönüyor...",
        description="Top dönüyor, heyecan dorukta... 🔄",
        color=discord.Color.blurple(),
    )
    mesaj = await ctx.send(embed=animasyon_embed)

    animasyon_renkleri = [
        "🔴 Kırmızı...",
        "⚫ Siyah...",
        "🟢 Yeşil...",
        "🔴 Kırmızı...",
        "⚫ Siyah...",
    ]
    for adim in animasyon_renkleri:
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
            embed.description = (
                f"Çarktan **🟢 Yeşil** çıktı!\nŞanslı vuruş yaptın ve"
                f" **{kazanc} Coin** kazandın! 🚀\nGüncel bakiye:"
                f" **{COINLER[user_id]} Coin**"
            )
        else:
            kazanc = miktar * 2
            COINLER[user_id] += kazanc - miktar
            embed.color = discord.Color.gold()
            embed.title = "✨ KAZANDIN!"
            embed.description = (
                f"Çarktan **{('🔴 Kırmızı' if gelen_renk == 'kırmızı' else '⚫ Siyah')}**"
                f" çıktı!\nBahsini kazandın ve **{kazanc} Coin** aldın! 💰\nGüncel"
                f" bakiye: **{COINLER[user_id]} Coin**"
            )
    else:
        COINLER[user_id] -= miktar
        embed.color = discord.Color.red()
        embed.title = "💸 KAYBETTİN!"
        embed.description = (
            f"Çarktan **{('🔴 Kırmızı' if gelen_renk == 'kırmızı' else ('⚫ Siyah' if gelen_renk == 'siyah' else '🟢 Yeşil'))}**"
            f" çıktı.\nBahsini kaybettin ve **{miktar} Coin** çöp oldu... 🤡\nGüncel"
            f" bakiye: **{COINLER[user_id]} Coin**"
        )

    verileri_kaydet()
    await mesaj.edit(embed=embed)


# --- BLACKJACK (21) OYUNU ---
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

    @discord.ui.button(
        label="Kart Çek (Hit)",
        style=discord.ButtonStyle.primary,
        custom_id="bj_hit",
    )
    async def hit_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                "❌ Bu oyunu sen başlatmadın!", ephemeral=True
            )
            return

        await interaction.response.defer()

        self.oy_kartlar.append(self.deste.pop())
        oy_toplam = self.kart_toplam(self.oy_kartlar)

        if oy_toplam > 21:
            COINLER[self.ctx.author.id] -= self.miktar
            verileri_kaydet()

            embed = discord.Embed(
                title="💥 PATLADIN! (21'i Geçtin)",
                description=(
                    f"Senin Kartların: {self.oy_kartlar} (Toplam:"
                    f" **{oy_toplam}**)\n**{self.miktar} Coin** kaybettin! 💸"
                ),
                color=discord.Color.red(),
            )
            self.stop()
            await interaction.message.edit(embed=embed, view=None)
        else:
            embed = discord.Embed(
                title="🃏 Blackjack (21)",
                description=(
                    f"**Senin Kartların:** {self.oy_kartlar} (Toplam:"
                    f" **{oy_toplam}**)\n**Botun Açık Kartı:**"
                    f" [{self.bot_kartlar[0]}, ?]"
                ),
                color=discord.Color.blue(),
            )
            await interaction.message.edit(embed=embed, view=self)

    @discord.ui.button(
        label="Dur (Stand)", style=discord.ButtonStyle.success, custom_id="bj_stand"
    )
    async def stand_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                "❌ Bu oyunu sen başlatmadın!", ephemeral=True
            )
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
                f"**Senin Kartların:** {self.oy_kartlar} (Toplam:"
                f" **{oy_toplam}**)\n**Botun Kartları:** {self.bot_kartlar}"
                f" (Toplam: **{bot_toplam}**)\n\nTebrikler! **{self.miktar}"
                " Coin** kazandın! 💰"
            )
        elif oy_toplam < bot_toplam:
            COINLER[user_id] -= self.miktar
            embed.color = discord.Color.red()
            embed.title = "💸 KAYBETTİN!"
            embed.description = (
                f"**Senin Kartların:** {self.oy_kartlar} (Toplam:"
                f" **{oy_toplam}**)\n**Botun Kartları:** {self.bot_kartlar}"
                f" (Toplam: **{bot_toplam}**)\n\nBot seni geçti,"
                f" **{self.miktar} Coin** kaybettin! 🤡"
            )
        else:
            embed.color = discord.Color.gold()
            embed.title = "🤝 BERABERE!"
            embed.description = (
                f"**Senin Kartların:** {self.oy_kartlar} (Toplam:"
                f" **{oy_toplam}**)\n**Botun Kartları:** {self.bot_kartlar}"
                f" (Toplam: **{bot_toplam}**)\n\nParan iade edildi."
            )

        verileri_kaydet()
        self.stop()
        await interaction.message.edit(embed=embed, view=None)


@bot.command(
    name="blackjack",
    aliases=["bj", "21"],
    description="Bot ile 21 oynarsın. Kullanım: !bj <miktar>",
)
async def blackjack(ctx, miktar: int):
    if "blackjack" not in ctx.channel.name.lower():
        await ctx.send(
            "❌ Bu komutu sadece **🃏blackjack** kanalında kullanabilirsin!"
        )
        return

    if miktar <= 0:
        await ctx.send("❌ 0'dan büyük bir bahis miktarı girmelisin!")
        return

    user_id = ctx.author.id
    bakiye = bakiye_al(user_id)

    if bakiye < miktar:
        await ctx.send(
            f"❌ Yeterli coinin yok! Güncel bakiyen: **{bakiye} Coin** 🪙"
        )
        return

    deste = [2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 10, 10, 11] * 4
    random.shuffle(deste)

    oy_kartlar = [deste.pop(), deste.pop()]
    bot_kartlar = [deste.pop(), deste.pop()]

    view = BlackjackView(ctx, miktar, oy_kartlar, bot_kartlar, deste)

    embed = discord.Embed(
        title="🃏 Blackjack (21)",
        description=(
            f"**Senin Kartların:** {oy_kartlar} (Toplam:"
            f" **{view.kart_toplam(oy_kartlar)}**)\n**Botun Açık Kartı:**"
            f" [{bot_kartlar[0]}, ?]\n\nKart çekmek mi istersin, durmak mı?"
        ),
        color=discord.Color.blue(),
    )

    await ctx.send(embed=embed, view=view)


# --- AVIATOR OYUNU ---
DEVAM_EDEN_AVIATORLER = set()

@bot.command(name="aviator")
async def aviator(ctx, miktar: int = None):
    izin_verilen_kanal = "✈️aviator" 
    
    if ctx.channel.name != izin_verilen_kanal:
        await ctx.send(f"❌ Bu komut sadece **#{izin_verilen_kanal}** kanalında kullanılabilir!", delete_after=5)
        return

    user_id = int(ctx.author.id)
    MAKS_BAHIS = 10000
    
    if miktar is None or miktar <= 0:
        await ctx.send("❌ Lütfen geçerli bir miktar gir! Örnek: `!aviator 100`")
        return
        
    if miktar > MAKS_BAHIS:
        await ctx.send(f"⚠️ Çok yüksek bahis! Tek seferde en fazla **{MAKS_BAHIS:,} Coin** yatırabilirsin.")
        return

    if user_id not in COINLER or COINLER[user_id] < miktar:
        bakiye = COINLER.get(user_id, 0)
        await ctx.send(f"❌ Yeterli coin'in yok! Mevcut cüzdanın: **{bakiye:,} Coin**")
        return

    if user_id in DEVAM_EDEN_AVIATORLER:
        await ctx.send("❌ Zaten devam eden bir Aviator oyunun var, önce onu bitir!")
        return

    COINLER[user_id] -= miktar
    if 'verileri_kaydet' in globals(): 
        try:
            verileri_kaydet()
        except Exception as e:
            print(f"Kayıt hatası (bahis düşerken): {e}")
    
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
            nonlocal kazandi_mi, carpan
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
            "```text\n"
            " 1.00x | ✈️ . . . . . . . . . . .\n"
            "       | ─────────────────────────\n"
            "```\n"
            f"**Bahis:** {miktar:,} Coin\n📈 **Anlık Çarpan:** `{carpan:.2f}x`"
        ),
        color=discord.Color.gold()
    )
    mesaj = await ctx.send(embed=embed, view=view)

    try:
        adim = 0
        while not view.value and carpan < patlama_noktasi:
            await asyncio.sleep(1.0)
            
            if kazandi_mi:
                break

            carpan += round(random.uniform(0.03, 0.18), 2)
            if carpan >= patlama_noktasi:
                carpan = patlama_noktasi
                break

            adim += 1
            oran = min(int((carpan - 1.0) / 2.8 * 10), 9)
            bosluk = " . " * oran
            kalan_bosluk = " . " * (9 - oran)

            embed.description = (
                f"✈️ **Uçak tırmanmaya devam ediyor!**\n\n"
                f"```text\n"
                f" {carpan:.2f}x |{bosluk}✈️{kalan_bosluk}\n"
                f"       | ─────────────────────────\n"
                f"```\n"
                f"**Bahis:** {miktar:,} Coin\n📈 **Anlık Çarpan:** `{carpan:.2f}x`"
            )
            await mesaj.edit(embed=embed, view=view)

        if kazandi_mi:
            kazanc = int(miktar * carpan)
            COINLER[user_id] = COINLER.get(user_id, 0) + kazanc
            
            if 'verileri_kaydet' in globals(): 
                try:
                    verileri_kaydet()
                except Exception as e:
                    print(f"Kayıt hatası (kazanç eklenirken): {e}")

            embed.title = "🎉 BAŞARILI TAHLİYE!"
            embed.color = discord.Color.green()
            embed.description = (
                f"Uçak uçup gitmeden parayı zamanında çektin!\n\n"
                f"✨ **Çarpan:** `{carpan:.2f}x`\n"
                f"💰 **Kazanılan:** **+{kazanc:,} Coin**\n"
                f"🏦 **Yeni Cüzdan:** `{COINLER[user_id]:,} Coin`"
            )
            await mesaj.edit(embed=embed, view=None)
        else:
            if 'verileri_kaydet' in globals(): 
                try:
                    verileri_kaydet()
                except Exception as e:
                    print(f"Kayıt hatası (kayıp kaydedilirken): {e}")

            embed.title = "💥 UÇAK KAÇTI (BOOM)!"
            embed.color = discord.Color.red()
            embed.description = (
                f"Geç kaldın! Uçak `{patlama_noktasi}x` oranında gözden kayboldu.\n\n"
                f"```text\n"
                f" 💥 BOOM! | ✈️💨 (Gözden kayboldu)\n"
                f"```\n"
                f"💸 **Kaybedilen:** `{miktar:,} Coin`\n"
                f"🏦 **Kalan Cüzdan:** `{COINLER[user_id]:,} Coin`"
            )
            await mesaj.edit(embed=embed, view=None)

    except Exception as e:
        print(f"Aviator genel hata: {e}")
    finally:
        DEVAM_EDEN_AVIATORLER.discard(user_id)


# --- MESLEK SİSTEMİ ---

GECERLI_MESLEKLER = ["polis", "pilot", "doktor"]

async def kanal_kontrol(ctx):
    if "meslekler" not in ctx.channel.name.lower():
        await ctx.send("❌ Bu komutu sadece **🥼meslekler** kanalında kullanabilirsin!")
        return False
    return True

@bot.command(name="meslekler", description="Sunucudaki meslekleri listeler.")
async def meslekler_komut(ctx):
    if not await kanal_kontrol(ctx):
        return

    embed = discord.Embed(
        title="🥼 Sunucu Meslekler Paneli 2.0",
        description="Güncellenen ekonomi ve yeni ödül/ceza oranlarıyla meslekler:\n\n* Meslek seçmek için: `!meslekseç <polis/pilot/doktor>`\n* Komutlar her **5 dakikada bir** kullanılabilir.\n* İstifa etmek için: `!istifa`",
        color=discord.Color.blue(),
    )
    embed.add_field(
        name="👮 Polis",
        value="`!polis` yazarak suçlu kovalarsın.\n• **Yakalarsa:** +550 Coin\n• **Kaçırırsa:** -250 Coin",
        inline=False,
    )
    embed.add_field(
        name="👨‍⚕️ Doktor",
        value="`!doktor` yazarak ameliyata girersin.\n• **Başarılı:** +1.000 Coin\n• **Başarısız:** Cüzdanın %5'i silinir",
        inline=False,
    )
    embed.add_field(
        name="✈️ Pilot",
        value="`!pilot` yazarak uçuş yaparsın.\n• **Başarılı:** +1.000 Coin\n• **Başarısız:** 30 dakika uçuş yasağı (men)",
        inline=False,
    )
    await ctx.send(embed=embed)

@bot.command(name="meslekseç", description="Belirtilen mesleğe giriş yapar ve rolünü verir.")
async def mesleksec(ctx, *, meslek_adi: str):
    if not await kanal_kontrol(ctx):
        return

    meslek_adi = meslek_adi.lower()
    user_id = str(ctx.author.id)

    if meslek_adi not in GECERLI_MESLEKLER:
        await ctx.send("❌ Geçersiz meslek! Sadece şu meslekleri seçebilirsin: `polis`, `pilot`, `doktor`")
        return

    simdiki_zaman = datetime.datetime.now().timestamp()

    if 'MESLEKLER_VERI' not in globals():
        global MESLEKLER_VERI
        MESLEKLER_VERI = {}

    if user_id in MESLEKLER_VERI:
        son_degisim = MESLEKLER_VERI[user_id].get("son_degisim", 0)
        gecen_sure = simdiki_zaman - son_degisim
        
        if gecen_sure < 86400:
            kalan_sure = int(86400 - gecen_sure)
            saat = kalan_sure // 3600
            dakika = (kalan_sure % 3600) // 60
            await ctx.send(f"⏳ Yeni bir meslek seçmek veya meslek değiştirmek için **{saat} saat {dakika} dakika** daha beklemelisin!")
            return

    rol_ismi = meslek_adi.capitalize()
    hedef_rol = discord.utils.get(ctx.guild.roles, name=rol_ismi)

    if not hedef_rol:
        await ctx.send(f"⚠️ Sunucuda **{rol_ismi}** isimli rol bulunamadı! Lütfen sunucuda bu isimde bir rol oluştur.")
        return

    for diger_meslek in GECERLI_MESLEKLER:
        diger_rol_ismi = diger_meslek.capitalize()
        diger_rol = discord.utils.get(ctx.guild.roles, name=diger_rol_ismi)
        if diger_rol and diger_rol in ctx.author.roles:
            try:
                await ctx.author.remove_roles(diger_rol)
            except Exception as e:
                print(f"Eski rol silinirken hata: {e}")

    try:
        await ctx.author.add_roles(hedef_rol)
    except Exception as e:
        await ctx.send(f"❌ Rol verilirken bir hata oluştu: {e}")
        return

    if user_id not in MESLEKLER_VERI:
        MESLEKLER_VERI[user_id] = {}

    MESLEKLER_VERI[user_id]["meslek"] = meslek_adi
    MESLEKLER_VERI[user_id]["son_degisim"] = simdiki_zaman
    MESLEKLER_VERI[user_id]["cezali"] = False

    if 'verileri_kaydet' in globals():
        verileri_kaydet()

    await ctx.send(f"🎉 Tebrikler! Eski meslek rollerin temizlendi ve başarıyla **{rol_ismi}** oldun!")

@bot.command(name="istifa", description="Mevcut mesleğinden istifa eder ve rolünü siler.")
async def istifa_komut(ctx):
    if not await kanal_kontrol(ctx):
        return

    user_id = str(ctx.author.id)

    if 'MESLEKLER_VERI' not in globals() or user_id not in MESLEKLER_VERI or not MESLEKLER_VERI[user_id].get("meslek"):
        await ctx.send("❌ Zaten halihazırda bir mesleğin yok!")
        return

    for meslek in GECERLI_MESLEKLER:
        rol_ismi = meslek.capitalize()
        rol = discord.utils.get(ctx.guild.roles, name=rol_ismi)
        if rol and rol in ctx.author.roles:
            try:
                await ctx.author.remove_roles(rol)
            except Exception as e:
                print(f"İstifa sırasında rol silinemedi: {e}")

    MESLEKLER_VERI[user_id]["meslek"] = None
    MESLEKLER_VERI[user_id]["cezali"] = False

    if 'verileri_kaydet' in globals():
        verileri_kaydet()

    await ctx.send(f"💼 **{ctx.author.mention}**, başarıyla mesleğinden istifa etti. Yeni bir meslek seçebilmek için 24 saatlik sürenin dolmasını beklemelisin!")

@bot.command(name="polis", description="Suçluyu kovalamaya başlarsın.")
async def polis_komut(ctx):
    if not await kanal_kontrol(ctx):
        return

    user_id = str(ctx.author.id)
    if 'MESLEKLER_VERI' not in globals() or user_id not in MESLEKLER_VERI or MESLEKLER_VERI[user_id].get("meslek") != "polis":
        await ctx.send("❌ Sen bir polis değilsin! Polis olmak için `!meslekseç polis` komutunu kullanmalısın.")
        return

    simdiki_zaman = datetime.datetime.now().timestamp()
    son_polis_islem = MESLEKLER_VERI[user_id].get("son_polis_islem", 0)
    cooldown_suresi = 300  # 5 Dakika

    if simdiki_zaman - son_polis_islem < cooldown_suresi:
        kalan = int(cooldown_suresi - (simdiki_zaman - son_polis_islem))
        dakika = kalan // 60
        saniye = kalan % 60
        await ctx.send(f"⏳ Çok yoruldun! Yeni bir operasyona çıkmak için **{dakika} dakika {saniye} saniye** beklemelisin.")
        return

    MESLEKLER_VERI[user_id]["son_polis_islem"] = simdiki_zaman
    if 'verileri_kaydet' in globals(): verileri_kaydet()

    bakiye_al(int(user_id))
    basarili = random.choice([True, False])

    if basarili:
        COINLER[int(user_id)] += 550
        if 'verileri_kaydet' in globals(): verileri_kaydet()
        embed = discord.Embed(
            title="🚨 Suçlu Yakalandı!",
            description=f"**{ctx.author.mention}**, sokaklarda suçlunun peşine düştü ve kıskıvrak yakaladı!\n🎉 Cüzdanına **+550 Coin** eklendi! 🪙\nGüncel Bakiye: **{COINLER[int(user_id)]:,} Coin**",
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)
    else:
        COINLER[int(user_id)] = max(0, COINLER[int(user_id)] - 250)
        if 'verileri_kaydet' in globals(): verileri_kaydet()
        embed = discord.Embed(
            title="🏃 Suçlu Kaçtı!",
            description=f"**{ctx.author.mention}**, şüpheliyi köşeye sıkıştırdı ancak elinden kaçırmayı başardı!\n💸 Ceza olarak **-250 Coin** kaybettin...\nGüncel Bakiye: **{COINLER[int(user_id)]:,} Coin**",
            color=discord.Color.red(),
        )
        await ctx.send(embed=embed)

@bot.command(name="doktor", description="Ameliyata girersin.")
async def doktor_komut(ctx):
    if not await kanal_kontrol(ctx):
        return

    user_id = str(ctx.author.id)
    if 'MESLEKLER_VERI' not in globals() or user_id not in MESLEKLER_VERI or MESLEKLER_VERI[user_id].get("meslek") != "doktor":
        await ctx.send("❌ Sen bir doktor değilsin! Doktor olmak için `!meslekseç doktor` komutunu kullanmalısın.")
        return

    simdiki_zaman = datetime.datetime.now().timestamp()
    son_doktor_islem = MESLEKLER_VERI[user_id].get("son_doktor_islem", 0)
    cooldown_suresi = 300  # 5 Dakika

    if simdiki_zaman - son_doktor_islem < cooldown_suresi:
        kalan = int(cooldown_suresi - (simdiki_zaman - son_doktor_islem))
        dakika = kalan // 60
        saniye = kalan % 60
        await ctx.send(f"⏳ Ameliyattan yeni çıktın! Yeniden ameliyata girmek için **{dakika} dakika {saniye} saniye** dinlenmelisin.")
        return

    MESLEKLER_VERI[user_id]["son_doktor_islem"] = simdiki_zaman
    if 'verileri_kaydet' in globals(): verileri_kaydet()

    bakiye_al(int(user_id))
    basarili = random.choice([True, False])

    if basarili:
        COINLER[int(user_id)] += 1000
        if 'verileri_kaydet' in globals(): verileri_kaydet()
        embed = discord.Embed(
            title="🏥 Başarılı Ameliyat!",
            description=f"**{ctx.author.mention}**, zorlu bir ameliyatı başarıyla tamamladı ve hastasının hayatını kurtardı!\n🎉 Cüzdanına **+1,000 Coin** eklendi! 🪙\nGüncel Bakiye: **{COINLER[int(user_id)]:,} Coin**",
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)
    else:
        mevcut_bakiye = COINLER[int(user_id)]
        kesinti = int(mevcut_bakiye * 0.05)  # %5 Kesinti
        COINLER[int(user_id)] = max(0, mevcut_bakiye - kesinti)
        if 'verileri_kaydet' in globals(): verileri_kaydet()
        embed = discord.Embed(
            title="💔 Başarısız Ameliyat!",
            description=f"**{ctx.author.mention}**, ne yazık ki hastayı kurtaramadı ve tazminat ödemek zorunda kaldı!\n💸 Mevcut cüzdanının %5'i olan **-{kesinti:,} Coin** kesildi...\nGüncel Bakiye: **{COINLER[int(user_id)]:,} Coin**",
            color=discord.Color.red(),
        )
        await ctx.send(embed=embed)

@bot.command(name="pilot", description="Uçuş yaparsın.")
async def pilot_komut(ctx):
    if not await kanal_kontrol(ctx):
        return

    user_id = str(ctx.author.id)
    if 'MESLEKLER_VERI' not in globals() or user_id not in MESLEKLER_VERI or MESLEKLER_VERI[user_id].get("meslek") != "pilot":
        await ctx.send("❌ Sen bir pilot değilsin! Pilot olmak için `!meslekseç pilot` komutunu kullanmalısın.")
        return

    simdiki_zaman = datetime.datetime.now().timestamp()
    son_islem = MESLEKLER_VERI[user_id].get("son_islem", 0)
    
    yasak_suresi = 1800 if MESLEKLER_VERI[user_id].get("cezali", False) else 0
    if yasak_suresi > 0 and simdiki_zaman - son_islem < yasak_suresi:
        kalan = int(yasak_suresi - (simdiki_zaman - son_islem))
        dakika = kalan // 60
        saniye = kalan % 60
        await ctx.send(f"⏳ Kaza/men cezan devam ediyor! Tekrar uçmak için **{dakika} dakika {saniye} saniye** beklemelisin.")
        return

    son_pilot_islem = MESLEKLER_VERI[user_id].get("son_pilot_islem", 0)
    cooldown_suresi = 300  # 5 Dakika
    if simdiki_zaman - son_pilot_islem < cooldown_suresi:
        kalan = int(cooldown_suresi - (simdiki_zaman - son_pilot_islem))
        dakika = kalan // 60
        saniye = kalan % 60
        await ctx.send(f"⏳ Uçak bakımda! Yeni bir sefere çıkmak için **{dakika} dakika {saniye} saniye** beklemelisin.")
        return

    MESLEKLER_VERI[user_id]["son_pilot_islem"] = simdiki_zaman
    MESLEKLER_VERI[user_id]["cezali"] = False
    MESLEKLER_VERI[user_id]["son_islem"] = simdiki_zaman
    bakiye_al(int(user_id))

    basarili = random.choice([True, False])

    if basarili:
        COINLER[int(user_id)] += 1000
        if 'verileri_kaydet' in globals(): verileri_kaydet()
        embed = discord.Embed(
            title="✈️ Güvenli Uçuş Tamamlandı!",
            description=f"**{ctx.author.mention}**, uçağı güvenli bir şekilde hedef noktaya indirdi!\n🎉 Cüzdanına **+1,000 Coin** eklendi! 🪙\nGüncel Bakiye: **{COINLER[int(user_id)]:,} Coin**",
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)
    else:
        MESLEKLER_VERI[user_id]["cezali"] = True
        MESLEKLER_VERI[user_id]["son_islem"] = simdiki_zaman
        if 'verileri_kaydet' in globals(): verileri_kaydet()
        embed = discord.Embed(
            title="⚠️ Hava Muhalefeti / Uçuş İptali!",
            description=f"**{ctx.author.mention}**, uçuş sırasında tehlikeli hava koşullarıyla karşılaştı ve sefer iptal edildi!\n🚫 Kaza/kural ihlali nedeniyle **30 dakika uçuş yasağı (men)** aldın!",
            color=discord.Color.red(),
        )
        await ctx.send(embed=embed)


# --- MODERASYON KOMUTLARI ---
def sure_hesapla(sayi: int, birim: str):
    birim = birim.lower()
    if birim in ["saniye", "s"]:
        return sayi
    elif birim in ["dakika", "d"]:
        return sayi * 60
    elif birim in ["saat", "h"]:
        return sayi * 3600
    elif birim in ["gün", "d"]:
        return sayi * 86400
    return None


@bot.command(
    name="mute", description="Bir kullanıcıyı belirttiğin süre kadar susturur."
)
@commands.has_permissions(moderate_members=True)
async def mute(ctx, kullanici: discord.Member, sayi: int, birim: str):
    toplam_saniye = sure_hesapla(sayi, birim)
    if not toplam_saniye:
        await ctx.send("❌ Geçersiz süre birimi! (`s`, `d`, `h`, `gün`)")
        return
    sure = datetime.timedelta(seconds=toplam_saniye)
    try:
        await kullanici.timeout(
            sure, reason=f"{ctx.author} tarafından mutelendi."
        )
        await ctx.send(
            f"🔒 **{kullanici.mention}** başarıyla **{sayi} {birim}** süreyle"
            " susturuldu!"
        )

        mod_kanal = discord.utils.get(
            ctx.guild.text_channels, name="bot-moderasyon"
        )
        if mod_kanal:
            embed = discord.Embed(
                title="🔒 Mute Atıldı",
                color=discord.Color.red(),
                timestamp=datetime.datetime.now(),
            )
            embed.add_field(
                name="Ceza Alan Üye",
                value=f"{kullanici.mention} (`{kullanici.id}`)",
                inline=False,
            )
            embed.add_field(
                name="Cezayı Veren Yetkili",
                value=f"{ctx.author.mention} (`{ctx.author.id}`)",
                inline=False,
            )
            embed.add_field(
                name="Süre", value=f"{sayi} {birim}", inline=False
            )
            await mod_kanal.send(embed=embed)
    except Exception as e:
        await ctx.send(f"Bir hata oluştu: {e}")


@bot.command(
    name="unmute", description="Bir kullanıcının susturmasını kaldırır."
)
@commands.has_permissions(moderate_members=True)
async def unmute(ctx, kullanici: discord.Member):
    try:
        await kullanici.timeout(
            None,
            reason=f"{ctx.author} tarafından susturması kaldırıldı.",
        )
        await ctx.send(
            f"🔊 **{kullanici.mention}** adlı kullanıcının susturması kaldırıldı!"
        )

        mod_kanal = discord.utils.get(
            ctx.guild.text_channels, name="bot-moderasyon"
        )
        if mod_kanal:
            embed = discord.Embed(
                title="🔊 Mute Kaldırıldı (Unmute)",
                color=discord.Color.green(),
                timestamp=datetime.datetime.now(),
            )
            embed.add_field(
                name="Affedilen Üye",
                value=f"{kullanici.mention} (`{kullanici.id}`)",
                inline=False,
            )
            embed.add_field(
                name="İşlemi Yapan Yetkili",
                value=f"{ctx.author.mention} (`{ctx.author.id}`)",
                inline=False,
            )
            await mod_kanal.send(embed=embed)
    except Exception as e:
        await ctx.send(f"Bir hata oluştu: {e}")


@bot.command(
    name="ban", description="Bir kullanıcıyı sunucudan kalıcı olarak yasaklar."
)
@commands.has_permissions(ban_members=True)
async def ban(ctx, kullanici: discord.Member, *, sebep: str = "Belirtilmedi"):
    try:
        await kullanici.ban(reason=sebep)
        await ctx.send(f"🔨 **{kullanici.name}** sunucudan yasaklandı! Sebep: {sebep}")

        mod_kanal = discord.utils.get(
            ctx.guild.text_channels, name="bot-moderasyon"
        )
        if mod_kanal:
            embed = discord.Embed(
                title="🔨 Sunucudan Banlandı",
                color=discord.Color.dark_red(),
                timestamp=datetime.datetime.now(),
            )
            embed.add_field(
                name="Yasaklanan Üye",
                value=f"{kullanici.mention} (`{kullanici.id}`)",
                inline=False,
            )
            embed.add_field(
                name="Yasaklayan Yetkili",
                value=f"{ctx.author.mention} (`{ctx.author.id}`)",
                inline=False,
            )
            embed.add_field(name="Sebep", value=sebep, inline=False)
            await mod_kanal.send(embed=embed)
    except Exception as e:
        await ctx.send(f"Bir hata oluştu: {e}")


@bot.command(name="kick", description="Bir kullanıcıyı sunucudan atar.")
@commands.has_permissions(kick_members=True)
async def kick(ctx, kullanici: discord.Member, *, sebep: str = "Belirtilmedi"):
    try:
        await kullanici.kick(reason=sebep)
        await ctx.send(f"👢 **{kullanici.name}** sunucudan atıldı! Sebep: {sebep}")

        mod_kanal = discord.utils.get(
            ctx.guild.text_channels, name="bot-moderasyon"
        )
        if mod_kanal:
            embed = discord.Embed(
                title="👢 Sunucudan Atıldı (Kick)",
                color=discord.Color.orange(),
                timestamp=datetime.datetime.now(),
            )
            embed.add_field(
                name="Atılan Üye",
                value=f"{kullanici.mention} (`{kullanici.id}`)",
                inline=False,
            )
            embed.add_field(
                name="İşlemi Yapan Yetkili",
                value=f"{ctx.author.mention} (`{ctx.author.id}`)",
                inline=False,
            )
            embed.add_field(name="Sebep", value=sebep, inline=False)
            await mod_kanal.send(embed=embed)
    except Exception as e:
        await ctx.send(f"Bir hata oluştu: {e}")


@bot.command(
    name="unban", description="ID'si verilen kullanıcının yasağını kaldırır."
)
@commands.has_permissions(ban_members=True)
async def unban(ctx, user_id: str):
    try:
        if not user_id.isdigit():
            await ctx.send(
                "❌ Lütfen geçerli bir **Kullanıcı ID'si** girin (Örn:"
                " `!unban 123456789123456789`)."
            )
            return

        user = await bot.fetch_user(int(user_id))
        await ctx.guild.unban(user)
        await ctx.send(f"🔓 **{user.name}** adlı kullanıcının yasağı kaldırıldı!")

        mod_kanal = discord.utils.get(
            ctx.guild.text_channels, name="bot-moderasyon"
        )
        if mod_kanal:
            embed = discord.Embed(
                title="🔓 Ban Kaldırıldı (Unban)",
                color=discord.Color.green(),
                timestamp=datetime.datetime.now(),
            )
            embed.add_field(
                name="Affedilen Üyenin ID", value=f"`{user_id}`", inline=False
            )
            embed.add_field(
                name="İşlemi Yapan Yetkili",
                value=f"{ctx.author.mention} (`{ctx.author.id}`)",
                inline=False,
            )
            await mod_kanal.send(embed=embed)
    except Exception as e:
        await ctx.send(f"Bir hata oluştu veya kullanıcı bulunamadı: {e}")


@bot.command(
    name="odayaçek",
    aliases=["çek"],
    description="Ses kanalındaki bir kullanıcıyı bulunduğun odaya çeker.",
)
async def odayacek(ctx, kullanici: discord.Member):
    if not ctx.author.guild_permissions.move_members:
        await ctx.send(
            "❌ Bu komutu kullanabilmek için **Üyeleri Taşı** yetkisine sahip"
            " olmalısın!"
        )
        return

    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("❌ Önce bir ses kanalına girmelisin!")
        return

    if not kullanici.voice or not kullanici.voice.channel:
        await ctx.send(f"❌ **{kullanici.name}** herhangi bir ses kanalında değil!")
        return

    hedef_kanal = ctx.author.voice.channel
    try:
        await kullanici.move_to(
            hedef_kanal, reason=f"{ctx.author} tarafından odaya çekildi."
        )
        await ctx.send(
            f"🎯 **{kullanici.mention}** başarıyla **{hedef_kanal.name}** adlı odana"
            " çekildi!"
        )
    except Exception as e:
        await ctx.send(
            f"Bir hata oluştu (Botun yetkisi veya hedef kanal dolu olabilir):"
            f" {e}"
        )


@bot.command(
    name="sil", description="Kanalda belirtilen miktarda mesajı siler."
)
@commands.has_permissions(manage_messages=True)
async def sil(ctx, sayi: int):
    if sayi <= 0:
        await ctx.send("❌ Lütfen 0'dan büyük bir sayı gir!")
        return
    silinen = await ctx.channel.purge(limit=sayi + 1)
    mesaj = await ctx.send(f"🧹 Başarıyla **{len(silinen) - 1}** adet mesaj silindi!")
    await asyncio.sleep(3)
    await mesaj.delete()


@bot.command(
    name="kapat",
    description="Bulunulan kanalı herkesin mesaj yazmasına kapatır.",
)
@commands.has_permissions(manage_channels=True)
async def kapat(ctx):
    kanal = ctx.channel
    rol = ctx.guild.default_role
    await kanal.set_permissions(rol, send_messages=False)
    await ctx.send(f"🔒 **{kanal.name}** kanalı herkesin mesaj yazmasına kapatıldı!")


@bot.command(
    name="aç", description="Kapatılmış olan kanalı tekrar mesaj yazmaya açar."
)
@commands.has_permissions(manage_channels=True)
async def ac(ctx):
    kanal = ctx.channel
    rol = ctx.guild.default_role
    await kanal.set_permissions(rol, send_messages=True)
    await ctx.send(
        f"🔓 **{kanal.name}** kanalı yeniden herkesin mesaj yazmasına açıldı!"
    )


@bot.command(
    name="slowmode", description="Kanalın yavaş mod süresini ayarlar."
)
@commands.has_permissions(manage_channels=True)
async def slowmode(ctx, saniye: int = 0):
    try:
        await ctx.channel.edit(slowmode_delay=saniye)
        if saniye == 0:
            await ctx.send("⏱️ Bu kanalın yavaş mod süresi kaldırıldı.")
        else:
            await ctx.send(
                f"⏱️ Bu kanalın yavaş mod süresi **{saniye}** saniye yapıldı!"
            )
    except Exception as e:
        await ctx.send(f"Bir hata oluştu: {e}")


        # Döngüye girecek durumların listesi
richie_rich_durumlari = itertools.cycle([
    "Rulet Oynuyor 🎰",
    "Blackjack Oynuyor 🃏",
    "Aviator Oynuyor ✈️"
])

@tasks.loop(hours=3) # Her 3 saatte bir durumu değiştirir
async def durumu_guncelle():
    yeni_durum = next(richie_rich_durumlari)
    await bot.change_presence(activity=discord.Game(name=yeni_durum))

@bot.event
async def on_ready():
    print(f"{bot.user} olarak giriş yapıldı!")
    durumu_guncelle.start() # Bot açıldığı an döngüyü başlatır
from flask import Flask
from threading import Thread

app = Flask('')


@app.route('/')
def home():
  schl = "Bot aktif ve çalışıyor!"
  return schl


def run():
  app.run(host='0.0.0.0', port=8080)


def web_sunucusunu_baslat():
  t = Thread(target=run)
  t.start()


# Botu başlatmadan önce web sunucusunu tetikle
if __name__ == '__main__':
  web_sunucusunu_baslat()

# --- BOTU BAŞLATMA ---
bot.run(TOKEN)
