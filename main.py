import os, threading, io, time, json
from flask import Flask, render_template_string, send_file, request, jsonify
from telebot import TeleBot, types
from pymongo import MongoClient, DESCENDING
from bson.objectid import ObjectId
import gridfs
from datetime import datetime

# ================= কনফিগারেশন =================
BOT_TOKEN = "8655043839:AAGMxkYoZXR-nUzlcapZZfVwci09Z6x0-UE"
MONGO_URI = "mongodb+srv://drama:drama@cluster0.sa4kvgu.mongodb.net/?appName=Cluster0"
WEBAPP_URL = "https://indirect-meris-yeasinvai-95120fc6.koyeb.app" 
FILE_CHANNEL_ID = -1003985353441 
ADMIN_IDS = [7120801813]

# ডাটাবেস কানেকশন
client = MongoClient(MONGO_URI)
db = client['mini_app_db']
movies_col, users_col, settings_col = db['movies'], db['users'], db['settings']
tasks_col, premium_col, fs = db['tasks'], db['premium_plans'], gridfs.GridFS(db)
logs_col = db['task_logs'] # টাস্ক লিমিট চেক করার জন্য

bot = TeleBot(BOT_TOKEN)
app = Flask(__name__)
user_states = {}

# ================= ইউটিলিটি ফাংশনস =================
def is_admin(m):
    return m.from_user.id in ADMIN_IDS

def get_setting(key, default):
    s = settings_col.find_one({"key": key})
    return s['value'] if s else default

def get_user(tg_id, name="User"):
    user = users_col.find_one({"tg_id": str(tg_id)})
    if not user:
        user = {"tg_id": str(tg_id), "name": name, "balance": 0, "premium_until": 0}
        users_col.insert_one(user)
    return user

def create_btn(key, default_text, default_val):
    data = get_setting(key, {"text": default_text, "val": default_val})
    if str(data['val']).startswith("http"):
        return types.InlineKeyboardButton(data['text'], url=data['val'])
    return types.InlineKeyboardButton(data['text'], callback_data=key)

# ================= টেলিグラム বট কমান্ডস =================

@bot.message_handler(commands=['start'])
def start_cmd(message):
    if message.text.startswith('/start getfile_'):
        msg_id = message.text.split('getfile_')[1]
        try: bot.copy_message(message.chat.id, FILE_CHANNEL_ID, int(msg_id))
        except: bot.send_message(message.chat.id, "❌ ফাইলটি পাওয়া যায়নি!")
        return

    get_user(message.from_user.id, message.from_user.full_name)
    site_name = get_setting("site_name", "Moviee BD")
    banner = get_setting("start_poster", "https://via.placeholder.com/800x450")

    markup = types.InlineKeyboardMarkup(row_width=2)
    # WebApp URL properly formatted
    markup.add(types.InlineKeyboardButton("🎬 Watch Now", web_app=types.WebAppInfo(WEBAPP_URL)))
    markup.add(create_btn("btn1", "📩 Movie Request", "Request..."), create_btn("btn2", "🔗 My Referral Link", "ref_logic"))
    markup.add(create_btn("btn3", "❓ Help & Tutorial", "Tutorial..."), create_btn("btn4", "🔗 All Channels", "https://t.me/your_link"))

    try:
        bot.send_photo(message.chat.id, banner, caption=f"Hello {message.from_user.first_name}!\nWelcome to {site_name} ❤️🍿", reply_markup=markup)
    except:
        bot.send_message(message.chat.id, f"Welcome to {site_name} ❤️🍿\n(Banner Error)", reply_markup=markup)

@bot.message_handler(commands=['sitename', 'notice', 'ads', 'step', 'lock', 'poster', 'add', 'adtask', 'monitask', 'addpr', 'btn1', 'btn2', 'btn3', 'btn4', 'dltask'])
def admin_router(message):
    if not is_admin(message):
        bot.reply_to(message, "🚫 আপনি এই বটের অ্যাডমিন নন!")
        return

    cmd = message.text.split()[0][1:]
    
    if cmd == 'add':
        user_states[message.chat.id] = {'step': 'm_name', 'files': []}
        bot.send_message(message.chat.id, "🎬 মুভির নাম লিখুন:")
    elif cmd in ['sitename', 'notice', 'ads', 'step', 'lock', 'poster']:
        user_states[message.chat.id] = {'step': f'up_{cmd}'}
        bot.send_message(message.chat.id, f"📝 নতুন {cmd} এর তথ্য দিন:")
    elif cmd in ['btn1', 'btn2', 'btn3', 'btn4']:
        try:
            raw = message.text.split(None, 1)[1]
            text, val = map(str.strip, raw.split('|'))
            settings_col.update_one({"key": cmd}, {"$set": {"value": {"text": text, "val": val}}}, upsert=True)
            bot.reply_to(message, "✅ বাটন আপডেট হয়েছে!")
        except: bot.reply_to(message, "ব্যবহার: `/btn1 নাম | লিঙ্ক বা টেক্সট`")
    elif cmd == 'adtask':
        try:
            _, link, point, limit = message.text.split()
            tasks_col.insert_one({"type": "link", "url": link, "point": int(point), "limit": int(limit)})
            bot.send_message(message.chat.id, "✅ লিঙ্ক টাস্ক সেভ হয়েছে!")
        except: bot.send_message(message.chat.id, "ব্যবহার: `/adtask লিঙ্ক পয়েন্ট লিমিট`")
    elif cmd == 'monitask':
        try:
            _, zone, point, limit = message.text.split()
            tasks_col.insert_one({"type": "monet", "zone_id": zone, "point": int(point), "limit": int(limit)})
            bot.send_message(message.chat.id, "✅ মনিটেগ টাস্ক সেভ হয়েছে!")
        except: bot.send_message(message.chat.id, "ব্যবহার: `/monitask জোনআইডি পয়েন্ট লিমিট`")
    elif cmd == 'addpr':
        try:
            _, day_str, coin = message.text.split()
            days = int(day_str.replace("day", ""))
            premium_col.insert_one({"days": days, "cost": int(coin), "label": day_str})
            bot.send_message(message.chat.id, "✅ প্রিমিয়াম প্ল্যান যুক্ত হয়েছে!")
        except: bot.send_message(message.chat.id, "ব্যবহার: `/addpr 01day 30`")
    elif cmd == 'dltask':
        tasks_col.delete_many({})
        bot.send_message(message.chat.id, "🗑 সকল টাস্ক ডিলিট করা হয়েছে।")

@bot.message_handler(func=lambda m: m.chat.id in user_states, content_types=['text', 'photo', 'video', 'document'])
def state_manager(message):
    chat_id, state = message.chat.id, user_states[message.chat.id]
    step = state['step']

    if step.startswith('up_'):
        key = step.replace('up_', '')
        if key == 'poster' and message.content_type == 'photo':
            p_id = fs.put(bot.download_file(bot.get_file(message.photo[-1].file_id).file_path), filename="banner.jpg")
            settings_col.update_one({"key": "start_poster"}, {"$set": {"value": f"{WEBAPP_URL}/poster/{p_id}"}}, upsert=True)
            bot.send_message(chat_id, "✅ ব্যানার আপডেট হয়েছে!")
        else:
            val = int(message.text) if key in ['step', 'lock'] else message.text
            settings_col.update_one({"key": key}, {"$set": {"value": val}}, upsert=True)
            bot.send_message(chat_id, f"✅ {key} আপডেট হয়েছে!")
        del user_states[chat_id]

    elif step == 'm_name':
        state['name'], state['step'] = message.text, 'm_cat'
        bot.send_message(chat_id, "📂 ক্যাটাগরি লিখুন:")
    elif step == 'm_cat':
        state['category'], state['step'] = message.text, 'm_poster'
        bot.send_message(chat_id, "🖼 পোস্টার ফটো পাঠান:")
    elif step == 'm_poster' and message.content_type == 'photo':
        p_id = fs.put(bot.download_file(bot.get_file(message.photo[-1].file_id).file_path), filename="p.jpg")
        state['poster_url'], state['step'] = f"{WEBAPP_URL}/poster/{p_id}", 'm_upload'
        bot.send_message(chat_id, "📁 ফাইলগুলো দিন, শেষ হলে /done দিন:")
    elif step == 'm_upload':
        if message.content_type in ['video', 'document']:
            fwd = bot.copy_message(FILE_CHANNEL_ID, chat_id, message.message_id)
            ep_name = f"Episode {len(state['files'])+1:02d}"
            state['files'].append({"name": ep_name, "msg_id": fwd.message_id})
            bot.send_message(chat_id, f"✅ {ep_name} রিসিভ হয়েছে।")
        elif message.text == '/done':
            movies_col.insert_one({"title": state['name'], "category": state['category'], "poster": state['poster_url'], "episodes": state['files'], "views": [], "stars": 5.0, "likes": 0})
            bot.send_message(chat_id, "🚀 মুভি সেভ হয়েছে!")
            del user_states[chat_id]

@bot.callback_query_handler(func=lambda call: True)
def cb_handler(call):
    data = get_setting(call.data, None)
    if call.data == "btn2" and data and data['val'] == "ref_logic":
        bot.send_message(call.message.chat.id, f"🔗 আপনার রেফারেল লিঙ্ক: https://t.me/{bot.get_me().username}?start={call.from_user.id}")
    elif data:
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, data['val'])

# ================= ফ্লাস্ক ওয়েব অ্যাপ =================

@app.route('/poster/<file_id>')
def serve_poster(file_id):
    try: return send_file(io.BytesIO(fs.get(ObjectId(file_id)).read()), mimetype='image/jpeg')
    except: return "404", 404

@app.route('/api/user/<tg_id>')
def api_user(tg_id): 
    u = get_user(tg_id)
    return jsonify(u)

@app.route('/api/claim', methods=['POST'])
def api_claim():
    d = request.json
    tg_id, task_id = str(d['tg_id']), d['task_id']
    task = tasks_col.find_one({"_id": ObjectId(task_id)})
    
    today = datetime.now().strftime("%Y-%m-%d")
    count = logs_col.count_documents({"tg_id": tg_id, "task_id": task_id, "date": today})
    
    if count < task.get('limit', 1):
        users_col.update_one({"tg_id": tg_id}, {"$inc": {"balance": int(task['point'])}})
        logs_col.insert_one({"tg_id": tg_id, "task_id": task_id, "date": today})
        return jsonify({"status": "ok", "msg": f"Success! {task['point']} Coins Added."})
    return jsonify({"status": "fail", "msg": "Daily Limit Reached!"})

@app.route('/api/like/<m_id>', methods=['POST'])
def api_like(m_id):
    movies_col.update_one({"_id": ObjectId(m_id)}, {"$inc": {"likes": 1}})
    return jsonify({"status": "ok"})

@app.route('/api/buy_premium', methods=['POST'])
def api_buy_pr():
    d = request.json
    u, p = get_user(d['tg_id']), premium_col.find_one({"_id": ObjectId(d['plan_id'])})
    if u['balance'] >= p['cost']:
        expire = max(u['premium_until'], time.time()*1000) + (p['days']*86400000)
        users_col.update_one({"tg_id": str(d['tg_id'])}, {"$set": {"premium_until": expire}, "$inc": {"balance": -p['cost']}})
        return jsonify({"status": "ok"})
    return jsonify({"status": "fail"})

BASE_LAYOUT = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swiper@10/swiper-bundle.min.css" />
    <style>
        body { background: #0b0f19; color: white; padding-bottom: 90px; font-family: 'Inter', sans-serif; overflow-x: hidden; }
        .glass { background: rgba(30, 41, 59, 0.6); backdrop-filter: blur(12px); border: 1px solid rgba(255,255,255,0.08); }
        .nav-item { flex:1; text-align:center; font-size:11px; color:#94a3b8; text-decoration:none; transition: 0.3s; }
        .nav-item.active { color:#6366f1; transform: translateY(-3px); }
        .loader { border: 3px solid #f3f3f3; border-top: 3px solid #6366f1; border-radius: 50%; width: 20px; height: 20px; animation: spin 1s linear infinite; display: none; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    </style>
</head>
<body>
    <div id="loading-overlay" class="fixed inset-0 bg-black z-[100] flex items-center justify-center transition-opacity duration-500">
        <div class="loader" style="display:block; width:40px; height:40px;"></div>
    </div>
    <div class="bg-indigo-600/20 py-2 px-4 border-b border-white/5"><marquee class="text-[10px] font-medium">{{ notice }}</marquee></div>
    <div id="main-content" class="p-4">{{ content | safe }}</div>
    
    <div class="fixed bottom-4 left-4 right-4 glass rounded-[30px] flex py-4 px-2 z-50 shadow-2xl">
        <a href="/" class="nav-item {{'active' if page=='home'}}">🏠<br>Home</a>
        <a href="/tasks" class="nav-item {{'active' if page=='tasks'}}">📋<br>Tasks</a>
        <a href="/premium" class="nav-item {{'active' if page=='premium'}}">💎<br>Premium</a>
        <a href="/profile" class="nav-item {{'active' if page=='profile'}}">👤<br>Profile</a>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/swiper@10/swiper-bundle.min.js"></script>
    <script>
        const tg = window.Telegram.WebApp; tg.expand();
        const user = tg.initDataUnsafe.user || {id: "7120801813", first_name: "Admin", last_name: "User"};
        
        window.onload = () => { 
            document.getElementById('loading-overlay').style.opacity = '0';
            setTimeout(() => document.getElementById('loading-overlay').style.display = 'none', 500);
        };

        function showLoading() { document.getElementById('loading-overlay').style.display = 'flex'; document.getElementById('loading-overlay').style.opacity = '1'; }
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    site_name = get_setting("site_name", "Moviee BD")
    all_movies = list(movies_col.find())
    # unique IP views calculation
    for m in all_movies:
        ip = request.remote_addr
        if 'views' not in m or not isinstance(m['views'], list): m['views'] = []
        if ip not in m['views']:
            movies_col.update_one({"_id": m['_id']}, {"$push": {"views": ip}})
    
    top_movies = list(movies_col.find().sort("views", DESCENDING).limit(5))
    
    content = render_template_string("""
        <h1 class="text-2xl font-black mb-6 text-indigo-500 uppercase tracking-tighter">{{site_name}}</h1>
        
        <h2 class="text-xs font-bold mb-3 text-gray-400 flex items-center">🔥 TRENDING NOW</h2>
        <div class="swiper mb-8">
            <div class="swiper-wrapper">
                {% for m in top_movies %}
                <div class="swiper-slide rounded-3xl overflow-hidden relative glass" onclick="showLoading(); location.href='/movie/{{m._id}}'">
                    <img src="{{m.poster}}" class="w-full h-44 object-cover">
                    <div class="absolute bottom-0 p-3 bg-gradient-to-t from-black w-full">
                        <p class="text-[11px] font-bold truncate">{{m.title}}</p>
                    </div>
                </div>
                {% endfor %}
            </div>
        </div>

        <h2 class="text-xs font-bold mb-4 text-gray-400">🎬 RECENT UPLOADS</h2>
        <div class="grid grid-cols-2 gap-4">
            {% for m in movies %}
            <div class="glass rounded-[25px] overflow-hidden relative shadow-xl" onclick="showLoading(); location.href='/movie/{{m._id}}'">
                <img src="{{m.poster}}" class="w-full h-52 object-cover">
                <span class="absolute top-2 left-2 bg-indigo-600 text-[8px] font-bold px-2 py-1 rounded-lg">⭐ EP {{m.episodes|length}}</span>
                <div class="p-3">
                    <h3 class="text-[11px] font-bold truncate">{{m.title}}</h3>
                    <p class="text-[9px] text-indigo-400 font-bold uppercase mt-1">{{m.category}}</p>
                </div>
            </div>
            {% endfor %}
        </div>
        <script>new Swiper('.swiper', { slidesPerView: 'auto', spaceBetween: 15 });</script>
    """, movies=all_movies, top_movies=top_movies, site_name=site_name)
    return render_template_string(BASE_LAYOUT, content=content, page='home', notice=get_setting("notice", "Welcome"))

@app.route('/movie/<id>')
def movie_detail(id):
    movie = movies_col.find_one({"_id": ObjectId(id)})
    content = render_template_string("""
        <div class="relative">
            <img src="{{m.poster}}" class="w-full h-[450px] object-cover rounded-[40px] shadow-2xl mb-6">
            <button onclick="history.back()" class="absolute top-4 left-4 glass w-10 h-10 rounded-full flex items-center justify-center">❮</button>
        </div>
        <h1 class="text-2xl font-black mb-1 px-2">{{m.title}}</h1>
        <p class="text-indigo-400 text-[10px] font-bold mb-6 px-2 tracking-widest uppercase">{{m.category}} • ⭐ 5.0 • 👁 {{m.views|length}} Views</p>
        
        <div class="flex justify-between mb-8 glass p-4 rounded-[30px] text-[10px] text-center font-bold mx-2">
            <div class="flex-1 text-pink-500" onclick="like('{{m._id}}')">❤️<br><span id="lcnt">{{m.likes}}</span> Likes</div>
            <div class="flex-1 border-x border-white/10" onclick="alert('Comments coming soon!')">💬<br>Chat</div>
            <div class="flex-1 text-blue-400" onclick="tg.shareUrl('{{webapp_url}}')">🔗<br>Share</div>
        </div>

        <h3 class="text-xs font-bold mb-4 px-2">📺 EPISODES</h3>
        <div class="grid grid-cols-3 gap-3 px-2">
            {% for ep in m.episodes %}
            <div id="ep-{{loop.index}}" onclick="play('{{ep.msg_id}}', '{{loop.index}}')" class="glass py-5 rounded-2xl text-center border border-white/5 active:scale-95 transition">
                <span class="text-[8px] font-bold block opacity-50 mb-1" id="lab-{{loop.index}}">LOCKED</span>
                <span class="text-xs font-black">{{ep.name}}</span>
            </div>
            {% endfor %}
        </div>

        <script src='//libtl.com/sdk.js' data-zone='{{zone}}' data-sdk='show_{{zone}}'></script>
        <script>
            let steps = {{steps}}, lockMin = {{lock}}, zone = "{{zone}}";
            function like(id) { fetch('/api/like/'+id, {method:'POST'}).then(()=> {
                document.getElementById('lcnt').innerText = parseInt(document.getElementById('lcnt').innerText)+1;
            }); }

            function play(id, idx) {
                let sKey = "unl_"+id, d = JSON.parse(localStorage.getItem(sKey) || '{"s":0, "e":0}');
                if(d.e > Date.now() || window.isPremium) {
                    window.open("https://t.me/{{bot_user}}?start=getfile_"+id, "_blank");
                } else if(d.s < steps) {
                    if(typeof window['show_'+zone] === 'function') {
                        window['show_'+zone]().then(() => { d.s++; localStorage.setItem(sKey, JSON.stringify(d)); updateUI(id, idx); });
                    } else { alert("Ad Script Loading... Please wait"); }
                } else {
                    d.e = Date.now() + (lockMin*60000); localStorage.setItem(sKey, JSON.stringify(d));
                    updateUI(id, idx); alert("Successfully Unlocked for "+lockMin+" mins!");
                }
            }
            function updateUI(id, idx) {
                let d = JSON.parse(localStorage.getItem("unl_"+id) || '{"s":0, "e":0}');
                let lab = document.getElementById("lab-"+idx);
                if(d.e > Date.now() || window.isPremium) { 
                    lab.innerText = "READY"; lab.style.color="#10b981";
                } else { lab.innerText = d.s+"/"+steps+" ADS"; }
            }
            fetch('/api/user/'+user.id).then(r=>r.json()).then(u=>{ window.isPremium = u.premium_until > Date.now(); 
                {% for ep in m.episodes %} updateUI('{{ep.msg_id}}', '{{loop.index}}'); {% endfor %}
            });
        </script>
    """, m=movie, zone=get_setting("ads", "10351894"), steps=get_setting("step", 3), 
       lock=get_setting("lock", 60), bot_user=bot.get_me().username, webapp_url=WEBAPP_URL)
    return render_template_string(BASE_LAYOUT, content=content, page='home', notice="Loading...")

@app.route('/tasks')
def tasks_page():
    ts = list(tasks_col.find())
    content = render_template_string("""
        <h2 class="text-xl font-black mb-6 text-indigo-400">EARN COINS</h2>
        <script src='//libtl.com/sdk.js'></script>
        {% for t in ts %}
        <div class="glass p-5 rounded-[30px] mb-4 flex justify-between items-center border-l-4 border-indigo-500 shadow-xl">
            <div>
                <p class="font-bold text-sm">{{'Watch Video Ad' if t.type=='monet' else 'Visit Website'}}</p>
                <p class="text-[10px] text-yellow-500 font-bold mt-1">+{{t.point}} COINS (Limit: {{t.limit}})</p>
            </div>
            <button onclick="doT('{{t._id}}','{{t.type}}','{{t.url}}','{{t.zone_id}}')" class="bg-indigo-600 px-5 py-2 rounded-2xl text-[10px] font-black uppercase">Start</button>
        </div>
        {% endfor %}
        <script>
            function doT(id, ty, url, zone) {
                if(ty==='link') { window.open(url,'_blank'); setTimeout(()=>claim(id), 5000); }
                else { 
                    let fn = 'show_'+zone;
                    if(typeof window[fn] === 'function') window[fn]().then(()=>claim(id));
                    else alert("Ad script not ready");
                }
            }
            function claim(id) { 
                fetch('/api/claim',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tg_id:user.id, task_id:id})})
                .then(r=>r.json()).then(res=>alert(res.msg)); 
            }
        </script>
    """, ts=ts)
    return render_template_string(BASE_LAYOUT, content=content, page='tasks', notice="Complete tasks to get Premium")

@app.route('/premium')
def premium_page():
    plans = list(premium_col.find())
    content = render_template_string("""
        <h2 class="text-xl font-black mb-2 text-indigo-400">MEMBERSHIP</h2>
        <p class="text-[10px] text-gray-500 mb-8 uppercase tracking-widest">Get rid of all annoying ads</p>
        {% for p in plans %}
        <div class="glass p-6 rounded-[35px] mb-4 flex justify-between items-center border-r-4 border-indigo-500 shadow-2xl">
            <div><p class="text-lg font-black">{{p.label}}</p><p class="text-xs text-yellow-500 font-bold">{{p.cost}} COINS</p></div>
            <button onclick="buy('{{p._id}}')" class="bg-indigo-600 px-6 py-2 rounded-2xl text-xs font-black uppercase">Buy</button>
        </div>
        {% endfor %}
        <script>
            function buy(id) { fetch('/api/buy_premium',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tg_id:user.id, plan_id:id})})
                .then(r=>r.json()).then(res=>alert(res.status==='ok'?"Success! Premium Activated.":"Failed! Low balance.")); }
        </script>
    """, plans=plans)
    return render_template_string(BASE_LAYOUT, content=content, page='premium', notice="Premium users see no ads")

@app.route('/profile')
def profile_page():
    content = """
    <div class="text-center py-12">
        <div id="av" class="w-24 h-24 bg-gradient-to-tr from-indigo-600 to-purple-600 rounded-full mx-auto mb-5 flex items-center justify-center text-3xl font-black shadow-[0_0_40px_rgba(79,70,229,0.4)] border-4 border-white/10">?</div>
        <h2 id="un" class="text-2xl font-black mb-1">Loading...</h2>
        <p id="ui" class="text-gray-500 text-[10px] mb-10 tracking-[3px] uppercase">ID: 00000000</p>
        
        <div class="grid grid-cols-2 gap-4 px-4">
            <div class="glass p-6 rounded-[35px] shadow-xl"><p class="text-[10px] text-gray-400 uppercase font-bold mb-1">My Coins</p><p id="bl" class="text-2xl font-black text-yellow-500">0</p></div>
            <div class="glass p-6 rounded-[35px] shadow-xl"><p class="text-[10px] text-gray-400 uppercase font-bold mb-1">Status</p><p id="st" class="text-[11px] font-black text-green-500">FREE</p></div>
        </div>
        
        <button onclick="tg.close()" class="mt-12 text-gray-500 text-xs font-bold uppercase tracking-widest">Close WebApp</button>
    </div>
    <script>
        document.getElementById('un').innerText = (user.first_name || 'User') + ' ' + (user.last_name || '');
        document.getElementById('ui').innerText = "ID: " + user.id;
        document.getElementById('av').innerText = user.first_name ? user.first_name[0] : 'U';
        
        fetch('/api/user/'+user.id).then(r=>r.json()).then(d=>{
            document.getElementById('bl').innerText = d.balance || 0;
            document.getElementById('st').innerText = d.premium_until > Date.now() ? "👑 PREMIUM" : "FREE USER";
        });
    </script>
    """
    return render_template_string(BASE_LAYOUT, content=content, page='profile', notice="")

# ================= রানার =================
if __name__ == "__main__":
    threading.Thread(target=lambda: bot.polling(none_stop=True)).start()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
