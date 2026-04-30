import asyncio
import logging
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from telegraph import upload_file
import uvicorn
from jinja2 import Template

# --- কনফিগারেশন ---
TOKEN = "8655043839:AAH8Wxhd8jE8Y85XBdz8kRG2suLmqQx7mSU"
MONGO_URL = "mongodb+srv://drama:drama@cluster0.sa4kvgu.mongodb.net/?appName=Cluster0"
OWNER_ID = 7120801813
APP_URL = "https://indirect-meris-yeasinvai-95120fc6.koyeb.app"

# ডাটাবেস কানেকশন
client = AsyncIOMotorClient(MONGO_URL)
db = client['movie_dramabd']
content_col = db['contents']
settings_col = db['settings']
notif_col = db['notif_channels']

# বট ও ওয়েব অ্যাপ অবজেক্ট
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
app = FastAPI()

# --- এফএসএম স্টেটস ---
class MovieState(StatesGroup):
    name = State()
    photo = State()
    quality = State()
    file = State()

class SeriesState(StatesGroup):
    name = State()
    photo = State()
    files = State()

# --- হেল্পার: ছবি আপলোড ---
async def upload_to_web(message: types.Message):
    file = await bot.get_file(message.photo[-1].file_id)
    file_path = file.file_path
    destination = f"{message.photo[-1].file_id}.jpg"
    await bot.download_file(file_path, destination)
    try:
        response = upload_file(destination)
        os.remove(destination)
        return f"https://telegra.ph{response[0]}"
    except:
        return None

# --- বটের কমান্ড হ্যান্ডলারস ---

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Watch Now", url=APP_URL)],
        [InlineKeyboardButton(text="📥 Movie Request", callback_data="req"),
         InlineKeyboardButton(text="🚀 Share Bot", switch_inline_query="")],
        [InlineKeyboardButton(text="📢 Main Channel", url="https://t.me/movie_channel")],
        [InlineKeyboardButton(text="🔗 All Channels", url="https://t.me/all_channels")]
    ])
    banner = "https://telegra.ph/file/your_banner_link.jpg"
    await message.answer_photo(photo=banner, caption="Hello! Welcome to Moviee BD. ❤️🍿", reply_markup=kb)

# মুভি আপলোড লজিক
@dp.message(Command("movie"))
async def movie_start(message: types.Message, state: FSMContext):
    if message.from_user.id != OWNER_ID: return
    await message.answer("🎬 মুভির নাম লিখুন:")
    await state.set_state(MovieState.name)

@dp.message(MovieState.name)
async def movie_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text, links=[], views=0)
    await message.answer("🖼 এখন মুভির পোস্টারটি (Photo) সরাসরি এখানে পাঠান:")
    await state.set_state(MovieState.photo)

@dp.message(MovieState.photo, F.photo)
async def movie_photo(message: types.Message, state: FSMContext):
    msg = await message.answer("⏳ পোস্টার প্রসেস হচ্ছে...")
    url = await upload_to_web(message)
    await state.update_data(poster=url)
    await msg.edit_text("⚙️ কোয়ালিটি লিখুন (যেমন: 720p) বা শেষ করতে 'Done' দিন:", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Done")]], resize_keyboard=True))
    await state.set_state(MovieState.quality)

@dp.message(MovieState.quality)
async def movie_quality(message: types.Message, state: FSMContext):
    if message.text == "Done":
        data = await state.get_data()
        await content_col.insert_one({"type": "movie", **data, "date": datetime.now()})
        await message.answer("✅ মুভি আপলোড সফল!", reply_markup=types.ReplyKeyboardRemove())
        await state.clear()
    else:
        await state.update_data(temp_q=message.text)
        await message.answer(f"🔗 {message.text} এর ফাইল লিঙ্ক দিন:")
        await state.set_state(MovieState.file)

@dp.message(MovieState.file)
async def movie_file(message: types.Message, state: FSMContext):
    data = await state.get_data()
    data['links'].append({"q": data['temp_q'], "link": message.text})
    await state.update_data(links=data['links'])
    await message.answer("পরবর্তী কোয়ালিটি অথবা Done লিখুন।")
    await state.set_state(MovieState.quality)

# সিরিজ আপলোড লজিক
@dp.message(Command("series"))
async def series_start(message: types.Message, state: FSMContext):
    if message.from_user.id != OWNER_ID: return
    await message.answer("📺 সিরিজ/ড্রামার নাম লিখুন:")
    await state.set_state(SeriesState.name)

@dp.message(SeriesState.name)
async def series_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text, episodes=[], views=0)
    await message.answer("🖼 সিরিজের পোস্টারটি (Photo) সরাসরি পাঠান:")
    await state.set_state(SeriesState.photo)

@dp.message(SeriesState.photo, F.photo)
async def series_photo(message: types.Message, state: FSMContext):
    url = await upload_to_web(message)
    await state.update_data(poster=url)
    await message.answer("📁 ১ম এপিসোড লিঙ্ক দিন (পরপর দিন, শেষ হলে Done লিখুন):", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Done")]], resize_keyboard=True))
    await state.set_state(SeriesState.files)

@dp.message(SeriesState.files)
async def series_files(message: types.Message, state: FSMContext):
    if message.text == "Done":
        data = await state.get_data()
        await content_col.insert_one({"type": "series", **data, "date": datetime.now()})
        await message.answer("✅ সিরিজ আপলোড সফল!", reply_markup=types.ReplyKeyboardRemove())
        await state.clear()
    else:
        data = await state.get_data()
        ep_num = len(data['episodes']) + 1
        data['episodes'].append({"ep": f"Episode {ep_num:02d}", "link": message.text})
        await state.update_data(episodes=data['episodes'])
        await message.answer(f"✅ Episode {ep_num:02d} যুক্ত হয়েছে। পরবর্তী লিঙ্ক দিন।")

# --- কন্ট্রোল কমান্ডস (বাকি সব কমান্ড) ---
@dp.message(Command("dm"))
async def del_m(m: types.Message):
    await content_col.delete_one({"title": m.text.replace("/dm ", ""), "type": "movie"})
    await m.answer("🗑 মুভি ডিলিট হয়েছে।")

@dp.message(Command("ds"))
async def del_s(m: types.Message):
    await content_col.delete_one({"title": m.text.replace("/ds ", ""), "type": "series"})
    await m.answer("🗑 সিরিজ ডিলিট হয়েছে।")

@dp.message(Command("dlall"))
async def del_all(m: types.Message):
    await content_col.delete_many({})
    await m.answer("💥 সব ক্লিয়ার!")

@dp.message(Command("setmtg"))
async def set_mtg(m: types.Message):
    await settings_col.update_one({"id": "config"}, {"$set": {"mtg": m.text.split()[1]}}, upsert=True)
    await m.answer("✅ Monetag ID আপডেট হয়েছে।")

@dp.message(Command("seemtg"))
async def see_mtg(m: types.Message):
    conf = await settings_col.find_one({"id": "config"})
    await m.answer(f"📢 বর্তমান Monetag ID: {conf.get('mtg', 'নাই')}")

@dp.message(Command("setstp"))
async def set_stp(m: types.Message):
    await settings_col.update_one({"id": "config"}, {"$set": {"stp": m.text.split()[1]}}, upsert=True)
    await m.answer("✅ এড স্টেপ আপডেট হয়েছে।")

@dp.message(Command("setnotice"))
async def set_note(m: types.Message):
    await settings_col.update_one({"id": "config"}, {"$set": {"note": m.text.replace("/setnotice ", "")}}, upsert=True)
    await m.answer("✅ নোটিশ সেট হয়েছে।")

@dp.message(Command("setname"))
async def set_name(m: types.Message):
    await settings_col.update_one({"id": "config"}, {"$set": {"site_name": m.text.replace("/setname ", "")}}, upsert=True)
    await m.answer("✅ সাইট নাম সেট হয়েছে।")

@dp.message(Command("perpost"))
async def set_per(m: types.Message):
    await settings_col.update_one({"id": "config"}, {"$set": {"per": int(m.text.split()[1])}}, upsert=True)
    await m.answer("✅ পেজ লিমিট সেট হয়েছে।")

@dp.message(Command("stats"))
async def stats(m: types.Message):
    c = await content_col.count_documents({})
    await m.answer(f"📊 মোট পোস্ট: {c}")

@dp.message(Command("notifi"))
async def set_notif(m: types.Message):
    await notif_col.update_one({"id": m.text.split()[1]}, {"$set": {"id": m.text.split()[1]}}, upsert=True)
    await m.answer("✅ চ্যানেল নোটিফিকেশন যুক্ত।")

# --- ওয়েবসাইট টেমপ্লেট ---
INDEX_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{{ settings.site_name }}</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css">
    <style>
        body { background: #000; color: #fff; }
        .notice { background: red; padding: 5px; text-align: center; }
        .poster { position: relative; border-radius: 10px; overflow: hidden; }
        .poster img { width: 100%; height: 260px; object-fit: cover; }
        .views { position: absolute; top: 5px; right: 5px; background: rgba(0,0,0,0.6); padding: 2px 5px; font-size: 10px; border-radius: 3px; }
        .title { font-size: 13px; text-align: center; margin-top: 5px; }
        .slider img { width: 100%; height: 200px; object-fit: cover; border-radius: 10px; }
    </style>
</head>
<body>
    <div class="notice">{{ settings.note }}</div>
    <div class="container mt-3">
        <h3 class="text-center mb-3">{{ settings.site_name }}</h3>
        
        <!-- Slider -->
        <div class="slider mb-4">
            {% if slider %}<a href="/view/{{ slider[0]._id }}"><img src="{{ slider[0].poster }}"></a>{% endif %}
        </div>

        <div class="row row-cols-2 g-3">
            {% for item in items %}
            <div class="col">
                <a href="/view/{{ item._id }}" class="text-decoration-none text-white">
                    <div class="poster">
                        <span class="views">👁 {{ item.views }}</span>
                        <img src="{{ item.poster }}">
                    </div>
                    <div class="title">{{ item.name }}</div>
                </a>
            </div>
            {% endfor %}
        </div>

        <div class="d-flex justify-content-between mt-4">
            {% if page > 1 %}<a href="?page={{ page-1 }}" class="btn btn-sm btn-danger">Prev</a>{% endif %}
            <span>Page {{ page }}</span>
            <a href="?page={{ page+1 }}" class="btn btn-sm btn-danger">Next</a>
        </div>
    </div>
</body>
</html>
"""

VIEW_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{{ item.name }}</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css">
    <style>
        body { background: #111; color: #fff; text-align: center; }
        .main-img { width: 90%; border-radius: 15px; margin-top: 20px; box-shadow: 0 0 15px red; }
        .btn-box { background: #222; margin: 20px; padding: 20px; border-radius: 15px; }
        .d-btn { display: block; background: red; color: #fff; padding: 10px; margin-bottom: 10px; border-radius: 5px; text-decoration: none; font-weight: bold; }
    </style>
</head>
<body>
    <img src="{{ item.poster }}" class="main-img">
    <h2 class="mt-3">{{ item.name }}</h2>
    <div class="btn-box">
        {% if item.type == 'movie' %}
            {% for l in item.links %}<a href="{{ l.link }}" class="d-btn">Download {{ l.q }}</a>{% endfor %}
        {% else %}
            {% for e in item.episodes %}<a href="{{ e.link }}" class="d-btn">{{ e.ep }} - Play</a>{% endfor %}
        {% endif %}
    </div>
    <a href="/" class="btn btn-secondary">Home</a>
</body>
</html>
"""

# --- ওয়েব রাউটস ---
@app.get("/", response_class=HTMLResponse)
async def home(page: int = 1):
    conf = await settings_col.find_one({"id": "config"}) or {}
    per = conf.get("per", 10)
    items = await content_col.find().sort("date", -1).skip((page-1)*per).limit(per).to_list(None)
    slider = await content_col.find().sort("views", -1).limit(1).to_list(None)
    return Template(INDEX_HTML).render(items=items, slider=slider, settings=conf, page=page)

@app.get("/view/{id}", response_class=HTMLResponse)
async def detail(id: str):
    item = await content_col.find_one({"_id": ObjectId(id)})
    await content_col.update_one({"_id": ObjectId(id)}, {"$inc": {"views": 1}})
    return Template(VIEW_HTML).render(item=item)

# --- সার্ভার রান ---
import os
async def run_bot():
    await dp.start_polling(bot)

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(run_bot())
    uvicorn.run(app, host="0.0.0.0", port=8000)
