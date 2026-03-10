# YouTube List Search

A modern, high-performance Next.js web application designed to help users intelligently filter, manage, and categorize their massive YouTube playlists using Google's Gemini AI.

## Features

- **AI-Powered Categorization:** Integrates with Gemini 2.5 Flash to automatically classify YouTube videos into custom, user-defined topics at lightning speed.
- **SaaS First & Multi-Tenant:** Users provide their own Gemini API keys directly in the UI, ensuring infinite scalability without hitting a central server rate limit. 
- **Google Sheets Cloud Sync:** Acts as a serverless database by auto-generating and syncing a hidden Google Spreadsheet in the user's Drive to persist AI mappings across sessions.
- **Blazing Fast Local Caching:** Video feeds and AI tags are cached in the browser for an instant load time on subsequent visits.
- **Sleek UI/UX:** A responsive, neon-green dark mode dashboard equipped with real-time text search, column sorting, and instant video removal mechanisms.
- **Secure Authentication:** Features robust OAuth 2.0 integration via `NextAuth.js`, safely handling tokens without exposing credentials.

## Tech Stack

- **Core:** Next.js (App Router), React, TypeScript
- **Styling:** Tailwind CSS, Lucide Icons
- **Auth:** NextAuth (Google Provider)
- **Integrations:** YouTube Data API v3, Google Sheets API v4, Google GenAI (Gemini)

## Environment Setup

To run locally simply provide your Google Cloud OAuth credentials in your environment (`.env.local`):

```env
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=your_random_secure_string

GOOGLE_CLIENT_ID=your_oauth_client_id
GOOGLE_CLIENT_SECRET=your_oauth_client_secret
```
*(Note: Users will input their own Gemini API Keys directly within the web interface.)*