import json
import asyncio
from typing import List, Dict, Any
from google import genai
from pydantic import BaseModel, ValidationError
import streamlit as st

class VideoCategoryMatch(BaseModel):
    id: str
    category: str

async def _process_chunk_async(client, prompt: str, semaphore: asyncio.Semaphore, index: int, target_categories: List[str]) -> Dict[str, str]:
    """Single asynchronous request to Gemini with semaphore bounding."""
    async with semaphore:
        try:
            # We use an async HTTP call directly via generated clients if available, or simulate IO wait natively. 
            # Note: `genai` module requires exact async bindings. Assuming async_generate_content natively.
            response = await client.aio.models.generate_content(
                model='gemini-flash-lite-latest', 
                contents=prompt
            )
            raw_text = response.text.strip()
            if raw_text.startswith("```json"): raw_text = raw_text[7:-3]
            elif raw_text.startswith("```"): raw_text = raw_text[3:-3]
            
            # Pydantic validation guarantees list of dicts with appropriate keys
            parsed_data = json.loads(raw_text.strip())
            valid_results = {}
            for item in parsed_data:
                try:
                    match = VideoCategoryMatch(**item)
                    if match.category in target_categories:
                        valid_results[match.id] = match.category
                except ValidationError:
                    continue  # skip hallucinatory items safely
            return valid_results
        except Exception as e:
            print(f"Error in batch {index}: {str(e)}")
            return {}

async def _batch_gemini_categorize_async(df_to_process, gemini_api_key: str, target_categories: List[str], chunk_size: int = 50) -> Dict[str, str]:
    client = genai.Client(api_key=gemini_api_key)
    # Strictly map a semaphore to Gemini RPS limit (usually 15 RPM for standard free tiers)
    semaphore = asyncio.Semaphore(25) 
    
    total_chunks = (len(df_to_process) // chunk_size) + (1 if len(df_to_process) % chunk_size != 0 else 0)
    tasks = []
    
    categories_str = "\n".join([f"{idx+1}. {cat}" for idx, cat in enumerate(target_categories)])
    
    for i in range(total_chunks):
        chunk = df_to_process.iloc[i*chunk_size : (i+1)*chunk_size]
        if chunk.empty: continue
            
        video_list_str = "".join([f"ID: {row.video_id} | Title: {row.title} | Channel: {row.channel}\n" for row in chunk.itertuples(index=False)])
        
        prompt = f"""
        Below is a list of YouTube videos. Identify ONLY the videos that fit into these target categories:
        {categories_str}
        
        If a video does not fit, completely IGNORE it.
        Respond ONLY in valid JSON format mapping the parsed items.
        Example: [{{"id": "video_id", "category": "CategoryName"}}]
        
        Video List:
        {video_list_str}
        """
        task = asyncio.create_task(_process_chunk_async(client, prompt, semaphore, i, target_categories))
        tasks.append(task)
        
    # Gather chunks asynchronously in parallel instead of waiting 4 seconds serially
    results = await asyncio.gather(*tasks)
    
    final_map = {}
    for mapped_chunk in results:
        final_map.update(mapped_chunk)
        
    return final_map

def batch_gemini_categorize(df_to_process, gemini_api_key: str, target_categories: List[str]) -> Dict[str, str]:
    """Synchronous Streamlit entrypoint kicking off the async loop."""
    return asyncio.run(_batch_gemini_categorize_async(df_to_process, gemini_api_key, target_categories))
