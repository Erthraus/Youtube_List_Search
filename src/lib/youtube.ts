import { google } from "googleapis";

export interface YouTubeVideo {
  playlist_item_id: string;
  video_id: string;
  thumbnail: string;
  title: string;
  channel: string;
  yt_category: string;
  custom_category: string;
}

const getYouTubeClient = (accessToken: string) => {
  const auth = new google.auth.OAuth2();
  auth.setCredentials({ access_token: accessToken });
  return google.youtube({ version: "v3", auth });
};

async function getCategoryMapping(accessToken: string): Promise<Record<string, string>> {
  const yt = getYouTubeClient(accessToken);
  const response: any = await yt.videoCategories.list({ part: ["snippet"], regionCode: "US" });
  const map: Record<string, string> = {};
  response.data.items?.forEach((item: any) => {
    if (item.id && item.snippet?.title) {
      map[item.id] = item.snippet.title;
    }
  });
  return map;
}

async function fetchCategoriesForVideos(accessToken: string, videoIds: string[], categoryMap: Record<string, string>) {
  const yt = getYouTubeClient(accessToken);
  const chunkedIds = [];
  for (let i = 0; i < videoIds.length; i += 50) {
    chunkedIds.push(videoIds.slice(i, i + 50));
  }
  
  const idToCatMap: Record<string, string> = {};
  
  await Promise.all(chunkedIds.map(async (chunk) => {
    const res: any = await yt.videos.list({ part: ["snippet"], id: chunk });
    res.data.items?.forEach((item: any) => {
      if (item.id && item.snippet?.categoryId) {
         idToCatMap[item.id] = categoryMap[item.snippet.categoryId] || "Other";
      }
    });
  }));
  
  return idToCatMap;
}

export async function fetchPlaylistVideos(accessToken: string, playlistId: string): Promise<YouTubeVideo[]> {
  const yt = getYouTubeClient(accessToken);
  let pageToken: string | undefined | null = undefined;
  const videos: YouTubeVideo[] = [];
  
  const categoryMap = await getCategoryMapping(accessToken);

  do {
    const res: any = await yt.playlistItems.list({
      part: ["snippet"],
      playlistId,
      maxResults: 50,
      pageToken: pageToken || undefined
    });

    res.data.items?.forEach((item: any) => {
      const vidId = item.snippet?.resourceId?.videoId;
      if (vidId) {
        videos.push({
          playlist_item_id: item.id || "",
          video_id: vidId,
          title: item.snippet?.title || "Unknown",
          channel: item.snippet?.videoOwnerChannelTitle || "Unknown",
          thumbnail: item.snippet?.thumbnails?.default?.url || "",
          yt_category: "Unknown",
          custom_category: "General / Unrelated"
        });
      }
    });
    pageToken = res.data.nextPageToken;
  } while (pageToken);

  // Fetch Youtube Categories in parallel batches
  const ytCategoryMap = await fetchCategoriesForVideos(accessToken, videos.map(v => v.video_id), categoryMap);
  
  return videos.map(v => ({
    ...v,
    yt_category: ytCategoryMap[v.video_id] || "Unknown"
  }));
}

export async function deletePlaylistItem(accessToken: string, playlistItemId: string) {
  const yt = getYouTubeClient(accessToken);
  await yt.playlistItems.delete({ id: playlistItemId });
  return true;
}
