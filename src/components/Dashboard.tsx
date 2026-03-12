'use client';

import { useState, useEffect } from 'react';
import { signOut } from 'next-auth/react';
import { Search, Loader2, Play, Trash2, Cpu, RefreshCw, LogOut, ArrowUpDown, ArrowUp, ArrowDown } from 'lucide-react';
import { YouTubeVideo } from '@/lib/youtube';
import { GoogleGenAI } from '@google/genai';

export default function Dashboard() {
  const [playlistId, setPlaylistId] = useState('');
  const [videos, setVideos] = useState<YouTubeVideo[]>([]);
  const [loading, setLoading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [aiFilter, setAiFilter] = useState('All');
  const [ytFilter, setYtFilter] = useState('All');

  const [userGeminiKey, setUserGeminiKey] = useState('');
  const [targetCategoriesInput, setTargetCategoriesInput] = useState('');
  const [forceAllAnalysis, setForceAllAnalysis] = useState(false);

  const [sortConfig, setSortConfig] = useState<{ key: string; direction: 'asc' | 'desc' } | null>(null);

  useEffect(() => {
    const saved = localStorage.getItem('yt_playlist_id');
    if (saved) setPlaylistId(saved);

    const savedKey = localStorage.getItem('user_gemini_key');
    if (savedKey) setUserGeminiKey(savedKey);

    const savedCategories = localStorage.getItem('target_categories');
    if (savedCategories) setTargetCategoriesInput(savedCategories);
    
    // Try to load cached videos
    const cachedVideos = localStorage.getItem('yt_videos_cache');
    if (cachedVideos) {
      try {
        setVideos(JSON.parse(cachedVideos));
      } catch (e) {
        console.error("Failed to parse cached videos", e);
      }
    }
  }, []);

  const loadVideos = async () => {
    if (!playlistId) return;
    setLoading(true);
    localStorage.setItem('yt_playlist_id', playlistId);
    try {
      const res = await fetch(`/api/videos?playlistId=${playlistId}`);
      if (!res.ok) throw new Error('Failed to fetch videos');
      const data = await res.json();
      const fetchedVideos: YouTubeVideo[] = data.videos || [];

      // Build a map of existing local categories to prevent data loss when sheet is empty/unavailable.
      // Priority: server category > local cache category > "General / Unrelated"
      const cachedStr = localStorage.getItem('yt_videos_cache');
      const localCategoryMap: Record<string, string> = {};
      if (cachedStr) {
        try {
          const cached: YouTubeVideo[] = JSON.parse(cachedStr);
          cached.forEach(v => {
            if (v.custom_category && v.custom_category !== 'General / Unrelated') {
              localCategoryMap[v.video_id] = v.custom_category;
            }
          });
        } catch { /* ignore parse errors */ }
      }

      // Merge: if server doesn't know a category but local cache does, keep local.
      const merged = fetchedVideos.map(v => {
        if (v.custom_category && v.custom_category !== 'General / Unrelated') {
          return v; // Server has a real category (from sheet) — trust it
        }
        if (localCategoryMap[v.video_id]) {
          return { ...v, custom_category: localCategoryMap[v.video_id] }; // Use local cache
        }
        return v; // Genuinely uncategorized
      });

      setVideos(merged);
      localStorage.setItem('yt_videos_cache', JSON.stringify(merged));
    } catch (err) {
      alert('Error loading videos');
    } finally {
      setLoading(false);
    }

  };

    const runAiAnalysis = async () => {
    if (videos.length === 0) return;
    if (!userGeminiKey) {
      alert("Please enter your Gemini API Key.");
      return;
    }

    setAnalyzing(true);
    try {
      const targetCategories = targetCategoriesInput.split(',').map(c => c.trim()).filter(Boolean);
      if (targetCategories.length === 0) {
        alert("Please enter at least one target category.");
        return;
      }

      let unmapped = videos;
      if (!forceAllAnalysis) {
        unmapped = videos.filter(v => v.custom_category === 'General / Unrelated');
      }

      if (unmapped.length === 0) {
        alert('All videos already categorized. Enable "Force re-categorize ALL" to redo.');
        return;
      }

      // --- Client-side Gemini call (no Vercel timeout!) ---
      const ai = new GoogleGenAI({ apiKey: userGeminiKey });
      const model = "gemini-2.5-flash";
      const CHUNK_SIZE = 300;
      const delay = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

      const chunks: YouTubeVideo[][] = [];
      for (let i = 0; i < unmapped.length; i += CHUNK_SIZE) {
        chunks.push(unmapped.slice(i, i + CHUNK_SIZE));
      }

      const newTags: Record<string, string> = {};
      const catString = targetCategories.map((c, i) => `${i + 1}. ${c}`).join("\n");
      let debugText = "";
      let geminiError = "";

      for (const chunk of chunks) {
        const videoListStr = chunk.map(v => `ID: ${v.video_id} | Title: ${v.title} | Channel: ${v.channel}`).join("\n");

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
          const response = await ai.models.generateContent({ model, contents: prompt });
          let rawText = response.text || "[]";
          debugText += `\nRaw AI Response chunk:\n${rawText}\n`;

          rawText = rawText.trim();
          if (rawText.startsWith("```json")) rawText = rawText.slice(7, -3);
          else if (rawText.startsWith("```")) rawText = rawText.slice(3, -3);

          const parsed = JSON.parse(rawText.trim());
          if (Array.isArray(parsed)) {
            parsed.forEach((item: any) => {
              if (item.id && item.category && targetCategories.includes(item.category)) {
                newTags[item.id] = item.category;
              }
            });
          }
        } catch (err: any) {
          geminiError = err.message || "Failed to process chunk";
          debugText += `\nError inside chunk: ${geminiError}\n`;
          console.error("Error categorizing chunk:", err);
        }

        if (chunks.length > 1) await delay(4000);
      }
      // --- End Gemini call ---

      const mappedCount = Object.keys(newTags).length;

      if (mappedCount === 0) {
        if (geminiError?.includes('429') || geminiError?.includes('Quota')) {
          alert(`AI Quota Exceeded! You have hit the Gemini Free Tier limit. Please try again tomorrow.`);
        } else {
          console.error("Gemini Debug:", debugText, geminiError);
          alert(`0 videos mapped. Check browser console for Gemini debug trace.`);
        }
        return;
      }

      // Update local state immediately
      setVideos(prev => {
        const updated = prev.map(v =>
          newTags[v.video_id] ? { ...v, custom_category: newTags[v.video_id] } : v
        );
        localStorage.setItem('yt_videos_cache', JSON.stringify(updated));
        return updated;
      });

      // Save to Google Sheet (lightweight API call — no timeout risk)
      const saveRes = await fetch('/api/videos/categorize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ videos, playlistId, newTags })
      });
      const saveData = await saveRes.json();

      if (!saveRes.ok) {
        alert(`AI categorized ${mappedCount} videos, but failed to save to Google Sheet: ${saveData.error}`);
      } else {
        alert(`Successfully categorized ${mappedCount} videos and saved to Google Sheet!`);
      }
    } catch (err) {
      alert('Failed to run AI analysis. Check the console for details.');
      console.error("runAiAnalysis error:", err);
    } finally {
      setAnalyzing(false);
    }
  };

  const removeVideo = async (playlistItemId: string) => {
    if (!confirm('Are you sure you want to remove this video from your YouTube list?')) return;
    
    // Optimistic UI update
    setVideos(prev => {
      const updated = prev.filter(v => v.playlist_item_id !== playlistItemId);
      localStorage.setItem('yt_videos_cache', JSON.stringify(updated));
      return updated;
    });

    try {
      await fetch(`/api/videos?itemId=${playlistItemId}`, { method: 'DELETE' });
    } catch (err) {
      alert('Failed to delete video. Please refresh.');
    }
  };

  const handleSort = (key: string) => {
    let direction: 'asc' | 'desc' = 'asc';
    if (sortConfig && sortConfig.key === key && sortConfig.direction === 'asc') {
      direction = 'desc';
    }
    setSortConfig({ key, direction });
  };

  // derived state
  const targetCategories = targetCategoriesInput.split(',').map(c => c.trim()).filter(Boolean);
  // AI filter options: combine categories from textarea AND actual video data
  // so filters work even when the textarea is empty (e.g. on a fresh page load with cached data)
  const categoriesFromVideos = Array.from(new Set(videos.map(v => v.custom_category).filter(c => c && c !== 'General / Unrelated')));
  const allAiCategories = Array.from(new Set([...targetCategories, ...categoriesFromVideos])).sort();
  const aiOptions = ['All', 'General / Unrelated', ...allAiCategories];
  
  const ytOptions = ['All', ...Array.from(new Set(videos.map(v => v.yt_category)))].sort();

  let filteredVideos = videos.filter(v => {
    // Remove formatting like spaces for robust searching
    const sanitizedSearch = searchQuery.toLowerCase().replace(/\s+/g, '');
    const sanitizedTitle = v.title.toLowerCase().replace(/\s+/g, '');
    const sanitizedChannel = v.channel.toLowerCase().replace(/\s+/g, '');
    
    const matchesSearch = sanitizedTitle.includes(sanitizedSearch) || 
                          sanitizedChannel.includes(sanitizedSearch);
                          
    const matchesAiFilter = aiFilter === 'All' || v.custom_category === aiFilter;
    const matchesYtFilter = ytFilter === 'All' || v.yt_category === ytFilter;
    
    return matchesSearch && matchesAiFilter && matchesYtFilter;
  });

  if (sortConfig !== null) {
    filteredVideos.sort((a, b) => {
      let valA = '';
      let valB = '';
      
      if (sortConfig.key === 'channel') {
        valA = a.channel; valB = b.channel;
      } else if (sortConfig.key === 'yt_category') {
        valA = a.yt_category; valB = b.yt_category;
      } else if (sortConfig.key === 'custom_category') {
        valA = a.custom_category; valB = b.custom_category;
      }

      if (valA < valB) return sortConfig.direction === 'asc' ? -1 : 1;
      if (valA > valB) return sortConfig.direction === 'asc' ? 1 : -1;
      return 0;
    });
  }

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-white">
      {/* Header Bar */}
      <header className="sticky top-0 z-50 bg-[#111111]/80 backdrop-blur-md border-b border-[#333333] px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded bg-[#1a1a1a] border border-[#333] flex items-center justify-center">
            <Play className="w-4 h-4 text-[#00ff41]" />
          </div>
          <h1 className="font-bold tracking-tight text-lg">Playlist Dashboard</h1>
        </div>
        
        <div className="flex items-center gap-4">
          <button onClick={() => signOut()} className="flex items-center gap-2 text-sm text-[#888] hover:text-white transition-colors">
            <LogOut className="w-4 h-4" /> Disconnect
          </button>
        </div>
      </header>

      <main className="p-6 max-w-[1600px] mx-auto space-y-6">
        
        {/* Controls Section */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 bg-[#111] border border-[#222] rounded-xl p-5 space-y-4">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-[#00ff41]">Source Configuration</h2>
            <div className="flex gap-3">
              <input 
                type="text" 
                placeholder="Enter YouTube Playlist ID" 
                value={playlistId}
                onChange={e => setPlaylistId(e.target.value)}
                className="flex-1 bg-[#1a1a1a] border border-[#333] rounded-lg px-4 py-2 text-sm focus:outline-none focus:border-[#00ff41] transition-colors"
               />
               <button 
                  onClick={loadVideos}
                  disabled={loading || !playlistId}
                  className="bg-[#222] hover:bg-[#333] border border-[#444] text-white px-6 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 flex items-center gap-2"
                >
                 {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
                 {videos.length > 0 ? "Sync from YouTube" : "Load Videos"}
               </button>
            </div>
            <div className="flex flex-col gap-2">
              <label className="text-xs text-[#888]">Your Gemini API Key (Stored Locally)</label>
              <input 
                type="password"
                placeholder="AIzaSy..." 
                value={userGeminiKey}
                onChange={e => {
                  setUserGeminiKey(e.target.value);
                  localStorage.setItem('user_gemini_key', e.target.value);
                }}
                className="w-full bg-[#1a1a1a] border border-[#333] rounded-lg px-4 py-2 text-sm focus:outline-none focus:border-[#00ff41] transition-colors"
                autoComplete="new-password"
              />
            </div>
            
            <div className="flex flex-col gap-2">
              <label className="text-xs text-[#888]">Target AI Categories (comma separated)</label>
              <textarea 
                value={targetCategoriesInput}
                onChange={e => {
                  setTargetCategoriesInput(e.target.value);
                  localStorage.setItem('target_categories', e.target.value);
                }}
                placeholder="e.g. Technology, Politics, Music, Gaming"
                className="w-full bg-[#1a1a1a] border border-[#333] rounded-lg px-4 py-2 text-sm focus:outline-none focus:border-[#00ff41] transition-colors min-h-[60px]"
              />
            </div>
          </div>

          {/* Stats & AI Trigger */}
          <div className="bg-[#111] border border-[#222] rounded-xl p-5 flex flex-col justify-between">
            <div className="space-y-4">
              <h2 className="text-sm font-semibold uppercase tracking-wider text-[#00ff41]">Intelligence Processing</h2>
              <div className="grid grid-cols-2 gap-4">
                <div className="bg-[#1a1a1a] rounded-lg p-3 border border-[#333]">
                  <div className="text-2xl font-bold">{videos.length}</div>
                  <div className="text-xs text-[#888]">Total Tracks</div>
                </div>
                <div className="bg-[#1a1a1a] rounded-lg p-3 border border-[#333]">
                  <div className="text-2xl font-bold text-[#00ff41]">
                    {videos.filter(v => v.custom_category !== 'General / Unrelated').length}
                  </div>
                  <div className="text-xs text-[#888]">Categorized</div>
                </div>
              </div>
            </div>
            
            <div className="flex flex-col gap-3 mt-4">
              <label className="flex items-center gap-2 text-xs text-[#888] cursor-pointer hover:text-white transition-colors">
                <input 
                  type="checkbox" 
                  checked={forceAllAnalysis}
                  onChange={e => setForceAllAnalysis(e.target.checked)}
                  className="rounded border-[#333] bg-[#1a1a1a] text-[#00ff41] focus:ring-[#00ff41] focus:ring-offset-[#111]"
                />
                Force re-categorize ALL videos (Ignores previous tags)
              </label>
              <button 
                onClick={runAiAnalysis}
                disabled={analyzing || videos.length === 0}
                className="w-full bg-[#00ff41]/10 hover:bg-[#00ff41]/20 text-[#00ff41] border border-[#00ff41]/50 py-3 rounded-lg text-sm font-semibold transition-all flex items-center justify-center gap-2 disabled:opacity-50"
              >
                {analyzing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Cpu className="w-4 h-4" />}
                {analyzing ? 'Analyzing Batch...' : 'Run Gemini AI Analysis'}
              </button>
            </div>
          </div>
        </div>

        {/* Filters */}
        {videos.length > 0 && (
          <div className="flex flex-col md:flex-row gap-4">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#666]" />
              <input 
                type="text" 
                placeholder="Search titles or channels..." 
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                className="w-full bg-[#111] border border-[#222] rounded-lg pl-10 pr-4 py-3 text-sm focus:outline-none focus:border-[#333] transition-colors"
                />
            </div>
            


            <select 
              value={ytFilter}
              onChange={e => setYtFilter(e.target.value)}
              className="bg-[#111] border border-[#222] rounded-lg px-4 py-3 text-sm focus:outline-none min-w-[200px]"
              title="YouTube Category"
            >
              <option value="All" disabled hidden>YouTube Category</option>
              {ytOptions.map(opt => <option key={`yt-${opt}`} value={opt}>{opt === 'All' ? 'All YT Categories' : opt}</option>)}
            </select>

            <select 
              value={aiFilter}
              onChange={e => setAiFilter(e.target.value)}
              className="bg-[#111] border border-[#222] rounded-lg px-4 py-3 text-sm focus:outline-none min-w-[200px]"
              title="AI Category"
            >
              <option value="All" disabled hidden>AI Category</option>
              {aiOptions.map(opt => <option key={`ai-${opt}`} value={opt}>{opt === 'All' ? 'All AI Categories' : opt}</option>)}
            </select>
          </div>
        )}

        {/* Data Grid */}
        {videos.length > 0 && (
          <div className="bg-[#111] border border-[#222] rounded-xl overflow-hidden overflow-x-auto">
            <table className="w-full text-left border-collapse min-w-[800px]">
              <thead>
                <tr className="border-b border-[#222] bg-[#1a1a1a] text-[#888] text-xs uppercase tracking-wider">
                  <th className="p-4 font-medium">Cover</th>
                  <th 
                    className="p-4 font-medium w-1/3 cursor-pointer hover:text-[#00ff41] transition-colors group"
                    onClick={() => handleSort('channel')}
                  >
                    <div className="flex items-center gap-1">
                      Subject
                      {sortConfig?.key === 'channel' ? (
                        sortConfig.direction === 'asc' ? <ArrowUp className="w-3 h-3" /> : <ArrowDown className="w-3 h-3" />
                      ) : (
                        <ArrowUpDown className="w-3 h-3 opacity-0 group-hover:opacity-50" />
                      )}
                    </div>
                  </th>
                  <th 
                    className="p-4 font-medium cursor-pointer hover:text-[#00ff41] transition-colors group"
                    onClick={() => handleSort('yt_category')}
                  >
                    <div className="flex items-center gap-1">
                      YouTube Cat
                      {sortConfig?.key === 'yt_category' ? (
                        sortConfig.direction === 'asc' ? <ArrowUp className="w-3 h-3" /> : <ArrowDown className="w-3 h-3" />
                      ) : (
                        <ArrowUpDown className="w-3 h-3 opacity-0 group-hover:opacity-50" />
                      )}
                    </div>
                  </th>
                  <th 
                    className="p-4 font-medium cursor-pointer hover:text-[#00ff41] transition-colors group"
                    onClick={() => handleSort('custom_category')}
                  >
                    <div className="flex items-center gap-1">
                      AI Category
                      {sortConfig?.key === 'custom_category' ? (
                        sortConfig.direction === 'asc' ? <ArrowUp className="w-3 h-3" /> : <ArrowDown className="w-3 h-3" />
                      ) : (
                        <ArrowUpDown className="w-3 h-3 opacity-0 group-hover:opacity-50" />
                      )}
                    </div>
                  </th>
                  <th className="p-4 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#222]">
                {filteredVideos.map((video) => (
                  <tr key={video.playlist_item_id} className="hover:bg-[#1a1a1a]/50 transition-colors group">
                    <td className="p-4">
                      <div className="w-24 h-16 rounded-md bg-[#222] overflow-hidden relative border border-[#333]">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        {video.thumbnail ? (
                          <img src={video.thumbnail} alt={video.title} className="object-cover w-full h-full" />
                        ) : (
                          <div className="w-full h-full flex items-center justify-center text-[#444]">
                            <Play className="w-4 h-4" />
                          </div>
                        )}
                      </div>
                    </td>
                    <td className="p-4">
                      <a href={`https://youtube.com/watch?v=${video.video_id}`} target="_blank" rel="noopener noreferrer" className="font-medium hover:text-[#00ff41] transition-colors line-clamp-2">
                        {video.title}
                      </a>
                      <div className="text-sm text-[#888] mt-1">{video.channel}</div>
                    </td>
                    <td className="p-4">
                      <span className="text-xs bg-[#222] text-[#aaa] px-2 py-1 rounded-md border border-[#333]">{video.yt_category}</span>
                    </td>
                    <td className="p-4">
                      <span className={`inline-flex items-center text-xs px-2.5 py-1 rounded-full font-medium ${
                        video.custom_category !== 'General / Unrelated' 
                          ? 'bg-[#00ff41]/10 text-[#00ff41] border border-[#00ff41]/30' 
                          : 'bg-[#222] text-[#888] border border-[#333]'
                      }`}>
                        {video.custom_category}
                      </span>
                    </td>
                    <td className="p-4 text-right">
                      <button 
                        onClick={() => removeVideo(video.playlist_item_id)}
                        className="opacity-0 group-hover:opacity-100 p-2 text-[#666] hover:text-red-500 hover:bg-red-500/10 rounded-md transition-all"
                        title="Remove from Playlist"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            
            {filteredVideos.length === 0 && (
              <div className="p-12 text-center text-[#666]">
                No records matching active filters.
              </div>
            )}
          </div>
        )}

        {videos.length === 0 && !loading && (
          <div className="border border-dashed border-[#333] rounded-xl p-16 flex flex-col items-center justify-center text-center mt-10">
            <div className="w-16 h-16 bg-[#1a1a1a] border border-[#222] rounded-full flex items-center justify-center mb-4">
              <Play className="w-6 h-6 text-[#444]" />
            </div>
            <h3 className="text-lg font-medium text-white">No active feeds</h3>
            <p className="text-[#666] mt-2 max-w-md">Enter a legitimate YouTube Playlist ID in the configuration panel above to establish a video array uplink.</p>
          </div>
        )}

      </main>
    </div>
  );
}
