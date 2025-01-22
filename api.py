import os,time,sys
from pathlib import Path
root_dir=Path(__file__).parent.as_posix()

# ffmpeg
if sys.platform == 'win32':
    os.environ['PATH'] = root_dir + f';{root_dir}\\ffmpeg;' + os.environ['PATH']+f';{root_dir}/third_party/Matcha-TTS'
else:
    os.environ['PATH'] = root_dir + f':{root_dir}/ffmpeg:' + os.environ['PATH']
    os.environ['PYTHONPATH'] = os.environ.get('PYTHONPATH', '') + ':third_party/Matcha-TTS'
sys.path.append(f'{root_dir}/third_party/Matcha-TTS')
tmp_dir=Path(f'{root_dir}/tmp').as_posix()
logs_dir=Path(f'{root_dir}/logs').as_posix()
os.makedirs(tmp_dir,exist_ok=True)
os.makedirs(logs_dir,exist_ok=True)

from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import logging
from logging.handlers import RotatingFileHandler
import subprocess
import shutil
import datetime
from cosyvoice.cli.cosyvoice import CosyVoice, CosyVoice2
from cosyvoice.utils.file_utils import load_wav
from pydantic import BaseModel
from typing import Optional

import torchaudio,torch
from pathlib import Path
import base64

print("正在下载模型...")
# 下载模型
from modelscope import snapshot_download
snapshot_download('iic/CosyVoice2-0.5B', local_dir='pretrained_models/CosyVoice2-0.5B')
snapshot_download('iic/CosyVoice-300M-SFT', local_dir='pretrained_models/CosyVoice-300M-SFT')
print("模型下载完成!")

# 配置日志
logging.basicConfig(
    level=logging.WARNING,
    handlers=[
        RotatingFileHandler(
            logs_dir+f'/{datetime.datetime.now().strftime("%Y%m%d")}.log',
            maxBytes=1024 * 1024,
            backupCount=5
        )
    ],
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="CosyVoice API",
    description="语音合成与克隆 API",
    version="1.0.0"
)

# 添加 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

sft_model = None
tts_model = None 

VOICE_LIST=['中文女', '中文男', '日语男', '粤语女', '英文女', '英文男', '韩语女']

class TTSRequest(BaseModel):
    """TTS请求参数"""
    text: str = "你好，世界"
    role: str = "中文女"
    speed: float = 1.0
    version: str = "v2"

    class Config:
        json_schema_extra = {
            "example": {
                "text": "你好，世界",
                "role": "中文女",
                "speed": 1.0,
                "version": "v2"
            }
        }

class CloneRequest(BaseModel):
    """克隆请求参数"""
    text: str = "你好，世界"
    reference_audio: str = "example.wav"
    reference_text: Optional[str] = ""
    speed: float = 1.0

    class Config:
        json_schema_extra = {
            "example": {
                "text": "你好，世界",
                "reference_audio": "example.wav",
                "reference_text": "示例文本",
                "speed": 1.0
            }
        }

class OpenAITTSRequest(BaseModel):
    """OpenAI TTS请求参数"""
    model: str = "tts-1"
    input: str = "你好，世界"
    voice: str = "中文女"
    speed: float = 1.0
    response_format: str = "wav"

    class Config:
        json_schema_extra = {
            "example": {
                "model": "tts-1",
                "input": "你好，世界",
                "voice": "中文女",
                "speed": 1.0,
                "response_format": "wav"
            }
        }

class SpeakerListResponse(BaseModel):
    """角色列表响应"""
    v1: list[str] = []
    v2: list[str] = []
    
def get_available_speakers(version: str = "v2") -> list[str]:
    """获取可用的角色列表
    
    Args:
        version: 模型版本，v1或v2
    Returns:
        角色列表
    """
    model = load_model(version)
    return model.list_available_spks()

@app.get("/speakers", description="获取所有可用的角色列表")
async def list_speakers() -> SpeakerListResponse:
    """
    获取所有可用的角色列表
    
    返回 v1 和 v2 两个版本的所有可用角色列表。
    
    Returns:
        {
            "v1": ["角色1", "角色2", ...],
            "v2": ["角色1", "角色2", ...]
        }
    """
    try:
        v1_speakers = get_available_speakers("v1")
        v2_speakers = get_available_speakers("v2")
        return SpeakerListResponse(
            v1=v1_speakers,
            v2=v2_speakers
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取角色列表失败: {str(e)}")

@app.get("/speakers/{version}", description="获取指定版本的可用角色列表")
async def list_speakers_by_version(version: str) -> list[str]:
    """
    获取指定版本的可用角色列表
    
    参数说明:
    - version: 模型版本，必须是 v1 或 v2
    
    Returns:
        ["角色1", "角色2", ...]
    """
    if version not in ["v1", "v2"]:
        raise HTTPException(status_code=400, detail="版本必须是 v1 或 v2")
        
    try:
        speakers = get_available_speakers(version)
        return speakers
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取角色列表失败: {str(e)}")

def base64_to_wav(encoded_str, output_path):
    if not encoded_str:
        raise ValueError("Base64 encoded string is empty.")

    # 将base64编码的字符串解码为字节
    wav_bytes = base64.b64decode(encoded_str)

    # 检查输出路径是否存在，如果不存在则创建
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # 将解码后的字节写入文件
    with open(output_path, "wb") as wav_file:
        wav_file.write(wav_bytes)

    print(f"WAV file has been saved to {output_path}")

def del_tmp_files(tmp_files: list):
    print('正在删除缓存文件...')
    for f in tmp_files:
        if os.path.exists(f):
            print('删除缓存文件:', f)
            os.remove(f)

def load_model(version: str = "v2"):
    """加载模型
    
    Args:
        version: 模型版本，v1使用sft模型，v2使用tts模型
    """
    global sft_model, tts_model
    
    if version == "v1":
        if sft_model is None:
            print("正在加载SFT模型(v1)...")
            sft_model = CosyVoice('pretrained_models/CosyVoice-300M-SFT', load_jit=True)
            print("SFT模型加载完成!")
            # 预热模型
            print("正在预热SFT模型...")
            _ = sft_model.inference_sft("你好", "中文女", stream=False, speed=1.0)
            print("SFT模型预热完成!")
        return sft_model
    else:
        if tts_model is None:
            print("正在加载TTS模型(v2)...")
            tts_model = CosyVoice2('pretrained_models/CosyVoice2-0.5B', load_jit=True, load_trt=False)
            print("TTS模型加载完成!")
            # 预热模型
            print("正在预热TTS模型...")
            dummy_audio = torch.zeros(1, 16000)
            _ = tts_model.inference_cross_lingual("你好", dummy_audio, stream=False, speed=1.0)
            print("TTS模型预热完成!")
        return tts_model

# 实际批量合成完毕后连接为一个文件
def batch(tts_type,outname,params):
    if not shutil.which("ffmpeg"):
        raise HTTPException(status_code=500, detail='必须安装 ffmpeg')    
    prompt_speech_16k=None
    if tts_type!='tts':
        if not params.reference_audio or not os.path.exists(f"{params.reference_audio}"):
            raise HTTPException(status_code=500, detail=f'参考音频未传入或不存在 {params.reference_audio}')
        ref_audio=f"{tmp_dir}/-refaudio-{time.time()}.wav" 
        try:
            subprocess.run(["ffmpeg","-hide_banner", "-ignore_unknown","-y","-i",params.reference_audio,"-ar","16000",ref_audio],
                   stdout=subprocess.PIPE,
                   stderr=subprocess.PIPE,
                   encoding="utf-8",
                   check=True,
                   text=True,
                   creationflags=0 if sys.platform != 'win32' else subprocess.CREATE_NO_WINDOW)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f'处理参考音频失败:{str(e)}')
        
        prompt_speech_16k = load_wav(ref_audio, 16000)

    text=params.text
    audio_list=[]
    if tts_type=='tts':
        model = load_model(getattr(params, 'version', 'v2'))
        print(f"开始合成文本: {text}")
        # 仅文字合成语音
        if getattr(params, 'version', 'v2') == 'v1':
            for i, j in enumerate(model.inference_sft(text, params.role, stream=False, speed=params.speed)):
                audio_list.append(j['tts_speech'])
        else:
            for i, j in enumerate(model.inference_sft(text, params.role, stream=False, speed=params.speed)):
                audio_list.append(j['tts_speech'])
            
    elif tts_type=='clone_eq' and params.reference_text:
        model = load_model('v2')
        print(f"开始同语言克隆合成文本: {text}")
        for i, j in enumerate(model.inference_zero_shot(text,params.reference_text,prompt_speech_16k, stream=False,speed=params.speed)):
            audio_list.append(j['tts_speech'])

    else:
        model = load_model('v2')
        print(f"开始跨语言克隆合成文本: {text}")
        for i, j in enumerate(model.inference_cross_lingual(text,prompt_speech_16k, stream=False,speed=params.speed)):
            audio_list.append(j['tts_speech'])
    audio_data = torch.concat(audio_list, dim=1)
    
    # 根据模型yaml配置设置采样率
    if tts_type=='tts' and getattr(params, 'version', 'v2') == 'v1':
        torchaudio.save(tmp_dir + '/' + outname,audio_data, 22050, format="wav")   
    else:
        torchaudio.save(tmp_dir + '/' + outname,audio_data, 24000, format="wav")   
    
    print(f"音频文件生成成功：{tmp_dir}/{outname}")
    return tmp_dir + '/' + outname

@app.post("/tts", description="文字转语音接口 - 使用内置角色进行语音合成")
async def tts(request: TTSRequest):
    """
    文字转语音接口
    
    将文本转换为语音，支持多个内置角色和两个版本的模型。
    
    参数说明:
    - text: 需要合成的文本内容
    - role: 角色名称，可选值: 中文女、中文男、日语男、粤语女、英文女、英文男、韩语女
    - speed: 语速，范围 0.5-2.0，默认 1.0
    - version: 模型版本，可选 v1 或 v2，默认 v2
    
    注意事项:
    1. 首次请求时需要加载模型，可能需要等待一段时间
    2. v1 版本为较小模型，速度快但质量较低
    3. v2 版本为较大模型，质量好但速度较慢
    
    Returns:
        音频文件 (WAV格式)
    """
    if not request.text:
        raise HTTPException(status_code=400, detail="缺少待合成的文本")
    
    if request.role not in VOICE_LIST:
        raise HTTPException(status_code=400, detail=f"不支持的角色名称，可选值: {', '.join(VOICE_LIST)}")
        
    try:
        outname=f"tts-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S-')}.wav"
        outname=batch(tts_type='tts',outname=outname,params=request)
        return FileResponse(
            outname,
            media_type='audio/wav',
            filename=os.path.basename(outname)
        )
    except Exception as e:
        if os.path.exists(outname):
            os.remove(outname)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/clone", description="跨语言克隆接口 - 支持不同语言间的声音克隆")
@app.post("/clone_mul", description="跨语言克隆接口 - 支持不同语言间的声音克隆")
async def clone(request: CloneRequest):
    """
    跨语言克隆接口
    
    根据参考音频克隆说话人的声音特征，支持跨语言合成。
    
    参数说明:
    - text: 需要合成的目标文本
    - reference_audio: 参考音频文件路径（相对于api.py的路径）
    - speed: 语速，范围 0.5-2.0，默认 1.0
    
    注意事项:
    1. 参考音频需要是清晰的单人声音
    2. 支持不同语言间的克隆，如用中文音频克隆英文/日文等
    3. 参考音频最好是 3-10 秒的短音频
    
    Returns:
        音频文件 (WAV格式)
    """
    try:
        if not request.text:
            raise HTTPException(status_code=400, detail="缺少待合成的文本")
            
        outname=f"clone-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S-')}.wav"
        outname=batch(tts_type='clone',outname=outname,params=request)
        return FileResponse(
            outname,
            media_type='audio/wav',
            filename=os.path.basename(outname)
        )
    except Exception as e:
        if os.path.exists(outname):
            os.remove(outname)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/clone_eq", description="同语言克隆接口 - 相同语言的声音克隆")
async def clone_eq(request: CloneRequest):
    """
    同语言克隆接口
    
    根据参考音频克隆说话人的声音特征，仅支持相同语言。
    
    参数说明:
    - text: 需要合成的目标文本
    - reference_audio: 参考音频文件路径（相对于api.py的路径）
    - reference_text: 参考音频对应的文本内容
    - speed: 语速，范围 0.5-2.0，默认 1.0
    
    注意事项:
    1. 参考音频需要是清晰的单人声音
    2. 参考音频与目标文本必须是相同语言
    3. 必须提供参考音频对应的文本内容
    4. 参考音频最好是 3-10 秒的短音频
    
    Returns:
        音频文件 (WAV格式)
    """
    try:
        if not request.text:
            raise HTTPException(status_code=400, detail="缺少待合成的文本")
        if not request.reference_text:
            raise HTTPException(status_code=400, detail="同语言克隆必须传递引用文本")
            
        outname=f"clone-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S-')}.wav"
        outname=batch(tts_type='clone_eq',outname=outname,params=request)
        return FileResponse(
            outname,
            media_type='audio/wav',
            filename=os.path.basename(outname)
        )
    except Exception as e:
        if os.path.exists(outname):
            os.remove(outname)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/v1/audio/speech", description="OpenAI TTS API 兼容接口")
async def audio_speech(request: OpenAITTSRequest):
    """
    兼容 OpenAI TTS API 接口
    
    提供与 OpenAI TTS API 兼容的接口，支持使用内置角色或克隆音色。
    
    参数说明:
    - model: 模型名称，固定为 tts-1
    - input: 需要合成的文本内容
    - voice: 角色名称或参考音频路径
    - speed: 语速，范围 0.5-2.0，默认 1.0
    - response_format: 返回格式，固定为 wav
    
    使用示例:
    ```python
    from openai import OpenAI
    
    client = OpenAI(api_key='12314', base_url='http://127.0.0.1:9933/v1')
    response = client.audio.speech.create(
        model='tts-1',
        voice='中文女',
        input='你好啊，亲爱的朋友们',
        speed=1.0
    )
    
    # 保存音频文件
    response.stream_to_file('output.wav')
    ```
    
    Returns:
        音频文件 (WAV格式)
    """
    import random
    
    text = request.input
    speed = request.speed
    voice = request.voice
    
    if voice in VOICE_LIST:
        params = TTSRequest(text=text, role=voice, speed=speed, version="v2")
        api_name = 'tts'
    elif Path(voice).exists() or Path(f'{root_dir}/{voice}').exists():
        params = CloneRequest(text=text, reference_audio=voice, speed=speed)
        api_name = 'clone'
    else:
        raise HTTPException(
            status_code=400,
            detail={
                "message": f"必须填写配音角色名({', '.join(VOICE_LIST)})或参考音频路径",
                "type": "ValueError",
                "param": f'speed={speed},voice={voice},input={text}',
                "code": 400
            }
        )
    
    filename=f'openai-{len(text)}-{speed}-{time.time()}-{random.randint(1000,99999)}.wav'
    try:
        outname=batch(tts_type=api_name,outname=filename,params=params)
        return FileResponse(
            outname,
            media_type='audio/wav',
            filename=os.path.basename(outname)
        )
    except Exception as e:
        if os.path.exists(outname):
            os.remove(outname)
        raise HTTPException(
            status_code=400,
            detail={
                "message": str(e),
                "type": e.__class__.__name__,
                "param": f'speed={speed},voice={voice},input={text}',
                "code": 400
            }
        )

if __name__=='__main__':
    import uvicorn
    host='0.0.0.0'
    port=9933
    print(f'\n启动api:http://{host}:{port}\n')
    print("提示: 首次请求时会加载模型，可能需要一些时间...")
    uvicorn.run(app, host=host, port=port)
