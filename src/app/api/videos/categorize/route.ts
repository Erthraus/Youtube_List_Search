import { NextResponse } from 'next/server';
import { getServerSession } from 'next-auth';
import { authOptions } from '@/lib/auth';
import { createSheetIfNotExists, saveTagsToSheet, loadTagsFromSheet } from '@/lib/sheets';
import { YouTubeVideo } from '@/lib/youtube';

// This route now ONLY handles saving AI tags to Google Sheets.
// The actual Gemini AI call is made client-side in Dashboard.tsx to avoid Vercel timeout limits.
export async function POST(request: Request) {
  const session = await getServerSession(authOptions);
  
  if (!session || !session.accessToken) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const { videos, playlistId, newTags } = await request.json();
    
    if (!videos || !playlistId || !newTags) {
      return NextResponse.json({ error: 'Missing parameters' }, { status: 400 });
    }

    // Save back to Google Sheet
    const sheetId = await createSheetIfNotExists(session.accessToken, `YT_List_Search_Tags_${playlistId}`);
    
    // Merge with existing tags before writing to avoid overwriting the whole sheet
    const existingTags = await loadTagsFromSheet(session.accessToken, sheetId);

    // Build complete Map
    const allTagsMap: Record<string, {title: string, category: string}> = {};
    for (const v of videos as YouTubeVideo[]) {
      const existingInSheet = existingTags[v.video_id];
      const newlyMapped = newTags[v.video_id];
      
      const category = newlyMapped || existingInSheet || v.custom_category;
      
      if (category && category !== 'General / Unrelated') {
        allTagsMap[v.video_id] = { title: v.title, category };
      }
    }

    await saveTagsToSheet(session.accessToken, sheetId, allTagsMap);

    return NextResponse.json({ success: true, savedCount: Object.keys(allTagsMap).length });
  } catch (error: any) {
    console.error("POST Categorize (Save Tags) Error:", error);
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}
