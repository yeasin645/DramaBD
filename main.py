import os, threading, io, time, json
from flask import Flask, render_template_string, send_file, request, jsonify
from telebot import TeleBot, types
from pymongo import MongoClient, DESCENDING
from bson.objectid import ObjectId
import gridfs
from datetime import datetime

# ================= কনফিগারেশন (বিন্দুপরিমাণ ভুল করবেন না) =================
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
logs_col = db['task_logs'] 

bot = TeleBot(BOT_TOKEN)
app = Flask(__name__)
user_states = {}

# ================= ইউটিলিটি ফাংশনস =================
def is_admin(m):
    return m.from_user.id in ADMIN_IDS

def get_setting(key, default):
    s = settings_col.find_one({"key": key})
    if s: return s['value']
    return default

def get_user(tg_id, name="User"):
    user = users_col.find_one({"tg_id": str(tg_id)})
    if not user:
        user = {"tg_id": str(tg_id), "name": name, "balance": 0, "premium_until": 0}
        users_col.insert_one(user)
    return user

# ================= টেলিগ্রাম বট কমান্ডস =================

@bot.message_handler(commands=['start'])
def start_cmd(message):
    # ফাইল ডেলিভারি সিস্টেম (RRR - Episode 01 স্টাইলে নাম দিবে)
    if message.text.startswith('/start getfile_'):
        try:
            msg_id_str = message.text.split('getfile_')[1]
            msg_id = int(msg_id_str)
            movie = movies_col.find_one({"episodes.msg_id": msg_id})
            
            caption_text = "🎬 আপনার ফাইলটি প্রস্তুত!"
            if movie:
                ep_name = "Episode"
                for ep in movie['episodes']:
                    if ep['msg_id'] == msg_id:
                        ep_name = ep['name']
                        break
                caption_text = f"🎬 **Movie:** {movie['title']}\n📂 **File:** {ep_name}\n\n❤️ আমাদের সাথে থাকার জন্য ধন্যবাদ!"
            
            bot.copy_message(message.chat.id, FILE_CHANNEL_ID, msg_id, caption=caption_text, parse_mode="Markdown")
        except Exception as e:
            bot.send_message(message.chat.id, "❌ ফাইলটি পাওয়া যায়নি বা কোনো সমস্যা হয়েছে!")
        return

    get_user(message.from_user.id, message.from_user.full_name)
    site_name = get_setting("site_name", "Moviee BD")
    banner = get_setting("start_poster", "https://via.placeholder.com/800x450")

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("🎬 Watch Now", web_app=types.WebAppInfo(WEBAPP_URL)))
    
    btn1_data = get_setting("btn1", {"text": "📩 Movie Request", "val": "Request Mode"})
    btn2_data = get_setting("btn2", {"text": "🔗 My Referral Link", "val": "ref_logic"})
    btn3_data = get_setting("btn3", {"text": "❓ Help & Tutorial", "val": "Tutorial content"})
    btn4_data = get_setting("btn4", {"text": "🔗 All Channels", "val": "https://t.me/example"})

    markup.add(types.InlineKeyboardButton(btn1_data['text'], callback_data="btn1"),
               types.InlineKeyboardButton(btn2_data['text'], callback_data="btn2"))
    markup.add(types.InlineKeyboardButton(btn3_data['text'], callback_data="btn3"),
               types.InlineKeyboardButton(btn4_data['text'], url=btn4_data['val'] if btn4_data['val'].startswith("http") else "https://t.me/telegram"))

    try:
        bot.send_photo(message.chat.id, banner, caption=f"Hello {message.from_user.first_name}!\nWelcome to {site_name} ❤️🍿", reply_markup=markup)
    except:
        bot.send_message(message.chat.id, f"Welcome to {site_name} ❤️🍿", reply_markup=markup)

@bot.message_handler(commands=['sitename', 'notice', 'ads', 'step', 'lock', 'poster', 'add', 'adtask', 'monitask', 'addpr', 'btn1', 'btn2', 'btn3', 'btn4', 'dltask'])
def admin_router(message):
    if not is_admin(message): return
    cmd = message.text.split()[0][1:]
    
    if cmd == 'add':
        user_states[message.chat.id] = {'step': 'm_name', 'files': []}
        bot.send_message(message.chat.id, "🎬 মুভির নাম লিখুন:")
    elif cmd in ['sitename', 'notice', 'ads', 'step', 'lock', 'poster']:
        user_states[message.chat.id] = {'step': f'up_{cmd}'}
        bot.send_message(message.chat.id, f"📝 নতুন {cmd} তথ্য দিন:")
    elif cmd == 'adtask':
        try:
            _, link, point, limit = message.text.split()
            tasks_col.insert_one({"type": "link", "url": link, "point": int(point), "limit": int(limit)})
            bot.send_message(message.chat.id, "✅ লিঙ্ক টাস্ক সেভ হয়েছে!")
        except: bot.reply_to(message, "ব্যবহার: `/adtask লিঙ্ক পয়েন্ট লিমিট`")
    elif cmd == 'monitask':
        try:
            _, zone, point, limit = message.text.split()
            tasks_col.insert_one({"type": "monet", "zone_id": zone, "point": int(point), "limit": int(limit)})
            bot.send_message(message.chat.id, "✅ মনিটেগ টাস্ক সেভ হয়েছে!")
        except: bot.reply_to(message, "ব্যবহার: `/monitask জোনআইডি পয়েন্ট লিমিট`")
    elif cmd == 'dltask':
        tasks_col.delete_many({})
        bot.send_message(message.chat.id, "🗑 সকল টাস্ক ডিলিট করা হয়েছে।")

@bot.message_handler(func=lambda m: m.chat.id in user_states, content_types=['text', 'photo', 'video', 'document'])
def state_manager(message):
    chat_id, state = message.chat.id, user_states[message.chat.id]
    step = state['step']

    if step.startswith('up_'):
        key = step.replace('up_', '')
        val = message.text
        if key == 'poster' and message.content_type == 'photo':
            p_id = fs.put(bot.download_file(bot.get_file(message.photo[-1].file_id).file_path), filename="banner.jpg")
            val = f"{WEBAPP_URL}/poster/{p_id}"
        elif key in ['step', 'lock']: val = int(message.text)
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
        bot.send_message(chat_id, "📁 ফাইল দিন, শেষ হলে /done দিন:")
    elif step == 'm_upload':
        if message.content_type in ['video', 'document']:
            fwd = bot.copy_message(FILE_CHANNEL_ID, chat_id, message.message_id)
            ep_num = len(state['files']) + 1
            ep_name = f"Episode {ep_num:02d}"
            state['files'].append({"name": ep_name, "msg_id": fwd.message_id})
            bot.send_message(chat_id, f"✅ {ep_name} রিসিভ হয়েছে।")
        elif message.text == '/done':
            movies_col.insert_one({"title": state['name'], "category": state['category'], "poster": state['poster_url'], "episodes": state['files'], "views": [], "likes": 0})
            bot.send_message(chat_id, "🚀 মুভি সেভ হয়েছে!")
            del user_states[chat_id]

@bot.callback_query_handler(func=lambda call: True)
def cb_handler(call):
    if call.data == "btn2":
        bot.send_message(call.message.chat.id, f"🔗 রেফার লিঙ্ক: https://t.me/{bot.get_me().username}?start={call.from_user.id}")
    else:
        data = get_setting(call.data, None)
        if data: bot.send_message(call.message.chat.id, str(data['val']))
    bot.answer_callback_query(call.id)

# ================= এপিআই লজিক =================

@app.route('/poster/<file_id>')
def serve_poster(file_id):
    try: return send_file(io.BytesIO(fs.get(ObjectId(file_id)).read()), mimetype='image/jpeg')
    except: return "404", 404

@app.route('/api/user/<tg_id>')
def api_user(tg_id): return jsonify(get_user(tg_id))

@app.route('/api/claim', methods=['POST'])
def api_claim():
    d = request.json
    tg_id, task_id = str(d['tg_id']), d['task_id']
    task = tasks_col.find_one({"_id": ObjectId(task_id)})
    if not task: return jsonify({"status": "fail"})
    
    today = datetime.now().strftime("%Y-%m-%d")
    count = logs_col.count_documents({"tg_id": tg_id, "task_id": task_id, "date": today})
    
    if count < task.get('limit', 1):
        users_col.update_one({"tg_id": tg_id}, {"$inc": {"balance": int(task['point'])}})
        logs_col.insert_one({"tg_id": tg_id, "task_id": task_id, "date": today})
        return jsonify({"status": "ok", "msg": f"Success! {task['point']} Coins Added."})
    return jsonify({"status": "fail", "msg": "Daily Limit Reached!"})

# ================= ওয়েব অ্যাপ UI =================

BASE_LAYOUT = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        body { background: #0b0f19; color: white; padding-bottom: 100px; font-family: sans-serif; overflow-x: hidden; }
        .glass { background: rgba(30, 41, 59, 0.7); backdrop-filter: blur(10px); border: 1px solid rgba(255,255,255,0.05); }
        .nav-item { flex:1; text-align:center; font-size:10px; color:#64748b; text-decoration:none; transition: 0.3s; }
        .nav-item.active { color:#6366f1; }
        #loader { position: fixed; inset: 0; background: #0b0f19; z-index: 9999; display: flex; align-items: center; justify-content: center; font-weight: bold; }
    </style>
</head>
<body>
    <div id="loader">LOADING...</div>
    <div class="bg-indigo-600/20 py-2 px-4 border-b border-white/5"><marquee class="text-[10px]">{{ notice }}</marquee></div>
    <div id="main-content" class="p-4">{{ content | safe }}</div>
    
    <div class="fixed bottom-0 left-0 w-full glass border-t border-white/5 flex py-4 px-2 z-50">
        <a href="/" class="nav-item {{'active' if page=='home'}}">🏠<br>Home</a>
        <a href="/tasks" class="nav-item {{'active' if page=='tasks'}}">📋<br>Tasks</a>
        <a href="/premium" class="nav-item {{'active' if page=='premium'}}">💎<br>Premium</a>
        <a href="/profile" class="nav-item {{'active' if page=='profile'}}">👤<br>Profile</a>
    </div>

    <script>
        const tg = window.Telegram.WebApp; tg.expand();
        const user = tg.initDataUnsafe.user || {id: "7120801813", first_name: "User"};
        window.onload = () => { document.getElementById('loader').style.display = 'none'; };
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    movies = list(movies_col.find())
    content = render_template_string("""
        <h1 class="text-2xl font-black mb-6 text-indigo-500 uppercase">{{site_name}}</h1>
        <div class="grid grid-cols-2 gap-4">
            {% for m in movies %}
            <div class="glass rounded-3xl overflow-hidden shadow-2xl" onclick="location.href='/movie/{{m._id}}'">
                <img src="{{m.poster}}" class="w-full h-52 object-cover">
                <div class="p-3">
                    <h3 class="text-[11px] font-bold truncate">{{m.title}}</h3>
                    <div class="flex justify-between items-center mt-2 text-[9px] text-gray-500">
                        <span>👁 {{m.views|length}} Views</span>
                        <span class="text-indigo-400 font-bold uppercase">{{m.category}}</span>
                    </div>
                </div>
            </div>
            {% endfor %}
        </div>
    """, movies=movies, site_name=get_setting("site_name", "Moviee BD"))
    return render_template_string(BASE_LAYOUT, content=content, page='home', notice=get_setting("notice", "Welcome"))

@app.route('/movie/<id>')
def movie_detail(id):
    m = movies_col.find_one({"_id": ObjectId(id)})
    ip = request.remote_addr
    if ip not in m.get('views', []): movies_col.update_one({"_id": ObjectId(id)}, {"$push": {"views": ip}})
    
    content = render_template_string("""
        <div class="relative mb-6">
            <img src="{{m.poster}}" class="w-full h-96 object-cover rounded-[40px] shadow-2xl">
            <button onclick="history.back()" class="absolute top-4 left-4 glass w-10 h-10 rounded-full flex items-center justify-center">❮</button>
        </div>
        <h1 class="text-2xl font-black mb-1 px-2">{{m.title}}</h1>
        <p class="text-indigo-400 text-xs font-bold mb-4 px-2 tracking-widest uppercase">{{m.category}} • 👁 {{m.views|length}}</p>
        
        <div class="glass p-4 rounded-2xl mb-8 mx-2 border-l-4 border-yellow-500">
            <p class="text-xs font-bold text-yellow-500 uppercase">⏳ Unlock Info</p>
            <p class="text-[10px] text-gray-300">মুভিটি আনলক করার পর <b>{{lock}} মিনিট</b> পর্যন্ত দেখতে পারবেন। এরপর আবার লক হয়ে যাবে।</p>
        </div>

        <h3 class="text-sm font-bold mb-5 px-2">📂 EPISODES</h3>
        <div class="grid grid-cols-3 gap-3 px-2">
            {% for ep in m.episodes %}
            <div onclick="play('{{ep.msg_id}}', '{{loop.index}}')" class="glass py-5 rounded-2xl text-center active:scale-90 transition">
                <span class="text-[8px] font-bold block opacity-40 mb-1" id="lab-{{loop.index}}">LOCKED</span>
                <span class="text-xs font-black">{{ep.name}}</span>
            </div>
            {% endfor %}
        </div>

        <script src='//libtl.com/sdk.js' data-zone='{{zone}}' data-sdk='show_{{zone}}'></script>
        <script>
            let steps = {{steps}}, lockMin = {{lock}}, zone = "{{zone}}";
            function play(id, idx) {
                let sKey = "unl_"+id;
                let d = JSON.parse(localStorage.getItem(sKey) || '{"s":0, "e":0}');

                // লক টাইম চেক (সময় শেষ হলে রিসেট হবে)
                if(d.e > 0 && d.e < Date.now()) {
                    d = {"s":0, "e":0};
                    localStorage.setItem(sKey, JSON.stringify(d));
                }

                if(d.e > Date.now() || window.isPremium) {
                    window.open("https://t.me/{{bot_user}}?start=getfile_"+id, "_blank");
                } else if(d.s < steps) {
                    if(typeof window['show_'+zone] === 'function') {
                        window['show_'+zone]().then(() => { 
                            d.s++; 
                            localStorage.setItem(sKey, JSON.stringify(d)); 
                            updateUI(id, idx); 
                        });
                    } else { alert("Ad Script Loading..."); }
                } else {
                    d.e = Date.now() + (lockMin * 60000); 
                    localStorage.setItem(sKey, JSON.stringify(d));
                    updateUI(id, idx); 
                    alert("Unlocked! Enjoy for next "+lockMin+" minutes.");
                }
            }
            function updateUI(id, idx) {
                let d = JSON.parse(localStorage.getItem("unl_"+id) || '{"s":0, "e":0}');
                let lab = document.getElementById("lab-"+idx);
                if((d.e > 0 && d.e > Date.now()) || window.isPremium) { 
                    lab.innerText = "READY"; lab.style.color="#10b981";
                } else { 
                    lab.innerText = d.s+"/"+steps+" ADS"; 
                    lab.style.color="#64748b";
                }
            }
            fetch('/api/user/'+user.id).then(r=>r.json()).then(u=>{ 
                window.isPremium = u.premium_until > Date.now(); 
                {% for ep in m.episodes %} updateUI('{{ep.msg_id}}', '{{loop.index}}'); {% endfor %}
            });
        </script>
    """, m=m, zone=get_setting("ads", "10351894"), steps=get_setting("step", 3), 
       lock=get_setting("lock", 60), bot_user=bot.get_me().username)
    return render_template_string(BASE_LAYOUT, content=content, page='home', notice="Loading...")

@app.route('/tasks')
def tasks_page():
    ts = list(tasks_col.find())
    content = render_template_string("""
        <h2 class="text-xl font-black mb-6 text-indigo-400">TASK CENTER</h2>
        {% for t in ts %}
        <div class="glass p-5 rounded-[30px] mb-4 flex justify-between items-center border-r-4 border-indigo-500 shadow-xl">
            <div><p class="font-bold text-sm">{{'Watch Ad' if t.type=='monet' else 'Visit Link'}}</p>
            <p class="text-[10px] text-yellow-500 font-bold mt-1">+{{t.point}} COINS | Limit: {{t.limit}}</p></div>
            <button onclick="doT('{{t._id}}','{{t.type}}','{{t.url}}','{{t.zone_id}}')" class="bg-indigo-600 px-5 py-2 rounded-2xl text-[10px] font-black uppercase">Start</button>
        </div>
        {% endfor %}
        <script>
            function doT(id, ty, url, zone) {
                if(ty==='link') { 
                    window.open(url,'_blank'); 
                    setTimeout(()=>claim(id), 10000); 
                } else {
                    // রেন্ডম জোন আইডি স্ক্রিপ্ট ইনজেকশন
                    let s = document.createElement('script');
                    s.src = '//libtl.com/sdk.js';
                    s.setAttribute('data-zone', zone);
                    s.setAttribute('data-sdk', 'show_'+zone);
                    s.onload = () => {
                        window['show_'+zone]().then(() => claim(id));
                    };
                    document.body.appendChild(s);
                }
            }
            function claim(id) { 
                fetch('/api/claim',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tg_id:user.id, task_id:id})})
                .then(r=>r.json()).then(res=>alert(res.msg)); 
            }
        </script>
    """, ts=ts)
    return render_template_string(BASE_LAYOUT, content=content, page='tasks', notice="Complete tasks to get coins")

@app.route('/premium')
def premium_page():
    plans = list(premium_col.find())
    content = render_template_string("""
        <h2 class="text-xl font-black mb-6 text-indigo-400">MEMBERSHIP</h2>
        {% for p in plans %}
        <div class="glass p-6 rounded-[35px] mb-4 flex justify-between items-center border-l-4 border-indigo-500 shadow-2xl">
            <div><p class="text-lg font-black">{{p.label}}</p><p class="text-xs text-yellow-500 font-bold">{{p.cost}} COINS</p></div>
            <button onclick="buy('{{p._id}}')" class="bg-indigo-600 px-6 py-2 rounded-2xl text-xs font-black uppercase">Buy</button>
        </div>
        {% endfor %}
        <script>
            function buy(id) { 
                fetch('/api/buy_premium',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tg_id:user.id, plan_id:id})})
                .then(r=>r.json()).then(res=>alert(res.status==='ok'?"Membership Activated!":"Insufficient Coins.")); 
            }
        </script>
    """, plans=plans)
    return render_template_string(BASE_LAYOUT, content=content, page='premium', notice="Get Premium to hide all ads")

@app.route('/profile')
def profile_page():
    content = """
    <div class="text-center py-12">
        <div id="av" class="w-24 h-24 bg-indigo-600 rounded-full mx-auto mb-5 flex items-center justify-center text-3xl font-black border-4 border-white/10 shadow-2xl">?</div>
        <h2 id="un" class="text-2xl font-black mb-1">User</h2>
        <p id="ui" class="text-gray-500 text-[10px] mb-10 tracking-[5px]">ID: 000000</p>
        <div class="grid grid-cols-2 gap-4 px-4">
            <div class="glass p-6 rounded-[35px] shadow-xl"><p class="text-[10px] text-gray-400 uppercase font-bold mb-1">Balance</p><p id="bl" class="text-xl font-black text-yellow-500">0</p></div>
            <div class="glass p-6 rounded-[35px] shadow-xl"><p class="text-[10px] text-gray-400 uppercase font-bold mb-1">Status</p><p id="st" class="text-[11px] font-black text-green-500">FREE</p></div>
        </div>
    </div>
    <script>
        document.getElementById('un').innerText = user.first_name || 'Guest';
        document.getElementById('ui').innerText = "ID: " + user.id;
        document.getElementById('av').innerText = (user.first_name ? user.first_name[0] : 'U');
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
