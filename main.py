import os
import asyncio
import logging
import uuid
from datetime import datetime, timedelta
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

# --- ১. কনফিগারেশন সেকশন ---
TOKEN = "8655043839:AAH8Wxhd8jE8Y85XBdz8kRG2suLmqQx7mSU"
MONGO_URL = "mongodb+srv://drama:drama@cluster0.sa4kvgu.mongodb.net/?appName=Cluster0"
OWNER_ID = 7120801813
PUBLIC_CHANNEL = "@DramaStoreKing"
APP_URL = "https://indirect-meris-yeasinvai-95120fc6.koyeb.app" 
BOT_USERNAME = "dramastorkingsbot"
PORT = 8080 

# ডাটাবেস কানেকশন
client = AsyncIOMotorClient(MONGO_URL)
db = client['movie_dramabd']
content_col = db['contents']
settings_col = db['settings']
file_store = db['files']
notif_col = db['notif_channels']

# বট ও ওয়েব অ্যাপ অবজেক্ট
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
app = FastAPI()

# --- ২. এফএসএম (States) ---
class MovieState(StatesGroup):
    name = State()
    photo = State()
    quality = State()
    file = State()

class SeriesState(StatesGroup):
    name = State()
    photo = State()
    files = State()

# --- ৩. হেল্পার ফাংশন সমূহ ---
async def process_photo(message: types.Message):
    photo = message.photo[-1]
    file_info = await bot.get_file(photo.file_id)
    photo_name = f"{photo.file_id}.jpg"
    await bot.download_file(file_info.file_path, photo_name)
    try:
        response = upload_file(photo_name)
        os.remove(photo_name)
        return f"https://telegra.ph{response[0]}"
    except: return None

async def auto_delete_msg(chat_id, message_id, minutes):
    if minutes > 0:
        await asyncio.sleep(minutes * 60)
        try:
            await bot.delete_message(chat_id, message_id)
        except: pass

# --- ৪. বটের কমান্ড হ্যান্ডলারস ---

@dp.message(Command("start"))
async def start_cmd(message: types.Message, command: CommandObject):
    # Deep Linking: সাইট থেকে ফাইল নিতে আসলে
    if command.args:
        file_data = await file_store.find_one({"unique_id": command.args})
        if file_data:
            await bot.copy_message(
                chat_id=message.chat.id,
                from_chat_id=OWNER_ID,
                message_id=file_data['msg_id'],
                caption=f"🎥 মুভি: {file_data['name']}\n📢 চ্যানেল: {PUBLIC_CHANNEL}"
            )
            return

    conf = await settings_col.find_one({"id": "config"}) or {}
    logo_url = conf.get("logo", "https://telegra.ph/file/0f2e825a07530467776d5.jpg")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Watch Now (Website)", url=APP_URL)],
        [InlineKeyboardButton(text="📥 Movie Request", callback_data="req"),
         InlineKeyboardButton(text="🚀 Share Bot", switch_inline_query="")],
        [InlineKeyboardButton(text="📢 Main Channel", url=f"https://t.me/{PUBLIC_CHANNEL.replace('@','')}")],
        [InlineKeyboardButton(text="🔗 All Channels", url="https://t.me/all_channels_link")]
    ])
    await message.answer_photo(photo=logo_url, caption="Hello YA UPLODER!\n\nWelcome to Moviee BD click the button below to explore! ❤️🍿", reply_markup=kb)

# মুভি আপলোড (সরাসরি ফাইল স্টোর)
@dp.message(Command("movie"))
async def add_movie(message: types.Message, state: FSMContext):
    if message.from_user.id != OWNER_ID: return
    await message.answer("🎬 মুভির নাম লিখুন:")
    await state.set_state(MovieState.name)

@dp.message(MovieState.name)
async def m_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text, links=[], views=0)
    await message.answer("🖼 পোস্টারটি (Photo) সরাসরি পাঠান:")
    await state.set_state(MovieState.photo)

@dp.message(MovieState.photo, F.photo)
async def m_photo(message: types.Message, state: FSMContext):
    url = await process_photo(message)
    await state.update_data(poster=url)
    await message.answer("⚙️ কোয়ালিটি লিখুন (যেমন: 720p) অথবা Done দিন:", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Done")]], resize_keyboard=True))
    await state.set_state(MovieState.quality)

@dp.message(MovieState.quality)
async def m_quality(message: types.Message, state: FSMContext):
    if message.text == "Done":
        data = await state.get_data()
        await content_col.insert_one({"type": "movie", **data, "date": datetime.now()})
        conf = await settings_col.find_one({"id": "config"}) or {}
        dlt = int(conf.get("autodlt", 0))
        last_q = data['links'][-1]['q'] if data['links'] else "Standard"
        caption = f"🎬 মুভি: {data['name']}\n⚙️ কোয়ালিটি: {last_q}\n📢 চ্যানেল: {PUBLIC_CHANNEL}"
        post = await bot.send_photo(chat_id=PUBLIC_CHANNEL, photo=data['poster'], caption=caption)
        if dlt > 0: asyncio.create_task(auto_delete_msg(PUBLIC_CHANNEL, post.message_id, dlt))
        await message.answer("✅ মুভি ও ফাইল স্টোর সফল!", reply_markup=types.ReplyKeyboardRemove())
        await state.clear()
    else:
        await state.update_data(curr_q=message.text)
        await message.answer(f"📁 এখন {message.text} এর ভিডিও ফাইলটি সরাসরি পাঠান:")
        await state.set_state(MovieState.file)

@dp.message(MovieState.file, F.video | F.document)
async def m_file_store(message: types.Message, state: FSMContext):
    data = await state.get_data()
    uid = str(uuid.uuid4())[:8]
    await file_store.insert_one({"unique_id": uid, "msg_id": message.message_id, "name": data['name']})
    data['links'].append({"q": data['curr_q'], "uid": uid})
    await state.update_data(links=data['links'])
    await message.answer(f"✅ {data['curr_q']} ফাইলটি স্টোর হয়েছে। পরের কোয়ালিটি দিন বা Done লিখুন।")
    await state.set_state(MovieState.quality)

# সিরিজ আপলোড (সরাসরি ফাইল স্টোর)
@dp.message(Command("series"))
async def add_series(message: types.Message, state: FSMContext):
    if message.from_user.id != OWNER_ID: return
    await message.answer("📺 ড্রামার নাম লিখুন:")
    await state.set_state(SeriesState.name)

@dp.message(SeriesState.name)
async def s_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text, episodes=[], views=0)
    await message.answer("🖼 পোস্টারটি পাঠান:")
    await state.set_state(SeriesState.photo)

@dp.message(SeriesState.photo, F.photo)
async def s_photo(message: types.Message, state: FSMContext):
    url = await process_photo(message)
    await state.update_data(poster=url)
    await message.answer("📁 ১ম এপিসোড ফাইলটি সরাসরি পাঠান (শেষ হলে Done লিখুন):", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Done")]], resize_keyboard=True))
    await state.set_state(SeriesState.files)

@dp.message(SeriesState.files, F.video | F.document)
async def s_file_store(message: types.Message, state: FSMContext):
    data = await state.get_data()
    uid = str(uuid.uuid4())[:8]
    ep_n = f"Episode {len(data['episodes'])+1:02d}"
    await file_store.insert_one({"unique_id": uid, "msg_id": message.message_id, "name": f"{data['name']} {ep_n}"})
    data['episodes'].append({"ep": ep_n, "uid": uid})
    await state.update_data(episodes=data['episodes'])
    await message.answer(f"✅ {ep_n} সেভ হয়েছে। পরের ফাইল পাঠান বা Done লিখুন।")

@dp.message(SeriesState.files, F.text == "Done")
async def s_done(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await content_col.insert_one({"type": "series", **data, "date": datetime.now()})
    conf = await settings_col.find_one({"id": "config"}) or {}
    dlt = int(conf.get("autodlt", 0))
    caption = f"📺 ড্রামা: {data['name']}\n📁 এপিসোড সংখ্যা: {len(data['episodes'])}\n📢 চ্যানেল: {PUBLIC_CHANNEL}"
    post = await bot.send_photo(chat_id=PUBLIC_CHANNEL, photo=data['poster'], caption=caption)
    if dlt > 0: asyncio.create_task(auto_delete_msg(PUBLIC_CHANNEL, post.message_id, dlt))
    await message.answer("✅ সিরিজ স্টোর সফল!", reply_markup=types.ReplyKeyboardRemove())
    await state.clear()

# --- ৫. সকল কন্ট্রোল কমান্ডস ---
@dp.message(Command("logo"))
async def cmd_logo(m: types.Message):
    if m.from_user.id != OWNER_ID: return
    await settings_col.update_one({"id": "config"}, {"$set": {"logo": m.text.split()[1]}}, upsert=True)
    await m.answer("✅ লোগো আপডেট হয়েছে।")

@dp.message(Command("autodlt"))
async def cmd_autodlt(m: types.Message):
    await settings_col.update_one({"id": "config"}, {"$set": {"autodlt": int(m.text.split()[1])}}, upsert=True)
    await m.answer("✅ অটো ডিলিট সেট।")

@dp.message(Command("autolock"))
async def cmd_autolock(m: types.Message):
    await settings_col.update_one({"id": "config"}, {"$set": {"autolock": int(m.text.split()[1])}}, upsert=True)
    await m.answer("✅ অটো লক সেট।")

@dp.message(Command("setname"))
async def cmd_setname(m: types.Message):
    await settings_col.update_one({"id": "config"}, {"$set": {"site_name": m.text.replace("/setname ", "")}}, upsert=True)
    await m.answer("✅ সাইট নাম সেট।")

@dp.message(Command("setnotice"))
async def cmd_setnotice(m: types.Message):
    await settings_col.update_one({"id": "config"}, {"$set": {"note": m.text.replace("/setnotice ", "")}}, upsert=True)
    await m.answer("✅ নোটিশ সেট।")

@dp.message(Command("dm"))
async def cmd_dm(m: types.Message):
    await content_col.delete_one({"name": m.text.replace("/dm ", "")})
    await m.answer("🗑 মুভি ডিলিট সফল।")

@dp.message(Command("ds"))
async def cmd_ds(m: types.Message):
    await content_col.delete_one({"name": m.text.replace("/ds ", "")})
    await m.answer("🗑 সিরিজ ডিলিট সফল।")

@dp.message(Command("stats"))
async def cmd_stats(m: types.Message):
    c = await content_col.count_documents({})
    await m.answer(f"📊 মোট কন্টেন্ট: {c}")

@dp.message(Command("dlall"))
async def cmd_dlall(m: types.Message):
    await content_col.delete_many({}); await file_store.delete_many({}); await m.answer("💥 ক্লিয়ার!")

# --- ৬. প্রিমিয়াম ওয়েবসাইট ডিজাইন ---
LAYOUT_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{{ conf.site_name }}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swiper@10/swiper-bundle.min.css" />
    <style>
        body { background: #050505; color: #fff; font-family: sans-serif; }
        .notice { background: linear-gradient(90deg, #ff0055, #ffcc00); padding: 6px; text-align: center; font-weight: bold; }
        .poster-card { position: relative; border-radius: 12px; overflow: hidden; background: #111; transition: 0.3s; }
        .poster-card:hover { transform: scale(1.05); }
        .poster-card img { width: 100%; height: 260px; object-fit: cover; }
        .v-badge { position: absolute; top: 8px; right: 8px; background: rgba(0,0,0,0.8); color: #00ffcc; padding: 2px 6px; font-size: 11px; border-radius: 5px; }
        .m-title { padding: 8px; text-align: center; font-size: 13px; font-weight: bold; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .swiper { width: 100%; height: 220px; border-radius: 15px; margin-bottom: 20px; }
        .swiper-slide img { width: 100%; height: 100%; object-fit: cover; }
    </style>
</head>
<body>
    <div class="notice">{{ conf.note }}</div>
    <div class="container py-3">
        <h4 class="text-center mb-4 text-danger">{{ conf.site_name }}</h4>
        <div class="swiper mySwiper"><div class="swiper-wrapper">
            {% for s in slider %}<div class="swiper-slide"><a href="/view/{{ s._id }}"><img src="{{ s.poster }}"></a></div>{% endfor %}
        </div></div>
        <div class="row row-cols-2 g-3">
            {% for i in items %}<div class="col"><a href="/view/{{ i._id }}" class="text-decoration-none text-white">
                <div class="poster-card"><span class="v-badge">👁 {{ i.views }}</span><img src="{{ i.poster }}"><div class="m-title">{{ i.name }}</div></div>
            </a></div>{% endfor %}
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
        .poster { width: 85%; max-width: 350px; border-radius: 20px; box-shadow: 0 0 20px #ff0055; margin-bottom: 25px; }
        .p-box { background: #111; padding: 25px; border-radius: 20px; margin: 20px; border: 1px solid #222; }
        .d-btn { display: block; background: #222; color: #00ffcc; padding: 15px; margin-bottom: 12px; border-radius: 12px; text-decoration: none; font-weight: bold; border: 1px solid #444; }
        .lock { background: #ff0055; padding: 15px; border-radius: 12px; cursor: pointer; }
        .tg-icon { position: fixed; bottom: 25px; right: 25px; background: #0088cc; width: 55px; height: 55px; border-radius: 50%; display: flex; align-items: center; justify-content: center; box-shadow: 0 0 10px #0088cc; }
    </style>
</head>
<body>
    <a href="https://t.me/DramaStoreKing" class="tg-icon"><img src="https://upload.wikimedia.org/wikipedia/commons/8/82/Telegram_logo.svg" width="30"></a>
    <img src="{{ item.poster }}" class="poster"><h3>{{ item.name }}</h3>
    <div class="p-box">
        <div id="l-ui" class="lock" onclick="unlock()">🚀 Unlock File Link (Watch Ad)</div>
        <div id="u-ui" style="display:none;">
            {% if item.type == 'movie' %}
                {% for l in item.links %}<a href="https://t.me/{{ bot_u }}?start={{ l.uid }}" class="d-btn">Get File ({{ l.q }})</a>{% endfor %}
            {% else %}
                {% for e in item.episodes %}<a href="https://t.me/{{ bot_u }}?start={{ e.uid }}" class="d-btn">Get {{ e.ep }} File</a>{% endfor %}
            {% endif %}
        </div>
    </div>
    <script>
        const lock = {{ conf.autolock or 10 }} * 60 * 1000;
        if (localStorage.getItem('un_{{ item._id }}') && (Date.now() - localStorage.getItem('un_{{ item._id }}') < lock)) show();
        function unlock() { localStorage.setItem('un_{{ item._id }}', Date.now()); show(); }
        function show() { document.getElementById('l-ui').style.display='none'; document.getElementById('u-ui').style.display='block'; }
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    conf = await settings_col.find_one({"id": "config"}) or {"site_name": "File Store"}
    items = await content_col.find().sort("date", -1).to_list(length=20)
    slider = await content_col.find().sort("views", -1).limit(5).to_list(length=5)
    return Template(LAYOUT_HTML).render(items=items, slider=slider, conf=conf)

@app.get("/view/{id}", response_class=HTMLResponse)
async def detail(id: str):
    item = await content_col.find_one({"_id": ObjectId(id)})
    conf = await settings_col.find_one({"id": "config"}) or {}
    await content_col.update_one({"_id": ObjectId(id)}, {"$inc": {"views": 1}})
    return Template(DETAIL_HTML).render(item=item, conf=conf, bot_u=BOT_USERNAME)

# --- ৭. ফাইনাল রান ফাংশন ---
async def run_bot():
    await bot.delete_webhook(drop_pending_updates=True)
    print("🚀 Bot & Site is running...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(run_bot())
    uvicorn.run(app, host="0.0.0.0", port=PORT)
