# Personal AI Accountability Agent 🤖

An asynchronous Telegram bot engineered to automate daily habit tracking, technical interview preparation, and computer science active recall.

Built with Python, SQLite, `python-telegram-bot`, `APScheduler`, and integrated with the public LeetCode GraphQL API.

---
📌 Key Features

- **Automated LeetCode Integration:** Fetches the official daily problem (title, difficulty, direct problem URL) via LeetCode's public GraphQL endpoint.
- **GATE CS Active Recall Engine:** Delivers targeted concept challenges (OS, DBMS, Computer Networks, DSA) with automated keyword-based evaluation and review tracking.
- **Dynamic Habit Persistence:** Backed by SQLite (`agent.db`) to log daily achievements (Hydration, LeetCode, FSD, GATE) without hardcoding task categories.
- **Conversational Logging:** Parses plain-text input (e.g., *"drank water and worked on nestjs backend"*) using semantic keyword mapping.
- **Visual Analytics:** Generates 7-day progress charts on demand using `matplotlib` (`Agg` non-GUI backend).
- **Background Scheduling:** Runs non-blocking asynchronous cron jobs using `APScheduler` for hourly water reminders, morning coding dispatches, and nightly progress charts.
- **Zero-Trust Access Control:** Restricts execution exclusively to the authorized user's Telegram Chat ID.


