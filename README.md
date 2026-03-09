# YT Playlist Manager

A full-stack Next.js application designed to manage, categorize, and filter massive YouTube playlists, augmented with Gemini AI intelligence.

## Features
- **Intelligent Classification**: Leverages Google's Gemini Flash AI to categorize disorganized "Watch Later" lists into customized target subjects.
- **Cloud State Synchronization**: Automatically saves your AI-generated tags to a hidden Google Spreadsheet, guaranteeing that your categorizations stay synced whether running locally or on a deployed server.
- **Dashboard Interface**: Search, filter, and remove embedded videos efficiently without bouncing back to the default YouTube app.

## Quickstart (Local Development)

**1. Install Dependencies**
```bash
npm install
```

**2. Configure Environment**
Create or edit `.env.local` to securely embed your Google OAuth Application Keys (Type: Web Application) and Gemini API token.
```env
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=generate_any_random_string_here

GOOGLE_CLIENT_ID=your_gcp_client_id
GOOGLE_CLIENT_SECRET=your_gcp_client_secret

GEMINI_API_KEY=your_gemini_api_key
```

**3. Run the application**
```bash
npm run dev
```

Visit [http://localhost:3000](http://localhost:3000). You will be prompted to connect securely over Google OAuth 2.0.
