import os
import asyncio
import logging
import uuid
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from telegraph import upload_file
import uvicorn
from jinja2 import Template

# ==========================================
# ১. কনফিগারেশন (আপনার নতুন টোকেন সহ)
# ==========================================
TOKEN = "8655043839:AAHC6IzkAhvHzSE9FqQbkcs_hkxJkcpN9l0" # আপনার দেওয়া নতুন টোকেন
MONGO_URL = "mongodb+srv://drama:drama@cluster0.sa4kvgu.mongodb.net/?appName=Cluster0"
OWNER_ID = 7120801813
PUBLIC_CHANNEL = "@DramaStoreKing"
APP_URL = "https://indirect-meris-yeasinvai-95120fc6.koyeb.app" 
BOT_USERNAME = "dramastorkingsbot"
PORT = int(os.environ.get("PORT", 8080))

client = AsyncIOMotorClient(MONGO_URL)
db = client['movie_dramabd']
content_col = db['contents']
settings_col = db['settings']
file_store = db['files']
notif_col = db['notif_channels']

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
app = FastAPI()

# ==========================================
# ২. এফএসএম (স্টেট ম্যানেজমেন্ট)
# ==========================================
class MovieState(StatesGroup):
    name = State()
    photo = State()
    quality = State()
    file = State()

class SeriesState(StatesGroup):
    name = State()
    photo = State()
    files = State()

class ReqState(StatesGroup):
    movie_name = State()

# ==========================================
# ৩. হেল্পার ফাংশন সমূহ
# ==========================================
async def process_photo(message: types.Message):
    photo = message.photo[-1]
    file_info = await bot.get_file(photo.file_id)
    photo_name = f"{photo.file_id}.jpg"
    await bot.download_file(file_info.file_path, photo_name)
    try:
        response = upload_file(photo_name)
        if os.path.exists(photo_name): os.remove(photo_name)
        return f"https://telegra.ph{response[0]}"
    except: return "https://telegra.ph/file/0f2e825a07530467776d5.jpg"

async def auto_delete_task(chat_id, message_id, minutes):
    if minutes > 0:
        await asyncio.sleep(minutes * 60)
        try: await bot.delete_message(chat_id, message_id)
        except: pass

async def get_config():
    conf = await settings_col.find_one({"id": "config"})
    if not conf:
        conf = {"id": "config", "site_name": "Moviee BD", "note": "Welcome!", "logo": "https://telegra.ph/file/0f2e825a07530467776d5.jpg", "autodlt": 0, "autolock": 10, "per": 10, "mtg": "10351894", "stp": 1}
        await settings_col.insert_one(conf)
    return conf

# ==========================================
# ৪. ১৭টি কমান্ড হ্যান্ডলারস
# ==========================================

@dp.message(Command("start"))
async def cmd_start(message: types.Message, command: CommandObject):
    if command.args:
        f_data = await file_store.find_one({"unique_id": command.args})
        if f_data:
            await bot.copy_message(chat_id=message.chat.id, from_chat_id=OWNER_ID, message_id=f_data['msg_id'], caption=f"🎬 মুভি: {f_data['name']}\n📢 চ্যানেল: {PUBLIC_CHANNEL}")
            return
    conf = await get_config()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Watch Now (Website)", url=APP_URL)],
        [InlineKeyboardButton(text="📥 Movie Request", callback_data="req"), InlineKeyboardButton(text="🚀 Share Bot", switch_inline_query="")],
        [InlineKeyboardButton(text="📢 Main Channel", url=f"https://t.me/{PUBLIC_CHANNEL.replace('@','')}")],
        [InlineKeyboardButton(text="🔗 All Channels", url="https://t.me/all_channels")]
    ])
    
    caption = f"Hello YA UPLODER!\n\nWelcome to Moviee BD click the button below to explore! ❤️🍿"
    try:
        await message.answer_photo(photo=conf['logo'], caption=caption, reply_markup=kb)
    except Exception:
        # যদি লোগো লিঙ্ক কাজ না করে তবে টেক্সট মেসেজ পাঠাবে
        await message.answer(caption, reply_markup=kb)

# ২. /movie - মুভি আপলোড
@dp.message(Command("movie"))
async def cmd_movie(m: types.Message, state: FSMContext):
    if m.from_user.id != OWNER_ID: return
    await m.answer("🎬 মুভির নাম দিন:"); await state.set_state(MovieState.name)

@dp.message(MovieState.name)
async def m_st_name(m: types.Message, state: FSMContext):
    await state.update_data(name=m.text, links=[], views=0)
    await m.answer("🖼 পোস্টার ফটো পাঠান:"); await state.set_state(MovieState.photo)

@dp.message(MovieState.photo, F.photo)
async def m_st_photo(m: types.Message, state: FSMContext):
    url = await process_photo(m); await state.update_data(poster=url)
    await m.answer("⚙️ কোয়ালিটি দিন (যেমন: 720p) অথবা Done দিন:", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Done")]], resize_keyboard=True)); await state.set_state(MovieState.quality)

@dp.message(MovieState.quality)
async def m_st_quality(m: types.Message, state: FSMContext):
    if m.text == "Done":
        data = await state.get_data(); await content_col.insert_one({"type": "movie", **data, "date": datetime.now()})
        conf = await get_config()
        post = await bot.send_photo(chat_id=PUBLIC_CHANNEL, photo=data['poster'], caption=f"🎬 মুভি: {data['name']}\n📢 চ্যানেল: {PUBLIC_CHANNEL}")
        if int(conf['autodlt']) > 0: asyncio.create_task(auto_delete_task(PUBLIC_CHANNEL, post.message_id, int(conf['autodlt'])))
        await m.answer("✅ মুভি স্টোর সফল!", reply_markup=types.ReplyKeyboardRemove()); await state.clear()
    else:
        await state.update_data(cq=m.text); await m.answer(f"📁 {m.text} ভিডিও ফাইল পাঠান:"); await state.set_state(MovieState.file)

@dp.message(MovieState.file, F.video | F.document)
async def m_st_file(m: types.Message, state: FSMContext):
    data = await state.get_data(); uid = str(uuid.uuid4())[:8]
    await file_store.insert_one({"unique_id": uid, "msg_id": m.message_id, "name": data['name']})
    data['links'].append({"q": data['cq'], "uid": uid}); await state.update_data(links=data['links'])
    await m.answer(f"✅ {data['cq']} সেভ। পরের কোয়ালিটি বা Done দিন।"); await state.set_state(MovieState.quality)

# ৩. /series - ড্রামা আপলোড
@dp.message(Command("series"))
async def cmd_series(m: types.Message, state: FSMContext):
    if m.from_user.id != OWNER_ID: return
    await m.answer("📺 ড্রামার নাম দিন:"); await state.set_state(SeriesState.name)

@dp.message(SeriesState.name)
async def s_st_name(m: types.Message, state: FSMContext):
    await state.update_data(name=m.text, episodes=[], views=0)
    await m.answer("🖼 পোস্টার পাঠান:"); await state.set_state(SeriesState.photo)

@dp.message(SeriesState.photo, F.photo)
async def s_st_photo(m: types.Message, state: FSMContext):
    url = await process_photo(m); await state.update_data(poster=url)
    await m.answer("📁 ১ম এপিসোড ভিডিও ফাইল পাঠান (শেষ হলে Done দিন):", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Done")]], resize_keyboard=True)); await state.set_state(SeriesState.files)

@dp.message(SeriesState.files, F.video | F.document)
async def s_st_file(m: types.Message, state: FSMContext):
    data = await state.get_data(); uid = str(uuid.uuid4())[:8]; ep = f"Episode {len(data['episodes'])+1:02d}"
    await file_store.insert_one({"unique_id": uid, "msg_id": m.message_id, "name": f"{data['name']} {ep}"})
    data['episodes'].append({"ep": ep, "uid": uid}); await state.update_data(episodes=data['episodes'])
    await m.answer(f"✅ {ep} সেভ। পরেরটা পাঠান বা Done লিখুন।")

@dp.message(SeriesState.files, F.text == "Done")
async def s_st_done(m: types.Message, state: FSMContext):
    data = await state.get_data(); await content_col.insert_one({"type": "series", **data, "date": datetime.now()})
    conf = await get_config(); post = await bot.send_photo(chat_id=PUBLIC_CHANNEL, photo=data['poster'], caption=f"📺 ড্রামা: {data['name']}\n📢 {PUBLIC_CHANNEL}")
    if int(conf['autodlt']) > 0: asyncio.create_task(auto_delete_task(PUBLIC_CHANNEL, post.message_id, int(conf['autodlt'])))
    await m.answer("✅ ড্রামা স্টোর সফল!", reply_markup=types.ReplyKeyboardRemove()); await state.clear()

# ৪. /logo - লোগো পরিবর্তন
@dp.message(Command("logo"))
async def cmd_logo(m: types.Message):
    if m.from_user.id == OWNER_ID:
        try: await settings_col.update_one({"id": "config"}, {"$set": {"logo": m.text.split()[1]}}, upsert=True); await m.answer("✅ লোগো আপডেট।")
        except: await m.answer("/logo [লিঙ্ক]")

# ৫. /autodlt - অটো ডিলিট টাইম
@dp.message(Command("autodlt"))
async def cmd_autodlt(m: types.Message):
    if m.from_user.id == OWNER_ID:
        try: await settings_col.update_one({"id": "config"}, {"$set": {"autodlt": int(m.text.split()[1])}}, upsert=True); await m.answer("✅ অটো ডিলিট সেট।")
        except: pass

# ৬. /autolock - অটো লক টাইম
@dp.message(Command("autolock"))
async def cmd_autolock(m: types.Message):
    if m.from_user.id == OWNER_ID:
        try: await settings_col.update_one({"id": "config"}, {"$set": {"autolock": int(m.text.split()[1])}}, upsert=True); await m.answer("✅ অটো লক সেট।")
        except: pass

# ৭. /setname - সাইট নাম
@dp.message(Command("setname"))
async def cmd_setname(m: types.Message):
    if m.from_user.id == OWNER_ID:
        await settings_col.update_one({"id": "config"}, {"$set": {"site_name": m.text.replace("/setname ","")}}, upsert=True); await m.answer("✅ নাম আপডেট।")

# ৮. /setnotice - নোটিশ
@dp.message(Command("setnotice"))
async def cmd_setnotice(m: types.Message):
    if m.from_user.id == OWNER_ID:
        await settings_col.update_one({"id": "config"}, {"$set": {"note": m.text.replace("/setnotice ","")}}, upsert=True); await m.answer("✅ নোটিশ আপডেট।")

# ৯. /setmtg - মনিট্যাগ আইডি
@dp.message(Command("setmtg"))
async def cmd_setmtg(m: types.Message):
    if m.from_user.id == OWNER_ID:
        try: await settings_col.update_one({"id": "config"}, {"$set": {"mtg": m.text.split()[1]}}, upsert=True); await m.answer("✅ Monetag ID সেট।")
        except: pass

# ১০. /seemtg - মনিট্যাগ আইডি দেখুন
@dp.message(Command("seemtg"))
async def cmd_seemtg(m: types.Message):
    conf = await get_config(); await m.answer(f"📢 Monetag ID: {conf.get('mtg')}")

# ১১. /setstp - এড স্টেপ
@dp.message(Command("setstp"))
async def cmd_setstp(m: types.Message):
    if m.from_user.id == OWNER_ID:
        try: await settings_col.update_one({"id": "config"}, {"$set": {"stp": int(m.text.split()[1])}}, upsert=True); await m.answer("✅ এড স্টেপ আপডেট।")
        except: pass

# ১২. /dm - মুভি ডিলিট
@dp.message(Command("dm"))
async def cmd_dm(m: types.Message):
    if m.from_user.id == OWNER_ID:
        name = m.text.replace("/dm ", ""); await content_col.delete_one({"name": name, "type": "movie"}); await m.answer("🗑 মুভি ডিলিট সফল।")

# ১৩. /ds - সিরিজ ডিলিট
@dp.message(Command("ds"))
async def cmd_ds(m: types.Message):
    if m.from_user.id == OWNER_ID:
        name = m.text.replace("/ds ", ""); await content_col.delete_one({"name": name, "type": "series"}); await m.answer("🗑 ড্রামা ডিলিট সফল।")

# ১৪. /dlall - সব ডিলিট
@dp.message(Command("dlall"))
async def cmd_dlall(m: types.Message):
    if m.from_user.id == OWNER_ID:
        await content_col.delete_many({}); await file_store.delete_many({}); await m.answer("💥 সব ক্লিয়ার!")

# ১৫. /stats - পরিসংখ্যান
@dp.message(Command("stats"))
async def cmd_stats(m: types.Message):
    if m.from_user.id == OWNER_ID:
        c = await content_col.count_documents({}); await m.answer(f"📊 মোট পোস্ট: {c}\n🌐 {APP_URL}")

# ১৬. /perpost - পেজ লিমিট
@dp.message(Command("perpost"))
async def cmd_perpost(m: types.Message):
    if m.from_user.id == OWNER_ID:
        try: await settings_col.update_one({"id": "config"}, {"$set": {"per": int(m.text.split()[1])}}, upsert=True); await m.answer("✅ লিমিট সেট।")
        except: pass

# ১৭. /notifi - নোটিফিকেশন চ্যানেল
@dp.message(Command("notifi"))
async def cmd_notifi(m: types.Message):
    if m.from_user.id == OWNER_ID:
        try: ch = m.text.split()[1]; await notif_col.update_one({"id": ch}, {"$set": {"id": ch}}, upsert=True); await m.answer("✅ চ্যানেল যুক্ত।")
        except: pass

# রিকোয়েস্ট বাটন হ্যান্ডলার
@dp.callback_query(F.data == "req")
async def req_cb(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.answer("📝 মুভির নাম লিখে পাঠান:"); await state.set_state(ReqState.movie_name); await cb.answer()

@dp.message(ReqState.movie_name)
async def process_req(m: types.Message, state: FSMContext):
    await bot.send_message(chat_id=OWNER_ID, text=f"🚨 **রিকোয়েস্ট:**\n👤: {m.from_user.full_name}\n🎬: **{m.text}**"); await m.answer("✅ পাঠানো হয়েছে!"); await state.clear()

# ==========================================
# ৫. প্রিমিয়াম ওয়েবসাইট ডিজাইন (FastAPI)
# ==========================================

INDEX_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{{ conf.site_name }}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swiper@10/swiper-bundle.min.css" />
    <style>
        body { background: #000; color: #fff; font-family: sans-serif; }
        .notice { background: linear-gradient(90deg, #ff0055, #ffcc00); padding: 7px; text-align: center; font-weight: bold; position: sticky; top: 0; z-index: 1000; }
        .poster-card { position: relative; border-radius: 15px; overflow: hidden; background: #111; border: 1px solid #222; transition: 0.3s; }
        .poster-card:hover { transform: scale(1.05); border-color: #ff0055; }
        .poster-card img { width: 100%; height: 260px; object-fit: cover; }
        .v-badge { position: absolute; top: 10px; right: 10px; background: rgba(0,0,0,0.8); color: #00ffcc; padding: 2px 7px; font-size: 11px; border-radius: 5px; }
        .m-name { padding: 10px; text-align: center; font-size: 13px; font-weight: bold; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .swiper { width: 100%; height: 220px; border-radius: 15px; margin-bottom: 20px; }
        .swiper-slide img { width: 100%; height: 100%; object-fit: cover; }
    </style>
</head>
<body>
    <div class="notice">{{ conf.note }}</div>
    <div class="container py-4">
        <h4 class="text-center mb-3 text-danger">{{ conf.site_name }}</h4>
        <div class="swiper mySwiper"><div class="swiper-wrapper">
            {% for s in slider %}<div class="swiper-slide"><a href="/view/{{ s._id }}"><img src="{{ s.poster }}"></a></div>{% endfor %}
        </div></div>
        <div class="row row-cols-2 row-cols-md-4 g-3">
            {% for i in items %}
            <div class="col"><a href="/view/{{ i._id }}" class="text-decoration-none text-white">
                <div class="poster-card"><span class="v-badge">👁 {{ i.views }}</span><img src="{{ i.poster }}"><div class="m-name">{{ i.name }}</div></div>
            </a></div>
            {% endfor %}
        </div>
        <div class="d-flex justify-content-center mt-5">
            {% if page > 1 %}<a href="?page={{ page-1 }}" class="btn btn-outline-danger me-2">Prev</a>{% endif %}
            <button class="btn btn-danger">Page {{ page }}</button>
            <a href="?page={{ page+1 }}" class="btn btn-outline-danger ms-2">Next</a>
        </div>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/swiper@10/swiper-bundle.min.js"></script>
    <script>new Swiper(".mySwiper", { autoplay: true, loop: true });</script>
</body>
</html>
"""

DETAIL_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{{ item.name }}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background: #000; color: #fff; text-align: center; padding-top: 30px; }
        .poster { width: 85%; max-width: 360px; border-radius: 20px; box-shadow: 0 0 25px #ff0055; margin-bottom: 25px; }
        .p-box { background: #111; padding: 25px; border-radius: 20px; margin: 20px; border: 1px solid #333; }
        .d-btn { display: block; background: #222; color: #00ffcc; padding: 15px; margin-bottom: 12px; border-radius: 12px; text-decoration: none; font-weight: bold; border: 1px solid #444; }
        .lock { background: linear-gradient(45deg, #ff0055, #ffcc00); padding: 17px; border-radius: 15px; font-weight: bold; cursor: pointer; }
        .tg-icon { position: fixed; bottom: 25px; right: 25px; background: #0088cc; width: 55px; height: 55px; border-radius: 50%; display: flex; align-items: center; justify-content: center; box-shadow: 0 0 12px #0088cc; }
    </style>
</head>
<body>
    <a href="https://t.me/DramaStoreKing" class="tg-icon"><img src="https://upload.wikimedia.org/wikipedia/commons/8/82/Telegram_logo.svg" width="30"></a>
    <img src="{{ item.poster }}" class="poster"><h3>{{ item.name }}</h3>
    <div class="p-box">
        <div id="l-ui" class="lock" onclick="unlock()">🚀 Unlock Links (Watch Ad)</div>
        <div id="u-ui" style="display:none;">
            {% if item.type == 'movie' %}
                {% for l in item.links %}<a href="https://t.me/{{ bot_u }}?start={{ l.uid }}" class="d-btn">Get File ({{ l.q }})</a>{% endfor %}
            {% else %}
                {% for e in item.episodes %}<a href="https://t.me/{{ bot_u }}?start={{ e.uid }}" class="d-btn">Get {{ e.ep }}</a>{% endfor %}
            {% endif %}
        </div>
    </div>
    <script>
        const lock = {{ conf.autolock or 10 }} * 60 * 1000;
        if (localStorage.getItem('un_{{ item._id }}') && (Date.now() - localStorage.getItem('un_{{ item._id }}') < lock)) show();
        function unlock() { localStorage.setItem('un_{{ item._id }}', Date.now()); show(); }
        function show() { document.getElementById('l-ui').style.display='none'; document.getElementById('u-ui').style.display='block'; }
    </script>
    <a href="/" class="btn btn-outline-danger mt-4 px-5">Home</a>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def home(page: int = 1):
    conf = await get_config()
    items = await content_col.find().sort("date", -1).skip((page-1)*conf['per']).limit(conf['per']).to_list(None)
    slider = await content_col.find().sort("views", -1).limit(5).to_list(None)
    return Template(INDEX_HTML).render(items=items, slider=slider, conf=conf, page=page)

@app.get("/view/{id}", response_class=HTMLResponse)
async def detail(id: str):
    item = await content_col.find_one({"_id": ObjectId(id)})
    conf = await get_config(); await content_col.update_one({"_id": ObjectId(id)}, {"$inc": {"views": 1}})
    return Template(DETAIL_HTML).render(item=item, conf=conf, bot_u=BOT_USERNAME)

# ==========================================
# ৬. রান ফাংশন (Conflict Fix সহ)
# ==========================================
@app.on_event("startup")
async def on_startup():
    # drop_pending_updates=True দিলে কনফ্লিক্ট এরর ফিক্স হবে
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(dp.start_polling(bot))
    print("🚀 Master Bot started in background...")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, log_level="info")
