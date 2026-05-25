# ReplyBot — Instagram Comment Auto-Replier

A Flask app that:
1. Fetches Instagram post content (caption + audio transcript for Reels) using the **existing InstaLens project**
2. Loads comments via **Instagram Graph API**
3. Generates context-aware replies using **Google Gemini**
4. Posts replies back to Instagram
5. Logs everything to **Google Cloud SQL (MySQL)**

---

## Project Structure

```
insta-replier/
├── app.py            ← Flask app, all routes
├── db.py             ← Cloud SQL connection + helpers
├── instagram.py      ← Instagram Graph API calls
├── gemini.py         ← Gemini reply generator
├── requirements.txt
├── .env.example      ← Copy to .env and fill in
└── templates/
    └── index.html    ← Dashboard UI
```

---

## Step 1 — Install Dependencies

```bash
cd insta-replier
pip install -r requirements.txt
```

---

## Step 2 — Set Up Google Cloud SQL (MySQL)

### A. Create a Cloud SQL Instance
1. Go to [console.cloud.google.com](https://console.cloud.google.com) → **SQL**
2. Click **Create Instance** → Choose **MySQL**
3. Set instance ID, root password, region
4. Under **Connections** → enable **Public IP**
5. Add your IP to **Authorized Networks** (or use `0.0.0.0/0` for dev)

### B. Create the Database
```sql
CREATE DATABASE insta_replier CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```
Tables are **auto-created** when the app starts.

---

## Step 3 — Instagram Graph API Setup

1. Go to [developers.facebook.com](https://developers.facebook.com) → Create App
2. Add **Instagram Graph API** product
3. Connect your **Instagram Business/Creator** account
4. Generate a **Long-Lived Access Token** (valid 60 days)
5. Get your **Instagram User ID** from the API Explorer:
   ```
   GET https://graph.facebook.com/v19.0/me?fields=id,username&access_token=YOUR_TOKEN
   ```

---

## Step 4 — Get Gemini API Key

1. Go to [aistudio.google.com](https://aistudio.google.com)
2. Click **Get API Key** → **Create API Key**
3. Copy it to your `.env`

---

## Step 5 — Configure .env

```bash
cp .env.example .env
```

Fill in all values in `.env`:

```env
IG_ACCESS_TOKEN=your_token_here
IG_USER_ID=your_ig_user_id
GEMINI_API_KEY=your_gemini_key
GEMINI_TONE=friendly
BRAND_NAME=YourBrand
CLOUD_SQL_HOST=34.xxx.xxx.xxx   # Your Cloud SQL public IP
CLOUD_SQL_PORT=3306
CLOUD_SQL_USER=root
CLOUD_SQL_PASSWORD=your_password
CLOUD_SQL_DATABASE=insta_replier
WEBHOOK_VERIFY_TOKEN=any_random_secret
```

---

## Step 6 — Run the App

```bash
python app.py
```

Open: **http://localhost:5001**

---

## Step 7 — (Optional) Webhook for Real-Time Replies

To auto-reply the moment a comment is posted:

1. Deploy the app to a public URL (e.g., Railway, Render, or ngrok for dev)
2. In Meta Developer Console → **Webhooks**
3. Subscribe to `instagram → comments`
4. Callback URL: `https://your-domain.com/webhook`
5. Verify Token: (same as `WEBHOOK_VERIFY_TOKEN` in .env)

---

## How It Works

```
User posts comment
       ↓
Instagram → Webhook → Flask /webhook
       ↓
get_post_context()   ← fetches caption + transcript
       ↓
generate_reply()     ← Gemini generates smart reply
       ↓
post_reply()         ← posts reply to Instagram
       ↓
save_reply_log()     ← saves to Cloud SQL
```

---

## Gemini Tone Options

Set `GEMINI_TONE` in `.env`:
- `friendly` — warm and approachable (default)
- `professional` — clean and polished
- `funny` — witty and humorous
- `casual` — relaxed, like a friend
- `enthusiastic` — high energy
