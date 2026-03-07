import csv
import os
import pandas as pd
import threading
import re

def save_tags_to_csv(dataframe, filepath="json_files/exported_ai_tags.csv"):
    """
    Exports the video ID, Title, and Custom Category to a localized CSV backup.
    """
    try:
        # Filter down strictly to categorized items
        tagged_df = dataframe[dataframe['custom_category'] != "General / Unrelated"]
        
        # Select columns to save
        export_df = tagged_df[['video_id', 'title', 'channel', 'custom_category']]
        
        export_df.to_csv(filepath, index=False, quoting=csv.QUOTE_MINIMAL)
        return True, filepath
    except Exception as e:
        return False, str(e)


def save_local_session(playlist_id, dataframe, directory="json_files"):
    """
    Serializes a Pandas DataFrame into a CSV file to persist over logins/reloads securely.
    Offloaded to a background thread to prevent UI blocking.
    """
    def _save():
        try:
            os.makedirs(directory, exist_ok=True)
            safe_pl_id = re.sub(r'[^a-zA-Z0-9_\-]', '', playlist_id)
            filepath = os.path.join(directory, f"{safe_pl_id}_cache.csv")
            dataframe.copy().to_csv(filepath, index=False)
        except Exception:
            pass
            
    threading.Thread(target=_save, daemon=True).start()
    return True
        
def load_local_session(playlist_id, directory="json_files"):
    """
    Deserializes a CSV file if it exists, bypassing the need to fetch YouTube endpoints again.
    """
    safe_pl_id = re.sub(r'[^a-zA-Z0-9_\-]', '', playlist_id)
    filepath = os.path.join(directory, f"{safe_pl_id}_cache.csv")
    if os.path.exists(filepath):
        try:
            return pd.read_csv(filepath)
        except Exception:
            return None
    return None

def merge_csv_tags(current_df, uploaded_csv_file):
    """
    Parses a user-uploaded CSV file mapping back specific 'custom_category' overrides
    locally without wrecking the master index.
    """
    try:
        imported_df = pd.read_csv(uploaded_csv_file)
        if 'video_id' not in imported_df.columns or 'custom_category' not in imported_df.columns:
            return False, "CSV Missing required 'video_id' or 'custom_category' columns."
            
        # Create an update dictionary
        import_dict = imported_df.set_index('video_id')['custom_category'].to_dict()
        
        # Apply dictionary masking over original Datalist
        for vid_id, category in import_dict.items():
            if vid_id in current_df['video_id'].values:
                current_df.loc[current_df['video_id'] == vid_id, 'custom_category'] = category
                
        return True, "Tags synchronized successfully."
    except Exception as e:
        return False, str(e)
