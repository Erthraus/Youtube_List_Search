import { NextResponse } from 'next/server';
import { getServerSession } from 'next-auth';
import { authOptions } from '@/lib/auth';
import { categorizeVideosWithAI } from '@/lib/gemini';
import { createSheetIfNotExists, saveTagsToSheet, loadTagsFromSheet } from '@/lib/sheets';
import { YouTubeVideo } from '@/lib/youtube';

export async function POST(request: Request) {
  const session = await getServerSession(authOptions);
  
  if (!session || !session.accessToken) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const { videos, playlistId, targetCategories, forceAll, userApiKey } = await request.json();
    
    if (!videos || !playlistId || !targetCategories || !userApiKey) {
      return NextResponse.json({ error: 'Missing parameters. Please ensure your Gemini API Key is entered.' }, { status: 400 });
    }

    let unmapped: YouTubeVideo[] = videos;
    if (!forceAll) {
      unmapped = videos.filter((v: YouTubeVideo) => v.custom_category === 'General / Unrelated');
    }
    
    if (unmapped.length === 0) {
      return NextResponse.json({ message: 'All videos already categorized.' });
    }

    // Call Gemini AI
    const { tags: newTags, debugText, error: geminiError } = await categorizeVideosWithAI(unmapped, targetCategories, userApiKey);

    // Save back to Google Sheet
    const sheetId = await createSheetIfNotExists(session.accessToken, `YT_List_Search_Tags_${playlistId}`);
    
    // We should merge with existing tags before writing to not overwrite the whole sheet with only new ones
    // Wait, saveTagsToSheet overwrites everything. Let's fetch the existing sheet first.
    const existingTags = await loadTagsFromSheet(session.accessToken, sheetId);

    // Build complete Map
    const allTagsMap: Record<string, {title: string, category: string}> = {};
    for (const v of videos) {
      const existingInSheet = existingTags[v.video_id];
      const newlyMapped = newTags[v.video_id];
      
      const category = newlyMapped || existingInSheet || v.custom_category;
      
      if (category !== 'General / Unrelated') {
        allTagsMap[v.video_id] = { title: v.title, category };
      }
    }

    await saveTagsToSheet(session.accessToken, sheetId, allTagsMap);

    return NextResponse.json({ 
      mappedCount: Object.keys(newTags).length, 
      tags: newTags,
      debugText,
      geminiError
    });
  } catch (error: any) {
    console.error("POST Categorize Error:", error);
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}
