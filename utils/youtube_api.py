import json
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import streamlit as st

SCOPES = ['https://www.googleapis.com/auth/youtube']

def get_youtube_service_api(api_key):
    try:
        return build('youtube', 'v3', developerKey=api_key)
    except Exception as e:
        st.error(f"Invalid YouTube API Key: {e}")
        return None

def get_youtube_service_oauth(creds_dict, cookie_manager):
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

@st.cache_data(show_spinner=False, ttl=86400)
def get_category_mapping(_youtube_client):
    request = _youtube_client.videoCategories().list(part="snippet", regionCode="US")
    response = request.execute()
    return {item['id']: item['snippet']['title'] for item in response.get('items', [])}

def assign_youtube_categories(youtube_client, videos, category_mapping):
    video_ids = [vid['video_id'] for vid in videos]
    
    cat_lookup = {}
    def callback(request_id, response, exception):
        if exception is None and response:
            for item in response.get('items', []):
                cat_lookup[item['id']] = item['snippet']['categoryId']
                
    batch = youtube_client.new_batch_http_request()
    
    for i in range(0, len(video_ids), 50):
        chunk_ids = video_ids[i:i+50]
        request = youtube_client.videos().list(part="snippet", id=",".join(chunk_ids))
        batch.add(request, callback=callback)
        
    batch.execute()
    
    for vid in videos:
        cat_id = cat_lookup.get(vid['video_id'])
        if cat_id:
            vid['yt_category'] = category_mapping.get(cat_id, "Other")
            
    return videos

@st.cache_data(show_spinner=False, ttl=3600)
def fetch_playlist_videos_cached(playlist_id, auth_identifier, _cookie_manager=None, default_category="General / Unrelated"):
    youtube_client = get_youtube_service_api(auth_identifier) if isinstance(auth_identifier, str) else get_youtube_service_oauth(auth_identifier, _cookie_manager)
    
    cat_map = get_category_mapping(_youtube_client=youtube_client)
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
                'custom_category': default_category
            })
            
        next_page_token = response.get('nextPageToken')
        if not next_page_token:
            break
            
    videos = assign_youtube_categories(youtube_client, videos, cat_map)
    return videos

def delete_videos_batch(youtube_client, playlist_item_ids):
    batch = youtube_client.new_batch_http_request()
    
    def delete_callback(request_id, response, exception):
        if exception:
            print(f"Error deleting {request_id}: {exception}")
            
    for item_id in playlist_item_ids:
        request = youtube_client.playlistItems().delete(id=item_id)
        batch.add(request, callback=delete_callback)
        
    batch.execute()
