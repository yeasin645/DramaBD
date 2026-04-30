import asyncio
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient

# --- কনফিগারেশন (আপনার দেওয়া তথ্য অনুযায়ী) ---
TOKEN = "8655043839:AAH8Wxhd8jE8Y85XBdz8kRG2suLmqQx7mSU"
MONGO_URL = "mongodb+srv://drama:drama@cluster0.sa4kvgu.mongodb.net/?appName=Cluster0"
OWNER_ID = 7120801813
APP_URL = "https://indirect-meris-yeasinvai-95120fc6.koyeb.app"
CHANNEL_ID = "-1003309004720"
BOT_USERNAME = "dramastorkingsbot"

# --- ডাটাবেস কানেকশন ---
client = AsyncIOMotorClient(MONGO_URL)
db = client['movie_dramabd']
content_col = db['contents']    # মুভি ও সিরিজ স্টোর করার জন্য
settings_col = db['settings']  # সাইট সেটিংসের জন্য
notif_col = db['notif_channels'] # নোটিফিকেশন চ্যানেলের জন্য

# --- বটের অবজেক্ট ---
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- FSM States (ধাপে ধাপে তথ্য নেওয়ার জন্য) ---
class MovieForm(StatesGroup):
    name = State()
    poster = State()
    quality = State()
    file = State()

class SeriesForm(StatesGroup):
    name = State()
    poster = State()
    files = State()

# --- কিবোর্ডস ---
def get_main_kb():
    buttons = [
        [InlineKeyboardButton(text="🎬 Watch Now", url=APP_URL)],
        [InlineKeyboardButton(text="📥 Movie Request", callback_data="req"),
         InlineKeyboardButton(text="🚀 Share Bot", switch_inline_query="")],
        [InlineKeyboardButton(text="📢 Main Channel", url="https://t.me/movie_channel_link")],
        [InlineKeyboardButton(text="🔗 All Channels", url="https://t.me/all_channels_link")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_skip_done_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Done"), KeyboardButton(text="Skip")]],
        resize_keyboard=True
    )

def get_finish_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Finish Upload")]],
        resize_keyboard=True
    )

# --- অটো নোটিফিকেশন ফাংশন ---
async def send_broadcast(text):
    channels = await notif_col.find().to_list(length=100)
    for ch in channels:
        try:
            await bot.send_message(ch['chat_id'], text)
        except:
            pass

# --- কমান্ড হ্যান্ডলারস ---

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    photo = "https://telegra.ph/file/your_banner_image.jpg" # আপনার স্ক্রিনশটের ব্যানার ইমেজ
    text = (f"Hello {message.from_user.first_name}!\n\n"
            "Welcome to Moviee BD click the button below to explore! ❤️🍿")
    await message.answer_photo(photo=photo, caption=text, reply_markup=get_main_kb())

# --- মুভি আপলোড লজিক (/movie) ---
@dp.message(Command("movie"))
async def cmd_movie(message: types.Message, state: FSMContext):
    if message.from_user.id != OWNER_ID: return
    await message.answer("🎬 মুভির নাম দিন:")
    await state.set_state(MovieForm.name)

@dp.message(MovieForm.name)
async def process_m_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text, links=[])
    await message.answer("🖼 মুভির পোস্টার লিঙ্ক দিন:")
    await state.set_state(MovieForm.poster)

@dp.message(MovieForm.poster)
async def process_m_poster(message: types.Message, state: FSMContext):
    await state.update_data(poster=message.text)
    await message.answer("⚙️ কোয়ালিটি লিখুন (যেমন: 720p) অথবা শেষ করতে 'Done' দিন:", reply_markup=get_skip_done_kb())
    await state.set_state(MovieForm.quality)

@dp.message(MovieForm.quality)
async def process_m_quality(message: types.Message, state: FSMContext):
    if message.text == "Done":
        data = await state.get_data()
        await content_col.insert_one({"type": "movie", "title": data['name'], "poster": data['poster'], "links": data['links'], "date": datetime.now()})
        await message.answer("✅ মুভিটি সাইটে আপলোড হয়েছে!", reply_markup=types.ReplyKeyboardRemove())
        await send_broadcast(f"🎬 New Movie: {data['name']} is now available!")
        await state.clear()
    elif message.text == "Skip":
        await message.answer("কোয়ালিটি স্কিপ করা হয়েছে। সরাসরি ফাইল লিঙ্ক দিন:")
        await state.update_data(current_q="Standard")
        await state.set_state(MovieForm.file)
    else:
        await state.update_data(current_q=message.text)
        await message.answer(f"🔗 {message.text} এর জন্য ফাইল লিঙ্ক দিন:")
        await state.set_state(MovieForm.file)

@dp.message(MovieForm.file)
async def process_m_file(message: types.Message, state: FSMContext):
    data = await state.get_data()
    links = data['links']
    links.append({"quality": data['current_q'], "link": message.text})
    await state.update_data(links=links)
    await message.answer("পরবর্তী কোয়ালিটি লিখুন অথবা 'Done' বাটনে ক্লিক করুন:", reply_markup=get_skip_done_kb())
    await state.set_state(MovieForm.quality)

# --- সিরিজ আপলোড লজিক (/series) ---
@dp.message(Command("series"))
async def cmd_series(message: types.Message, state: FSMContext):
    if message.from_user.id != OWNER_ID: return
    await message.answer("📺 ওয়েব সিরিজ বা ড্রামার নাম দিন:")
    await state.set_state(SeriesForm.name)

@dp.message(SeriesForm.name)
async def process_s_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text, episodes=[])
    await message.answer("🖼 পোস্টার লিঙ্ক দিন:")
    await state.set_state(SeriesForm.poster)

@dp.message(SeriesForm.poster)
async def process_s_poster(message: types.Message, state: FSMContext):
    await state.update_data(poster=message.text)
    await message.answer("📁 এপিসোড লিঙ্কগুলো একে একে দিন। শেষ হলে 'Finish Upload' এ ক্লিক করুন:", reply_markup=get_finish_kb())
    await state.set_state(SeriesForm.files)

@dp.message(SeriesForm.files)
async def process_s_files(message: types.Message, state: FSMContext):
    if message.text == "Finish Upload":
        data = await state.get_data()
        await content_col.insert_one({"type": "series", "title": data['name'], "poster": data['poster'], "episodes": data['episodes'], "date": datetime.now()})
        await message.answer("✅ সিরিজটি সাইটে আপলোড হয়েছে!", reply_markup=types.ReplyKeyboardRemove())
        await send_broadcast(f"📺 New Drama: {data['name']} - All episodes uploaded!")
        await state.clear()
    else:
        data = await state.get_data()
        ep_num = len(data['episodes']) + 1
        new_ep = {"label": f"Episode {ep_num:02d}", "link": message.text}
        data['episodes'].append(new_ep)
        await state.update_data(episodes=data['episodes'])
        await message.answer(f"✅ {new_ep['label']} যুক্ত হয়েছে। পরবর্তী লিঙ্ক দিন বা ফিনিশ করুন।")

# --- কন্ট্রোল এবং সেটিংস কমান্ডস ---

@dp.message(Command("dm")) # Delete Movie
async def cmd_dm(message: types.Message):
    if message.from_user.id != OWNER_ID: return
    name = message.text.replace("/dm", "").strip()
    res = await content_col.delete_one({"title": name, "type": "movie"})
    await message.answer("🗑 মুভি ডিলিট হয়েছে।" if res.deleted_count else "❌ মুভি পাওয়া যায়নি।")

@dp.message(Command("ds")) # Delete Series
async def cmd_ds(message: types.Message):
    if message.from_user.id != OWNER_ID: return
    name = message.text.replace("/ds", "").strip()
    res = await content_col.delete_one({"title": name, "type": "series"})
    await message.answer("🗑 সিরিজ ডিলিট হয়েছে।" if res.deleted_count else "❌ পাওয়া যায়নি।")

@dp.message(Command("dlall"))
async def cmd_dlall(message: types.Message):
    if message.from_user.id != OWNER_ID: return
    await content_col.delete_many({})
    await message.answer("💥 সকল মুভি ও ড্রামা সিরিজ ডাটাবেস থেকে মুছে ফেলা হয়েছে!")

@dp.message(Command("setmtg"))
async def cmd_setmtg(message: types.Message):
    if message.from_user.id != OWNER_ID: return
    val = message.text.replace("/setmtg", "").strip()
    await settings_col.update_one({"id": "config"}, {"$set": {"monetag_id": val}}, upsert=True)
    await message.answer(f"✅ Monetag ID সেট হয়েছে: {val}")

@dp.message(Command("seemtg"))
async def cmd_seemtg(message: types.Message):
    if message.from_user.id != OWNER_ID: return
    config = await settings_col.find_one({"id": "config"})
    await message.answer(f"📢 বর্তমান Monetag ID: {config.get('monetag_id', 'Not Set')}")

@dp.message(Command("setstp"))
async def cmd_setstp(message: types.Message):
    if message.from_user.id != OWNER_ID: return
    val = message.text.replace("/setstp", "").strip()
    await settings_col.update_one({"id": "config"}, {"$set": {"ad_steps": val}}, upsert=True)
    await message.answer(f"✅ Ad Steps সেট হয়েছে: {val}")

@dp.message(Command("setnotice"))
async def cmd_setnotice(message: types.Message):
    if message.from_user.id != OWNER_ID: return
    val = message.text.replace("/setnotice", "").strip()
    await settings_col.update_one({"id": "config"}, {"$set": {"notice": val}}, upsert=True)
    await message.answer("✅ সাইট নোটিশ আপডেট হয়েছে।")

@dp.message(Command("setname"))
async def cmd_setname(message: types.Message):
    if message.from_user.id != OWNER_ID: return
    val = message.text.replace("/setname", "").strip()
    await settings_col.update_one({"id": "config"}, {"$set": {"site_name": val}}, upsert=True)
    await message.answer(f"✅ সাইটের নাম রাখা হয়েছে: {val}")

@dp.message(Command("perpost"))
async def cmd_perpost(message: types.Message):
    if message.from_user.id != OWNER_ID: return
    val = message.text.replace("/perpost", "").strip()
    await settings_col.update_one({"id": "config"}, {"$set": {"per_page": int(val)}}, upsert=True)
    await message.answer(f"✅ এখন থেকে প্রতি পেজে {val} টি পোস্ট থাকবে।")

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    if message.from_user.id != OWNER_ID: return
    m_count = await content_col.count_documents({"type": "movie"})
    s_count = await content_col.count_documents({"type": "series"})
    await message.answer(f"📊 পরিসংখ্যান:\n🎬 মুভি: {m_count}\n📺 ড্রামা সিরিজ: {s_count}")

@dp.message(Command("notifi"))
async def cmd_notifi(message: types.Message):
    if message.from_user.id != OWNER_ID: return
    parts = message.text.split()
    if len(parts) < 2: return await message.answer("ব্যবহার: `/notifi -100xxx` (অ্যাড) অথবা `/notifi del -100xxx` (ডিলিট)")
    
    if parts[1] == "del":
        await notif_col.delete_one({"chat_id": parts[2]})
        await message.answer("🗑 চ্যানেল রিমুভ করা হয়েছে।")
    else:
        await notif_col.update_one({"chat_id": parts[1]}, {"$set": {"chat_id": parts[1]}}, upsert=True)
        await message.answer("✅ চ্যানেল নোটিফিকেশন লিস্টে যুক্ত হয়েছে।")

# --- বট স্টার্ট ---
async def main():
    logging.basicConfig(level=logging.INFO)
    print("🚀 বট রান হচ্ছে...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
