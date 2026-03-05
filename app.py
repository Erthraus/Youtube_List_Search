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
        "page_title": "📺 YouTube İzleme Listesi Yöneticisi",
        "header": "📺 YouTube İzleme Listesi Yöneticisi ve Arama Motoru",
        "settings_header": "⚙️ API Ayarları",
        "yt_api_key": "1. YouTube API Key",
        "playlist_id": "2. Oynatma Listesi ID",
        "gemini_api_key": "3. Gemini API Key",
        "btn_save": "💾 Kaydet",
        "btn_fetch": "📥 Verileri Çek",
        "msg_saved": "Bilgiler kaydedildi!",
        "msg_fetching": "Videolar YouTube'dan çekiliyor... (Sayfa sayısına göre sürebilir)",
        "msg_mapping": "YouTube Resmi Kategorileri eşleştiriliyor...",
        "msg_fetch_success": "Başarıyla {count} video çekildi!",
        "msg_fetch_error": "YouTube verisi çekilirken hata oluştu: Lütfen ID ve Key'i kontrol edin.",
        "msg_missing_keys": "Lütfen YouTube API Key ve Liste ID girin.",
        "search_header": "### 🔍 Videolarımda Arama Yap",
        "search_title": "🎬 Video Adında Ara:",
        "search_channel": "👤 Kanal Adında Ara:",
        "filter_category": "📂 YouTube Kategorisi:",
        "all": "Tümü",
        "showing_count": "**Gösterilen Video Sayısı: {count}**",
        "ai_expander": "✨ Gemini ile Hedefli Sınıflandırma (Kişisel Gelişim, Vokal, Yazılım)",
        "ai_info": "Bu özellik, listedeki tüm videoları tek seferde yapay zekaya gönderir ve SADECE sizin belirlediğiniz 3 kategoriye uyanları bulup etiketler. İlgisiz videolar 'Genel / İlgisiz' olarak bırakılır.",
        "btn_ai_scan": "Listeyi Yapay Zeka İle Tarat",
        "msg_missing_gemini": "Lütfen sol menüden Gemini API Key girin.",
        "msg_ai_processing": "Gemini videoları topluca inceliyor... Lütfen bekleyin.",
        "msg_chunk_progress": "İşleniyor: {current}/{total} paket tamamlandı.",
        "msg_ai_success": "Yapay Zeka etiketlemesi tamamlandı!",
        "msg_ai_error": "Bir pakette okuma hatası oldu: {error}",
        "col_thumb": "Kapak Fotoğrafı",
        "col_custom_cat": "Özel Kategori",
        "col_title": "Video Adı",
        "col_channel": "Kanal Adı",
        "col_yt_cat": "Kategori",
        "col_link": "▶️ Video Linki",
        "cat_personal": "Kişisel Gelişim",
        "cat_vocal": "Vokal Eğitimi",
        "cat_software": "Yazılımcı",
        "cat_general": "Genel / İlgisiz"
    },
    "en": {
        "page_title": "📺 YouTube Playlist Manager",
        "header": "📺 YouTube Playlist Manager & Search Engine",
        "settings_header": "⚙️ API Settings",
        "yt_api_key": "1. YouTube API Key",
        "playlist_id": "2. Playlist ID",
        "gemini_api_key": "3. Gemini API Key",
        "btn_save": "💾 Save",
        "btn_fetch": "📥 Fetch Data",
        "msg_saved": "Settings saved successfully!",
        "msg_fetching": "Fetching videos from YouTube... (This may take a while)",
        "msg_mapping": "Mapping official YouTube categories...",
        "msg_fetch_success": "Successfully fetched {count} videos!",
        "msg_fetch_error": "Error fetching YouTube data: Please check your ID and Key.",
        "msg_missing_keys": "Please enter YouTube API Key and Playlist ID.",
        "search_header": "### 🔍 Search My Videos",
        "search_title": "🎬 Search in Title:",
        "search_channel": "👤 Search in Channel:",
        "filter_category": "📂 YouTube Category:",
        "all": "All",
        "showing_count": "**Showing {count} videos**",
        "ai_expander": "✨ Targeted AI Classification (Self Impr., Vocal, Software)",
        "ai_info": "This feature sends all listed videos to the AI and tags ONLY the ones fitting your 3 target categories. Unrelated videos remain 'General / Unrelated'.",
        "btn_ai_scan": "Scan List with AI",
        "msg_missing_gemini": "Please enter Gemini API Key in the sidebar.",
        "msg_ai_processing": "Gemini is processing the videos in batches... Please wait.",
        "msg_chunk_progress": "Processing: {current}/{total} batches completed.",
        "msg_ai_success": "AI tagging completed successfully!",
        "msg_ai_error": "Read error in a batch: {error}",
        "col_thumb": "Thumbnail",
        "col_custom_cat": "Custom Category",
        "col_title": "Video Title",
        "col_channel": "Channel Name",
        "col_yt_cat": "Category",
        "col_link": "▶️ Video Link",
        "cat_personal": "Personal Development",
        "cat_vocal": "Vocal Training",
        "cat_software": "Software Developer",
        "cat_general": "General / Unrelated"
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
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"youtube_api_key": "", "playlist_id": "", "gemini_api_key": ""}

def save_settings(yt_key, pl_id, gem_key):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "youtube_api_key": yt_key, 
            "playlist_id": pl_id, 
            "gemini_api_key": gem_key
        }, f)

# ==========================================
# 3. YOUTUBE API FUNCTIONS
# ==========================================
def get_youtube_service(api_key):
    return build('youtube', 'v3', developerKey=api_key)

def get_category_mapping(youtube):
    # Fetching category names (Defaults to US regions to standardize, then we translate if needed, but keeping TR for localization)
    request = youtube.videoCategories().list(part="snippet", regionCode="US")
    response = request.execute()
    mapping = {}
    for item in response.get('items', []):
        mapping[item['id']] = item['snippet']['title']
    return mapping

def fetch_playlist_videos(youtube, playlist_id):
    videos = []
    next_page_token = None
    
    with st.spinner(t("msg_fetching")):
        while True:
            request = youtube.playlistItems().list(
                part="snippet",
                playlistId=playlist_id,
                maxResults=50,
                pageToken=next_page_token
            )
            response = request.execute()
            
            for item in response['items']:
                video_id = item['snippet']['resourceId']['videoId']
                title = item['snippet']['title']
                channel = item['snippet']['videoOwnerChannelTitle'] if 'videoOwnerChannelTitle' in item['snippet'] else 'Unknown Channel'
                
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

def assign_youtube_categories(youtube, videos, category_mapping):
    video_ids = [vid['video_id'] for vid in videos]
    
    with st.spinner(t("msg_mapping")):
        for i in range(0, len(video_ids), 50):
            chunk_ids = video_ids[i:i+50]
            request = youtube.videos().list(
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
    client = genai.Client(api_key=gemini_api_key)
    category_map = {}
    
    chunk_size = 100
    total_chunks = (len(df) // chunk_size) + (1 if len(df) % chunk_size != 0 else 0)
    
    my_bar = st.progress(0, text=t("msg_ai_processing"))
    
    for i in range(total_chunks):
        chunk = df.iloc[i*chunk_size : (i+1)*chunk_size]
        if chunk.empty:
            continue
            
        video_list_str = ""
        for _, row in chunk.iterrows():
            video_list_str += f"ID: {row['video_id']} | Title: {row['title']} | Channel: {row['channel']}\n"
            
        prompt = f"""
        Below is a list of YouTube videos. 
        I want you to identify ONLY the videos that fit into these 3 target categories:
        1. Personal Development
        2. Vocal Training
        3. Software Developer
        
        If a video does not fit into any of these three, completely IGNORE it and do not include it in the list.
        
        Respond ONLY in valid JSON format as shown below. Do not add any greetings, markdown formatting, or explanations:
        [
          {{"id": "video_id_here", "category": "Software Developer"}},
          {{"id": "another_id", "category": "Vocal Training"}}
        ]
        
        Video List:
        {video_list_str}
        """
        
        try:
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
            
        my_bar.progress((i + 1) / total_chunks, text=t("msg_chunk_progress", current=i+1, total=total_chunks))
        time.sleep(5)
        
    return category_map


# ==========================================
# 5. STREAMLIT USER INTERFACE
# ==========================================
st.set_page_config(page_title="YouTube AI Manager", layout="wide")

# Language Selector
lang_col1, lang_col2 = st.columns([9, 1])
with lang_col2:
    selected_lang = st.selectbox("🌐", ["tr", "en"], index=0 if st.session_state.get('lang', 'tr') == 'tr' else 1, label_visibility="collapsed")
    st.session_state['lang'] = selected_lang

st.title(t("header"))

# Load Settings
settings = load_settings()

# Sidebar
st.sidebar.header(t("settings_header"))

yt_api_key = st.sidebar.text_input(t("yt_api_key"), type="password", value=settings.get("youtube_api_key", ""))
pl_id = st.sidebar.text_input(t("playlist_id"), value=settings.get("playlist_id", ""))
gem_api_key = st.sidebar.text_input(t("gemini_api_key"), type="password", value=settings.get("gemini_api_key", ""))

col_btn1, col_btn2 = st.sidebar.columns(2)
with col_btn1:
    if st.button(t("btn_save")):
        save_settings(yt_api_key, pl_id, gem_api_key)
        st.success(t("msg_saved"))
with col_btn2:
    fetch_btn = st.button(t("btn_fetch"))

st.sidebar.markdown("---")

# Fetch Data Logic
if fetch_btn:
    if yt_api_key and pl_id:
        try:
            youtube = get_youtube_service(yt_api_key)
            cat_mapping = get_category_mapping(youtube)
            
            raw_vids = fetch_playlist_videos(youtube, pl_id)
            final_vids = assign_youtube_categories(youtube, raw_vids, cat_mapping)
            
            st.session_state['df'] = pd.DataFrame(final_vids)
            st.success(t("msg_fetch_success", count=len(final_vids)))
        except Exception as e:
            st.error(t("msg_fetch_error"))
    else:
        st.warning(t("msg_missing_keys"))

# Main Screen Logic
if 'df' in st.session_state:
    df = st.session_state['df']
    
    st.markdown(t("search_header"))
    
    col_s1, col_s2, col_s3 = st.columns(3)
    with col_s1:
        search_title = st.text_input(t("search_title"))
    with col_s2:
        search_channel = st.text_input(t("search_channel"))
    with col_s3:
        categories = [t("all")] + list(df['yt_category'].unique())
        selected_cat = st.selectbox(t("filter_category"), categories)

    # Filtering
    filtered_df = df.copy()
    if search_title:
        filtered_df = filtered_df[filtered_df['title'].str.contains(search_title, case=False, na=False)]
    if search_channel:
        filtered_df = filtered_df[filtered_df['channel'].str.contains(search_channel, case=False, na=False)]
    if selected_cat != t("all"):
        filtered_df = filtered_df[filtered_df['yt_category'] == selected_cat]

    st.write(t("showing_count", count=len(filtered_df)))

    # AI Section
    st.markdown("---")
    with st.expander(t("ai_expander")):
        st.info(t("ai_info"))
        
        if st.button(t("btn_ai_scan")):
            if not gem_api_key:
                st.error(t("msg_missing_gemini"))
            else:
                temp_df = st.session_state['df'].copy() 
                matched_categories = batch_gemini_categorize(temp_df, gem_api_key)
                
                # Mapping AI responses to localized strings
                def map_ai_category(vid_id):
                    cat = matched_categories.get(vid_id, "General / Unrelated")
                    if cat == "Personal Development": return t("cat_personal")
                    if cat == "Vocal Training": return t("cat_vocal")
                    if cat == "Software Developer": return t("cat_software")
                    return t("cat_general")

                st.session_state['df']['custom_category'] = st.session_state['df']['video_id'].apply(map_ai_category)
                st.rerun()

    # Display Formatting
    display_df = filtered_df.copy()
    
    display_df['video_link'] = "https://youtube.com/watch?v=" + display_df['video_id']
    display_df = display_df.drop(columns=['video_id'])
    
    # Reordering columns
    cols = display_df.columns.tolist()
    
    if 'custom_category' in cols:
        cols.insert(0, cols.pop(cols.index('custom_category')))
    if 'thumbnail' in cols:
        cols.insert(0, cols.pop(cols.index('thumbnail')))
        
    display_df = display_df[cols]

    # Renaming columns for display
    display_df = display_df.rename(columns={
        "thumbnail": t("col_thumb"),
        "custom_category": t("col_custom_cat"),
        "title": t("col_title"),
        "channel": t("col_channel"),
        "yt_category": t("col_yt_cat"),
        "video_link": t("col_link")
    })

    st.dataframe(
        display_df, 
        column_config={
            t("col_link"): st.column_config.LinkColumn(t("col_link")),
            t("col_thumb"): st.column_config.ImageColumn(t("col_thumb")) 
        },
        width='stretch', 
        hide_index=True
    )