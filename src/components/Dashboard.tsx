'use client';

import { useState, useEffect } from 'react';
import { useSession, signOut } from 'next-auth/react';
import {
  Search, Loader2, Play, Trash2, Cpu, RefreshCw, LogOut,
  ArrowUpDown, ArrowUp, ArrowDown, Download, Plus, X, AlertTriangle,
  ChevronDown, BarChart2, Save
} from 'lucide-react';
import { YouTubeVideo } from '@/lib/youtube';
import { GoogleGenAI } from '@google/genai';

// ─── Types ────────────────────────────────────────────────────────────────────

interface SavedPlaylist {
  id: string;
  label: string; // user-defined nickname or just the ID
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function Dashboard() {
  const { data: session } = useSession();

  // Core state
  const [playlistId, setPlaylistId]   = useState('');
  const [videos, setVideos]           = useState<YouTubeVideo[]>([]);
  const [loading, setLoading]         = useState(false);
  const [loadingStatus, setLoadingStatus] = useState('');   // sync progress text
  const [analyzing, setAnalyzing]     = useState(false);
  const [analysisStatus, setAnalysisStatus] = useState(''); // chunk progress text

  // Filters / search
  const [searchQuery, setSearchQuery] = useState('');
  const [aiFilter, setAiFilter]       = useState('All');
  const [ytFilter, setYtFilter]       = useState('All');

  // Configuration
  const [userGeminiKey, setUserGeminiKey]           = useState('');
  const [targetCategoriesInput, setTargetCategoriesInput] = useState('');
  const [forceAllAnalysis, setForceAllAnalysis]     = useState(false);

  // Multi-playlist
  const [savedPlaylists, setSavedPlaylists] = useState<SavedPlaylist[]>([]);
  const [playlistDropdownOpen, setPlaylistDropdownOpen] = useState(false);

  // Sort
  const [sortConfig, setSortConfig] = useState<{ key: string; direction: 'asc' | 'desc' } | null>(null);

  // Saving state and status
  const [saving, setSaving] = useState(false);
  const [showStats, setShowStats] = useState(false);

  // ── Load persisted state ────────────────────────────────────────────────────
  useEffect(() => {
    const saved = localStorage.getItem('yt_playlist_id');
    if (saved) setPlaylistId(saved);

    const savedKey = localStorage.getItem('user_gemini_key');
    if (savedKey) setUserGeminiKey(savedKey);

    const savedCategories = localStorage.getItem('target_categories');
    if (savedCategories) setTargetCategoriesInput(savedCategories);

    const savedLists = localStorage.getItem('yt_playlist_history');
    if (savedLists) {
      try { setSavedPlaylists(JSON.parse(savedLists)); } catch {}
    }

    const cachedVideos = localStorage.getItem('yt_videos_cache');
    if (cachedVideos) {
      try { setVideos(JSON.parse(cachedVideos)); } catch {}
    }
  }, []);

  // ── Multi-playlist helpers ──────────────────────────────────────────────────
  const saveCurrentPlaylist = () => {
    if (!playlistId) return;
    const existing = savedPlaylists.find(p => p.id === playlistId);
    if (existing) return; // already saved
    const updated = [...savedPlaylists, { id: playlistId, label: playlistId }];
    setSavedPlaylists(updated);
    localStorage.setItem('yt_playlist_history', JSON.stringify(updated));
  };

  const switchPlaylist = (id: string) => {
    setPlaylistId(id);
    localStorage.setItem('yt_playlist_id', id);
    setVideos([]);
    setPlaylistDropdownOpen(false);
    // Load cached videos for this playlist if available
    const key = `yt_videos_cache_${id}`;
    const cached = localStorage.getItem(key) || localStorage.getItem('yt_videos_cache');
    if (cached) {
      try { setVideos(JSON.parse(cached)); } catch {}
    }
  };

  const removePlaylist = (id: string) => {
    const updated = savedPlaylists.filter(p => p.id !== id);
    setSavedPlaylists(updated);
    localStorage.setItem('yt_playlist_history', JSON.stringify(updated));
  };

  // ── Load videos ─────────────────────────────────────────────────────────────
  const loadVideos = async () => {
    if (!playlistId) return;
    setLoading(true);
    setLoadingStatus('Connecting to YouTube...');
    localStorage.setItem('yt_playlist_id', playlistId);
    saveCurrentPlaylist();

    try {
      const res = await fetch(`/api/videos?playlistId=${playlistId}`);
      if (!res.ok) throw new Error('Failed to fetch videos');
      const data = await res.json();
      const fetchedVideos: YouTubeVideo[] = data.videos || [];

      setLoadingStatus(`Merging ${fetchedVideos.length} videos with local cache...`);

      // Merge: keep local cached categories when sheet is empty / unavailable
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
        } catch { /* ignore */ }
      }

      const merged = fetchedVideos.map(v => {
        if (v.custom_category && v.custom_category !== 'General / Unrelated') return v;
        if (localCategoryMap[v.video_id]) return { ...v, custom_category: localCategoryMap[v.video_id] };
        return v;
      });

      setVideos(merged);
      localStorage.setItem('yt_videos_cache', JSON.stringify(merged));
      setLoadingStatus(`Loaded ${merged.length} videos`);
    } catch (err) {
      alert('Error loading videos. Check the console.');
      console.error(err);
      setLoadingStatus('');
    } finally {
      setLoading(false);
      setTimeout(() => setLoadingStatus(''), 3000);
    }
  };

  // ── AI Analysis ─────────────────────────────────────────────────────────────
  const runAiAnalysis = async () => {
    if (videos.length === 0) return;
    if (!userGeminiKey) { alert('Please enter your Gemini API Key.'); return; }

    setAnalyzing(true);
    try {
      const targetCategories = targetCategoriesInput.split(',').map(c => c.trim()).filter(Boolean);
      if (targetCategories.length === 0) {
        alert('Please enter at least one target category.');
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

      // Client-side Gemini call (no Vercel timeout!)
      const ai        = new GoogleGenAI({ apiKey: userGeminiKey });
      const model     = 'gemini-2.5-flash';
      const CHUNK_SIZE = 300;
      const delay     = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

      const chunks: YouTubeVideo[][] = [];
      for (let i = 0; i < unmapped.length; i += CHUNK_SIZE) {
        chunks.push(unmapped.slice(i, i + CHUNK_SIZE));
      }

      const newTags: Record<string, string> = {};
      const catString  = targetCategories.map((c, i) => `${i + 1}. ${c}`).join('\n');
      let debugText    = '';
      let geminiError  = '';

      for (let ci = 0; ci < chunks.length; ci++) {
        const chunk = chunks[ci];
        setAnalysisStatus(`Analyzing chunk ${ci + 1} of ${chunks.length} (${chunk.length} videos)...`);

        const videoListStr = chunk
          .map(v => `ID: ${v.video_id} | Title: ${v.title} | Channel: ${v.channel}`)
          .join('\n');

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
          let rawText = response.text || '[]';
          debugText += `\nRaw AI Response chunk:\n${rawText}\n`;

          rawText = rawText.trim();
          if (rawText.startsWith('```json')) rawText = rawText.slice(7, -3);
          else if (rawText.startsWith('```'))  rawText = rawText.slice(3, -3);

          const parsed = JSON.parse(rawText.trim());
          if (Array.isArray(parsed)) {
            parsed.forEach((item: any) => {
              if (item.id && item.category && targetCategories.includes(item.category)) {
                newTags[item.id] = item.category;
              }
            });
          }
        } catch (err: any) {
          geminiError = err.message || 'Failed to process chunk';
          debugText  += `\nError inside chunk: ${geminiError}\n`;
          console.error('Error categorizing chunk:', err);
        }

        if (ci < chunks.length - 1) {
          setAnalysisStatus(`Chunk ${ci + 1} done. Waiting before next request...`);
          await delay(4000);
        }
      }

      const mappedCount = Object.keys(newTags).length;

      if (mappedCount === 0) {
        if (geminiError?.includes('429') || geminiError?.includes('Quota')) {
          alert('AI Quota Exceeded! You have hit the Gemini Free Tier limit. Try again tomorrow.');
        } else {
          console.error('Gemini Debug:', debugText, geminiError);
          alert('0 videos mapped. Check browser console for Gemini debug trace.');
        }
        return;
      }

      setAnalysisStatus('Saving tags to Google Sheet...');

      // Update local state immediately
      setVideos(prev => {
        const updated = prev.map(v =>
          newTags[v.video_id] ? { ...v, custom_category: newTags[v.video_id] } : v
        );
        localStorage.setItem('yt_videos_cache', JSON.stringify(updated));
        return updated;
      });

      // Save to Google Sheet
      const saveRes = await fetch('/api/videos/categorize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ videos, playlistId, newTags }),
      });
      const saveData = await saveRes.json();

      if (!saveRes.ok) {
        alert(`AI categorized ${mappedCount} videos, but failed to save to Google Sheet: ${saveData.error}`);
      } else {
        alert(`Successfully categorized ${mappedCount} videos and saved to Google Sheet!`);
      }
    } catch (err) {
      alert('Failed to run AI analysis. Check the console for details.');
      console.error('runAiAnalysis error:', err);
    } finally {
      setAnalyzing(false);
      setAnalysisStatus('');
    }
  };

  // ── Save current categories to Sheet (without re-running AI) ──────────────
  const saveToSheet = async () => {
    const categorized = videos.filter(v => v.custom_category !== 'General / Unrelated');
    if (categorized.length === 0) { alert('No categorized videos to save.'); return; }
    if (!playlistId) { alert('No playlist loaded.'); return; }
    setSaving(true);
    try {
      const newTags: Record<string, string> = {};
      categorized.forEach(v => { newTags[v.video_id] = v.custom_category; });
      const res = await fetch('/api/videos/categorize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ videos, playlistId, newTags }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Unknown error');
      alert(`Saved ${data.savedCount} categories to Google Sheet!`);
    } catch (err: any) {
      alert(`Failed to save: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  // ── CSV Export ────────────────────────────────────────────────────────────
  const exportCSV = () => {
    const header = ['Video ID', 'Title', 'Channel', 'YouTube Category', 'AI Category', 'URL'];
    const rows = videos.map(v => [
      v.video_id,
      `"${v.title.replace(/"/g, '""')}"`,
      `"${v.channel.replace(/"/g, '""')}"`,
      v.yt_category,
      v.custom_category,
      `https://youtube.com/watch?v=${v.video_id}`,
    ]);
    const csv = [header, ...rows].map(r => r.join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href = url;
    a.download = `playlist_${playlistId}_${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // ── Remove video ────────────────────────────────────────────────────────────
  const removeVideo = async (playlistItemId: string) => {
    if (!confirm('Remove this video from your YouTube playlist?')) return;
    setVideos(prev => {
      const updated = prev.filter(v => v.playlist_item_id !== playlistItemId);
      localStorage.setItem('yt_videos_cache', JSON.stringify(updated));
      return updated;
    });
    try {
      await fetch(`/api/videos?itemId=${playlistItemId}`, { method: 'DELETE' });
    } catch { alert('Failed to delete video. Please refresh.'); }
  };

  // ── Sort ────────────────────────────────────────────────────────────────────
  const handleSort = (key: string) => {
    const direction = sortConfig?.key === key && sortConfig.direction === 'asc' ? 'desc' : 'asc';
    setSortConfig({ key, direction });
  };

  // ── Derived / computed ──────────────────────────────────────────────────────
  const targetCategories    = targetCategoriesInput.split(',').map(c => c.trim()).filter(Boolean);
  const categoriesFromVideos = Array.from(new Set(
    videos.map(v => v.custom_category).filter(c => c && c !== 'General / Unrelated')
  ));
  const allAiCategories = Array.from(new Set([...targetCategories, ...categoriesFromVideos])).sort();
  const aiOptions       = ['All', 'General / Unrelated', ...allAiCategories];
  const ytOptions       = ['All', ...Array.from(new Set(videos.map(v => v.yt_category)))].sort();

  // Category stats: { category: count }
  const categoryStats = videos.reduce<Record<string, number>>((acc, v) => {
    const cat = v.custom_category || 'General / Unrelated';
    acc[cat] = (acc[cat] || 0) + 1;
    return acc;
  }, {});
  const categorizedCount = videos.filter(v => v.custom_category !== 'General / Unrelated').length;

  let filteredVideos = videos.filter(v => {
    const s  = searchQuery.toLowerCase().replace(/\s+/g, '');
    const ok = v.title.toLowerCase().replace(/\s+/g, '').includes(s) ||
               v.channel.toLowerCase().replace(/\s+/g, '').includes(s);
    return ok &&
      (aiFilter === 'All' || v.custom_category === aiFilter) &&
      (ytFilter === 'All' || v.yt_category   === ytFilter);
  });

  if (sortConfig) {
    filteredVideos = [...filteredVideos].sort((a, b) => {
      const map: Record<string, keyof YouTubeVideo> = {
        channel: 'channel', yt_category: 'yt_category', custom_category: 'custom_category',
      };
      const field = map[sortConfig.key];
      const va = field ? String(a[field]) : '';
      const vb = field ? String(b[field]) : '';
      return va < vb ? (sortConfig.direction === 'asc' ? -1 : 1) :
             va > vb ? (sortConfig.direction === 'asc' ?  1 : -1) : 0;
    });
  }

  const SortIcon = ({ col }: { col: string }) =>
    sortConfig?.key === col
      ? sortConfig.direction === 'asc' ? <ArrowUp className="w-3 h-3" /> : <ArrowDown className="w-3 h-3" />
      : <ArrowUpDown className="w-3 h-3 opacity-0 group-hover:opacity-50" />;

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-[#0a0a0a] text-white">

      {/* ── Session Error Banner ─────────────────────────────────────────── */}
      {session?.error === 'RefreshAccessTokenError' && (
        <div className="bg-red-900/60 border-b border-red-700 px-6 py-3 flex items-center gap-3 text-sm">
          <AlertTriangle className="w-4 h-4 text-red-400 shrink-0" />
          <span className="text-red-200">Oturumunun süresi doldu. Google API çağrıları başarısız olabilir.</span>
          <button
            onClick={() => signOut()}
            className="ml-auto text-red-300 hover:text-white underline"
          >
            Yeniden giriş yap
          </button>
        </div>
      )}

      {/* ── Header ──────────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-50 bg-[#111111]/80 backdrop-blur-md border-b border-[#333333] px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded bg-[#1a1a1a] border border-[#333] flex items-center justify-center">
            <Play className="w-4 h-4 text-[#00ff41]" />
          </div>
          <h1 className="font-bold tracking-tight text-lg">Playlist Dashboard</h1>
        </div>

        <div className="flex items-center gap-3">
          {videos.length > 0 && (
            <>
              <button
                onClick={() => setShowStats(s => !s)}
                className={`flex items-center gap-2 text-sm transition-colors ${showStats ? 'text-[#00ff41]' : 'text-[#888] hover:text-white'}`}
                title="Toggle category stats"
              >
                <BarChart2 className="w-4 h-4" />
                <span className="hidden sm:inline">Stats</span>
              </button>
              <button
                onClick={exportCSV}
                className="flex items-center gap-2 text-sm text-[#888] hover:text-white transition-colors"
                title="Export as CSV"
              >
                <Download className="w-4 h-4" />
                <span className="hidden sm:inline">Export CSV</span>
              </button>
            </>
          )}
          <button onClick={() => signOut()} className="flex items-center gap-2 text-sm text-[#888] hover:text-white transition-colors">
            <LogOut className="w-4 h-4" /> <span className="hidden sm:inline">Disconnect</span>
          </button>
        </div>
      </header>

      <main className="p-6 max-w-[1600px] mx-auto space-y-6">

        {/* ── Controls ──────────────────────────────────────────────────── */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

          {/* Source Config */}
          <div className="lg:col-span-2 bg-[#111] border border-[#222] rounded-xl p-5 space-y-4">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-[#00ff41]">Source Configuration</h2>

            {/* Playlist input + saved dropdown */}
            <div className="flex gap-2">
              <div className="relative flex-1">
                <input
                  type="text"
                  placeholder="Enter YouTube Playlist ID"
                  value={playlistId}
                  onChange={e => setPlaylistId(e.target.value)}
                  className="w-full bg-[#1a1a1a] border border-[#333] rounded-lg px-4 py-2 text-sm focus:outline-none focus:border-[#00ff41] transition-colors pr-10"
                />
                {savedPlaylists.length > 0 && (
                  <div className="absolute right-0 top-0 h-full">
                    <button
                      onClick={() => setPlaylistDropdownOpen(o => !o)}
                      className="h-full px-3 text-[#666] hover:text-white transition-colors border-l border-[#333]"
                      title="Saved playlists"
                    >
                      <ChevronDown className="w-4 h-4" />
                    </button>
                    {playlistDropdownOpen && (
                      <div className="absolute right-0 top-full mt-1 bg-[#1a1a1a] border border-[#333] rounded-lg overflow-hidden z-10 min-w-[280px] shadow-xl">
                        {savedPlaylists.map(p => (
                          <div key={p.id} className="flex items-center gap-2 px-3 py-2 hover:bg-[#222] group">
                            <button
                              onClick={() => switchPlaylist(p.id)}
                              className="flex-1 text-left text-sm text-[#ccc] truncate"
                            >
                              {p.label}
                            </button>
                            <button
                              onClick={() => removePlaylist(p.id)}
                              className="opacity-0 group-hover:opacity-100 text-[#555] hover:text-red-400 transition-all"
                            >
                              <X className="w-3 h-3" />
                            </button>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>

              <button
                onClick={loadVideos}
                disabled={loading || !playlistId}
                className="bg-[#222] hover:bg-[#333] border border-[#444] text-white px-5 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 flex items-center gap-2 shrink-0"
              >
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
                {videos.length > 0 ? 'Sync' : 'Load'}
              </button>
            </div>

            {/* Sync progress */}
            {(loading || loadingStatus) && (
              <div className="flex items-center gap-2 text-xs text-[#888]">
                {loading && <Loader2 className="w-3 h-3 animate-spin text-[#00ff41]" />}
                <span>{loadingStatus}</span>
              </div>
            )}

            {/* Gemini key */}
            <div className="flex flex-col gap-2">
              <label className="text-xs text-[#888]">Your Gemini API Key (Stored Locally)</label>
              <input
                type="password"
                placeholder="AIzaSy..."
                value={userGeminiKey}
                onChange={e => { setUserGeminiKey(e.target.value); localStorage.setItem('user_gemini_key', e.target.value); }}
                className="w-full bg-[#1a1a1a] border border-[#333] rounded-lg px-4 py-2 text-sm focus:outline-none focus:border-[#00ff41] transition-colors"
                autoComplete="new-password"
              />
            </div>

            {/* Target categories */}
            <div className="flex flex-col gap-2">
              <label className="text-xs text-[#888]">Target AI Categories (comma separated)</label>
              <textarea
                value={targetCategoriesInput}
                onChange={e => { setTargetCategoriesInput(e.target.value); localStorage.setItem('target_categories', e.target.value); }}
                placeholder="e.g. Technology, Politics, Music, Gaming"
                className="w-full bg-[#1a1a1a] border border-[#333] rounded-lg px-4 py-2 text-sm focus:outline-none focus:border-[#00ff41] transition-colors min-h-[60px]"
              />
            </div>
          </div>

          {/* Stats & AI trigger */}
          <div className="bg-[#111] border border-[#222] rounded-xl p-5 flex flex-col justify-between">
            <div className="space-y-4">
              <h2 className="text-sm font-semibold uppercase tracking-wider text-[#00ff41]">Intelligence Processing</h2>
              <div className="grid grid-cols-2 gap-3">
                <div className="bg-[#1a1a1a] rounded-lg p-3 border border-[#333]">
                  <div className="text-2xl font-bold">{videos.length}</div>
                  <div className="text-xs text-[#888]">Total Tracks</div>
                </div>
                <div className="bg-[#1a1a1a] rounded-lg p-3 border border-[#333]">
                  <div className="text-2xl font-bold text-[#00ff41]">{categorizedCount}</div>
                  <div className="text-xs text-[#888]">Categorized</div>
                </div>
                {videos.length > 0 && (
                  <div className="col-span-2 bg-[#1a1a1a] rounded-lg p-3 border border-[#333]">
                    <div className="flex justify-between text-xs text-[#888] mb-1">
                      <span>Coverage</span>
                      <span>{Math.round((categorizedCount / videos.length) * 100)}%</span>
                    </div>
                    <div className="w-full bg-[#333] rounded-full h-1.5">
                      <div
                        className="bg-[#00ff41] h-1.5 rounded-full transition-all duration-500"
                        style={{ width: `${(categorizedCount / videos.length) * 100}%` }}
                      />
                    </div>
                  </div>
                )}
              </div>
            </div>

            <div className="flex flex-col gap-3 mt-4">
              <label className="flex items-center gap-2 text-xs text-[#888] cursor-pointer hover:text-white transition-colors">
                <input
                  type="checkbox"
                  checked={forceAllAnalysis}
                  onChange={e => setForceAllAnalysis(e.target.checked)}
                  className="rounded border-[#333] bg-[#1a1a1a]"
                />
                Force re-categorize ALL videos
              </label>
              <button
                onClick={runAiAnalysis}
                disabled={analyzing || saving || videos.length === 0}
                className="w-full bg-[#00ff41]/10 hover:bg-[#00ff41]/20 text-[#00ff41] border border-[#00ff41]/50 py-3 rounded-lg text-sm font-semibold transition-all flex items-center justify-center gap-2 disabled:opacity-50"
              >
                {analyzing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Cpu className="w-4 h-4" />}
                {analyzing ? 'Analyzing...' : 'Run Gemini AI Analysis'}
              </button>
              {/* Save to Sheet — re-syncs existing local categories without re-running AI */}
              <button
                onClick={saveToSheet}
                disabled={saving || analyzing || categorizedCount === 0}
                className="w-full bg-[#1a1a1a] hover:bg-[#222] text-[#aaa] hover:text-white border border-[#333] py-2.5 rounded-lg text-sm font-medium transition-all flex items-center justify-center gap-2 disabled:opacity-40"
                title="Save current local categories to Google Sheet without running AI again"
              >
                {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                {saving ? 'Saving...' : `Save ${categorizedCount} Tags to Sheet`}
              </button>
              {analyzing && analysisStatus && (
                <p className="text-xs text-[#888] text-center animate-pulse">{analysisStatus}</p>
              )}
            </div>
          </div>
        </div>

        {/* ── Category Stats Panel ─────────────────────────────────────── */}
        {showStats && videos.length > 0 && (
          <div className="bg-[#111] border border-[#222] rounded-xl p-5">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-[#00ff41] mb-4">Category Breakdown</h2>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 gap-3">
              {Object.entries(categoryStats)
                .sort(([, a], [, b]) => b - a)
                .map(([cat, count]) => (
                  <button
                    key={cat}
                    onClick={() => setAiFilter(cat)}
                    className={`text-left p-3 rounded-lg border transition-all ${
                      aiFilter === cat
                        ? 'bg-[#00ff41]/10 border-[#00ff41]/50'
                        : 'bg-[#1a1a1a] border-[#333] hover:border-[#555]'
                    }`}
                  >
                    <div className={`text-xl font-bold ${cat !== 'General / Unrelated' ? 'text-[#00ff41]' : 'text-[#888]'}`}>
                      {count}
                    </div>
                    <div className="text-xs text-[#888] truncate mt-1">{cat}</div>
                    <div className="text-[10px] text-[#555] mt-0.5">
                      {Math.round((count / videos.length) * 100)}%
                    </div>
                  </button>
                ))}
            </div>
            {aiFilter !== 'All' && (
              <button
                onClick={() => setAiFilter('All')}
                className="mt-3 text-xs text-[#888] hover:text-white flex items-center gap-1 transition-colors"
              >
                <X className="w-3 h-3" /> Clear filter
              </button>
            )}
          </div>
        )}

        {/* ── Filters ──────────────────────────────────────────────────── */}
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
              className="bg-[#111] border border-[#222] rounded-lg px-4 py-3 text-sm focus:outline-none min-w-[180px]"
            >
              <option value="All" disabled hidden>YouTube Category</option>
              {ytOptions.map(opt => (
                <option key={opt} value={opt}>{opt === 'All' ? 'All YT Categories' : opt}</option>
              ))}
            </select>

            <select
              value={aiFilter}
              onChange={e => setAiFilter(e.target.value)}
              className="bg-[#111] border border-[#222] rounded-lg px-4 py-3 text-sm focus:outline-none min-w-[180px]"
            >
              <option value="All" disabled hidden>AI Category</option>
              {aiOptions.map(opt => (
                <option key={opt} value={opt}>{opt === 'All' ? 'All AI Categories' : opt}</option>
              ))}
            </select>
          </div>
        )}

        {/* Filter result count */}
        {videos.length > 0 && filteredVideos.length !== videos.length && (
          <div className="flex items-center gap-2 text-xs text-[#888]">
            <span>Showing {filteredVideos.length} of {videos.length} videos</span>
            <button
              onClick={() => { setSearchQuery(''); setAiFilter('All'); setYtFilter('All'); }}
              className="text-[#00ff41] hover:underline flex items-center gap-1"
            >
              <X className="w-3 h-3" /> Clear filters
            </button>
          </div>
        )}

        {/* ── Data Grid ────────────────────────────────────────────────── */}
        {videos.length > 0 && (
          <div className="bg-[#111] border border-[#222] rounded-xl overflow-hidden overflow-x-auto">
            <table className="w-full text-left border-collapse min-w-[800px]">
              <thead>
                <tr className="border-b border-[#222] bg-[#1a1a1a] text-[#888] text-xs uppercase tracking-wider">
                  <th className="p-4 font-medium">Cover</th>
                  <th className="p-4 font-medium w-1/3 cursor-pointer hover:text-[#00ff41] group" onClick={() => handleSort('channel')}>
                    <div className="flex items-center gap-1">Subject <SortIcon col="channel" /></div>
                  </th>
                  <th className="p-4 font-medium cursor-pointer hover:text-[#00ff41] group" onClick={() => handleSort('yt_category')}>
                    <div className="flex items-center gap-1">YouTube Cat <SortIcon col="yt_category" /></div>
                  </th>
                  <th className="p-4 font-medium cursor-pointer hover:text-[#00ff41] group" onClick={() => handleSort('custom_category')}>
                    <div className="flex items-center gap-1">AI Category <SortIcon col="custom_category" /></div>
                  </th>
                  <th className="p-4 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#222]">
                {filteredVideos.map(video => (
                  <tr key={video.playlist_item_id} className="hover:bg-[#1a1a1a]/50 transition-colors group">
                    <td className="p-4">
                      <div className="w-24 h-16 rounded-md bg-[#222] overflow-hidden border border-[#333]">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        {video.thumbnail
                          ? <img src={video.thumbnail} alt={video.title} className="object-cover w-full h-full" />
                          : <div className="w-full h-full flex items-center justify-center text-[#444]"><Play className="w-4 h-4" /></div>
                        }
                      </div>
                    </td>
                    <td className="p-4">
                      <a
                        href={`https://youtube.com/watch?v=${video.video_id}`}
                        target="_blank" rel="noopener noreferrer"
                        className="font-medium hover:text-[#00ff41] transition-colors line-clamp-2"
                      >
                        {video.title}
                      </a>
                      <div className="text-sm text-[#888] mt-1">{video.channel}</div>
                    </td>
                    <td className="p-4">
                      <span className="text-xs bg-[#222] text-[#aaa] px-2 py-1 rounded-md border border-[#333]">
                        {video.yt_category}
                      </span>
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
              <div className="p-12 text-center text-[#666]">No records matching active filters.</div>
            )}
          </div>
        )}

        {/* ── Empty state ───────────────────────────────────────────────── */}
        {videos.length === 0 && !loading && (
          <div className="border border-dashed border-[#333] rounded-xl p-16 flex flex-col items-center justify-center text-center mt-10">
            <div className="w-16 h-16 bg-[#1a1a1a] border border-[#222] rounded-full flex items-center justify-center mb-4">
              <Plus className="w-6 h-6 text-[#444]" />
            </div>
            <h3 className="text-lg font-medium text-white">No active feeds</h3>
            <p className="text-[#666] mt-2 max-w-md">
              Enter a YouTube Playlist ID above and press <strong className="text-[#999]">Load</strong> to get started.
            </p>
          </div>
        )}

      </main>
    </div>
  );
}
