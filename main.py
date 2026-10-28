import os
import sqlite3
import datetime
import requests
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ALLOWED_CHAT_ID = int(os.getenv("MY_CHAT_ID", "0"))
DB_NAME = "agent.db"

# In-memory flag to know if user's next text is an answer to a GATE question
PENDING_GATE_QUESTION = {}

# --- GATE QUESTION BANK ---
GATE_QUESTIONS = [
    {
        "id": 1,
        "subject": "Operating Systems",
        "question": "What is the primary cause of internal fragmentation in paging, and how does segmentation avoid it?",
        "keywords": ["page size", "fixed", "variable", "variable size", "allocated"]
    },
    {
        "id": 2,
        "subject": "DBMS",
        "question": "What is the key difference between Conflict Serializability and View Serializability?",
        "keywords": ["blind write", "precedence graph", "cycle", "view", "conflict equivalent"]
    },
    {
        "id": 3,
        "subject": "Computer Networks",
        "question": "Why does TCP use a Three-Way Handshake instead of a Two-Way Handshake for connection establishment?",
        "keywords": ["syn", "ack", "duplicate", "delayed", "sequence number", "old"]
    },
    {
        "id": 4,
        "subject": "Data Structures & Algorithms",
        "question": "What is the worst-case time complexity of QuickSort, and in what scenario does it occur?",
        "keywords": ["o(n^2)", "o(n2)", "sorted", "reverse", "pivot", "unbalanced"]
    },
    {
        "id": 5,
        "subject": "Theory of Computation",
        "question": "Is the problem of checking whether a context-free grammar (CFG) is ambiguous decidable or undecidable?",
        "keywords": ["undecidable", "pcp", "post correspondence"]
    }
]

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS habits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            habit_name TEXT NOT NULL,
            log_date TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS gate_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id INTEGER,
            answer TEXT,
            result TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    default_habits = ["Water", "LeetCode", "FSD", "GATE"]
    for h in default_habits:
        cur.execute("INSERT OR IGNORE INTO habits (name) VALUES (?)", (h,))
    conn.commit()
    conn.close()

def add_new_habit(name: str):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO habits (name) VALUES (?)", (name,))
    conn.commit()
    conn.close()

def get_all_habits():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT name FROM habits")
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]

def log_completion(habit_name: str):
    today = datetime.date.today().isoformat()
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("INSERT INTO logs (habit_name, log_date) VALUES (?, ?)", (habit_name, today))
    conn.commit()
    conn.close()

def fetch_weekly_counts():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        SELECT habit_name, COUNT(*) FROM logs 
        WHERE created_at >= datetime('now', '-7 days')
        GROUP BY habit_name
    """)
    counts = dict(cur.fetchall())
    conn.close()
    return counts

# --- EXTERNAL API: LEETCODE OF THE DAY ---
def fetch_leetcode_daily():
    url = "https://leetcode.com/graphql"
    query = """
    query questionOfToday {
        activeDailyCodingChallengeQuestion {
            date
            link
            question {
                title
                titleSlug
                difficulty
            }
        }
    }
    """
    try:
        response = requests.post(url, json={"query": query}, timeout=10)
        data = response.json()
        challenge = data["data"]["activeDailyCodingChallengeQuestion"]
        title = challenge["question"]["title"]
        difficulty = challenge["question"]["difficulty"]
        link = f"https://leetcode.com{challenge['link']}"
        return title, difficulty, link
    except Exception as e:
        print(f"Error fetching LeetCode daily: {e}")
        return "Daily Challenge", "Medium", "https://leetcode.com/problemset/all/"

# --- DYNAMIC CHART GENERATOR ---
def generate_chart() -> str:
    habits = get_all_habits()
    stats = fetch_weekly_counts()
    counts = [stats.get(h, 0) for h in habits]

    fig, ax = plt.subplots(figsize=(7, 4))
    bars = ax.bar(habits, counts, color='#3F51B5')
    ax.set_ylabel("Completions (Last 7 Days)")
    ax.set_title("Weekly Accountability Dashboard")
    ax.set_ylim(0, max(max(counts, default=0) + 2, 6))

    for bar in bars:
        height = bar.get_height()
        ax.annotate(f'{height}',
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3),
                    textcoords="offset points",
                    ha='center', va='bottom')

    chart_path = "progress.png"
    plt.tight_layout()
    plt.savefig(chart_path)
    plt.close()
    return chart_path

def is_authorized(update: Update) -> bool:
    return update.effective_chat.id == ALLOWED_CHAT_ID

# --- SCHEDULED BACKGROUND TASKS ---
async def hourly_water_check(app: Application):
    kb = [[InlineKeyboardButton("💧 Drank 250ml", callback_data="done_Water")]]
    await app.bot.send_message(
        chat_id=ALLOWED_CHAT_ID,
        text="💧 **Hydration Reminder:** Take a break and drink a glass of water!",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def morning_leetcode_dispatch(app: Application):
    title, difficulty, link = fetch_leetcode_daily()
    kb = [
        [InlineKeyboardButton("🔗 Open Problem", url=link)],
        [InlineKeyboardButton("✅ Solved Problem", callback_data="done_LeetCode")]
    ]
    await app.bot.send_message(
        chat_id=ALLOWED_CHAT_ID,
        text=(
            f"🧠 **Daily LeetCode Challenge!**\n\n"
            f"📌 **{title}**\n"
            f"⚡ Difficulty: `{difficulty}`\n\n"
            f"Solve it today and tap below when finished!"
        ),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def evening_gate_quizzer(app: Application):
    import random
    q = random.choice(GATE_QUESTIONS)
    PENDING_GATE_QUESTION[ALLOWED_CHAT_ID] = q

    await app.bot.send_message(
        chat_id=ALLOWED_CHAT_ID,
        text=(
            f"📚 **GATE Prep Check-in ({q['subject']})**\n\n"
            f"❓ *{q['question']}*\n\n"
            f"Reply directly with your answer in 1-2 sentences to test your recall."
        ),
        parse_mode="Markdown"
    )

async def evening_daily_summary(app: Application):
    chart_path = generate_chart()
    with open(chart_path, "rb") as photo_file:
        await app.bot.send_photo(
            chat_id=ALLOWED_CHAT_ID,
            photo=photo_file,
            caption="📊 **End-of-Day Review:** Here is your active 7-day consistency graph."
        )

# --- LIFECYCLE HOOK ---
async def post_init(app: Application):
    scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")
    
    # 1. Hourly water reminder (9 AM to 10 PM IST)
    scheduler.add_job(hourly_water_check, "cron", hour="9-22", minute="0", args=[app])

    # 2. LeetCode Problem of the Day (10:00 AM IST)
    scheduler.add_job(morning_leetcode_dispatch, "cron", hour="10", minute="0", args=[app])

    # 3. GATE Active Recall Question (7:30 PM IST)
    scheduler.add_job(evening_gate_quizzer, "cron", hour="19", minute="30", args=[app])

    # 4. Nightly Progress Summary (10:30 PM IST)
    scheduler.add_job(evening_daily_summary, "cron", hour="22", minute="30", args=[app])
    
    scheduler.start()
    print("⏰ Scheduler started with LeetCode, GATE, Water, and Summary jobs!")

# --- BOT COMMANDS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    await update.message.reply_text(
        "👋 **Welcome to your AI Accountability Agent!**\n\n"
        "Features active:\n"
        "• `/tasks` - Quick completion buttons\n"
        "• `/leetcode` - Fetch today's official LeetCode problem now\n"
        "• `/gate` - Trigger an instant GATE quiz question\n"
        "• `/add <name>` - Add a new tracking category\n"
        "• `/stats` - View your weekly progress graph\n\n"
        "💬 *You can also just text me naturally, e.g., 'drank water and did leetcode' to log!*"
    )

async def tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    habits = get_all_habits()
    keyboard = [[InlineKeyboardButton(f"✅ {h}", callback_data=f"done_{h}")] for h in habits]
    await update.message.reply_text("Select a completed task to log:", reply_markup=InlineKeyboardMarkup(keyboard))

async def add_habit_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    if not context.args:
        await update.message.reply_text("Please provide a name: `/add Reading`", parse_mode="Markdown")
        return
    habit_name = " ".join(context.args)
    add_new_habit(habit_name)
    await update.message.reply_text(f"🎯 New habit added: **{habit_name}**!", parse_mode="Markdown")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    chart_path = generate_chart()
    with open(chart_path, "rb") as photo_file:
        await update.message.reply_photo(photo=photo_file, caption="📈 Your live weekly progress:")

async def leetcode_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    title, difficulty, link = fetch_leetcode_daily()
    kb = [
        [InlineKeyboardButton("🔗 Open Problem", url=link)],
        [InlineKeyboardButton("✅ Solved Problem", callback_data="done_LeetCode")]
    ]
    await update.message.reply_text(
        f"🧠 **Today's LeetCode Challenge:**\n\n"
        f"📌 **{title}**\n"
        f"⚡ Difficulty: `{difficulty}`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def gate_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    import random
    q = random.choice(GATE_QUESTIONS)
    PENDING_GATE_QUESTION[ALLOWED_CHAT_ID] = q
    await update.message.reply_text(
        f"📚 **GATE Question ({q['subject']}):**\n\n"
        f"❓ *{q['question']}*\n\n"
        f"Reply with your answer in 1-2 lines.",
        parse_mode="Markdown"
    )

# --- NATURAL LANGUAGE & QUIZ HANDLER ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    
    user_text = update.message.text.strip()
    user_lower = user_text.lower()

    # 1. Check if user is answering a pending GATE question
    if ALLOWED_CHAT_ID in PENDING_GATE_QUESTION:
        q = PENDING_GATE_QUESTION.pop(ALLOWED_CHAT_ID)
        matched_keywords = [kw for kw in q["keywords"] if kw in user_lower]
        
        conn = sqlite3.connect(DB_NAME)
        cur = conn.cursor()
        
        if len(matched_keywords) > 0:
            cur.execute("INSERT INTO gate_history (question_id, answer, result) VALUES (?, ?, ?)",
                        (q["id"], user_text, "CORRECT"))
            conn.commit()
            conn.close()
            log_completion("GATE")
            await update.message.reply_text(
                f"✅ **Solid Recall!** You hit the core concepts ({', '.join(matched_keywords)}).\n"
                f"Logged **GATE** to your daily progress!",
                parse_mode="Markdown"
            )
        else:
            cur.execute("INSERT INTO gate_history (question_id, answer, result) VALUES (?, ?, ?)",
                        (q["id"], user_text, "REVIEW_NEEDED"))
            conn.commit()
            conn.close()
            await update.message.reply_text(
                f"📖 **Good attempt!** Key concepts expected for this question were: *{', '.join(q['keywords'])}*.\n"
                f"Take 2 minutes to review this topic in your notes.",
                parse_mode="Markdown"
            )
        return

    # 2. Natural Language Logging: detect keywords in the message
    detected = []
    habits = get_all_habits()
    
    synonyms = {
        "Water": ["water", "drank", "hydrated", "hydration"],
        "LeetCode": ["leetcode", "dsa", "solved", "two sum"],
        "FSD": ["fsd", "nestjs", "backend", "fullstack", "full stack", "typeorm"],
        "GATE": ["gate", "revision", "pyq", "algorithms"]
    }

    for habit in habits:
        keys = synonyms.get(habit, [habit.lower()])
        if any(k in user_lower for k in keys):
            log_completion(habit)
            detected.append(habit)

    if detected:
        await update.message.reply_text(
            f"🤖 Got it! Logged completion for: **{', '.join(detected)}**.",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "I heard you! To log an activity, you can mention tasks like *'drank water'*, *'did leetcode'*, or use `/tasks`.",
            parse_mode="Markdown"
        )

async def on_button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.message.chat.id != ALLOWED_CHAT_ID:
        return
    await query.answer()

    data = query.data
    if data.startswith("done_"):
        habit = data.replace("done_", "")
        log_completion(habit)
        await query.edit_message_text(f"🎉 Marked **{habit}** as completed today!", parse_mode="Markdown")

# --- MAIN ---
def main():
    init_db()

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # Command Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("tasks", tasks))
    app.add_handler(CommandHandler("add", add_habit_cmd))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("leetcode", leetcode_cmd))
    app.add_handler(CommandHandler("gate", gate_cmd))
    
    # Button clicks
    app.add_handler(CallbackQueryHandler(on_button_click))

    # Natural Language message handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 All-in-one AI Agent is running...")
    app.run_polling()

if __name__ == "__main__":
    main()