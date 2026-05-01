import os
import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
import uvicorn
from jinja2 import Template

# ==========================================
# ১. কনফিগারেশন এবং ডাটাবেস সেটআপ
# ==========================================
TOKEN = "8655043839:AAHC6IzkAhvHzSE9FqQbkcs_hkxJkcpN9l0"
MONGO_URL = "mongodb+srv://drama:drama@cluster0.sa4kvgu.mongodb.net/?appName=Cluster0"
OWNER_ID = 7120801813
PUBLIC_CHANNEL = "@DramaStoreKing"
APP_URL = "https://indirect-meris-yeasinvai-95120fc6.koyeb.app" 
BOT_USERNAME = "dramastorkingsbot"
PORT = int(os.environ.get("PORT", 8080))

logging.basicConfig(level=logging.INFO)
client = AsyncIOMotorClient(MONGO_URL)
db = client['movie_dramabd']
content_col = db['contents']
settings_col = db['settings']
file_store = db['files']
user_col = db['users']
view_logs = db['view_logs']
notif_col = db['notif_channels']
media_store = db['media_store']

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- লাইফস্প্যান (নতুন সিস্টেম) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: বট পোলিং শুরু
    await bot.delete_webhook(drop_pending_updates=True)
    polling_task = asyncio.create_task(dp.start_polling(bot))
    logging.info("Bot started polling...")
    yield
    # Shutdown: বট বন্ধ করা
    polling_task.cancel()
    await bot.session.close()

app = FastAPI(lifespan=lifespan)

# --- এফএসএম ---
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

# --- হেল্পার ফাংশন ---
async def get_config():
    conf = await settings_col.find_one({"id": "config"})
    if not conf:
        conf = {
            "id": "config", "site_name": "Moviee BD", "note": "মুভি দেখার নতুন ঠিকানা!", 
            "logo": f"{APP_URL}/media/default", 
            "autodlt": 10, "autolock": 10, "per": 10, "mtg": "10351894", "stp": 1, "protect": False
        }
        await settings_col.insert_one(conf)
    return conf

async def process_photo(message: types.Message):
    try:
        photo = message.photo[-1]
        file_info = await bot.get_file(photo.file_id)
        photo_bytes = await bot.download_file(file_info.file_path)
        media_id = str(uuid.uuid4())[:12]
        await media_store.insert_one({
            "media_id": media_id,
            "data": photo_bytes.read(),
            "mime": "image/jpeg"
        })
        return f"{APP_URL}/media/{media_id}"
    except Exception as e:
        logging.error(f"Image Save Error: {e}")
        return "https://telegra.ph/file/0f2e825a07530467776d5.jpg"

async def auto_delete_task(chat_id, message_id, minutes):
    if minutes > 0:
        await asyncio.sleep(minutes * 60)
        try: await bot.delete_message(chat_id, message_id)
        except: pass

# ==========================================
# ২. বট কমান্ডস
# ==========================================

@dp.message(Command("start"))
async def cmd_start(message: types.Message, command: CommandObject):
    user_data = {"id": message.from_user.id, "name": message.from_user.full_name, "username": message.from_user.username, "date": datetime.now()}
    await user_col.update_one({"id": message.from_user.id}, {"$set": user_data}, upsert=True)
    conf = await get_config()
    if command.args:
        f_data = await file_store.find_one({"unique_id": command.args})
        if f_data:
            is_protect = conf.get("protect", False)
            await bot.copy_message(chat_id=message.chat.id, from_chat_id=OWNER_ID, message_id=f_data['msg_id'], caption=f"🎬 মুভি: {f_data['name']}\n📢 চ্যানেল: {PUBLIC_CHANNEL}", protect_content=is_protect)
            return
    login_url = f"{APP_URL}/?user_id={message.from_user.id}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Watch Now (Login)", url=login_url)],
        [InlineKeyboardButton(text="📥 Request", callback_data="req"), InlineKeyboardButton(text="🚀 Share", switch_inline_query="")],
        [InlineKeyboardButton(text="📢 Channel", url=f"https://t.me/{PUBLIC_CHANNEL.replace('@','')}")]
    ])
    await message.answer_photo(photo=conf['logo'], caption=f"Hello {message.from_user.first_name}! ❤️🍿\n\nমুভি দেখতে নিচের বাটনে ক্লিক করুন।", reply_markup=kb)

@dp.message(Command("movie"))
async def add_movie(m: types.Message, state: FSMContext):
    if m.from_user.id != OWNER_ID: return
    await m.answer("🎬 মুভির নাম লিখুন:"); await state.set_state(MovieState.name)

@dp.message(MovieState.name)
async def m_name(m: types.Message, state: FSMContext):
    await state.update_data(name=m.text, links=[], views=0)
    await m.answer("🖼 পোস্টার ফটো পাঠান:"); await state.set_state(MovieState.photo)

@dp.message(MovieState.photo, F.photo)
async def m_photo(m: types.Message, state: FSMContext):
    url = await process_photo(m)
    await state.update_data(poster=url)
    await m.answer("⚙️ কোয়ালিটি দিন (যেমন: 720p):"); await state.set_state(MovieState.quality)

@dp.message(MovieState.quality)
async def m_quality(m: types.Message, state: FSMContext):
    if m.text and m.text.strip().casefold() == "done":
        data = await state.get_data()
        if not data.get('links'): await m.answer("❌ কোনো ফাইল নেই!"); return
        await content_col.insert_one({"type": "movie", **data, "date": datetime.now()})
        conf = await get_config()
        post = await bot.send_photo(chat_id=PUBLIC_CHANNEL, photo=data['poster'], caption=f"🎬 মুভি: {data['name']}\n📢 {PUBLIC_CHANNEL}")
        if int(conf['autodlt']) > 0: asyncio.create_task(auto_delete_task(PUBLIC_CHANNEL, post.message_id, int(conf['autodlt'])))
        await m.answer("✅ মুভি সাইটে আপলোড হয়েছে!", reply_markup=types.ReplyKeyboardRemove()); await state.clear()
    else:
        await state.update_data(cq=m.text)
        await m.answer(f"📁 {m.text} এর ফাইলটি পাঠান (বা Done লিখুন):", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Done")]], resize_keyboard=True))
        await state.set_state(MovieState.file)

@dp.message(MovieState.file, F.video | F.document)
async def m_file_store(m: types.Message, state: FSMContext):
    data = await state.get_data(); uid = str(uuid.uuid4())[:8]
    await file_store.insert_one({"unique_id": uid, "msg_id": m.message_id, "name": data['name']})
    links = data.get('links', []); links.append({"q": data['cq'], "uid": uid}); await state.update_data(links=links)
    await m.answer(f"✅ {data['cq']} সেভ। পরের কোয়ালিটি দিন বা Done লিখুন।"); await state.set_state(MovieState.quality)

# সিরিজ আপলোড (অনুরূপভাবে)
@dp.message(Command("series"))
async def add_series(m: types.Message, state: FSMContext):
    if m.from_user.id != OWNER_ID: return
    await m.answer("📺 ড্রামার নাম লিখুন:"); await state.set_state(SeriesState.name)

@dp.message(SeriesState.name)
async def s_name(m: types.Message, state: FSMContext):
    await state.update_data(name=m.text, episodes=[], views=0); await m.answer("🖼 পোস্টার ফটো পাঠান:"); await state.set_state(SeriesState.photo)

@dp.message(SeriesState.photo, F.photo)
async def s_photo(m: types.Message, state: FSMContext):
    url = await process_photo(m); await state.update_data(poster=url)
    await m.answer("📁 ১ম এপিসোড ফাইল পাঠান:", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Done")]], resize_keyboard=True))
    await state.set_state(SeriesState.files)

@dp.message(SeriesState.files)
async def s_files_store(m: types.Message, state: FSMContext):
    if m.text and m.text.strip().casefold() == "done":
        data = await state.get_data()
        await content_col.insert_one({"type": "series", **data, "date": datetime.now()})
        conf = await get_config()
        post = await bot.send_photo(chat_id=PUBLIC_CHANNEL, photo=data['poster'], caption=f"📺 ড্রামা: {data['name']}\n📢 {PUBLIC_CHANNEL}")
        if int(conf['autodlt']) > 0: asyncio.create_task(auto_delete_task(PUBLIC_CHANNEL, post.message_id, int(conf['autodlt'])))
        await m.answer("✅ ড্রামা সাইটে আপলোড হয়েছে!", reply_markup=types.ReplyKeyboardRemove()); await state.clear()
    elif m.video or m.document:
        data = await state.get_data(); uid = str(uuid.uuid4())[:8]
        ep_n = f"Episode {len(data['episodes'])+1:02d}"
        await file_store.insert_one({"unique_id": uid, "msg_id": m.message_id, "name": f"{data['name']} {ep_n}"})
        eps = data.get('episodes', []); eps.append({"ep": ep_n, "uid": uid}); await state.update_data(episodes=eps)
        await m.answer(f"✅ {ep_n} সেভ। পরের ফাইল দিন বা Done লিখুন।")

@dp.message(Command("protect"))
async def cmd_protect(m: types.Message):
    if m.from_user.id != OWNER_ID: return
    conf = await get_config(); ns = not conf.get("protect", False)
    await settings_col.update_one({"id": "config"}, {"$set": {"protect": ns}}, upsert=True)
    await m.answer(f"🔐 ফাইল প্রটেকশন: {'অন' if ns else 'অফ'}")

@dp.message(Command("stats"))
async def get_stats(m: types.Message):
    if m.from_user.id == OWNER_ID:
        c = await content_col.count_documents({}); u = await user_col.count_documents({})
        await m.answer(f"📊 পরিসংখ্যান:\nপোস্ট: {c}\nইউজার: {u}")

@dp.callback_query(F.data == "req")
async def req_cb(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.answer("📝 মুভির নাম লিখে পাঠান:"); await state.set_state(ReqState.movie_name); await cb.answer()

@dp.message(ReqState.movie_name)
async def req_process(m: types.Message, state: FSMContext):
    await bot.send_message(chat_id=OWNER_ID, text=f"🚨 রিকোয়েস্ট: {m.text}\n👤: {m.from_user.full_name}")
    await m.answer("✅ পাঠানো হয়েছে!"); await state.clear()

# ==========================================
# ৩. ওয়েব সার্ভার এবং ডিজাইন
# ==========================================

@app.get("/media/{media_id}")
async def serve_media(media_id: str):
    media = await media_store.find_one({"media_id": media_id})
    if media: return Response(content=media['data'], media_type=media['mime'])
    return Response(status_code=404)

INDEX_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{{ conf.site_name }}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background: #050505; color: #fff; }
        .notice { background: linear-gradient(90deg, #ff0055, #ffcc00); padding: 10px; text-align: center; color: #000; font-weight: bold; }
        .movie-card { background: #111; border-radius: 12px; overflow: hidden; border: 1px solid #222; margin-bottom: 12px; }
        .movie-card img { width: 100%; height: 260px; object-fit: cover; }
        .m-name { padding: 8px; font-size: 13px; text-align: center; font-weight: bold; min-height: 50px; }
    </style>
</head>
<body>
    <div class="notice">{{ conf.note }}</div>
    <div class="container py-4">
        <h4 class="mb-4">🎬 {{ conf.site_name }}</h4>
        <div class="row row-cols-2 row-cols-md-4 g-2">
            {% for i in items %}
            <div class="col">
                <a href="/view/{{ i._id }}" class="text-decoration-none text-white">
                    <div class="movie-card">
                        <img src="{{ i.poster }}" alt="Poster" loading="lazy">
                        <div class="m-name">{{ i.name }}</div>
                    </div>
                </a>
            </div>
            {% endfor %}
        </div>
    </div>
</body>
</html>
"""

DETAIL_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{{ item.name }}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src='//libtl.com/sdk.js' data-zone='{{ conf.mtg }}' data-sdk='show_{{ conf.mtg }}'></script>
    <style>
        body { background: #000; color: #fff; text-align: center; padding-top: 20px; }
        .poster { width: 90%; max-width: 300px; border-radius: 15px; border: 2px solid #ff0055; margin-bottom: 20px; }
        .unlock-btn { display: block; background: linear-gradient(45deg, #ff0055, #ffcc00); color: #000; padding: 15px; border-radius: 10px; font-weight: bold; text-decoration: none; margin: 10px auto; max-width: 400px; cursor: pointer; }
    </style>
</head>
<body>
    <img src="{{ item.poster }}" class="poster">
    <h3>{{ item.name }}</h3>
    <div class="container py-4">
        {% if item.type == 'movie' %}
            {% for l in item.links %}
                <div id="lock-{{ l.uid }}" class="unlock-btn" onclick="triggerAd('{{ l.uid }}')">🔓 UNLOCK FILE ({{ l.q }})</div>
                <div id="box-{{ l.uid }}" style="display:none;">
                    <a href="https://t.me/{{ bot_u }}?start={{ l.uid }}" class="btn btn-outline-info p-3 w-100 mb-3">📥 GET MOVIE</a>
                </div>
            {% endfor %}
        {% else %}
            {% for e in item.episodes %}
                <div id="lock-{{ e.uid }}" class="unlock-btn" onclick="triggerAd('{{ e.uid }}')">🔓 UNLOCK {{ e.ep }}</div>
                <div id="box-{{ e.uid }}" style="display:none;">
                    <a href="https://t.me/{{ bot_u }}?start={{ e.uid }}" class="btn btn-outline-info p-3 w-100 mb-3">📥 GET {{ e.ep }}</a>
                </div>
            {% endfor %}
        {% endif %}
    </div>
    <script>
        function triggerAd(uid) {
            if (typeof show_{{ conf.mtg }} === 'function') { show_{{ conf.mtg }}(); }
            document.getElementById('lock-' + uid).style.display = 'none';
            document.getElementById('box-' + uid).style.display = 'block';
        }
    </script>
    <a href="/" class="btn btn-dark mt-4">Back to Home</a>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, user_id: str = None):
    conf = await get_config()
    if user_id:
        response = RedirectResponse(url="/")
        response.set_cookie(key="tg_user_id", value=user_id, max_age=31536000)
        return response
    items = await content_col.find().sort("date", -1).to_list(100)
    return Template(INDEX_HTML).render(items=items, conf=conf)

@app.get("/view/{id}", response_class=HTMLResponse)
async def detail(request: Request, id: str):
    item = await content_col.find_one({"_id": ObjectId(id)})
    conf = await get_config()
    if not item: return "Not Found"
    return Template(DETAIL_HTML).render(item=item, conf=conf, bot_u=BOT_USERNAME)

# ==========================================
# ৪. মেইন এন্ট্রি পয়েন্ট
# ==========================================

if __name__ == "__main__":
    # প্রোডাকশনে uvicorn রান করার জন্য main:app ব্যবহার করা হয়েছে
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, log_level="info")
