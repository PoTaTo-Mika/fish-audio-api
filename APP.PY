import gradio as gr
import httpx
import ormsgpack
from pydantic import BaseModel, conint
from typing import Annotated, Literal
import tempfile
import os
import json
import shutil
from datetime import datetime

# 定义缓存文件路径
CACHE_FILE = "token_cache.json"
CACHE_FOLDER = "cache"

# 确保缓存文件夹存在
if not os.path.exists(CACHE_FOLDER):
    os.makedirs(CACHE_FOLDER)

class ServeReferenceAudio(BaseModel):
    audio: bytes
    text: str

class ServeTTSRequest(BaseModel):
    text: str
    chunk_length: Annotated[int, conint(ge=100, le=300, strict=True)] = 200
    format: Literal["wav", "pcm", "mp3"] = "mp3"
    mp3_bitrate: Literal[64, 128, 192] = 128
    references: list[ServeReferenceAudio] = []
    reference_id: str | None = None
    normalize: bool = True
    latency: Literal["normal", "balanced"] = "normal"

def load_cached_data():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r') as f:
            cache = json.load(f)
            return cache.get('api_key', ''), cache.get('api_url', 'https://api.fish.audio/v1/tts')
    return '', 'https://api.fish.audio/v1/tts'

def save_cached_data(api_key, api_url):
    with open(CACHE_FILE, 'w') as f:
        json.dump({'api_key': api_key, 'api_url': api_url}, f)

def text_to_speech(api_key, api_url, text, reference_audio, reference_text):
    if not api_key:
        return None, "Please enter your API key."
    
    if not api_url:
        return None, "Please enter the API URL."
    
    # 保存API密钥和URL到缓存
    save_cached_data(api_key, api_url)
    
    references = []
    if reference_audio is not None:
        with open(reference_audio.name, "rb") as f:
            audio_bytes = f.read()
        references.append(ServeReferenceAudio(audio=audio_bytes, text=reference_text))

    request = ServeTTSRequest(
        text=text,
        references=references
    )

    with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as temp_file:
        output_filename = temp_file.name

        with httpx.Client() as client:
            with client.stream(
                "POST",
                api_url,
                content=ormsgpack.packb(request, option=ormsgpack.OPT_SERIALIZE_PYDANTIC),
                headers={
                    "authorization": f"Bearer {api_key}",
                    "content-type": "application/msgpack",
                },
                timeout=None,
            ) as response:
                if response.status_code != 200:
                    return None, f"Error: {response.status_code} - {response.text}"
                for chunk in response.iter_bytes():
                    temp_file.write(chunk)

    # 生成唯一的文件名并保存到缓存文件夹
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    cache_filename = f"generate_voice_{timestamp}.wav"
    cache_path = os.path.join(CACHE_FOLDER, cache_filename)
    shutil.copy(output_filename, cache_path)

    return output_filename, f"Text-to-speech conversion completed successfully! Saved as {cache_filename}"

with gr.Blocks() as demo:
    gr.Markdown("# [Fish.audio](https://fish.audio) Text-to-Speech WebUI")
    
    cached_api_key, cached_api_url = load_cached_data()
    
    with gr.Row():
        api_key = gr.Textbox(
            label="API Key", 
            placeholder="Enter your Fish.audio API key here", 
            value=cached_api_key
        )
        api_url = gr.Textbox(
            label="API URL",
            placeholder="Enter the API URL here",
            value=cached_api_url
        )
    
    gr.Markdown("You can get the API Key from [here](https://fish.audio/go-api)")

    with gr.Row():
        text_input = gr.Textbox(label="Text to convert", placeholder="Enter the text you want to convert to speech")

    with gr.Row():
        reference_audio = gr.File(label="Reference Audio (optional)")
        reference_text = gr.Textbox(label="Reference Text", placeholder="Enter the text corresponding to the reference audio")

    with gr.Row():
        convert_button = gr.Button("Convert to Speech")

    with gr.Row():
        output_audio = gr.Audio(label="Generated Speech")
        output_message = gr.Textbox(label="Message")

    convert_button.click(
        text_to_speech,
        inputs=[api_key, api_url, text_input, reference_audio, reference_text],
        outputs=[output_audio, output_message]
    )

demo.launch()
