import { GoogleGenAI } from "@google/genai";
import { YouTubeVideo } from "./youtube";

export async function categorizeVideosWithAI(
  videos: YouTubeVideo[], 
  targetCategories: string[]
): Promise<{ tags: Record<string, string>, debugText: string, error?: string }> {
  if (videos.length === 0) return { tags: {}, debugText: "No videos provided" };
  
  let debugText = "";
  let errorMsg = "";
  const results: Record<string, string> = {};

  try {
    const apiKey = process.env.GEMINI_API_KEY;
    if (!apiKey || apiKey === 'your_gemini_api_key') {
      throw new Error("GEMINI_API_KEY is missing or invalid in .env.local. Did you forget to restart the Next.js server?");
    }
  
    const ai = new GoogleGenAI({ apiKey });
    const model = "gemini-2.5-flash";
    // Increased chunk size from 50 to 300 to drastically reduce the number of API calls 
    // and easily stay under the 20 requests per day / 15 requests per minute Free Tier quota.
    const CHUNK_SIZE = 300; 
    
    const chunks = [];
    
    for (let i = 0; i < videos.length; i += CHUNK_SIZE) {
      chunks.push(videos.slice(i, i + CHUNK_SIZE));
    }
    
    const catString = targetCategories.map((c, i) => `${i + 1}. ${c}`).join("\\n");
    const delay = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

    for (const chunk of chunks) {
      const videoListStr = chunk.map(v => `ID: ${v.video_id} | Title: ${v.title} | Channel: ${v.channel}`).join("\\n");
      
      const prompt = `
        Below is a list of YouTube videos. Identify ONLY the videos that fit into these target categories:
        ${catString}
        
        If a video does not fit, completely IGNORE it.
        Respond ONLY in valid JSON array format mapping the parsed items.
        Example: [{"id": "video_id", "category": "CategoryName"}]
        
        Video List:
        ${videoListStr}
      `;

      try {
        const response = await ai.models.generateContent({
          model: model,
          contents: prompt
        });
        
        let rawText = response.text || "[]";
        debugText += `\nRaw AI Response chunk: ${rawText}\n`;
        
        rawText = rawText.trim();
        if (rawText.startsWith("\`\`\`json")) rawText = rawText.slice(7, -3);
        else if (rawText.startsWith("\`\`\`")) rawText = rawText.slice(3, -3);
        
        const parsed = JSON.parse(rawText.trim());
        if (Array.isArray(parsed)) {
          parsed.forEach((item: any) => {
            if (item.id && item.category && targetCategories.includes(item.category)) {
              results[item.id] = item.category;
            }
          });
        }
      } catch (err: any) {
        errorMsg = err.message || "Failed to process chunk";
        debugText += `\nError inside chunk: ${errorMsg}\n`;
        console.error("Error categorizing chunk:", err);
      }
      
      // Free tier rate limit is 15 requests per minute. 
      // Add a 4 second buffer (60s / 15) between requests to avoid overlapping 429 quota exhaustion.
      if (chunks.length > 1) {
        await delay(4000);
      }
    }
  } catch (err: any) {
    errorMsg = err.message || "Global initialization error";
    debugText += `\nGlobal Error: ${errorMsg}\n`;
  }

  return { tags: results, debugText, error: errorMsg };
}
