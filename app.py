"""
YouTube Playlist AI Manager & Editor
Open Source SaaS Project for fetching, managing, and categorizing YouTube playlist videos using Gemini AI.
Fully compatible with Streamlit Cloud Deployment, using Browser Cookies and Session States.
"""

import streamlit as st
import pandas as pd
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google import genai
import extra_streamlit_components as stx
import time
import json
import os

# Allow OAuth testing over HTTP for local development
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

# ==========================================
# 1. PAGE CONFIG & CUSTOM CSS
# ==========================================
st.set_page_config(page_title="YT Playlist Manager", layout="wide", page_icon="📺")

st.markdown("""
<style>
    .block-container { padding-top: 2rem; padding-bottom: 2rem; }
    [data-testid="stMetricValue"], [data-testid="stMetricLabel"], label, p { cursor: default !important; user-select: none !important; }
    [data-baseweb="select"], [data-baseweb="select"] * { cursor: pointer !important; }
    input { cursor: text !important; user-select: auto !important; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. CONSTANTS & AI CATEGORIES
# ==========================================
CLIENT_SECRETS_FILE = "client_secret.json"
SCOPES = ['https://www.googleapis.com/auth/youtube']

TARGET_CATEGORIES = [
    "Personal Development",
    "Vocal Training",
    "Software Developer",
    "Politics",
    "FNAF Theory",
    "Gameplay"
]
DEFAULT_CATEGORY = "General / Unrelated"

# ==========================================
# 3. COOKIE MANAGER INITIALIZATION
# ==========================================
cookie_manager = stx.CookieManager()
time.sleep(0.1)

# ==========================================
# 4. YOUTUBE API & OAUTH FUNCTIONS
# ==========================================
def get_youtube_service_api(api_key):
    try:
        return build('youtube', 'v3', developerKey=api_key)
    except Exception as e:
        st.error(f"Invalid YouTube API Key: {e}")
        return None

def get_youtube_service_oauth(creds_dict):
    try:
        creds = Credentials.from_authorized_user_info(creds_dict, SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            oauth_json = json.loads(creds.to_json())
            st.session_state["oauth_token"] = oauth_json
            cookie_manager.set('oauth_token', oauth_json, key="update_oauth_cookie")
        return build('youtube', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"OAuth Authentication Error: {e}")
        return None

def get_category_mapping(youtube_client):
    request = youtube_client.videoCategories().list(part="snippet", regionCode="US")
    response = request.execute()
    return {item['id']: item['snippet']['title'] for item in response.get('items', [])}

def assign_youtube_categories(youtube_client, videos, category_mapping):
    video_ids = [vid['video_id'] for vid in videos]
    for i in range(0, len(video_ids), 50):
        chunk_ids = video_ids[i:i+50]
        request = youtube_client.videos().list(part="snippet", id=",".join(chunk_ids))
        response = request.execute()
        for j, item in enumerate(response.get('items', [])):
            cat_id = item['snippet']['categoryId']
            videos[i+j]['yt_category'] = category_mapping.get(cat_id, "Other")
    return videos

@st.cache_data(show_spinner=False, ttl=3600)
def fetch_playlist_videos_cached(playlist_id, auth_identifier):
    youtube_client = get_youtube_service_api(auth_identifier) if isinstance(auth_identifier, str) else get_youtube_service_oauth(auth_identifier)
    
    cat_map = get_category_mapping(youtube_client)
    videos = []
    next_page_token = None
    
    while True:
        request = youtube_client.playlistItems().list(
            part="snippet",
            playlistId=playlist_id,
            maxResults=50,
            pageToken=next_page_token
        )
        response = request.execute()
        
        for item in response.get('items', []):
            playlist_item_id = item['id'] 
            video_id = item['snippet']['resourceId']['videoId']
            title = item['snippet']['title']
            channel = item['snippet'].get('videoOwnerChannelTitle', 'Unknown')
            thumb_url = item['snippet'].get('thumbnails', {}).get('default', {}).get('url', '')
            
            videos.append({
                'playlist_item_id': playlist_item_id,
                'video_id': video_id,
                'thumbnail': thumb_url,  
                'title': title,
                'channel': channel,
                'yt_category': "Unknown", 
                'custom_category': DEFAULT_CATEGORY
            })
            
        next_page_token = response.get('nextPageToken')
        if not next_page_token:
            break
            
    videos = assign_youtube_categories(youtube_client, videos, cat_map)
    return videos

def delete_video_from_playlist(youtube_client, playlist_item_id):
    youtube_client.playlistItems().delete(id=playlist_item_id).execute()
    fetch_playlist_videos_cached.clear()

# ==========================================
# 5. GEMINI AI BATCH PROCESSING
# ==========================================
def batch_gemini_categorize(df_to_process, gemini_api_key):
    client = genai.Client(api_key=gemini_api_key)
    category_map = {}
    chunk_size = 250 
    total_chunks = (len(df_to_process) // chunk_size) + (1 if len(df_to_process) % chunk_size != 0 else 0)
    
    progress_bar = st.progress(0, text="AI is analyzing remaining videos... Please wait.")
    
    for i in range(total_chunks):
        chunk = df_to_process.iloc[i*chunk_size : (i+1)*chunk_size]
        if chunk.empty: continue
            
        video_list_str = "".join([f"ID: {row['video_id']} | Title: {row['title']} | Channel: {row['channel']}\n" for _, row in chunk.iterrows()])
        
        categories_str = "\n".join([f"{idx+1}. {cat}" for idx, cat in enumerate(TARGET_CATEGORIES)])
        
        prompt = f"""
        Below is a list of YouTube videos. Identify ONLY the videos that fit into these {len(TARGET_CATEGORIES)} target categories:
        {categories_str}
        
        If a video does not fit, completely IGNORE it.
        Respond ONLY in valid JSON format exactly like this example: 
        [{{"id": "video_id", "category": "FNAF Theory"}}]
        
        Video List:
        {video_list_str}
        """
        try:
            response = client.models.generate_content(model='gemini-flash-lite-latest', contents=prompt)
            raw_text = response.text.strip()
            if raw_text.startswith("```json"): raw_text = raw_text[7:-3]
            elif raw_text.startswith("```"): raw_text = raw_text[3:-3]
            for item in json.loads(raw_text.strip()):
                if item['category'] in TARGET_CATEGORIES:
                    category_map[item['id']] = item['category']
        except Exception as e:
            st.error(f"Read error in batch {i+1}: {str(e)}")
            
        progress_bar.progress((i + 1) / total_chunks, text=f"Status: Batch {i+1} of {total_chunks} completed.")
        time.sleep(4) 
    return category_map


# ==========================================
# 6. UI: MAIN APP & SIDEBAR
# ==========================================
st.title("📺 YouTube Playlist Dashboard")

with st.sidebar:
    st.header("⚙️ Settings & Login")
    
    saved_yt_key = cookie_manager.get(cookie="yt_api_key") or ""
    saved_pl_id = cookie_manager.get(cookie="playlist_id") or ""
    saved_gem_key = cookie_manager.get(cookie="gem_api_key") or ""
    saved_oauth = st.session_state.get("oauth_token") or cookie_manager.get(cookie="oauth_token")
    
    auth_mode = st.radio("Authentication Mode", ["🔑 API Key (Read Only)", "👤 Google Account (Full Access)"])
    st.write("---")
    
    yt_client = None
    is_authenticated = False
    auth_identifier = None

    if auth_mode == "🔑 API Key (Read Only)":
        input_yt_api = st.text_input("1. YouTube API Key", type="password", value=saved_yt_key)
        if input_yt_api:
            yt_client = get_youtube_service_api(input_yt_api)
            is_authenticated = True
            auth_identifier = input_yt_api
    else:
        st.info("Ensure 'client_secret.json' is in your repo securely to use Google Login.")
        
        if saved_oauth:
            yt_client = get_youtube_service_oauth(saved_oauth)
            if yt_client:
                is_authenticated = True
                auth_identifier = saved_oauth
                st.success("✅ Logged in to Google Account.")
                if st.button("Logout", key="btn_logout"):
                    if "oauth_token" in st.session_state:
                        del st.session_state["oauth_token"]
                    cookie_manager.delete("oauth_token")
                    st.rerun()
        else:
            try:
                redirect_uri = st.text_input("OAuth Redirect URI (Required for Cloud)", value="http://localhost:8501/")
                
                # Read from .oauth_state.json to persist state across Streamlit reruns
                state_file = ".oauth_state.json"
                try:
                    with open(state_file, "r") as f:
                        oauth_states = json.load(f)
                except (FileNotFoundError, json.JSONDecodeError):
                    oauth_states = {}

                if "auth_url" not in st.session_state or st.session_state.get("redirect_uri") != redirect_uri:
                    flow = Flow.from_client_secrets_file(
                        CLIENT_SECRETS_FILE,
                        scopes=SCOPES,
                        redirect_uri=redirect_uri
                    )
                    auth_url, state = flow.authorization_url(prompt='consent')
                    
                    # Save the code_verifier mapped by state to file
                    oauth_states[state] = getattr(flow, "code_verifier", None)
                    with open(state_file, "w") as f:
                        json.dump(oauth_states, f)
                        
                    st.session_state["auth_url"] = auth_url
                    st.session_state["redirect_uri"] = redirect_uri
                
                st.markdown(f'<a href="{st.session_state["auth_url"]}" target="_self"><button style="width:100%; background-color:#4285F4; color:white; border:none; padding:10px; border-radius:5px; cursor:pointer;">1. Login with Google</button></a>', unsafe_allow_html=True)
                
                query_params = st.query_params
                if "code" in query_params and "state" in query_params:
                    auth_code = query_params["code"]
                    auth_state = query_params["state"]
                    if auth_code != st.session_state.get("processed_auth_code"):
                        flow = Flow.from_client_secrets_file(
                            CLIENT_SECRETS_FILE,
                            scopes=SCOPES,
                            redirect_uri=redirect_uri
                        )
                        # Restore code verifier from state logic cache
                        if auth_state in oauth_states:
                            flow.code_verifier = oauth_states[auth_state]
                        
                        # Use auth_response URL to prevent state validation issues
                        auth_response = st.query_params.to_dict()
                        full_url = f"{redirect_uri}?{'&'.join([f'{k}={v}' for k,v in auth_response.items()])}"
                        flow.fetch_token(authorization_response=full_url)
                        creds = flow.credentials
                        oauth_json = json.loads(creds.to_json())
                        st.session_state["oauth_token"] = oauth_json
                        cookie_manager.set("oauth_token", oauth_json, key="set_oauth")
                        st.session_state["processed_auth_code"] = auth_code
                        st.query_params.clear() 
                        st.success("Login successful! Reloading...")
                        time.sleep(1)
                        st.rerun()
            except Exception as e:
                st.error(f"OAuth configuration missing or invalid. {e}")

    input_pl_id = st.text_input("2. Playlist ID", value=saved_pl_id)
    input_gemini_api = st.text_input("3. Gemini API Key", type="password", value=saved_gem_key)

    st.write("") 
    col_btn_save, col_btn_fetch = st.columns(2)
    with col_btn_save:
        if st.button("💾 Save Settings", use_container_width=True):
            cookie_manager.set("yt_api_key", input_yt_api if auth_mode == "🔑 API Key (Read Only)" else "", key="s_yt")
            cookie_manager.set("playlist_id", input_pl_id, key="s_pl")
            cookie_manager.set("gem_api_key", input_gemini_api, key="s_gem")
            st.toast("Settings saved to cookies securely!", icon="✅")
            
    with col_btn_fetch:
        btn_fetch_data = st.button("📥 Fetch Data", type="primary", use_container_width=True)

# ==========================================
# 7. UI: DATA FETCHING LOGIC
# ==========================================
if btn_fetch_data:
    if is_authenticated and input_pl_id:
        try:
            with st.spinner("Fetching videos..."):
                raw_videos = fetch_playlist_videos_cached(input_pl_id, auth_identifier)
                
                if 'df' in st.session_state and not st.session_state['df'].empty:
                    existing_tags = st.session_state['df'].set_index('video_id')['custom_category'].to_dict()
                    for vid in raw_videos:
                        if vid['video_id'] in existing_tags:
                            vid['custom_category'] = existing_tags[vid['video_id']]
                
                st.session_state['df'] = pd.DataFrame(raw_videos)
            st.toast(f"Successfully loaded {len(raw_videos)} videos!", icon="🎉")
        except Exception as e:
            st.error(f"Error fetching data: {e}")
    else:
        st.warning("Please provide necessary authentication and Playlist ID.")

# ==========================================
# 8. UI: MAIN DASHBOARD
# ==========================================
if 'df' in st.session_state and not st.session_state['df'].empty:
    data_frame = st.session_state['df']
    
    metric_col1, metric_col2, metric_col3 = st.columns(3)
    with metric_col1:
        with st.container(border=True): st.metric(label="Total Videos", value=len(data_frame))
    with metric_col2:
        with st.container(border=True): st.metric(label="Unique Channels", value=data_frame['channel'].nunique())
    with metric_col3:
        tagged_count = len(data_frame[data_frame['custom_category'] != DEFAULT_CATEGORY])
        with st.container(border=True): st.metric(label="AI Tagged Videos", value=f"{tagged_count} / {len(data_frame)}")
            
    st.write("---")
    tab_search, tab_ai = st.tabs(["🔍 Search & Edit", "🤖 AI Assistant"])
    
    # ----------------------------------------
    # TAB 1: SEARCH & EDIT
    # ----------------------------------------
    with tab_search:
        search_col1, search_col2, search_col3, search_col4 = st.columns(4)
        with search_col1: search_title = st.text_input("🎬 Search Title")
        with search_col2: search_channel = st.text_input("👤 Search Channel")
        with search_col3: 
            unique_yt_categories = ["All"] + sorted(list(data_frame['yt_category'].unique()))
            selected_yt_category = st.selectbox("📺 YouTube Category Filter", unique_yt_categories)
        with search_col4: 
            unique_categories = ["All"] + TARGET_CATEGORIES + [DEFAULT_CATEGORY]
            selected_category = st.selectbox("📂 AI Category Filter", unique_categories)

        filtered_data = data_frame.copy()
        if search_title: filtered_data = filtered_data[filtered_data['title'].str.contains(search_title, case=False, na=False)]
        if search_channel: filtered_data = filtered_data[filtered_data['channel'].str.contains(search_channel, case=False, na=False)]
        if selected_yt_category != "All": filtered_data = filtered_data[filtered_data['yt_category'] == selected_yt_category]
        if selected_category != "All": filtered_data = filtered_data[filtered_data['custom_category'] == selected_category]

        display_data = filtered_data.copy()
        display_data['video_link'] = "https://youtube.com/watch?v=" + display_data['video_id']
        
        cols = display_data.columns.tolist()
        if 'custom_category' in cols: cols.insert(0, cols.pop(cols.index('custom_category')))
        if 'thumbnail' in cols: cols.insert(0, cols.pop(cols.index('thumbnail')))
        display_data = display_data[cols]
        
        show_delete_options = (auth_mode == "👤 Google Account (Full Access)")
        if show_delete_options:
            display_data.insert(0, 'Select', False)

        display_data = display_data.rename(columns={
            "thumbnail": "Thumb",
            "custom_category": "AI Category",
            "yt_category": "YouTube Category",
            "title": "Video Title",
            "channel": "Channel",
            "video_link": "Watch"
        })

        with st.container(border=True):
            if show_delete_options:
                edited_df = st.data_editor(
                    display_data, 
                    column_config={
                        "Select": st.column_config.CheckboxColumn("Select", default=False),
                        "Watch": st.column_config.LinkColumn("▶️"),
                        "Thumb": st.column_config.ImageColumn(""),
                        "playlist_item_id": None, 
                        "video_id": None
                    },
                    width='stretch', hide_index=True, height=500
                )
                
                videos_to_delete = edited_df[edited_df["Select"] == True]
                if not videos_to_delete.empty:
                    if st.button("🗑️ Remove Selected Videos", type="primary"):
                        try:
                            for pl_item_id in videos_to_delete['playlist_item_id']:
                                delete_video_from_playlist(yt_client, pl_item_id)
                                time.sleep(0.5) 
                            st.success(f"Successfully removed {len(videos_to_delete)} videos! Fetching updated list...")
                            del st.session_state['df']
                            time.sleep(1)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Deletion error: {e}")
            else:
                st.dataframe(
                    display_data, 
                    column_config={
                        "Watch": st.column_config.LinkColumn("▶️"),
                        "Thumb": st.column_config.ImageColumn(""),
                        "playlist_item_id": None,
                        "video_id": None
                    },
                    width='stretch', hide_index=True, height=600 
                )
        
    # ----------------------------------------
    # TAB 2: AI ASSISTANT (SMART TAGGING)
    # ----------------------------------------
    with tab_ai:
        with st.container(border=True):
            st.info("To avoid API limits, this tool only scans videos that haven't been tagged yet.", icon="🤖")
            
            uncategorized_df = data_frame[data_frame['custom_category'] == DEFAULT_CATEGORY]
            st.write(f"**Remaining Videos to Tag:** {len(uncategorized_df)}")
            
            if len(uncategorized_df) == 0:
                st.success("All videos are already categorized! 🎉")
            else:
                if st.button("Start AI Analysis", type="primary"):
                    if not input_gemini_api:
                        st.error("Gemini API Key is missing in the sidebar.")
                    else:
                        matched_results = batch_gemini_categorize(uncategorized_df, input_gemini_api)
                        
                        for vid_id, category in matched_results.items():
                            st.session_state['df'].loc[st.session_state['df']['video_id'] == vid_id, 'custom_category'] = category
                            
                        st.success("✨ AI classification completed successfully!")
                        st.rerun()

else:
    st.info("### Welcome! 👋\n\nPlease configure your Settings and Authentication on the sidebar, then click **Fetch Data** to load your playlist.")