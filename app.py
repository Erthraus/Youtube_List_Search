"""
YouTube Playlist Manager & AI Categorizer
Open Source Project for fetching, managing and categorizing YouTube playlist videos using Gemini AI.
"""

import streamlit as st
import pandas as pd
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google import genai
import time
import json
import os

# ==========================================
# 1. CONSTANTS & TRANSLATIONS
# ==========================================
SETTINGS_FILE = "settings.json"
CLIENT_SECRETS_FILE = "client_secret.json"
TOKEN_FILE = "token.json"
SCOPES = ['https://www.googleapis.com/auth/youtube']

TRANSLATIONS = {
    "tr": {
        "page_title": "YouTube Liste Yöneticisi",
        "header": "📺 YouTube Playlist Dashboard",
        "settings_header": "⚙️ Ayarlar & Giriş",
        "auth_mode": "Giriş Yöntemi",
        "mode_api": "🔑 API Key (Sadece Okuma)",
        "mode_oauth": "👤 Google Hesabı (Tam Yetki)",
        "yt_api_key": "1. YouTube API Key",
        "playlist_id": "2. Oynatma Listesi ID",
        "gemini_api_key": "3. Gemini API Key",
        "btn_save": "💾 Kaydet",
        "btn_fetch": "📥 Verileri Çek",
        "btn_login": "Google ile Giriş Yap",
        "msg_need_secret": "Tam yetki için proje klasöründe 'client_secret.json' dosyası bulunmalıdır.",
        "msg_login_success": "Google hesabınıza başarıyla giriş yapıldı!",
        "msg_saved": "Ayarlar başarıyla kaydedildi!",
        "msg_fetching": "Videolar YouTube'dan çekiliyor... Lütfen bekleyin.",
        "msg_mapping": "Kategoriler eşleştiriliyor...",
        "msg_fetch_success": "Harika! Toplam {count} video listeye eklendi.",
        "msg_fetch_error": "Hata: YouTube verisi çekilemedi. Bağlantıyı ve ID'leri kontrol edin.",
        "msg_missing_keys": "Devam etmek için gerekli ID ve Key bilgilerini doldurun.",
        "tab_search": "🔍 Arama ve Düzenleme",
        "tab_ai": "🤖 Yapay Zeka Asistanı",
        "search_title": "🎬 Video Adında Ara",
        "search_channel": "👤 Kanal Adında Ara",
        "filter_category": "📂 Kategori Filtresi",
        "all": "Tümü",
        "metric_total": "Toplam Video",
        "metric_channels": "Farklı Kanal",
        "ai_info": "Bu araç, API limitlerine takılmamanız için 1000 videoyu 250'şerli dev paketler halinde yapay zekaya gönderir.",
        "btn_ai_scan": "Yapay Zeka Analizini Başlat",
        "msg_missing_gemini": "Gemini API Key eksik. Lütfen sol menüden ekleyin.",
        "msg_ai_processing": "Yapay Zeka analiz ediyor (Paket başı ~5 sn)...",
        "msg_chunk_progress": "Durum: {total} paketten {current}. si tamamlandı.",
        "msg_ai_success": "✨ Yapay Zeka sınıflandırması başarıyla tamamlandı!",
        "msg_ai_error": "Okuma hatası: {error}",
        "col_select": "Seç",
        "col_thumb": "Kapak",
        "col_custom_cat": "AI Kategorisi",
        "col_title": "Video Adı",
        "col_channel": "Kanal",
        "col_yt_cat": "YouTube Kategorisi",
        "col_link": "İzle",
        "btn_delete_selected": "🗑️ Seçili Videoları Listeden Çıkar",
        "msg_delete_success": "Seçilen {count} video YouTube listenizden silindi! Tabloyu yenilemek için verileri tekrar çekin.",
        "cat_personal": "Kişisel Gelişim",
        "cat_vocal": "Vokal Eğitimi",
        "cat_software": "Yazılımcı",
        "cat_politics": "Siyaset",
        "cat_general": "Genel / İlgisiz",
        "welcome_title": "Hoş Geldiniz! 👋",
        "welcome_text": "Lütfen sol menüden Giriş Yönteminizi seçerek başlayın."
    },
    "en": {
        "page_title": "YouTube Playlist Manager",
        "header": "📺 YouTube Playlist Dashboard",
        "settings_header": "⚙️ Settings & Login",
        "auth_mode": "Authentication Mode",
        "mode_api": "🔑 API Key (Read Only)",
        "mode_oauth": "👤 Google Account (Full Access)",
        "yt_api_key": "1. YouTube API Key",
        "playlist_id": "2. Playlist ID",
        "gemini_api_key": "3. Gemini API Key",
        "btn_save": "💾 Save Settings",
        "btn_fetch": "📥 Fetch Data",
        "btn_login": "Login with Google",
        "msg_need_secret": "'client_secret.json' file is required in the root folder for Full Access.",
        "msg_login_success": "Successfully logged in to your Google account!",
        "msg_saved": "Settings saved successfully!",
        "msg_fetching": "Fetching videos from YouTube... Please wait.",
        "msg_mapping": "Mapping categories...",
        "msg_fetch_success": "Awesome! {count} videos fetched successfully.",
        "msg_fetch_error": "Error: Could not fetch data. Check your credentials.",
        "msg_missing_keys": "Please fill in the required ID and Key fields to continue.",
        "tab_search": "🔍 Search & Edit",
        "tab_ai": "🤖 AI Assistant",
        "search_title": "🎬 Search Title",
        "search_channel": "👤 Search Channel",
        "filter_category": "📂 Category Filter",
        "all": "All",
        "metric_total": "Total Videos",
        "metric_channels": "Unique Channels",
        "ai_info": "This tool sends videos in large batches of 250 to avoid API rate limits.",
        "btn_ai_scan": "Start AI Analysis",
        "msg_missing_gemini": "Gemini API Key is missing in the sidebar.",
        "msg_ai_processing": "AI is analyzing (approx. 5s per batch)...",
        "msg_chunk_progress": "Status: Batch {current} of {total} completed.",
        "msg_ai_success": "✨ AI classification completed successfully!",
        "msg_ai_error": "Read error: {error}",
        "col_select": "Select",
        "col_thumb": "Thumb",
        "col_custom_cat": "AI Category",
        "col_title": "Video Title",
        "col_channel": "Channel",
        "col_yt_cat": "YouTube Category",
        "col_link": "Watch",
        "btn_delete_selected": "🗑️ Remove Selected Videos",
        "msg_delete_success": "Successfully removed {count} videos! Fetch data again to update the table.",
        "cat_personal": "Personal Development",
        "cat_vocal": "Vocal Training",
        "cat_software": "Software Developer",
        "cat_politics": "Politics",
        "cat_general": "General / Unrelated",
        "welcome_title": "Welcome! 👋",
        "welcome_text": "Please select your Authentication Mode from the sidebar to begin."
    }
}

# ==========================================
# 2. HELPER FUNCTIONS
# ==========================================
def t(key, **kwargs):
    lang = st.session_state.get('lang', 'tr')
    text = TRANSLATIONS[lang].get(key, key)
    return text.format(**kwargs) if kwargs else text

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    return {"youtube_api_key": "", "playlist_id": "", "gemini_api_key": ""}

def save_settings(yt_key, pl_id, gem_key):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as file:
        json.dump({"youtube_api_key": yt_key, "playlist_id": pl_id, "gemini_api_key": gem_key}, file)

# ==========================================
# 3. YOUTUBE API & OAUTH FUNCTIONS
# ==========================================
def get_youtube_service_api(api_key):
    """Initializes read-only YouTube client using API Key."""
    return build('youtube', 'v3', developerKey=api_key)

def get_youtube_service_oauth():
    """Initializes full-access YouTube client using OAuth 2.0."""
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CLIENT_SECRETS_FILE):
                st.sidebar.error(t("msg_need_secret"))
                return None
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
    return build('youtube', 'v3', credentials=creds)

def get_category_mapping(youtube_client):
    request = youtube_client.videoCategories().list(part="snippet", regionCode="US")
    response = request.execute()
    return {item['id']: item['snippet']['title'] for item in response.get('items', [])}

def fetch_playlist_videos(youtube_client, playlist_id):
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
                # playlist_item_id is CRUCIAL for deleting videos!
                playlist_item_id = item['id'] 
                video_id = item['snippet']['resourceId']['videoId']
                title = item['snippet']['title']
                channel = item['snippet'].get('videoOwnerChannelTitle', 'Unknown')
                thumb_url = item['snippet'].get('thumbnails', {}).get('default', {}).get('url', '')
                
                videos.append({
                    'playlist_item_id': playlist_item_id, # Hidden ID used for deletion
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
    video_ids = [vid['video_id'] for vid in videos]
    with st.spinner(t("msg_mapping")):
        for i in range(0, len(video_ids), 50):
            chunk_ids = video_ids[i:i+50]
            request = youtube_client.videos().list(part="snippet", id=",".join(chunk_ids))
            response = request.execute()
            for j, item in enumerate(response['items']):
                cat_id = item['snippet']['categoryId']
                videos[i+j]['yt_category'] = category_mapping.get(cat_id, "Other")
    return videos

def delete_video_from_playlist(youtube_client, playlist_item_id):
    """Deletes a specific video from the playlist using its unique playlist_item_id."""
    youtube_client.playlistItems().delete(id=playlist_item_id).execute()

# ==========================================
# 4. GEMINI AI BATCH PROCESSING
# ==========================================
def batch_gemini_categorize(df, gemini_api_key):
    client = genai.Client(api_key=gemini_api_key)
    category_map = {}
    chunk_size = 250 
    total_chunks = (len(df) // chunk_size) + (1 if len(df) % chunk_size != 0 else 0)
    
    progress_bar = st.progress(0, text=t("msg_ai_processing"))
    for i in range(total_chunks):
        chunk = df.iloc[i*chunk_size : (i+1)*chunk_size]
        if chunk.empty: continue
            
        video_list_str = "".join([f"ID: {row['video_id']} | Title: {row['title']} | Channel: {row['channel']}\n" for _, row in chunk.iterrows()])
            
        prompt = f"""
        Below is a list of YouTube videos. Identify ONLY the videos that fit into these 4 target categories:
        1. Personal Development
        2. Vocal Training
        3. Software Developer
        4. Politics
        
        If a video does not fit, completely IGNORE it.
        Respond ONLY in valid JSON format: [{{"id": "video_id", "category": "Software Developer"}}]
        
        Video List:
        {video_list_str}
        """
        try:
            response = client.models.generate_content(model='gemini-flash-lite-latest', contents=prompt)
            raw_text = response.text.strip()
            if raw_text.startswith("```json"): raw_text = raw_text[7:-3]
            elif raw_text.startswith("```"): raw_text = raw_text[3:-3]
            for item in json.loads(raw_text.strip()):
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

st.markdown("""
<style>
    .block-container { padding-top: 2rem; padding-bottom: 2rem; }
    [data-testid="stMetricValue"], [data-testid="stMetricLabel"], label, p { cursor: default !important; user-select: none !important; }
    [data-baseweb="select"], [data-baseweb="select"] * { cursor: pointer !important; }
    input { cursor: text !important; user-select: auto !important; }
</style>
""", unsafe_allow_html=True)

col_spacer, col_lang = st.columns([10, 1])
with col_lang:
    selected_lang = st.selectbox("🌐", ["tr", "en"], index=0 if st.session_state.get('lang', 'tr') == 'tr' else 1, label_visibility="collapsed")
    st.session_state['lang'] = selected_lang

st.title(t("header"))

# ==========================================
# 6. UI: SIDEBAR (AUTH & SETTINGS)
# ==========================================
user_settings = load_settings()

with st.sidebar:
    st.header(t("settings_header"))
    
    auth_mode = st.radio(t("auth_mode"), [t("mode_api"), t("mode_oauth")])
    st.write("---")
    
    input_yt_api = ""
    is_authenticated = False
    yt_client = None

    if auth_mode == t("mode_api"):
        input_yt_api = st.text_input(t("yt_api_key"), type="password", value=user_settings.get("youtube_api_key", ""))
        if input_yt_api:
            yt_client = get_youtube_service_api(input_yt_api)
            is_authenticated = True
    else:
        if st.button(t("btn_login"), type="primary", use_container_width=True):
            yt_client = get_youtube_service_oauth()
            if yt_client:
                st.session_state['oauth_client'] = True
                st.success(t("msg_login_success"))
        
        # Keep client alive across re-runs if already logged in
        if st.session_state.get('oauth_client', False):
            yt_client = get_youtube_service_oauth()
            is_authenticated = True

    input_pl_id = st.text_input(t("playlist_id"), value=user_settings.get("playlist_id", ""))
    input_gemini_api = st.text_input(t("gemini_api_key"), type="password", value=user_settings.get("gemini_api_key", ""))

    st.write("") 
    col_btn_save, col_btn_fetch = st.columns(2)
    with col_btn_save:
        if st.button(t("btn_save"), use_container_width=True):
            save_settings(input_yt_api, input_pl_id, input_gemini_api)
            st.toast(t("msg_saved"), icon="✅")
    with col_btn_fetch:
        btn_fetch_data = st.button(t("btn_fetch"), use_container_width=True)

# ==========================================
# 7. UI: DATA FETCHING LOGIC
# ==========================================
if btn_fetch_data:
    if is_authenticated and input_pl_id:
        try:
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
    
    metric_col1, metric_col2, metric_col3 = st.columns(3)
    with metric_col1:
        with st.container(border=True): st.metric(label=t("metric_total"), value=len(data_frame))
    with metric_col2:
        with st.container(border=True): st.metric(label=t("metric_channels"), value=data_frame['channel'].nunique())
            
    st.write("---")
    tab_search, tab_ai = st.tabs([t("tab_search"), t("tab_ai")])
    
    # ----------------------------------------
    # TAB 1: SEARCH & EDIT (DELETE FEATURE)
    # ----------------------------------------
    with tab_search:
        search_col1, search_col2, search_col3 = st.columns(3)
        with search_col1: search_title = st.text_input(t("search_title"))
        with search_col2: search_channel = st.text_input(t("search_channel"))
        with search_col3: 
            unique_categories = [t("all")] + list(data_frame['yt_category'].unique())
            selected_category = st.selectbox(t("filter_category"), unique_categories)

        filtered_data = data_frame.copy()
        if search_title: filtered_data = filtered_data[filtered_data['title'].str.contains(search_title, case=False, na=False)]
        if search_channel: filtered_data = filtered_data[filtered_data['channel'].str.contains(search_channel, case=False, na=False)]
        if selected_category != t("all"): filtered_data = filtered_data[filtered_data['yt_category'] == selected_category]

        display_data = filtered_data.copy()
        display_data['video_link'] = "https://youtube.com/watch?v=" + display_data['video_id']
        
        # Setup columns for Data Editor
        cols = display_data.columns.tolist()
        if 'custom_category' in cols: cols.insert(0, cols.pop(cols.index('custom_category')))
        if 'thumbnail' in cols: cols.insert(0, cols.pop(cols.index('thumbnail')))
        display_data = display_data[cols]
        
        # Add a Checkbox column if in OAuth mode
        show_delete_options = (auth_mode == t("mode_oauth"))
        if show_delete_options:
            display_data.insert(0, 'selected', False)

        display_data = display_data.rename(columns={
            "selected": t("col_select"),
            "thumbnail": t("col_thumb"),
            "custom_category": t("col_custom_cat"),
            "title": t("col_title"),
            "channel": t("col_channel"),
            "yt_category": t("col_yt_cat"),
            "video_link": t("col_link")
        })

        with st.container(border=True):
            if show_delete_options:
                # Interactive Data Editor for Deletion
                edited_df = st.data_editor(
                    display_data, 
                    column_config={
                        t("col_select"): st.column_config.CheckboxColumn(t("col_select"), default=False),
                        t("col_link"): st.column_config.LinkColumn("▶️"),
                        t("col_thumb"): st.column_config.ImageColumn(""),
                        "playlist_item_id": None, # Hide secret ID from users
                        "video_id": None
                    },
                    width='stretch', hide_index=True, height=500
                )
                
                # Delete Button Logic
                videos_to_delete = edited_df[edited_df[t("col_select")] == True]
                if not videos_to_delete.empty:
                    if st.button(t("btn_delete_selected"), type="primary"):
                        try:
                            for pl_item_id in videos_to_delete['playlist_item_id']:
                                delete_video_from_playlist(yt_client, pl_item_id)
                                time.sleep(0.5) # Prevent hitting immediate rate limits
                            st.success(t("msg_delete_success", count=len(videos_to_delete)))
                            st.balloons()
                        except Exception as e:
                            st.error(f"Silme hatası / Deletion error: {e}")
            else:
                # Standard Dataframe for Read-Only mode
                st.dataframe(
                    display_data, 
                    column_config={
                        t("col_link"): st.column_config.LinkColumn("▶️"),
                        t("col_thumb"): st.column_config.ImageColumn(""),
                        "playlist_item_id": None,
                        "video_id": None
                    },
                    width='stretch', hide_index=True, height=600 
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
    st.info(f"### {t('welcome_title')}\n\n{t('welcome_text')}")