import os
import asyncio
import logging
import uuid
import re
from datetime import datetime, timedelta
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
from telegraph import upload_file
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

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
app = FastAPI()

# --- এফএসএম (স্টেট ম্যানেজমেন্ট) ---
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
            "logo": "https://telegra.ph/file/0f2e825a07530467776d5.jpg", 
            "autodlt": 0, "autolock": 10, "per": 10, "mtg": "10351894", "stp": 1
        }
        await settings_col.insert_one(conf)
    return conf

async def process_photo(message: types.Message):
    try:
        photo = message.photo[-1]
        file_path = f"img_{photo.file_id}.jpg"
        await bot.download(photo, destination=file_path)
        response = upload_file(file_path)
        if os.path.exists(file_path): os.remove(file_path)
        return f"https://telegra.ph{response[0]}"
    except:
        return "https://telegra.ph/file/0f2e825a07530467776d5.jpg"

async def auto_delete_task(chat_id, message_id, minutes):
    if minutes > 0:
        await asyncio.sleep(minutes * 60)
        try: await bot.delete_message(chat_id, message_id)
        except: pass

# ==========================================
# ২. ১৮টি কমান্ড হ্যান্ডলারস (সম্পূর্ণ)
# ==========================================

# ১. /start - ইউজার আইডি সেভ ও ফাইল রিকভার
@dp.message(Command("start"))
async def cmd_start(message: types.Message, command: CommandObject):
    user_data = {"id": message.from_user.id, "name": message.from_user.full_name, "username": message.from_user.username, "date": datetime.now()}
    await user_col.update_one({"id": message.from_user.id}, {"$set": user_data}, upsert=True)

    if command.args:
        f_data = await file_store.find_one({"unique_id": command.args})
        if f_data:
            await bot.copy_message(chat_id=message.chat.id, from_chat_id=OWNER_ID, message_id=f_data['msg_id'], caption=f"🎬 মুভি: {f_data['name']}\n📢 চ্যানেল: {PUBLIC_CHANNEL}")
            return

    conf = await get_config()
    login_url = f"{APP_URL}/?user_id={message.from_user.id}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Watch Now (Premium Login)", url=login_url)],
        [InlineKeyboardButton(text="📥 Movie Request", callback_data="req"), InlineKeyboardButton(text="🚀 Share Bot", switch_inline_query="")],
        [InlineKeyboardButton(text="📢 Main Channel", url=f"https://t.me/{PUBLIC_CHANNEL.replace('@','')}")],
        [InlineKeyboardButton(text="🔗 All Channels", url="https://t.me/all_channels")]
    ])
    await message.answer_photo(photo=conf['logo'], caption=f"Hello {message.from_user.first_name}!\n\nWelcome to Moviee BD. Click the button below to explore! ❤️🍿", reply_markup=kb)

# ২. /movie - মুভি ফাইল স্টোর
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
    url = await process_photo(m); await state.update_data(poster=url)
    await m.answer("⚙️ কোয়ালিটি দিন (যেমন: 720p) অথবা শেষ করতে Done দিন:", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Done")]], resize_keyboard=True))
    await state.set_state(MovieState.quality)

@dp.message(MovieState.quality)
async def m_quality(m: types.Message, state: FSMContext):
    if m.text == "Done":
        data = await state.get_data()
        if not data.get('links'): return await m.answer("কোন ফাইল এড করেননি!")
        await content_col.insert_one({"type": "movie", **data, "date": datetime.now()})
        conf = await get_config()
        cap = f"🎬 মুভি: {data['name']}\n📢 চ্যানেল: {PUBLIC_CHANNEL}"
        post = await bot.send_photo(chat_id=PUBLIC_CHANNEL, photo=data['poster'], caption=cap)
        if int(conf['autodlt']) > 0: asyncio.create_task(auto_delete_task(PUBLIC_CHANNEL, post.message_id, int(conf['autodlt'])))
        await m.answer(f"✅ মুভি আপলোড সফল: {data['name']}", reply_markup=types.ReplyKeyboardRemove()); await state.clear()
    else:
        await state.update_data(cq=m.text); await m.answer(f"📁 {m.text} এর ভিডিও ফাইলটি পাঠান:"); await state.set_state(MovieState.file)

@dp.message(MovieState.file, F.video | F.document)
async def m_file_store(m: types.Message, state: FSMContext):
    data = await state.get_data(); uid = str(uuid.uuid4())[:8]
    await file_store.insert_one({"unique_id": uid, "msg_id": m.message_id, "name": data['name']})
    links = data.get('links', [])
    links.append({"q": data['cq'], "uid": uid}); await state.update_data(links=links)
    await m.answer(f"✅ {data['cq']} সেভ হয়েছে। পরের কোয়ালিটি দিন বা Done লিখুন।"); await state.set_state(MovieState.quality)

# ৩. /series - সিরিজ আপলোড
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
    await m.answer("📁 ১ম এপিসোড ফাইল পাঠান (শেষ হলে Done লিখুন):", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Done")]], resize_keyboard=True))
    await state.set_state(SeriesState.files)

@dp.message(SeriesState.files)
async def s_files_store(m: types.Message, state: FSMContext):
    if m.text == "Done":
        data = await state.get_data()
        if not data.get('episodes'): return await m.answer("কোন এপিসোড এড করেননি!")
        await content_col.insert_one({"type": "series", **data, "date": datetime.now()})
        conf = await get_config()
        post_cap = f"📺 ড্রামা: {data['name']}\n📁 এপিসোড সংখ্যা: {len(data['episodes'])}\n📢 {PUBLIC_CHANNEL}"
        post = await bot.send_photo(chat_id=PUBLIC_CHANNEL, photo=data['poster'], caption=post_cap)
        if int(conf['autodlt']) > 0: asyncio.create_task(auto_delete_task(PUBLIC_CHANNEL, post.message_id, int(conf['autodlt'])))
        await m.answer(f"✅ ড্রামা আপলোড সফল: {data['name']}", reply_markup=types.ReplyKeyboardRemove()); await state.clear()
    elif m.video or m.document:
        data = await state.get_data(); uid = str(uuid.uuid4())[:8]
        ep_n = f"Episode {len(data['episodes'])+1:02d}"
        await file_store.insert_one({"unique_id": uid, "msg_id": m.message_id, "name": f"{data['name']} {ep_n}"})
        eps = data.get('episodes', [])
        eps.append({"ep": ep_n, "uid": uid}); await state.update_data(episodes=eps)
        await m.answer(f"✅ {ep_n} সেভ হয়েছে। পরের ফাইল দিন বা Done লিখুন।")

# ৪-১৮. সেটিংস এবং ম্যানেজমেন্ট কমান্ডস
@dp.message(Command("logo"))
async def set_logo(m: types.Message):
    if m.from_user.id == OWNER_ID:
        try: link = m.text.split()[1]; await settings_col.update_one({"id": "config"}, {"$set": {"logo": link}}, upsert=True); await m.answer("✅ লোগো আপডেট।")
        except: await m.answer("/logo [link]")

@dp.message(Command("autodlt"))
async def set_autodlt(m: types.Message):
    if m.from_user.id == OWNER_ID:
        try: v = int(m.text.split()[1]); await settings_col.update_one({"id": "config"}, {"$set": {"autodlt": v}}, upsert=True); await m.answer(f"✅ অটো ডিলিট {v} মিনিট।")
        except: pass

@dp.message(Command("autolock"))
async def set_autolock(m: types.Message):
    if m.from_user.id == OWNER_ID:
        try: v = int(m.text.split()[1]); await settings_col.update_one({"id": "config"}, {"$set": {"autolock": v}}, upsert=True); await m.answer(f"✅ অটো লক {v} মিনিট।")
        except: pass

@dp.message(Command("setname"))
async def set_name(m: types.Message):
    if m.from_user.id == OWNER_ID:
        name = m.text.replace("/setname ",""); await settings_col.update_one({"id": "config"}, {"$set": {"site_name": name}}, upsert=True); await m.answer("✅ সাইট নাম সেট।")

@dp.message(Command("setnotice"))
async def set_notice(m: types.Message):
    if m.from_user.id == OWNER_ID:
        note = m.text.replace("/setnotice ",""); await settings_col.update_one({"id": "config"}, {"$set": {"note": note}}, upsert=True); await m.answer("✅ নোটিশ সেট।")

@dp.message(Command("setmtg"))
async def set_mtg(m: types.Message):
    if m.from_user.id == OWNER_ID:
        try: val = m.text.split()[1]; await settings_col.update_one({"id": "config"}, {"$set": {"mtg": val}}, upsert=True); await m.answer(f"✅ Monetag ID: {val}")
        except: pass

@dp.message(Command("seemtg"))
async def see_mtg(m: types.Message):
    conf = await get_config(); await m.answer(f"📢 বর্তমান Monetag ID: `{conf.get('mtg')}`", parse_mode="Markdown")

@dp.message(Command("setstp"))
async def set_stp(m: types.Message):
    if m.from_user.id == OWNER_ID:
        try: v = int(m.text.split()[1]); await settings_col.update_one({"id": "config"}, {"$set": {"stp": v}}, upsert=True); await m.answer(f"✅ এড স্টেপ: {v}")
        except: pass

@dp.message(Command("dm"))
async def del_m(m: types.Message):
    if m.from_user.id == OWNER_ID:
        name = m.text.replace("/dm ",""); await content_col.delete_one({"name": name, "type": "movie"}); await m.answer(f"🗑 {name} ডিলিট।")

@dp.message(Command("ds"))
async def del_s(m: types.Message):
    if m.from_user.id == OWNER_ID:
        name = m.text.replace("/ds ",""); await content_col.delete_one({"name": name, "type": "series"}); await m.answer(f"🗑 {name} ডিলিট।")

@dp.message(Command("dlall"))
async def del_all(m: types.Message):
    if m.from_user.id == OWNER_ID:
        await content_col.delete_many({}); await file_store.delete_many({}); await m.answer("💥 অল ডিলিট সফল!")

@dp.message(Command("stats"))
async def get_stats(m: types.Message):
    if m.from_user.id == OWNER_ID:
        c = await content_col.count_documents({}); u = await user_col.count_documents({}); await m.answer(f"📊 স্ট্যাটস:\nপোস্ট: {c}\nইউজার: {u}")

@dp.message(Command("perpost"))
async def set_per(m: types.Message):
    if m.from_user.id == OWNER_ID:
        try: v = int(m.text.split()[1]); await settings_col.update_one({"id": "config"}, {"$set": {"per": v}}, upsert=True); await m.answer(f"✅ পেজ লিমিট: {v}")
        except: pass

@dp.message(Command("notifi"))
async def set_notif(m: types.Message):
    if m.from_user.id == OWNER_ID:
        try: ch = m.text.split()[1]; await notif_col.update_one({"id": ch}, {"$set": {"id": ch}}, upsert=True); await m.answer("✅ চ্যানেল যুক্ত।")
        except: pass

@dp.callback_query(F.data == "req")
async def req_cb(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.answer("📝 মুভির নাম লিখে পাঠান:"); await state.set_state(ReqState.movie_name); await cb.answer()

@dp.message(ReqState.movie_name)
async def req_process(m: types.Message, state: FSMContext):
    await bot.send_message(chat_id=OWNER_ID, text=f"🚨 **নতুন রিকোয়েস্ট!**\n👤: {m.from_user.full_name}\n🎬: **{m.text}**", parse_mode="Markdown")
    await m.answer("✅ রিকোয়েস্ট পাঠানো হয়েছে!"); await state.clear()

# ==========================================
# ৩. প্রিমিয়াম ডিজাইন ও লগিন সিস্টেম (Web)
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
        body { background: #050505; color: #fff; font-family: 'Segoe UI', sans-serif; }
        .notice { background: linear-gradient(90deg, #ff0055, #ffcc00); padding: 8px; text-align: center; font-weight: bold; position: sticky; top: 0; z-index: 1000; color: #000; }
        .user-panel { background: #111; padding: 12px; margin: 10px; border-radius: 12px; border: 1px solid #333; font-size: 14px; color: #00ffcc; display: flex; justify-content: space-between; }
        .movie-card { position: relative; border-radius: 15px; overflow: hidden; background: #111; border: 1px solid #222; transition: 0.3s; margin-bottom: 15px; }
        .movie-card:hover { transform: translateY(-5px); border-color: #ff0055; }
        .movie-card img { width: 100%; height: 260px; object-fit: cover; }
        .v-badge { position: absolute; top: 10px; right: 10px; background: rgba(0,0,0,0.8); color: #00ffcc; padding: 3px 8px; border-radius: 6px; font-size: 11px; }
        .m-name { padding: 10px; text-align: center; font-size: 13px; font-weight: bold; }
        .swiper { width: 100%; height: 230px; border-radius: 15px; margin: 15px 0; box-shadow: 0 4px 15px rgba(0,0,0,0.5); }
        .swiper-slide img { width: 100%; height: 100%; object-fit: cover; }
        .pagination .btn { background: #111; color: #fff; border: 1px solid #333; margin: 0 5px; }
        .pagination .active { background: #ff0055; border: none; }
    </style>
</head>
<body>
    <div class="notice">{{ conf.note }}</div>
    
    <div class="container py-2">
        <div class="user-panel">
            <span>🎬 <b>{{ conf.site_name }}</b></span>
            {% if user %}<span>👤 {{ user.name }}</span>{% else %}<span class="text-danger">Guest Mode</span>{% endif %}
        </div>

        <div class="swiper mySwiper"><div class="swiper-wrapper">
            {% for s in slider %}<div class="swiper-slide"><a href="/view/{{ s._id }}"><img src="{{ s.poster }}"></a></div>{% endfor %}
        </div></div>

        <div class="row row-cols-2 row-cols-md-4 g-2">
            {% for i in items %}
            <div class="col">
                <a href="/view/{{ i._id }}" class="text-decoration-none text-white">
                    <div class="movie-card">
                        <span class="v-badge">👁 {{ i.views }}</span>
                        <img src="{{ i.poster }}" loading="lazy">
                        <div class="m-name">{{ i.name }}</div>
                    </div>
                </a>
            </div>
            {% endfor %}
        </div>

        <div class="d-flex justify-content-center mt-5 pagination">
            {% if page > 1 %}<a href="?page={{ page-1 }}" class="btn">Prev</a>{% endif %}
            <button class="btn active">{{ page }}</button>
            <a href="?page={{ page+1 }}" class="btn">Next</a>
        </div>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/swiper@10/swiper-bundle.min.js"></script>
    <script>new Swiper(".mySwiper", { autoplay: {delay: 3000}, loop: true });</script>
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
    <!-- Monetag SDK -->
    <script src='//libtl.com/sdk.js' data-zone='{{ conf.mtg }}' data-sdk='show_{{ conf.mtg }}'></script>
    <style>
        body { background: #000; color: #fff; text-align: center; padding-top: 20px; font-family: sans-serif; }
        .poster { width: 90%; max-width: 380px; border-radius: 20px; box-shadow: 0 0 35px rgba(255,0,85,0.4); border: 2px solid #ff0055; margin-bottom: 20px; }
        .p-box { background: #111; padding: 20px; border-radius: 25px; margin: 15px; border: 1px solid #333; }
        .d-btn { display: block; background: #1a1a1a; color: #00ffcc; padding: 18px; margin-bottom: 12px; border-radius: 15px; text-decoration: none; font-weight: bold; border: 1px solid #444; }
        .unlock-btn { display: block; background: linear-gradient(45deg, #ff0055, #ffcc00); color: #000; padding: 18px; border-radius: 15px; font-weight: bold; cursor: pointer; text-transform: uppercase; margin-bottom: 12px; }
    </style>
</head>
<body>
    <img src="{{ item.poster }}" class="poster">
    <h3>{{ item.name }}</h3>
    
    <div class="p-box">
        {% if item.type == 'movie' %}
            {% for l in item.links %}
                <div id="lock-{{ l.uid }}" class="unlock-btn" onclick="triggerAd('{{ l.uid }}')">🔐 Unlock {{ l.q }} (Wait for Ad)</div>
                <div id="box-{{ l.uid }}" style="display:none;">
                    <a href="https://t.me/{{ bot_u }}?start={{ l.uid }}" class="d-btn">📥 Get Movie ({{ l.q }})</a>
                </div>
            {% endfor %}
        {% else %}
            {% for e in item.episodes %}
                <div id="lock-{{ e.uid }}" class="unlock-btn" onclick="triggerAd('{{ e.uid }}')">🔐 Unlock {{ e.ep }}</div>
                <div id="box-{{ e.uid }}" style="display:none;">
                    <a href="https://t.me/{{ bot_u }}?start={{ e.uid }}" class="d-btn">🎬 Get {{ e.ep }}</a>
                </div>
            {% endfor %}
        {% endif %}
    </div>
    
    <script>
        function triggerAd(uid) {
            // Monetag ad auto-triggered
            if (typeof show_{{ conf.mtg }} === 'function') {
                show_{{ conf.mtg }}();
            }
            // Reveal button
            document.getElementById('lock-' + uid).style.display = 'none';
            document.getElementById('box-' + uid).style.display = 'block';
        }
    </script>
    <a href="/" class="btn btn-outline-danger mt-4 mb-5 px-5">Back to Home</a>
</body>
</html>
"""

# ==========================================
# ৪. মেইন সার্ভার লজিক (লগিন ফিক্সড)
# ==========================================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, user_id: str = None, page: int = 1):
    conf = await get_config()
    
    # লগিন হ্যান্ডলিং (URL এ আইডি থাকলে কুকি সেভ করবে)
    if user_id:
        response = RedirectResponse(url="/")
        response.set_cookie(key="tg_user", value=user_id, max_age=31536000) # ১ বছর
        return response
    
    # কুকি থেকে ইউজার ডাটা চেক
    saved_id = request.cookies.get("tg_user")
    user = None
    if saved_id and saved_id.isdigit():
        user = await user_col.find_one({"id": int(saved_id)})

    items = await content_col.find().sort("date", -1).skip((page-1)*conf['per']).limit(conf['per']).to_list(None)
    slider = await content_col.find().sort("views", -1).limit(5).to_list(None)
    
    return Template(INDEX_HTML).render(items=items, slider=slider, conf=conf, page=page, user=user)

@app.get("/view/{id}", response_class=HTMLResponse)
async def detail(request: Request, id: str):
    ip = request.client.host; item = await content_col.find_one({"_id": ObjectId(id)}); conf = await get_config()
    # ভিউ কাউন্ট প্রসেস
    already = await view_logs.find_one({"ip": ip, "cid": id, "date": {"$gt": datetime.now() - timedelta(hours=1)}})
    if not already:
        await content_col.update_one({"_id": ObjectId(id)}, {"$inc": {"views": 1}})
        await view_logs.insert_one({"ip": ip, "cid": id, "date": datetime.now()})
    return Template(DETAIL_HTML).render(item=item, conf=conf, bot_u=BOT_USERNAME)

# --- রান ফাংশন ---
@app.on_event("startup")
async def on_startup():
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(dp.start_polling(bot))

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=PORT)
