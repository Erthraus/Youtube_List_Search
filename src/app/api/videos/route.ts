import { NextResponse } from 'next/server';
import { getServerSession } from 'next-auth';
import { authOptions } from '@/lib/auth';
import { fetchPlaylistVideos } from '@/lib/youtube';
import { createSheetIfNotExists, loadTagsFromSheet } from '@/lib/sheets';

export async function GET(request: Request) {
  const session = await getServerSession(authOptions);
  
  if (!session || !session.accessToken) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const { searchParams } = new URL(request.url);
  const playlistId = searchParams.get('playlistId');

  if (!playlistId) {
    return NextResponse.json({ error: 'Playlist ID required' }, { status: 400 });
  }

  try {
    const videos = await fetchPlaylistVideos(session.accessToken, playlistId);
    
    // Check for Google Sheet Tags
    const sheetId = await createSheetIfNotExists(session.accessToken, `YT_List_Search_Tags_${playlistId}`);
    const tags = await loadTagsFromSheet(session.accessToken, sheetId);
    
    // Merge Tags
    const merged = videos.map(vid => {
      if (tags[vid.video_id]) {
        return { ...vid, custom_category: tags[vid.video_id] };
      }
      return vid;
    });

    return NextResponse.json({ videos: merged });
  } catch (error: any) {
    console.error("GET Videos Error:", error);
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}

export async function DELETE(request: Request) {
  const session = await getServerSession(authOptions);
  if (!session || !session.accessToken) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  const { searchParams } = new URL(request.url);
  const itemId = searchParams.get('itemId');

  if (!itemId) return NextResponse.json({ error: 'Item ID required' }, { status: 400 });

  const { google } = await import('googleapis');
  const yt = google.youtube({ version: 'v3', auth: (() => {
    const auth = new google.auth.OAuth2();
    auth.setCredentials({ access_token: session.accessToken });
    return auth;
  })() });

  try {
    await yt.playlistItems.delete({ id: itemId });
    return NextResponse.json({ success: true });
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}
