import os
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
PORT = 8080 # Koyeb এর জন্য 8080 পোর্ট জরুরি

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

# --- এফএসএম (States) ---
class MovieState(StatesGroup):
    name = State()
    photo = State()
    quality = State()
    file = State()

class SeriesState(StatesGroup):
    name = State()
    photo = State()
    files = State()

# --- হেল্পার: সরাসরি ছবি আপলোড লজিক ---
async def process_photo(message: types.Message):
    photo = message.photo[-1]
    file_info = await bot.get_file(photo.file_id)
    photo_name = f"{photo.file_id}.jpg"
    await bot.download_file(file_info.file_path, photo_name)
    try:
        response = upload_file(photo_name)
        os.remove(photo_name)
        return f"https://telegra.ph{response[0]}"
    except Exception as e:
        logging.error(f"Upload failed: {e}")
        return None

# --- বটের কমান্ড হ্যান্ডলারস ---

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Watch Now", url="https://indirect-meris-yeasinvai-95120fc6.koyeb.app")],
        [InlineKeyboardButton(text="📥 Movie Request", callback_data="req"),
         InlineKeyboardButton(text="🚀 Share Bot", switch_inline_query="")],
        [InlineKeyboardButton(text="📢 Main Channel", url="https://t.me/movie_channel_link")],
        [InlineKeyboardButton(text="🔗 All Channels", url="https://t.me/all_channels_link")]
    ])
    banner = "https://telegra.ph/file/0f2e825a07530467776d5.jpg" # স্ক্রিনশট ব্যানার
    await message.answer_photo(photo=banner, caption="Hello! Welcome to Moviee BD. ❤️🍿\nClick the button below to explore!", reply_markup=kb)

# মুভি আপলোড লজিক (/movie)
@dp.message(Command("movie"))
async def add_movie(message: types.Message, state: FSMContext):
    if message.from_user.id != OWNER_ID: return
    await message.answer("🎬 মুভির নাম লিখুন:")
    await state.set_state(MovieState.name)

@dp.message(MovieState.name)
async def m_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text, links=[], views=0)
    await message.answer("🖼 এখন মুভির পোস্টারটি (ছবি) সরাসরি পাঠান:")
    await state.set_state(MovieState.photo)

@dp.message(MovieState.photo, F.photo)
async def m_photo(message: types.Message, state: FSMContext):
    msg = await message.answer("⏳ ছবি আপলোড হচ্ছে, অপেক্ষা করুন...")
    url = await process_photo(message)
    if not url:
        return await msg.edit_text("❌ ছবি আপলোড ব্যর্থ হয়েছে! আবার পাঠান।")
    await state.update_data(poster=url)
    await msg.edit_text("⚙️ কোয়ালিটি লিখুন (উদা: 720p) অথবা শেষ করতে Done লিখুন:", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Done")]], resize_keyboard=True))
    await state.set_state(MovieState.quality)

@dp.message(MovieState.quality)
async def m_quality(message: types.Message, state: FSMContext):
    if message.text == "Done":
        data = await state.get_data()
        await content_col.insert_one({"type": "movie", **data, "date": datetime.now()})
        await message.answer("✅ মুভিটি সাইটে সফলভাবে আপলোড হয়েছে!", reply_markup=types.ReplyKeyboardRemove())
        await state.clear()
    else:
        await state.update_data(curr_q=message.text)
        await message.answer(f"🔗 {message.text} এর ফাইল লিঙ্ক দিন:")
        await state.set_state(MovieState.file)

@dp.message(MovieState.file)
async def m_file(message: types.Message, state: FSMContext):
    data = await state.get_data()
    data['links'].append({"q": data['curr_q'], "link": message.text})
    await state.update_data(links=data['links'])
    await message.answer("পরবর্তী কোয়ালিটি লিখুন অথবা Done দিন।")
    await state.set_state(MovieState.quality)

# সিরিজ আপলোড লজিক (/series)
@dp.message(Command("series"))
async def add_series(message: types.Message, state: FSMContext):
    if message.from_user.id != OWNER_ID: return
    await message.answer("📺 সিরিজ/ড্রামার নাম লিখুন:")
    await state.set_state(SeriesState.name)

@dp.message(SeriesState.name)
async def s_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text, episodes=[], views=0)
    await message.answer("🖼 সিরিজের পোস্টারটি (ছবি) সরাসরি পাঠান:")
    await state.set_state(SeriesState.photo)

@dp.message(SeriesState.photo, F.photo)
async def s_photo(message: types.Message, state: FSMContext):
    url = await process_photo(message)
    await state.update_data(poster=url)
    await message.answer("📁 ১ম এপিসোড লিঙ্ক দিন (পরপর দিন, শেষ হলে Done লিখুন):", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Done")]], resize_keyboard=True))
    await state.set_state(SeriesState.files)

@dp.message(SeriesState.files)
async def s_files(message: types.Message, state: FSMContext):
    if message.text == "Done":
        data = await state.get_data()
        await content_col.insert_one({"type": "series", **data, "date": datetime.now()})
        await message.answer("✅ সিরিজটি সফলভাবে আপলোড হয়েছে!", reply_markup=types.ReplyKeyboardRemove())
        await state.clear()
    else:
        data = await state.get_data()
        ep_num = len(data['episodes']) + 1
        data['episodes'].append({"ep": f"Episode {ep_num:02d}", "link": message.text})
        await state.update_data(episodes=data['episodes'])
        await message.answer(f"✅ Episode {ep_num:02d} যুক্ত হয়েছে। পরবর্তী এপিসোড লিঙ্ক দিন।")

# --- সকল কন্ট্রোল কমান্ডস ---

@dp.message(Command("dm"))
async def cmd_dm(m: types.Message):
    await content_col.delete_one({"name": m.text.replace("/dm ", ""), "type": "movie"})
    await m.answer("🗑 মুভি ডিলিট হয়েছে।")

@dp.message(Command("ds"))
async def cmd_ds(m: types.Message):
    await content_col.delete_one({"name": m.text.replace("/ds ", ""), "type": "series"})
    await m.answer("🗑 সিরিজ ডিলিট হয়েছে।")

@dp.message(Command("dlall"))
async def cmd_dlall(m: types.Message):
    await content_col.delete_many({})
    await m.answer("💥 সকল ডেটা ডিলিট করা হয়েছে!")

@dp.message(Command("setmtg"))
async def cmd_setmtg(m: types.Message):
    await settings_col.update_one({"id": "config"}, {"$set": {"mtg": m.text.split()[1]}}, upsert=True)
    await m.answer("✅ Monetag ID সেট হয়েছে।")

@dp.message(Command("seemtg"))
async def cmd_seemtg(m: types.Message):
    conf = await settings_col.find_one({"id": "config"})
    await m.answer(f"📢 Monetag ID: {conf.get('mtg', 'নাই')}")

@dp.message(Command("setstp"))
async def cmd_setstp(m: types.Message):
    await settings_col.update_one({"id": "config"}, {"$set": {"stp": m.text.split()[1]}}, upsert=True)
    await m.answer("✅ Ad Steps আপডেট হয়েছে।")

@dp.message(Command("setnotice"))
async def cmd_setnotice(m: types.Message):
    await settings_col.update_one({"id": "config"}, {"$set": {"note": m.text.replace("/setnotice ", "")}}, upsert=True)
    await m.answer("✅ সাইট নোটিশ সেট হয়েছে।")

@dp.message(Command("setname"))
async def cmd_setname(m: types.Message):
    await settings_col.update_one({"id": "config"}, {"$set": {"site_name": m.text.replace("/setname ", "")}}, upsert=True)
    await m.answer("✅ সাইট নাম সেট হয়েছে।")

@dp.message(Command("perpost"))
async def cmd_perpost(m: types.Message):
    await settings_col.update_one({"id": "config"}, {"$set": {"per": int(m.text.split()[1])}}, upsert=True)
    await m.answer("✅ পেজ লিমিট আপডেট হয়েছে।")

@dp.message(Command("stats"))
async def cmd_stats(m: types.Message):
    c = await content_col.count_documents({})
    await m.answer(f"📊 মোট মুভি/সিরিজ: {c}")

@dp.message(Command("notifi"))
async def cmd_notifi(m: types.Message):
    await notif_col.update_one({"id": m.text.split()[1]}, {"$set": {"id": m.text.split()[1]}}, upsert=True)
    await m.answer("✅ নোটিফিকেশন চ্যানেল যুক্ত।")

# --- ওয়েবসাইট সেকশন ---

LAYOUT_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{{ conf.site_name }}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swiper@10/swiper-bundle.min.css" />
    <style>
        body { background: #000; color: #fff; font-family: sans-serif; }
        .notice { background: #ff0055; padding: 5px; text-align: center; font-size: 14px; font-weight: bold; }
        .poster-card { position: relative; border-radius: 12px; overflow: hidden; background: #111; border: 1px solid #222; }
        .poster-card img { width: 100%; height: 260px; object-fit: cover; }
        .v-count { position: absolute; top: 8px; right: 8px; background: rgba(0,0,0,0.7); color: #00ffcc; padding: 2px 6px; font-size: 11px; border-radius: 5px; }
        .m-name { padding: 8px; text-align: center; font-size: 13px; font-weight: bold; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .swiper { width: 100%; height: 200px; margin-bottom: 20px; border-radius: 12px; }
        .swiper-slide img { width: 100%; height: 100%; object-fit: cover; }
        .premium-box { background: #111; padding: 25px; border-radius: 20px; box-shadow: 0 0 15px rgba(255,0,85,0.3); }
        .d-btn { display: block; background: linear-gradient(to right, #ff0055, #ffcc00); color: #fff; text-decoration: none; padding: 12px; margin-bottom: 12px; border-radius: 10px; font-weight: bold; border: none; }
    </style>
</head>
<body>
    <div class="notice">{{ conf.note }}</div>
    <div class="container py-3">
        <h4 class="text-center mb-3">{{ conf.site_name }}</h4>
        
        <!-- স্লাইডার (Top 5 Viewed) -->
        <div class="swiper mySwiper">
            <div class="swiper-wrapper">
                {% for s in slider %}
                <div class="swiper-slide"><a href="/view/{{ s._id }}"><img src="{{ s.poster }}"></a></div>
                {% endfor %}
            </div>
        </div>

        <div class="row row-cols-2 g-3">
            {% for i in items %}
            <div class="col">
                <a href="/view/{{ i._id }}" class="text-decoration-none text-white">
                    <div class="poster-card">
                        <span class="v-count">👁 {{ i.views }}</span>
                        <img src="{{ i.poster }}">
                        <div class="m-name">{{ i.name }}</div>
                    </div>
                </a>
            </div>
            {% endfor %}
        </div>

        <div class="d-flex justify-content-between mt-4">
            {% if page > 1 %}<a href="?page={{ page-1 }}" class="btn btn-sm btn-outline-light">Prev</a>{% endif %}
            <span class="text-muted">Page {{ page }}</span>
            <a href="?page={{ page+1 }}" class="btn btn-sm btn-outline-light">Next</a>
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
        body { background: #000; color: #fff; text-align: center; padding-top: 20px; }
        .main-p { width: 85%; max-width: 350px; border-radius: 15px; box-shadow: 0 0 25px #ff0055; margin-bottom: 20px; }
        .premium-box { background: #111; padding: 20px; border-radius: 20px; margin: 20px; }
        .d-btn { display: block; background: #222; color: #00ffcc; padding: 15px; margin-bottom: 10px; border-radius: 12px; text-decoration: none; font-weight: bold; border: 1px solid #333; }
        .d-btn:hover { background: #00ffcc; color: #000; }
    </style>
</head>
<body>
    <img src="{{ item.poster }}" class="main-p">
    <h3>{{ item.name }}</h3>
    <p class="text-muted">Views: {{ item.views }}</p>
    <div class="premium-box">
        {% if item.type == 'movie' %}
            {% for l in item.links %}<a href="{{ l.link }}" class="d-btn">Watch/Download {{ l.q }}</a>{% endfor %}
        {% else %}
            {% for e in item.episodes %}<a href="{{ e.link }}" class="d-btn">{{ e.ep }} - Play Now</a>{% endfor %}
        {% endif %}
    </div>
    <a href="/" class="btn btn-outline-light mb-5">Back to Home</a>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, page: int = 1):
    conf = await settings_col.find_one({"id": "config"}) or {"site_name": "Moviee BD", "note": "Welcome!"}
    per = conf.get("per", 10)
    items = await content_col.find().sort("date", -1).skip((page-1)*per).limit(per).to_list(length=per)
    slider = await content_col.find().sort("views", -1).limit(5).to_list(length=5)
    return Template(LAYOUT_HTML).render(items=items, slider=slider, conf=conf, page=page)

@app.get("/view/{id}", response_class=HTMLResponse)
async def view_item(id: str):
    item = await content_col.find_one({"_id": ObjectId(id)})
    await content_col.update_one({"_id": ObjectId(id)}, {"$inc": {"views": 1}})
    return Template(DETAIL_HTML).render(item=item)

# --- বটের পোলিং এবং ওয়েবসাইট সার্ভার রান ---
async def start_polling():
    # Conflict এড়াতে পুরানো সেশন মুছে ফেলা
    await bot.delete_webhook(drop_pending_updates=True)
    print("🚀 বট রান হচ্ছে...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    loop = asyncio.get_event_loop()
    loop.create_task(start_polling())
    uvicorn.run(app, host="0.0.0.0", port=PORT)
