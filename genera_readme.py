readme_content = """# MyRunningAgent 🏃‍♂️🤖

![Python 3.11](https://img.shields.io/badge/Python-3.11-blue.svg)
![Google Cloud](https://img.shields.io/badge/GCP-Cloud_Run-4285F4.svg)
![Gemini AI](https://img.shields.io/badge/AI-Gemini_3.5_Flash-orange.svg)
![Telegram](https://img.shields.io/badge/Bot-Telegram-2CA5E0.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)

MyRunningAgent is an advanced, autonomous virtual running assistant integrated into Telegram. Acting as both a data analyst and a sports coach, it leverages Generative AI and the Model Context Protocol (MCP) to analyze training telemetry, track body metrics, and manage weekly workout plans.

## 🧠 Architecture: The "Omni-Agent Context"

Unlike traditional bots that passively receive and forward data, MyRunningAgent employs an agentic architecture:
- **Model Context Protocol (MCP) Bridge:** The AI (Gemini 3.5 Flash) connects to Runalyze APIs via HTTP Server-Sent Events. It autonomously browses available tools (e.g., `get_activities`, `get_health_metrics`) and decides which endpoints to call in a multi-turn loop to answer user queries.
- **Context Orchestration:** The orchestrator fuses historical state data stored in Firestore (e.g., last weigh-in, active training plans) with real-time Runalyze telemetry, injecting a comprehensive "invisible context" into the LLM prompt.
- **Serverless Infrastructure:** Hosted on Google Cloud Run (scaling from 0 to 3 instances) with asynchronous threading to respect Telegram's strict 10-second webhook timeouts.

## ✨ Core Features

*   📅 **Smart Workout Planning:** Create, edit, and track weekly training plans directly via Telegram inline buttons (✅ Complete, ↩️ Reopen, ❌ Delete).
*   📊 **Body Metrics OCR:** Send a screenshot of your smart scale app; the agent uses Vision capabilities to automatically extract weight, body fat, muscle mass, water, and bone mass, saving the structured data to Firestore.
*   👟 **Dynamic Shoe Management:** Cross-references Runalyze mileage with current body weight to evaluate foam wear-and-tear and shoe responsiveness.

## 🛠️ Technology Stack

*   **Language:** Python 3.11
*   **Web Framework:** Flask
*   **AI Engine:** Google GenAI SDK (`gemini-3.5-flash`)
*   **Cloud Hosting:** Google Cloud Run
*   **Database:** Google Cloud Firestore (NoSQL)
*   **Security:** HMAC-SHA256 (Webhook validation), Google Secret Manager
*   **Data Source:** Runalyze API

## 📂 Repository Structure

~~~text
├── webhook.py          # Flask entry-point, HMAC-SHA256 validation, Telegram cache & threading
├── orchestrator.py     # Business logic, Omni-Context formatting, inline keyboard routing
├── analyst.py          # AI engine, MCP loop, Prompt management, OCR execution
├── database.py         # Firestore CRUD (activities, metrics, training_plans, ai_chats)
├── mcp_bridge.py       # Server-Sent Events bridge mapping Runalyze APIs to MCP tools
├── telegram_client.py  # Messaging, HTML formatting, plain-text fallbacks, image handling
├── requirements.txt    # Python dependencies
└── .env.example        # Environment variables template
~~~

## 🚀 Local Setup

1. **Clone the repository:**
   ~~~bash
   git clone https://github.com/YOUR_USERNAME/my-running-agent.git
   cd my-running-agent
   ~~~

2. **Set up a virtual environment:**
   ~~~bash
   python3.11 -m venv venv
   source venv/bin/activate
   ~~~

3. **Install dependencies:**
   ~~~bash
   pip install -r requirements.txt
   ~~~

4. **Configure Environment Variables:**
   Copy the example environment file and fill in your keys.
   ~~~bash
   cp .env.example .env
   ~~~
   *Required variables:* `TELEGRAM_BOT_TOKEN`, `RUNALYZE_PERSONAL_TOKEN`, `GEMINI_API_KEY`, `GCP_PROJECT_ID`.

5. **Run locally:**
   ~~~bash
   python webhook.py
   ~~~
   *(Note: You will need a tunneling tool like [ngrok](https://ngrok.com/) to expose your local server to the Telegram Webhook).*

## ⚠️ Limitations & Workarounds
* **Telegram Timeouts:** Mitigated via early 200 OK responses and background threading.
* **LLM Rate Limits (429/503):** Handled via strict tool-calling constraints and retry logic.
* **Markdown Rendering Errors (400):** Implemented a try/except fallback to plain text if the AI generates unparseable HTML tags for Telegram.

## 📄 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
""".replace("~~~", "```")

with open("README.md", "w", encoding="utf-8") as f:
    f.write(readme_content)

print("Il file README.md è stato generato con successo e gli escape sono perfetti!")
