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
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo, MenuButtonWebApp
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

# --- এফএসএম (স্টেট ম্যানেজমেন্ট) ---
class MovieState(StatesGroup):
    name = State()
    category = State()
    photo = State()
    quality = State()
    file = State()

class SeriesState(StatesGroup):
    name = State()
    category = State()
    photo = State()
    files = State()

class ReqState(StatesGroup):
    movie_name = State()

# --- হেল্পার ফাংশন সমূহ ---
async def get_config():
    conf = await settings_col.find_one({"id": "config"})
    if not conf:
        conf = {
            "id": "config", "site_name": "Moviee BD", "note": "মুভি দেখার নতুন ঠিকানা!", 
            "logo": f"{APP_URL}/media/default_logo", 
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
        logging.error(f"Media Error: {e}")
        return "https://telegra.ph/file/0f2e825a07530467776d5.jpg"

async def auto_delete_task(chat_id, message_id, minutes):
    if minutes > 0:
        await asyncio.sleep(minutes * 60)
        try: await bot.delete_message(chat_id, message_id)
        except: pass

@asynccontextmanager
async def lifespan(app: FastAPI):
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(text="Watch Now 🎬", web_app=WebAppInfo(url=APP_URL))
    )
    polling_task = asyncio.create_task(dp.start_polling(bot))
    logging.info("বট পোলিং শুরু হয়েছে...")
    yield
    polling_task.cancel()
    await bot.session.close()

app = FastAPI(lifespan=lifespan)

# ==========================================
# ২. কমান্ড লজিক (অক্ষত রাখা হয়েছে)
# ==========================================

@dp.message(Command("start"))
async def cmd_start(message: types.Message, command: CommandObject):
    user_data = {"id": message.from_user.id, "name": message.from_user.full_name, "username": message.from_user.username, "date": datetime.now()}
    await user_col.update_one({"id": message.from_user.id}, {"$set": user_data}, upsert=True)
    conf = await get_config()
    if command.args:
        f_data = await file_store.find_one({"unique_id": command.args})
        if f_data:
            return await bot.copy_message(chat_id=message.chat.id, from_chat_id=OWNER_ID, message_id=f_data['msg_id'], caption=f"🎬 মুভি: {f_data['name']}\n📢 চ্যানেল: {PUBLIC_CHANNEL}", protect_content=conf.get("protect", False))
    login_url = f"{APP_URL}/?user_id={message.from_user.id}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Watch Now (Premium Login)", url=login_url)],
        [InlineKeyboardButton(text="📥 Movie Request", callback_data="req"), InlineKeyboardButton(text=" My Referral Link", switch_inline_query="")],
        [InlineKeyboardButton(text=" Help & Tutorial", url="https://t.me/MovieeBD"), InlineKeyboardButton(text=" All Channels", url="https://t.me/all_channels")]
    ])
    await message.answer_photo(photo=conf['logo'], caption=f"Hello {message.from_user.first_name}!\nWelcome to {conf['site_name']} ❤️🍿", reply_markup=kb)

@dp.message(Command("movie"))
async def add_movie(m: types.Message, state: FSMContext):
    if m.from_user.id != OWNER_ID: return
    await m.answer("🎬 মুভির নাম লিখুন:"); await state.set_state(MovieState.name)

@dp.message(MovieState.name)
async def m_name(m: types.Message, state: FSMContext):
    await state.update_data(name=m.text, links=[], views=0)
    await m.answer("📁 ক্যাটাগরি দিন (যেমন: Movie, CID, Bangla Natok):"); await state.set_state(MovieState.category)

@dp.message(MovieState.category)
async def m_cat(m: types.Message, state: FSMContext):
    await state.update_data(cat=m.text)
    await m.answer("🖼 পোস্টার ফটো পাঠান:"); await state.set_state(MovieState.photo)

@dp.message(MovieState.photo, F.photo)
async def m_photo(m: types.Message, state: FSMContext):
    url = await process_photo(m); await state.update_data(poster=url)
    await m.answer("⚙️ কোয়ালিটি দিন (যেমন: 720p):"); await state.set_state(MovieState.quality)

@dp.message(MovieState.quality)
async def m_quality(m: types.Message, state: FSMContext):
    if m.text and m.text.strip().casefold() == "done":
        data = await state.get_data()
        if not data.get('links'): return await m.answer("❌ কোনো ফাইল নেই!")
        # quality save for badge
        await content_col.insert_one({"type": "movie", **data, "quality": data.get('cq'), "date": datetime.now()})
        conf = await get_config()
        post = await bot.send_photo(chat_id=PUBLIC_CHANNEL, photo=data['poster'], caption=f"🎬 মুভি: {data['name']}\n📢 {PUBLIC_CHANNEL}")
        if int(conf['autodlt']) > 0: asyncio.create_task(auto_delete_task(PUBLIC_CHANNEL, post.message_id, int(conf['autodlt'])))
        await m.answer("✅ মুভি সাইটে আপলোড হয়েছে!", reply_markup=types.ReplyKeyboardRemove()); await state.clear()
    else:
        await state.update_data(cq=m.text)
        await m.answer(f"📁 {m.text} এর ফাইলটি দিন (বা Done লিখুন):", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Done")]], resize_keyboard=True))
        await state.set_state(MovieState.file)

@dp.message(MovieState.file, F.video | F.document)
async def m_file_store(m: types.Message, state: FSMContext):
    data = await state.get_data(); uid = str(uuid.uuid4())[:8]
    await file_store.insert_one({"unique_id": uid, "msg_id": m.message_id, "name": data['name']})
    links = data.get('links', []); links.append({"q": data['cq'], "uid": uid}); await state.update_data(links=links)
    await m.answer(f"✅ {data['cq']} সেভ। পরের কোয়ালিটি দিন বা Done লিখুন।"); await state.set_state(MovieState.quality)

@dp.message(Command("series"))
async def add_series(m: types.Message, state: FSMContext):
    if m.from_user.id != OWNER_ID: return
    await m.answer("📺 ড্রামার নাম লিখুন:"); await state.set_state(SeriesState.name)

@dp.message(SeriesState.name)
async def s_name(m: types.Message, state: FSMContext):
    await state.update_data(name=m.text, episodes=[], views=0)
    await m.answer("📁 ক্যাটাগরি দিন (যেমন: Series, CID):"); await state.set_state(SeriesState.category)

@dp.message(SeriesState.category)
async def s_cat(m: types.Message, state: FSMContext):
    await state.update_data(cat=m.text)
    await m.answer("🖼 পোস্টার ফটো পাঠান:"); await state.set_state(SeriesState.photo)

@dp.message(SeriesState.photo, F.photo)
async def s_photo(m: types.Message, state: FSMContext):
    url = await process_photo(m); await state.update_data(poster=url)
    await m.answer("📁 ১ম এপিসোড ফাইল পাঠান (বা Done):", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Done")]], resize_keyboard=True))
    await state.set_state(SeriesState.files)

@dp.message(SeriesState.files)
async def s_files_store(m: types.Message, state: FSMContext):
    if m.text and m.text.strip().casefold() == "done":
        data = await state.get_data(); await content_col.insert_one({"type": "series", **data, "date": datetime.now()})
        conf = await get_config()
        post = await bot.send_photo(chat_id=PUBLIC_CHANNEL, photo=data['poster'], caption=f"📺 ড্রামা: {data['name']}\n📢 {PUBLIC_CHANNEL}")
        if int(conf['autodlt']) > 0: asyncio.create_task(auto_delete_task(PUBLIC_CHANNEL, post.message_id, int(conf['autodlt'])))
        await m.answer("✅ ড্রামা সাইটে আপলোড হয়েছে!", reply_markup=types.ReplyKeyboardRemove()); await state.clear()
    elif m.video or m.document:
        data = await state.get_data(); uid = str(uuid.uuid4())[:8]
        ep_n = f"Episode {len(data['episodes'])+1:02d}"
        await file_store.insert_one({"unique_id": uid, "msg_id": m.message_id, "name": f"{data['name']} {ep_n}"})
        eps = data.get('episodes', []); eps.append({"ep": ep_n, "uid": uid}); await state.update_data(episodes=eps)
        await m.answer(f"✅ {ep_n} সেভ। পরের এপিসোড পাঠান বা Done লিখুন।")

@dp.message(Command("protect"))
async def cmd_protect(m: types.Message):
    if m.from_user.id != OWNER_ID: return
    conf = await get_config(); ns = not conf.get("protect", False)
    await settings_col.update_one({"id": "config"}, {"$set": {"protect": ns}}, upsert=True)
    await m.answer(f"🔐 ফাইল প্রটেকশন এখন: **{'অন' if ns else 'অফ'}**", parse_mode="Markdown")

@dp.message(Command("logo"))
async def set_logo(m: types.Message):
    if m.from_user.id != OWNER_ID: return
    try: 
        link = m.text.split()[1]
        await settings_col.update_one({"id": "config"}, {"$set": {"logo": link}}, upsert=True)
        await m.answer("✅ বটের লোগো আপডেট করা হয়েছে।")
    except: await m.answer("ব্যবহার: /logo [Image_URL]")

@dp.message(Command("autodlt"))
async def set_autodlt(m: types.Message):
    if m.from_user.id != OWNER_ID: return
    try: 
        v = int(m.text.split()[1])
        await settings_col.update_one({"id": "config"}, {"$set": {"autodlt": v}}, upsert=True)
        await m.answer(f"✅ অটো ডিলিট সময়: {v} মিনিট।")
    except: await m.answer("ব্যবহার: /autodlt 10")

@dp.message(Command("autolock"))
async def set_autolock(m: types.Message):
    if m.from_user.id != OWNER_ID: return
    try: 
        v = int(m.text.split()[1])
        await settings_col.update_one({"id": "config"}, {"$set": {"autolock": v}}, upsert=True)
        await m.answer(f"✅ অটো লক সময়: {v} মিনিট।")
    except: await m.answer("ব্যবহার: /autolock 10")

@dp.message(Command("setname"))
async def set_name(m: types.Message):
    if m.from_user.id != OWNER_ID: return
    n = m.text.replace("/setname ","")
    await settings_col.update_one({"id": "config"}, {"$set": {"site_name": n}}, upsert=True)
    await m.answer(f"✅ সাইটের নাম সেট করা হয়েছে: {n}")

@dp.message(Command("setnotice"))
async def set_notice(m: types.Message):
    if m.from_user.id != OWNER_ID: return
    n = m.text.replace("/setnotice ","")
    await settings_col.update_one({"id": "config"}, {"$set": {"note": n}}, upsert=True)
    await m.answer("✅ সাইট নোটিশ আপডেট হয়েছে।")

@dp.message(Command("setmtg"))
async def set_mtg(m: types.Message):
    if m.from_user.id != OWNER_ID: return
    try:
        v = m.text.split()[1]
        await settings_col.update_one({"id": "config"}, {"$set": {"mtg": v}}, upsert=True)
        await m.answer("✅ Monetag ID আপডেট হয়েছে।")
    except: await m.answer("ব্যবহার: /setmtg 123456")

@dp.message(Command("seemtg"))
async def see_mtg(m: types.Message):
    if m.from_user.id != OWNER_ID: return
    conf = await get_config()
    await m.answer(f"📢 বর্তমান Monetag ID: `{conf.get('mtg')}`")

@dp.message(Command("setstp"))
async def set_stp(m: types.Message):
    if m.from_user.id != OWNER_ID: return
    try:
        v = int(m.text.split()[1])
        await settings_col.update_one({"id": "config"}, {"$set": {"stp": v}}, upsert=True)
        await m.answer(f"✅ এড স্টেপ সেট করা হয়েছে: {v}")
    except: await m.answer("ব্যবহার: /setstp 2")

@dp.message(Command("dm"))
async def del_m(m: types.Message):
    if m.from_user.id != OWNER_ID: return
    n = m.text.replace("/dm ","")
    res = await content_col.delete_one({"name": n, "type": "movie"})
    await m.answer(f"🗑 {n} ডিলিট করা হয়েছে।" if res.deleted_count else "❌ পাওয়া যায়নি।")

@dp.message(Command("ds"))
async def del_s(m: types.Message):
    if m.from_user.id != OWNER_ID: return
    n = m.text.replace("/ds ","")
    res = await content_col.delete_one({"name": n, "type": "series"})
    await m.answer(f"🗑 {n} ডিলিট করা হয়েছে।" if res.deleted_count else "❌ পাওয়া যায়নি।")

@dp.message(Command("dlall"))
async def del_all(m: types.Message):
    if m.from_user.id == OWNER_ID:
        await content_col.delete_many({}); await file_store.delete_many({}); await m.answer("💥 সব মুছে ফেলা হয়েছে!")

@dp.message(Command("stats"))
async def get_stats(m: types.Message):
    if m.from_user.id == OWNER_ID:
        c = await content_col.count_documents({}); u = await user_col.count_documents({})
        await m.answer(f"📊 পরিসংখ্যান:\nপোস্ট: {c}\nইউজার: {u}")

@dp.message(Command("perpost"))
async def set_per(m: types.Message):
    if m.from_user.id == OWNER_ID:
        try:
            v = int(m.text.split()[1]); await settings_col.update_one({"id": "config"}, {"$set": {"per": v}}, upsert=True)
            await m.answer(f"✅ পেজ লিমিট সেট: {v}")
        except: pass

@dp.message(Command("notifi"))
async def set_notif(m: types.Message):
    if m.from_user.id == OWNER_ID:
        try:
            ch = m.text.split()[1]; await notif_col.update_one({"id": ch}, {"$set": {"id": ch}}, upsert=True)
            await m.answer(f"✅ চ্যানেল যুক্ত: {ch}")
        except: pass

@dp.callback_query(F.data == "req")
async def req_cb(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.answer("📝 মুভির নাম লিখে পাঠান:"); await state.set_state(ReqState.movie_name); await cb.answer()

@dp.message(ReqState.movie_name)
async def req_p(m: types.Message, state: FSMContext):
    await bot.send_message(chat_id=OWNER_ID, text=f"🚨 রিকোয়েস্ট: {m.text}\n👤: {m.from_user.full_name}"); await m.answer("✅ পাঠানো হয়েছে!"); await state.clear()

# ==========================================
# ৩. প্রিমিয়াম ওয়েব ডিজাইন (স্লাইডার, পেজিনেশন ও ব্যাজসহ)
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
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <style>
        body { background: #fff; color: #000; font-family: 'Segoe UI', sans-serif; }
        .header { display: flex; justify-content: space-between; align-items: center; padding: 15px; border-bottom: 1px solid #eee; }
        .logo { font-size: 20px; font-weight: bold; }
        .logo span { background: red; color: #fff; padding: 2px 6px; border-radius: 4px; margin-left: 5px; }
        .stats-bar { padding: 10px 15px; font-size: 13px; color: #666; background: #f9f9f9; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; }
        
        .filters { display: flex; overflow-x: auto; padding: 10px 15px; gap: 10px; scrollbar-width: none; }
        .filter-btn { background: #f0f0f0; border: none; padding: 8px 18px; border-radius: 20px; white-space: nowrap; font-size: 14px; cursor: pointer; }
        .filter-btn.active { background: #000; color: #fff; }

        /* স্লাইডার */
        .carousel-item img { height: 180px; object-fit: cover; border-radius: 15px; }
        .carousel-caption { background: rgba(0,0,0,0.5); border-radius: 10px; padding: 5px; }

        .search-area { padding: 10px 15px; }
        .search-box { width: 100%; padding: 12px 25px; border-radius: 30px; border: 2px solid #5d259e; outline: none; font-size: 15px; }

        /* গ্রিড (২টি করে) */
        .movie-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; padding: 10px; }
        .movie-card { border-radius: 15px; overflow: hidden; border: 2px solid #ffcc00; position: relative; }
        .movie-card img { width: 100%; height: 230px; object-fit: cover; }
        
        /* ব্যাজসমূহ */
        .badge-cat { position: absolute; top: 8px; left: 8px; background: rgba(0,0,0,0.7); color: #fff; font-size: 10px; padding: 3px 7px; border-radius: 5px; }
        .badge-quality { position: absolute; top: 8px; right: 8px; background: red; color: #fff; font-size: 10px; padding: 3px 7px; border-radius: 5px; font-weight: bold; }
        .badge-ep { position: absolute; bottom: 50px; right: 8px; background: #5d259e; color: #fff; font-size: 10px; padding: 3px 7px; border-radius: 5px; }
        
        .m-name { padding: 10px; font-weight: bold; font-size: 14px; color: #333; text-align: center; min-height: 45px; display: flex; align-items: center; justify-content: center; }
        
        .pagination { justify-content: center; margin-top: 20px; gap: 5px; }
        .page-link { border-radius: 50% !important; color: #000; border: 1px solid #eee; width: 35px; height: 35px; display: flex; align-items: center; justify-content: center; }
        .page-item.active .page-link { background: #000; border-color: #000; }
    </style>
</head>
<body>
    <div class="header">
        <div class="logo">Moviee <span>BD</span></div>
        <div style="width:35px;height:35px;background:#eee;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:12px">YA</div>
    </div>
    
    <div class="stats-bar">
        <span>🎬 Movies: {{ total_m }}</span>
        <span>📺 Series: {{ total_s }}</span>
    </div>

    <!-- টপ ভিউ স্লাইডার -->
    <div class="container mt-2">
        <div id="topSlider" class="carousel slide" data-bs-ride="carousel">
            <div class="carousel-inner">
                {% for t in top_items %}
                <div class="carousel-item {% if loop.first %}active{% endif %}">
                    <a href="/view/{{ t._id }}"><img src="{{ t.poster }}" class="d-block w-100"></a>
                    <div class="carousel-caption"><h6>{{ t.name }}</h6></div>
                </div>
                {% endfor %}
            </div>
        </div>
    </div>

    <div class="filters">
        <button class="filter-btn active" onclick="filterCat('all', this)">All</button>
        {% set cats = [] %}
        {% for i in all_cats_items %}{% if i.cat and i.cat not in cats %}{% set _ = cats.append(i.cat) %}{% endif %}{% endfor %}
        {% for c in cats %}<button class="filter-btn" onclick="filterCat('{{ c }}', this)">{{ c }}</button>{% endfor %}
    </div>

    <div class="search-area">
        <input type="text" class="search-box" placeholder="সার্চ করুন..." onkeyup="searchMe(this.value)">
    </div>

    <div class="movie-grid" id="movieList">
        {% for i in items %}
        <div class="movie-item" data-name="{{ i.name | lower }}" data-cat="{{ i.cat }}">
            <a href="/view/{{ i._id }}" class="text-decoration-none">
                <div class="movie-card" style="border-color: {{ ['#ff0000','#00ff00','#0000ff','#ffcc00','#5d259e'] | random }}">
                    <img src="{{ i.poster }}" loading="lazy">
                    <div class="badge-cat">{{ i.cat }}</div>
                    {% if i.type == 'movie' %}
                        <div class="badge-quality">{{ i.quality }}</div>
                    {% else %}
                        <div class="badge-ep">{{ i.episodes | length }} EP</div>
                    {% endif %}
                    <div class="m-name">{{ i.name }}</div>
                </div>
            </a>
        </div>
        {% endfor %}
    </div>

    <!-- পেজিনেশন -->
    <nav>
      <ul class="pagination">
        {% if current_page > 1 %}
        <li class="page-item"><a class="page-link" href="/?page={{ current_page - 1 }}">Prev</a></li>
        {% endif %}
        {% for p in range(1, total_pages + 1) %}
        <li class="page-item {% if p == current_page %}active{% endif %}">
            <a class="page-link" href="/?page={{ p }}">{{ p }}</a>
        </li>
        {% endfor %}
        {% if current_page < total_pages %}
        <li class="page-item"><a class="page-link" href="/?page={{ current_page + 1 }}">Next</a></li>
        {% endif %}
      </ul>
    </nav>

    <script>
        function filterCat(c, b) {
            document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
            b.classList.add('active');
            document.querySelectorAll('.movie-item').forEach(m => {
                if(c === 'all' || m.dataset.cat === c) m.style.display = 'block';
                else m.style.display = 'none';
            });
        }
        function searchMe(v) {
            v = v.toLowerCase();
            document.querySelectorAll('.movie-item').forEach(m => {
                if(m.dataset.name.includes(v)) m.style.display = 'block';
                else m.style.display = 'none';
            });
        }
    </script>
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
        body { background: #000; color: #fff; text-align: center; padding: 20px; }
        .poster { width: 100%; max-width: 350px; border-radius: 20px; border: 4px solid #00ff00; box-shadow: 0 0 20px #00ff00; }
        .btn-step { background: linear-gradient(45deg, #5d259e, #a020f0); color: #fff; padding: 18px; border-radius: 12px; margin: 15px auto; max-width: 400px; font-weight: bold; cursor: pointer; border: none; width: 100%; font-size: 16px; display: block; text-decoration: none; }
    </style>
</head>
<body>
    <img src="{{ item.poster }}" class="poster">
    <h3 class="my-3">{{ item.name }}</h3>

    <div id="unlock-section">
        {% if item.type == 'movie' %}{% for l in item.links %}
            <div id="box-{{ l.uid }}">
                <button id="btn-{{ l.uid }}" class="btn-step" onclick="doStep('{{ l.uid }}')">🔓 UNLOCK FILE (Step 1/{{ conf.stp }})</button>
                <div id="get-{{ l.uid }}" style="display:none;"><a href="https://t.me/{{ bot_u }}?start={{ l.uid }}" class="btn btn-primary btn-lg w-100 p-3">📥 GET MOVIE ({{ l.q }})</a></div>
            </div>
        {% endfor %}{% else %}{% for e in item.episodes %}
            <div id="box-{{ e.uid }}">
                <button id="btn-{{ e.uid }}" class="btn-step" onclick="doStep('{{ e.uid }}')">🔓 UNLOCK {{ e.ep }} (Step 1/{{ conf.stp }})</button>
                <div id="get-{{ e.uid }}" style="display:none;"><a href="https://t.me/{{ bot_u }}?start={{ e.uid }}" class="btn btn-primary btn-lg w-100 p-3">📥 GET {{ e.ep }}</a></div>
            </div>
        {% endfor %}{% endif %}
    </div>

    <script>
        const autolock = {{ conf.autolock }};
        const maxSteps = {{ conf.stp }};

        function setLocal(key, val, minutes) {
            const now = new Date();
            const item = { value: val, expiry: now.getTime() + (minutes * 60 * 1000) };
            localStorage.setItem(key, JSON.stringify(item));
        }

        function getLocal(key) {
            const itemStr = localStorage.getItem(key);
            if (!itemStr) return null;
            const item = JSON.parse(itemStr);
            const now = new Date();
            if (now.getTime() > item.expiry) {
                localStorage.removeItem(key);
                return null;
            }
            return item.value;
        }

        function checkPersistence() {
            document.querySelectorAll('[id^="btn-"]').forEach(btn => {
                const uid = btn.id.replace('btn-', '');
                if (getLocal('unlocked_' + uid)) {
                    btn.style.display = 'none';
                    document.getElementById('get-' + uid).style.display = 'block';
                }
            });
        }

        let currentSteps = {};
        function doStep(uid) {
            if (!currentSteps[uid]) currentSteps[uid] = 1;
            if (typeof show_{{ conf.mtg }} === 'function') { show_{{ conf.mtg }}(); }
            
            if (currentSteps[uid] >= maxSteps) {
                setLocal('unlocked_' + uid, 'true', autolock);
                document.getElementById('btn-' + uid).style.display = 'none';
                document.getElementById('get-' + uid).style.display = 'block';
            } else {
                currentSteps[uid]++;
                document.getElementById('btn-' + uid).innerText = `🔓 UNLOCK (Step ${currentSteps[uid]}/${maxSteps})`;
            }
        }
        window.onload = checkPersistence;
    </script>
    <br><a href="/" class="btn btn-dark">Back to Home</a>
</body>
</html>
"""

# --- রুট লজিক ---
@app.get("/", response_class=HTMLResponse)
async def home(request: Request, page: int = 1, user_id: str = None):
    conf = await get_config()
    if user_id:
        response = RedirectResponse(url="/")
        response.set_cookie(key="tg_user_id", value=user_id, max_age=31536000)
        return response
    
    per_page = conf.get('per', 10)
    
    # স্লাইডার: টপ ৫ ভিউ
    top_items = await content_col.find().sort("views", -1).limit(5).to_list(5)
    
    # কাউন্ট
    total_m = await content_col.count_documents({"type": "movie"})
    total_s = await content_col.count_documents({"type": "series"})
    total_all = await content_col.count_documents({})
    
    # পেজিনেশন
    total_pages = (total_all + per_page - 1) // per_page
    items = await content_col.find().sort("date", -1).skip((page - 1) * per_page).limit(per_page).to_list(per_page)
    
    all_cats_items = await content_col.find({}, {"cat": 1}).to_list(500)
    
    return Template(INDEX_HTML).render(
        items=items, conf=conf, top_items=top_items, 
        total_m=total_m, total_s=total_s,
        current_page=page, total_pages=total_pages,
        all_cats_items=all_cats_items
    )

@app.get("/view/{id}", response_class=HTMLResponse)
async def detail(id: str):
    await content_col.update_one({"_id": ObjectId(id)}, {"$inc": {"views": 1}})
    item = await content_col.find_one({"_id": ObjectId(id)})
    conf = await get_config()
    if not item: return "Not Found"
    return Template(DETAIL_HTML).render(item=item, conf=conf, bot_u=BOT_USERNAME)

# ==========================================
# ৪. মেইন এন্ট্রি পয়েন্ট
# ==========================================
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, log_level="info", workers=1)
