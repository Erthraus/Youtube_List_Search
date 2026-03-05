"""
YouTube Playlist Manager & AI Categorizer
"""

import streamlit as st
import pandas as pd
from googleapiclient.discovery import build
from google import genai
import time
import json
import os

# ==========================================
# 1. CONSTANTS & TRANSLATIONS
# ==========================================
SETTINGS_FILE = "settings.json"

TRANSLATIONS = {
    "tr": {
        "page_title": "YouTube Liste Yöneticisi",
        "header": "📺 YouTube Playlist Dashboard",
        "settings_header": "⚙️ API Ayarları",
        "yt_api_key": "1. YouTube API Key",
        "playlist_id": "2. Oynatma Listesi ID",
        "gemini_api_key": "3. Gemini API Key",
        "btn_save": "💾 Kaydet",
        "btn_fetch": "📥 Verileri Çek",
        "msg_saved": "Ayarlar başarıyla kaydedildi!",
        "msg_fetching": "Videolar YouTube'dan çekiliyor... Lütfen bekleyin.",
        "msg_mapping": "Kategoriler eşleştiriliyor...",
        "msg_fetch_success": "Harika! Toplam {count} video listeye eklendi.",
        "msg_fetch_error": "Hata: YouTube verisi çekilemedi. ID ve Key değerlerini kontrol edin.",
        "msg_missing_keys": "Devam etmek için YouTube API Key ve Liste ID gereklidir.",
        "tab_search": "🔍 Arama ve Filtreleme",
        "tab_ai": "🤖 Yapay Zeka Asistanı",
        "search_title": "🎬 Video Adında Ara",
        "search_channel": "👤 Kanal Adında Ara",
        "filter_category": "📂 Kategori Filtresi",
        "all": "Tümü",
        "metric_total": "Toplam Video",
        "metric_channels": "Farklı Kanal",
        "ai_info": "Bu araç, API limitlerine takılmamanız için 1000 videoyu 250'şerli dev paketler halinde yapay zekaya gönderir. SADECE hedeflediğiniz kategorileri seçer.",
        "btn_ai_scan": "Yapay Zeka Analizini Başlat",
        "msg_missing_gemini": "Gemini API Key eksik. Lütfen sol menüden ekleyin.",
        "msg_ai_processing": "Yapay Zeka analiz ediyor (Paket başı ~5 sn)...",
        "msg_chunk_progress": "Durum: {total} paketten {current}. si tamamlandı.",
        "msg_ai_success": "✨ Yapay Zeka sınıflandırması başarıyla tamamlandı!",
        "msg_ai_error": "Okuma hatası: {error}",
        "col_thumb": "Kapak",
        "col_custom_cat": "AI Kategorisi",
        "col_title": "Video Adı",
        "col_channel": "Kanal",
        "col_yt_cat": "YouTube Kategorisi",
        "col_link": "İzle",
        "cat_personal": "Kişisel Gelişim",
        "cat_vocal": "Vokal Eğitimi",
        "cat_software": "Yazılımcı",
        "cat_politics": "Siyaset",
        "cat_general": "Genel / İlgisiz",
        "welcome_title": "Hoş Geldiniz! 👋",
        "welcome_text": "Lütfen sol menüden API bilgilerinizi girip **Verileri Çek** butonuna basarak başlayın."
    },
    "en": {
        "page_title": "YouTube Playlist Manager",
        "header": "📺 YouTube Playlist Dashboard",
        "settings_header": "⚙️ API Settings",
        "yt_api_key": "1. YouTube API Key",
        "playlist_id": "2. Playlist ID",
        "gemini_api_key": "3. Gemini API Key",
        "btn_save": "💾 Save Settings",
        "btn_fetch": "📥 Fetch Data",
        "msg_saved": "Settings saved successfully!",
        "msg_fetching": "Fetching videos from YouTube... Please wait.",
        "msg_mapping": "Mapping categories...",
        "msg_fetch_success": "Awesome! {count} videos fetched successfully.",
        "msg_fetch_error": "Error: Could not fetch data. Check your ID and Key.",
        "msg_missing_keys": "YouTube API Key and Playlist ID are required.",
        "tab_search": "🔍 Search & Filter",
        "tab_ai": "🤖 AI Assistant",
        "search_title": "🎬 Search Title",
        "search_channel": "👤 Search Channel",
        "filter_category": "📂 Category Filter",
        "all": "All",
        "metric_total": "Total Videos",
        "metric_channels": "Unique Channels",
        "ai_info": "To avoid API rate limits, this tool sends videos in large batches of 250. It ONLY tags the specific target categories you want.",
        "btn_ai_scan": "Start AI Analysis",
        "msg_missing_gemini": "Gemini API Key is missing in the sidebar.",
        "msg_ai_processing": "AI is analyzing (approx. 5s per batch)...",
        "msg_chunk_progress": "Status: Batch {current} of {total} completed.",
        "msg_ai_success": "✨ AI classification completed successfully!",
        "msg_ai_error": "Read error: {error}",
        "col_thumb": "Thumb",
        "col_custom_cat": "AI Category",
        "col_title": "Video Title",
        "col_channel": "Channel",
        "col_yt_cat": "YouTube Category",
        "col_link": "Watch",
        "cat_personal": "Personal Development",
        "cat_vocal": "Vocal Training",
        "cat_software": "Software Developer",
        "cat_politics": "Politics",
        "cat_general": "General / Unrelated",
        "welcome_title": "Welcome! 👋",
        "welcome_text": "Please enter your API credentials in the sidebar and click **Fetch Data** to begin."
    }
}

# ==========================================
# 2. HELPER FUNCTIONS
# ==========================================
def t(key, **kwargs):
    """Returns the translated string for the given key based on selected language."""
    lang = st.session_state.get('lang', 'tr')
    text = TRANSLATIONS[lang].get(key, key)
    return text.format(**kwargs) if kwargs else text

def load_settings():
    """Loads API keys and Playlist ID from the local JSON file."""
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    return {"youtube_api_key": "", "playlist_id": "", "gemini_api_key": ""}

def save_settings(yt_key, pl_id, gem_key):
    """Saves API keys and Playlist ID to prevent data loss on refresh."""
    with open(SETTINGS_FILE, "w", encoding="utf-8") as file:
        json.dump({
            "youtube_api_key": yt_key, 
            "playlist_id": pl_id, 
            "gemini_api_key": gem_key
        }, file)

# ==========================================
# 3. YOUTUBE API FUNCTIONS
# ==========================================
def get_youtube_service(api_key):
    """Initializes the YouTube Data API v3 client."""
    return build('youtube', 'v3', developerKey=api_key)

def get_category_mapping(youtube_client):
    """Fetches official YouTube categories to map IDs to readable names."""
    request = youtube_client.videoCategories().list(part="snippet", regionCode="US")
    response = request.execute()
    mapping = {}
    for item in response.get('items', []):
        mapping[item['id']] = item['snippet']['title']
    return mapping

def fetch_playlist_videos(youtube_client, playlist_id):
    """Fetches all videos from the specified playlist handling pagination."""
    videos = []
    next_page_token = None
    
    with st.spinner(t("msg_fetching")):
        while True:
            request = youtube_client.playlistItems().list(
                part="snippet",
                playlistId=playlist_id,
                maxResults=50,
                pageToken=next_page_token
            )
            response = request.execute()
            
            for item in response['items']:
                video_id = item['snippet']['resourceId']['videoId']
                title = item['snippet']['title']
                channel = item['snippet'].get('videoOwnerChannelTitle', 'Unknown')
                
                thumbnails = item['snippet'].get('thumbnails', {})
                thumb_url = thumbnails.get('default', {}).get('url', '')
                
                videos.append({
                    'video_id': video_id,
                    'thumbnail': thumb_url,  
                    'title': title,
                    'channel': channel
                })
                
            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                break
                
    return videos

def assign_youtube_categories(youtube_client, videos, category_mapping):
    """Assigns readable category names to videos in chunks of 50."""
    video_ids = [vid['video_id'] for vid in videos]
    
    with st.spinner(t("msg_mapping")):
        for i in range(0, len(video_ids), 50):
            chunk_ids = video_ids[i:i+50]
            request = youtube_client.videos().list(
                part="snippet",
                id=",".join(chunk_ids)
            )
            response = request.execute()
            
            for j, item in enumerate(response['items']):
                cat_id = item['snippet']['categoryId']
                videos[i+j]['yt_category'] = category_mapping.get(cat_id, "Other")
                
    return videos

# ==========================================
# 4. GEMINI AI BATCH PROCESSING
# ==========================================
def batch_gemini_categorize(df, gemini_api_key):
    """Sends video data to Gemini API in batches to prevent rate limiting."""
    client = genai.Client(api_key=gemini_api_key)
    category_map = {}
    
    chunk_size = 250 
    total_chunks = (len(df) // chunk_size) + (1 if len(df) % chunk_size != 0 else 0)
    
    progress_bar = st.progress(0, text=t("msg_ai_processing"))
    
    for i in range(total_chunks):
        chunk = df.iloc[i*chunk_size : (i+1)*chunk_size]
        if chunk.empty:
            continue
            
        video_list_str = ""
        for _, row in chunk.iterrows():
            video_list_str += f"ID: {row['video_id']} | Title: {row['title']} | Channel: {row['channel']}\n"
            
        # Standardized prompt in English for better AI performance
        prompt = f"""
        Below is a list of YouTube videos. 
        I want you to identify ONLY the videos that fit into these 4 target categories:
        1. Personal Development
        2. Vocal Training
        3. Software Developer
        4. Politics
        
        If a video does not fit into any of these four, completely IGNORE it and do not include it in the list.
        
        Respond ONLY in valid JSON format as shown below. Do not add any greetings, markdown formatting, or explanations:
        [
          {{"id": "video_id_here", "category": "Software Developer"}},
          {{"id": "another_id", "category": "Politics"}}
        ]
        
        Video List:
        {video_list_str}
        """
        
        try:
            # Using flash-lite-latest to avoid free tier strict limits
            response = client.models.generate_content(
                model='gemini-flash-lite-latest',
                contents=prompt
            )
            
            raw_text = response.text.strip()
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:-3]
            elif raw_text.startswith("```"):
                raw_text = raw_text[3:-3]
                
            parsed_data = json.loads(raw_text.strip())
            
            for item in parsed_data:
                category_map[item['id']] = item['category']
                
        except Exception as e:
            st.error(t("msg_ai_error", error=str(e)))
            
        progress_bar.progress((i + 1) / total_chunks, text=t("msg_chunk_progress", current=i+1, total=total_chunks))
        time.sleep(4) 
        
    return category_map


# ==========================================
# 5. UI: PAGE CONFIG & STYLES
# ==========================================
st.set_page_config(page_title="YT Manager", layout="wide", page_icon="📺")

# Custom CSS for Cursor and Layout Fixes
st.markdown("""
<style>
    .block-container { padding-top: 2rem; padding-bottom: 2rem; }
    
    /* Disable text selection cursor on metrics and general labels */
    [data-testid="stMetricValue"], [data-testid="stMetricLabel"], label, p {
        cursor: default !important;
        user-select: none !important;
    }
    
    /* Enforce pointer cursor on dropdown elements (selectboxes) */
    [data-baseweb="select"], [data-baseweb="select"] * {
        cursor: pointer !important;
    }
    
    /* Only allow text cursor on actual text inputs */
    input {
        cursor: text !important;
        user-select: auto !important;
    }
</style>
""", unsafe_allow_html=True)

# Language Selector (Top Right)
col_spacer, col_lang = st.columns([10, 1])
with col_lang:
    selected_lang = st.selectbox("🌐", ["tr", "en"], index=0 if st.session_state.get('lang', 'tr') == 'tr' else 1, label_visibility="collapsed")
    st.session_state['lang'] = selected_lang

st.title(t("header"))

# ==========================================
# 6. UI: SIDEBAR
# ==========================================
user_settings = load_settings()

with st.sidebar:
    st.header(t("settings_header"))
    
    input_yt_api = st.text_input(t("yt_api_key"), type="password", value=user_settings.get("youtube_api_key", ""))
    input_pl_id = st.text_input(t("playlist_id"), value=user_settings.get("playlist_id", ""))
    input_gemini_api = st.text_input(t("gemini_api_key"), type="password", value=user_settings.get("gemini_api_key", ""))

    st.write("") 
    col_btn_save, col_btn_fetch = st.columns(2)
    with col_btn_save:
        if st.button(t("btn_save"), use_container_width=True):
            save_settings(input_yt_api, input_pl_id, input_gemini_api)
            st.toast(t("msg_saved"), icon="✅")
    with col_btn_fetch:
        btn_fetch_data = st.button(t("btn_fetch"), type="primary", use_container_width=True)

# ==========================================
# 7. UI: DATA FETCHING LOGIC
# ==========================================
if btn_fetch_data:
    if input_yt_api and input_pl_id:
        try:
            yt_client = get_youtube_service(input_yt_api)
            cat_map = get_category_mapping(yt_client)
            
            raw_videos = fetch_playlist_videos(yt_client, input_pl_id)
            final_videos = assign_youtube_categories(yt_client, raw_videos, cat_map)
            
            st.session_state['df'] = pd.DataFrame(final_videos)
            st.toast(t("msg_fetch_success", count=len(final_videos)), icon="🎉")
        except Exception as e:
            st.error(t("msg_fetch_error"))
    else:
        st.warning(t("msg_missing_keys"))

# ==========================================
# 8. UI: MAIN DASHBOARD
# ==========================================
if 'df' in st.session_state:
    data_frame = st.session_state['df']
    
    # Metrics Row 
    metric_col1, metric_col2, metric_col3 = st.columns(3)
    with metric_col1:
        with st.container(border=True):
            st.metric(label=t("metric_total"), value=len(data_frame))
    with metric_col2:
        with st.container(border=True):
            st.metric(label=t("metric_channels"), value=data_frame['channel'].nunique())
            
    st.write("---")
    
    # Tabs for Organization
    tab_search, tab_ai = st.tabs([t("tab_search"), t("tab_ai")])
    
    # ----------------------------------------
    # TAB 1: SEARCH & FILTER
    # ----------------------------------------
    with tab_search:
        search_col1, search_col2, search_col3 = st.columns(3)
        with search_col1: 
            search_title = st.text_input(t("search_title"))
        with search_col2: 
            search_channel = st.text_input(t("search_channel"))
        with search_col3: 
            unique_categories = [t("all")] + list(data_frame['yt_category'].unique())
            selected_category = st.selectbox(t("filter_category"), unique_categories)

        filtered_data = data_frame.copy()
        
        if search_title: 
            filtered_data = filtered_data[filtered_data['title'].str.contains(search_title, case=False, na=False)]
        if search_channel: 
            filtered_data = filtered_data[filtered_data['channel'].str.contains(search_channel, case=False, na=False)]
        if selected_category != t("all"): 
            filtered_data = filtered_data[filtered_data['yt_category'] == selected_category]

        display_data = filtered_data.copy()
        display_data['video_link'] = "https://youtube.com/watch?v=" + display_data['video_id']
        display_data = display_data.drop(columns=['video_id'])
        
        cols = display_data.columns.tolist()
        if 'custom_category' in cols: 
            cols.insert(0, cols.pop(cols.index('custom_category')))
        if 'thumbnail' in cols: 
            cols.insert(0, cols.pop(cols.index('thumbnail')))
            
        display_data = display_data[cols]

        display_data = display_data.rename(columns={
            "thumbnail": t("col_thumb"),
            "custom_category": t("col_custom_cat"),
            "title": t("col_title"),
            "channel": t("col_channel"),
            "yt_category": t("col_yt_cat"),
            "video_link": t("col_link")
        })

        with st.container(border=True):
            st.dataframe(
                display_data, 
                column_config={
                    t("col_link"): st.column_config.LinkColumn("▶️"),
                    t("col_thumb"): st.column_config.ImageColumn("") 
                },
                width='stretch', 
                hide_index=True,
                height=600 
            )
        
    # ----------------------------------------
    # TAB 2: AI ASSISTANT
    # ----------------------------------------
    with tab_ai:
        with st.container(border=True):
            st.info(t("ai_info"), icon="🤖")
            
            if st.button(t("btn_ai_scan"), type="primary"):
                if not input_gemini_api:
                    st.error(t("msg_missing_gemini"))
                else:
                    temp_data = st.session_state['df'].copy() 
                    matched_results = batch_gemini_categorize(temp_data, input_gemini_api)
                    
                    def map_ai_category(vid_id):
                        category = matched_results.get(vid_id, "General / Unrelated")
                        if category == "Personal Development": return t("cat_personal")
                        if category == "Vocal Training": return t("cat_vocal")
                        if category == "Software Developer": return t("cat_software")
                        if category == "Politics": return t("cat_politics")
                        return t("cat_general")

                    st.session_state['df']['custom_category'] = st.session_state['df']['video_id'].apply(map_ai_category)
                    st.success(t("msg_ai_success"))
                    st.rerun()

else:
    # Empty State (Welcome Screen)
    st.info(f"### {t('welcome_title')}\n\n{t('welcome_text')}")