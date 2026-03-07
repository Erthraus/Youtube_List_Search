"""
YouTube Playlist AI Manager & Editor
Open Source SaaS Project for fetching, managing, and categorizing YouTube playlist videos using Gemini AI.
Fully compatible with Streamlit Cloud Deployment, using Browser Cookies and Session States.
"""

import streamlit as st
import pandas as pd
from google_auth_oauthlib.flow import Flow
import extra_streamlit_components as stx
import time
import json
import os
import re
import secrets
import fcntl

# Import decoupled utilities
from utils.youtube_api import (
    get_youtube_service_api,
    get_youtube_service_oauth,
    fetch_playlist_videos_cached,
    delete_videos_batch
)
from utils.gemini_api import batch_gemini_categorize
from utils.storage import (
    save_tags_to_csv, 
    save_local_session, 
    load_local_session, 
    merge_csv_tags
)

# Allow OAuth testing over HTTP for local development (default true unless ENV=production)
if os.getenv("ENV", "development") != "production":
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

# ==========================================
# 1. PAGE CONFIG & CUSTOM CSS
# ==========================================
st.set_page_config(page_title="YT Playlist Manager", layout="wide")

st.markdown("""
<style>
    /* YouTube Aesthetics Constraints */
    .block-container { padding-top: 2rem; padding-bottom: 2rem; }
    [data-testid="stMetricValue"], [data-testid="stMetricLabel"], label, p { cursor: default !important; user-select: none !important; color: #f1f1f1 !important;}
    h1, h2, h3, h4 { color: #f1f1f1 !important; font-family: 'Roboto', Arial, sans-serif; letter-spacing: -0.5px; }
    [data-baseweb="select"], [data-baseweb="select"] * { cursor: pointer !important; }
    input, textarea { cursor: text !important; border: 1px solid #333333 !important; border-radius: 4px !important; }
    .stButton>button { border: 1px solid #333333 !important; color: #f1f1f1 !important; transition: all 0.2s ease-in-out; background-color: #212121; }
    .stButton>button:hover { background-color: #FF0000 !important; color: #ffffff !important; border-color: #FF0000 !important; }
    .stProgress > div > div > div > div { background-color: #FF0000; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. CONSTANTS & AI CATEGORIES
# ==========================================
SCOPES = ['https://www.googleapis.com/auth/youtube']

DEFAULT_CATEGORY = "General / Unrelated"

# ==========================================
# 3. COOKIE MANAGER INITIALIZATION
# ==========================================
cookie_manager = stx.CookieManager()
time.sleep(0.1)




# ==========================================
# 6. UI: MAIN APP & SIDEBAR
# ==========================================
st.title("YouTube Playlist Dashboard")

with st.sidebar:
    st.header("Settings & Login")
    
    saved_yt_key = cookie_manager.get(cookie="yt_api_key") or ""
    saved_pl_id = cookie_manager.get(cookie="playlist_id") or ""
    saved_gem_key = cookie_manager.get(cookie="gem_api_key") or ""
    saved_session_id = st.session_state.get("session_id") or cookie_manager.get(cookie="session_id")
    
    saved_oauth = None
    if saved_session_id:
        try:
            with open("json_files/.oauth_sessions.json", "r") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                sessions = json.load(f)
                saved_oauth = sessions.get(saved_session_id)
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
    
    st.write("---")
    
    yt_client = None
    is_authenticated = False
    auth_identifier = None

    if saved_oauth:
        yt_client = get_youtube_service_oauth(saved_oauth, cookie_manager)
        if yt_client:
            is_authenticated = True
            auth_identifier = saved_oauth
            st.success("System Linked (OAuth)")
            
            # The Logout Fix Hook
            if st.button("Disconnect Session", key="btn_logout"):
                if "session_id" in st.session_state: del st.session_state["session_id"]
                if "oauth_token" in st.session_state: del st.session_state["oauth_token"]
                if "df" in st.session_state: del st.session_state["df"]
                cookie_manager.delete("session_id")
                safe_pl_id = re.sub(r'[^a-zA-Z0-9_\-]', '', saved_pl_id)
                cache_filepath = os.path.join("json_files", f"{safe_pl_id}_cache.csv")
                if os.path.exists(cache_filepath):
                    try: os.remove(cache_filepath)
                    except Exception: pass
                # Agressive browser URL query wipe to combat streamlit state-loop bug
                st.query_params.clear()
                st.rerun()
    else:
        # Optional manual fallback
        input_yt_api = st.text_input("YouTube API Key (Fallback)", type="password", value=saved_yt_key)
        if input_yt_api:
            yt_client = get_youtube_service_api(input_yt_api)
            is_authenticated = True
            auth_identifier = input_yt_api
        else:
            input_yt_api = ""

    input_pl_id = st.text_input("Target Playlist ID", value=saved_pl_id)
    input_gemini_api = st.text_input("Gemini Engine Key", type="password", value=saved_gem_key)

    st.write("---")
    st.subheader("Custom Target Categories")
    custom_categories_input = st.text_area(
        "Enter categories separated by commas:", 
        value="Personal Development, Vocal Training, Software Developer, Politics, Gameplay",
        help="These are the labels Gemini will use to organize your list."
    )
    # Parse list on the fly
    TARGET_CATEGORIES = [cat.strip() for cat in custom_categories_input.split(",") if cat.strip()]

    st.write("") 
    col_btn_save, col_btn_fetch = st.columns(2)
    with col_btn_save:
        if st.button("Save Variables", use_container_width=True):
            if not saved_oauth:
                cookie_manager.set("yt_api_key", input_yt_api, key="s_yt")
            cookie_manager.set("playlist_id", input_pl_id, key="s_pl")
            cookie_manager.set("gem_api_key", input_gemini_api, key="s_gem")
            st.toast("Settings saved reliably.")
            
    with col_btn_fetch:
        btn_fetch_data = st.button("Refresh YouTube API", type="primary", use_container_width=True)

# ==========================================
# 7. UI: DATA FETCHING / PERSISTENCE LOGIC
# ==========================================
# Auto-load local session if available on startup/rerun
if 'df' not in st.session_state and is_authenticated and input_pl_id:
    local_df = load_local_session(input_pl_id)
    if local_df is not None:
        st.session_state['df'] = local_df
        st.session_state['sidebar_state'] = 'collapsed'

# Force explicit sync from YouTube
if btn_fetch_data:
    if is_authenticated and input_pl_id:
        try:
            with st.spinner("Fetching videos..."):
                raw_videos = fetch_playlist_videos_cached(input_pl_id, auth_identifier, cookie_manager)
                
                if 'df' in st.session_state and not st.session_state['df'].empty:
                    existing_tags = st.session_state['df'].set_index('video_id')['custom_category'].to_dict()
                    for vid in raw_videos:
                        if vid['video_id'] in existing_tags:
                            vid['custom_category'] = existing_tags[vid['video_id']]
                
                st.session_state['df'] = pd.DataFrame(raw_videos)
                
                # Persist to physical database (PKL)
                save_local_session(input_pl_id, st.session_state['df'])
                
            st.session_state['sidebar_state'] = 'collapsed'  # Collapse sidebar to save space
            st.toast(f"Successfully loaded {len(raw_videos)} videos!")
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
    tab_search, tab_ai = st.tabs(["Search & Edit", "AI Assistant"])
    
    # ----------------------------------------
    # TAB 1: SEARCH & EDIT
    # ----------------------------------------
    with tab_search:
        search_col1, search_col2, search_col3, search_col4 = st.columns(4)
        with search_col1: search_title = st.text_input("Search Title")
        with search_col2: search_channel = st.text_input("Search Channel")
        with search_col3: 
            unique_yt_categories = ["All"] + sorted(list(data_frame['yt_category'].unique()))
            selected_yt_category = st.selectbox("YouTube Category Filter", unique_yt_categories)
        with search_col4: 
            unique_categories = ["All"] + TARGET_CATEGORIES + [DEFAULT_CATEGORY]
            selected_category = st.selectbox("AI Category Filter", unique_categories)

        filtered_data = data_frame
        if search_title: filtered_data = filtered_data[filtered_data['title'].str.contains(search_title, case=False, na=False)]
        if search_channel: filtered_data = filtered_data[filtered_data['channel'].str.contains(search_channel, case=False, na=False)]
        if selected_yt_category != "All": filtered_data = filtered_data[filtered_data['yt_category'] == selected_yt_category]
        if selected_category != "All": filtered_data = filtered_data[filtered_data['custom_category'] == selected_category]
        
        # UI Pagination chunking
        if 'page_number' not in st.session_state:
            st.session_state.page_number = 0
            
        PAGE_SIZE = 100
        total_pages = (len(filtered_data) // PAGE_SIZE) + (1 if len(filtered_data) % PAGE_SIZE > 0 else 0)
        
        display_data = filtered_data.copy()
        display_data['video_link'] = "https://youtube.com/watch?v=" + display_data['video_id']
        
        cols = display_data.columns.tolist()
        if 'custom_category' in cols: cols.insert(0, cols.pop(cols.index('custom_category')))
        if 'thumbnail' in cols: cols.insert(0, cols.pop(cols.index('thumbnail')))
        display_data = display_data[cols]
        
        show_delete_options = saved_oauth is not None
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
        
        # Slice for current active page
        current_page = st.session_state.page_number
        start_idx = current_page * PAGE_SIZE
        end_idx = start_idx + PAGE_SIZE
        paginated_data = display_data.iloc[start_idx:end_idx]

        with st.container(border=True):
            # Define YouTube-like badge colors
            badge_colors = ["#FF0000", "#FF4500", "#1E90FF", "#32CD32", "#FFD700", "#8A2BE2"]
            category_color_map = {cat: badge_colors[i % len(badge_colors)] for i, cat in enumerate(TARGET_CATEGORIES)}
            
            column_config_dict = {
                "Watch": st.column_config.LinkColumn("Watch"),
                "Thumb": st.column_config.ImageColumn("Preview"),
                "playlist_item_id": None, 
                "video_id": None,
                "AI Category": st.column_config.TextColumn("AI Category", help="Generated by Gemini")
            }
            
            if show_delete_options:
                column_config_dict["Select"] = st.column_config.CheckboxColumn("Select", default=False)
                edited_df = st.data_editor(
                    paginated_data, 
                    column_config=column_config_dict,
                    width='stretch', hide_index=True, height=500
                )
                
                videos_to_delete = edited_df[edited_df["Select"] == True]
                if not videos_to_delete.empty:
                    if st.button("Remove Selected Videos", type="primary"):
                        try:
                            item_ids = videos_to_delete['playlist_item_id'].tolist()
                            delete_videos_batch(yt_client, item_ids)
                            fetch_playlist_videos_cached.clear()
                            
                            # Filter memory frame explicitly and resave datalist immediately to avoid fetching again
                            st.session_state['df'] = st.session_state['df'][~st.session_state['df']['playlist_item_id'].isin(item_ids)]
                            save_local_session(input_pl_id, st.session_state['df'])
                            
                            st.success(f"Successfully removed {len(videos_to_delete)} videos!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Deletion error: {e}")
            else:
                st.dataframe(
                    paginated_data, 
                    column_config=column_config_dict,
                    width='stretch', hide_index=True, height=600 
                )
                
        # Pagination controls row
        pg_col1, pg_col2, pg_col3 = st.columns([1, 2, 1])
        with pg_col1:
            if st.button("Previous") and st.session_state.page_number > 0:
                st.session_state.page_number -= 1
                st.rerun()
        with pg_col2:
            st.markdown(f"<div style='text-align: center'>Page {current_page + 1} of {max(total_pages, 1)} <br> <small>(Showing {len(paginated_data)} records)</small></div>", unsafe_allow_html=True)
        with pg_col3:
            if st.button("Next") and (st.session_state.page_number + 1) < total_pages:
                st.session_state.page_number += 1
                st.rerun()
        
    # ----------------------------------------
    # TAB 2: AI ASSISTANT (SMART TAGGING)
    # ----------------------------------------
    with tab_ai:
        with st.container(border=True):
            st.info("To avoid API limits, this tool only scans videos that haven't been tagged yet.")
            
            uncategorized_df = data_frame[data_frame['custom_category'] == DEFAULT_CATEGORY]
            st.write(f"**Remaining Videos to Tag:** {len(uncategorized_df)}")
            
            if len(uncategorized_df) == 0:
                st.success("All videos are already categorized.")
            else:
                if st.button("Start AI Analysis", type="primary"):
                    if not input_gemini_api:
                        st.error("Gemini API Key is missing in the sidebar.")
                    else:
                        with st.spinner("Asynchronously batching to Gemini AI..."):
                            matched_results = batch_gemini_categorize(uncategorized_df, input_gemini_api, TARGET_CATEGORIES)
                            
                        for vid_id, category in matched_results.items():
                            st.session_state['df'].loc[st.session_state['df']['video_id'] == vid_id, 'custom_category'] = category
                            
                        # Reserialize immediately to lock in ML changes locally without needing reload
                        save_local_session(input_pl_id, st.session_state['df'])
                        
                        st.success("AI classification completed successfully.")
                        st.rerun()
                        
            st.write("---")
            
            # --- AI Tab Utilities Footer ---
            ft_col1, ft_col2 = st.columns(2)
            with ft_col1:
                st.write("**Import AI Tags:**")
                uploaded_csv = st.file_uploader("Upload an exported CSV to sync tag overrides locally", type=["csv"], label_visibility="collapsed")
                if uploaded_csv:
                    success, message = merge_csv_tags(st.session_state['df'], uploaded_csv)
                    if success:
                        save_local_session(input_pl_id, st.session_state['df'])
                        st.success(message)
                        st.rerun()
                    else:
                        st.error(message)

            with ft_col2:
                st.write("**Export AI Tags:**")
                if st.button("Export Classified Tags to CSV", use_container_width=True):
                    success, msg = save_tags_to_csv(data_frame)
                    if success:
                        st.success(f"Tags saved locally to {msg}.")
                    else:
                        st.error(f"Failed to export: {msg}")

else:
    # Minimalist System Gateway Design 
    st.markdown("<h1 style='text-align: center; color: #FF0000;'>SYSTEM ACCESS REQUIRED</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #aaaaaa;'>Secure connection to YouTube properties is not established.</p><br>", unsafe_allow_html=True)
    
    col_e1, col_e2, col_e3 = st.columns([1, 2, 1])
    with col_e2:
        with st.container(border=True):
            st.markdown("<h3 style='text-align: center;'>OAUTH 2.0 GATEWAY</h3>", unsafe_allow_html=True)
            st.markdown("<p style='text-align: center;'>Please authenticate with Google to securely provision read and write access to your playlists.</p>", unsafe_allow_html=True)
            st.write("")
            
            try:
                # --------------------------------------------------------------------------------
                # SECRET CONFIGURATION CHECK
                # --------------------------------------------------------------------------------
                if "gcp_oauth" not in st.secrets:
                    st.error("Missing Google OAuth credentials in Streamlit Secrets.")
                    st.markdown("""
                    **How to fix this:**
                    1. Create a file called `.streamlit/secrets.toml` in your project root.
                    2. Add your Google OAuth Web credentials like this:
                    ```toml
                    [gcp_oauth.web]
                    client_id = "YOUR_CLIENT_ID"
                    project_id = "YOUR_PROJECT_ID"
                    auth_uri = "https://accounts.google.com/o/oauth2/auth"
                    token_uri = "https://oauth2.googleapis.com/token"
                    auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
                    client_secret = "YOUR_CLIENT_SECRET"
                    redirect_uris = ["http://localhost:8501/", "https://your-production-app.com/"]
                    ```
                    *(Note: Ensure you leave `[gcp_oauth.web]` exactly as-is so the dictionary parses correctly).*
                    """)
                    st.stop()
                    
                ALLOWED_REDIRECTS = ["http://localhost:8501/", "https://your-production-app.com/"]
                redirect_uri = st.selectbox("Redirect URI Proxy", ALLOWED_REDIRECTS)
                state_file = "json_files/.oauth_state.json"
                try:
                    with open(state_file, "r") as f:
                        fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                        oauth_states = json.load(f)
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                except (FileNotFoundError, json.JSONDecodeError):
                    oauth_states = {}

                if "auth_url" not in st.session_state or st.session_state.get("redirect_uri") != redirect_uri:
                    # Switch from file to config dictionary via st.secrets
                    flow = Flow.from_client_config(dict(st.secrets["gcp_oauth"]), scopes=SCOPES, redirect_uri=redirect_uri)
                    auth_url, state = flow.authorization_url(prompt='consent')
                    
                    current_time = time.time()
                    sanitized_states = {k: v for k, v in oauth_states.items() if isinstance(v, dict) and (current_time - v.get("ts", 0)) < 3600}
                    sanitized_states[state] = {"verifier": getattr(flow, "code_verifier", None), "ts": current_time}
                    
                    # Safe Write for States
                    with open(state_file, "a+") as f:
                        f.seek(0)
                        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                        try:
                            file_content = f.read()
                            current_states = json.loads(file_content) if file_content else {}
                        except json.JSONDecodeError:
                            current_states = {}
                        current_states.update(sanitized_states)
                        f.seek(0)
                        f.truncate()
                        json.dump(current_states, f)
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                        
                    st.session_state["auth_url"] = auth_url
                    st.session_state["redirect_uri"] = redirect_uri
                
                st.markdown(f'<a href="{st.session_state["auth_url"]}" target="_self"><button style="width:100%; background-color:#FF0000; color:#FFFFFF; border: none; padding:12px; border-radius:4px; font-weight:bold; cursor:pointer;">[ INITIATE CONNECTION SEQUENCE ]</button></a>', unsafe_allow_html=True)
                
                query_params = st.query_params
                if "code" in query_params and "state" in query_params:
                    auth_code = query_params["code"]
                    auth_state = query_params["state"]
                    if auth_code != st.session_state.get("processed_auth_code"):
                        flow = Flow.from_client_config(dict(st.secrets["gcp_oauth"]), scopes=SCOPES, redirect_uri=redirect_uri)
                        if auth_state in oauth_states:
                            state_data = oauth_states[auth_state]
                            flow.code_verifier = state_data.get("verifier") if isinstance(state_data, dict) else state_data
                        
                        auth_response = st.query_params.to_dict()
                        full_url = f"{redirect_uri}?{'&'.join([f'{k}={v}' for k,v in auth_response.items()])}"
                        flow.fetch_token(authorization_response=full_url)
                        creds = flow.credentials
                        oauth_json = json.loads(creds.to_json())
                        
                        # Generate securely mapped session token
                        session_id = secrets.token_hex(32)
                        st.session_state["session_id"] = session_id
                        st.session_state["oauth_token"] = oauth_json
                        cookie_manager.set("session_id", session_id, key="set_oauth_session")
                        
                        # Save OAuth payload to backend storage securely
                        sessions_file = "json_files/.oauth_sessions.json"
                        with open(sessions_file, "a+") as f:
                            f.seek(0)
                            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                            try:
                                content = f.read()
                                active_sessions = json.loads(content) if content else {}
                            except json.JSONDecodeError:
                                active_sessions = {}
                            active_sessions[session_id] = oauth_json
                            f.seek(0)
                            f.truncate()
                            json.dump(active_sessions, f)
                            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                        
                        st.session_state["processed_auth_code"] = auth_code
                        st.query_params.clear() 
                        st.success("Uplink Established! Standardizing interface...")
                        st.rerun()
            except Exception as e:
                st.error(f"Authentication Error: {e}")