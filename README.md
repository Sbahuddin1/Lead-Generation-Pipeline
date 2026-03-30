# Lead Gen AI Prototype

An automated B2B lead generation system that scans industry news, qualifies leads using AI, and generates personalized outreach emails.

## Features
- **Stage 1: Discovery** — Fetches news via energy-targeted RSS feeds (Rigzone, Google News, etc.).
- **Stage 2: Filtering** — Fast keyword-based regex filtering to narrow down relevancy.
- **Stage 3: Qualification** — LLM-based analysis to identify high-intent project expansions.
- **Stage 4: Extraction** — Web crawling to find specific contact names, titles, and domains.
- **Stage 5: Verification** — Email lookup via Hunter.io API.
- **Stage 6: Outreach** — AI-generated personalized emails based on news context.

---

## Prerequisites

1. **Python 3.10+** is recommended.
2. **Environment Variables:** Create a `.env` file in the root directory with the following keys:
   ```env
   OPENAI_API_KEY=your_openai_key
   HUNTER_API_KEY=your_hunter_io_key
   ```
3. **Browser Dependencies:** The system uses `playwright` for crawling. You must install the browser engines after installing requirements.

---

## Installation

1. **Clone the repository** (if not already in it).
2. **Create a virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
4. **Install Playwright browsers:**
   ```bash
   playwright install
   ```

---

## How to Run

### MVP 1: Manual Outreach (Static Leads)
MVP1 takes a hardcoded list of companies (Shell, BP, ExxonMobil), finds the latest news for them, and writes outreach emails.

1. Navigate to the `mvp1` directory:
   ```bash
   cd mvp1
   ```
2. Run the application:
   ```bash
   python app.py
   ```
3. Open your browser at: `http://localhost:5000`

### MVP 2: Automated Pipeline (Discovery Mode)
MVP2 is the fully automated version. It discovers new companies from RSS feeds, filters them, and builds a lead list from scratch.

1. Navigate to the `mvp2` directory:
   ```bash
   cd mvp2
   ```
2. Run the application:
   ```bash
   python app.py
   ```
3. Open your browser at: `http://localhost:5001`
4. Click **"Start Discovery Pipeline"** to watch the 6-stage process in real-time.

---

## Technical Stack
- **Backend:** Flask (Python)
- **AI/LLM:** OpenAI GPT-4o / Google Gemini via `litellm`.
- **Crawler:** `Crawl4AI` / `playwright`.
- **Lead Discovery:** RSS Feeds via `feedparser`.
- **Emails:** `Hunter.io` API.
