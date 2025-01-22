这是用于 [CosyVoice2](https://github.com/FunAudioLLM/CosyVoice) 的 api 文件，部署好 cosyVoice 项目后，将该 `api.py` 文件同 `webui.py`放在一起，然后执行 `python api.py`。

如果是三方整合包，将 `api.py` 同 bat 脚本放在一起，然后查找其中`python.exe`所在的位置，在bat所在当前文件夹地址栏中输入`cmd`回车，然后执行 `目录/python.exe api.py`

如果执行时提示模块未找到，请执行以下命令安装依赖：
```bash
python.exe -m pip install fastapi uvicorn
```

启动后可以访问以下地址查看接口文档：
- Swagger UI: http://localhost:9933/docs
- ReDoc: http://localhost:9933/redoc

## 根据内置角色合成文字

- 接口地址: `/tts`
- 请求方法: POST
- 请求类型: Content-Type: application/json

### 参数说明

- `text`: 需要合成语音的文字
- `role`: 角色名称，可选值: '中文女', '中文男', '日语男', '粤语女', '英文女', '英文男', '韩语女'
- `speed`: 语速，范围 0.5-2.0，默认 1.0
- `version`: 模型版本，可选 v1 或 v2，默认 v2

### 注意事项
1. v1 版本为较小模型，速度快但质量较低
2. v2 版本为较大模型，质量好但速度较慢
3. 首次请求时需要加载模型，可能需要等待一段时间

### 示例代码
```python
import requests

# 使用 v2 版本（默认）
data = {
    "text": "你好啊亲爱的朋友们",
    "role": "中文女",
    "speed": 1.0
}

# 使用 v1 版本
data = {
    "text": "你好啊亲爱的朋友们",
    "role": "中文女",
    "speed": 1.0,
    "version": "v1"
}

response = requests.post("http://127.0.0.1:9933/tts", json=data, timeout=3600)
with open("output.wav", "wb") as f:
    f.write(response.content)
```

## 同语言克隆音色合成  

- 接口地址：`/clone_eq`
- 请求方法: POST
- 请求类型: Content-Type: application/json

### 参数说明

- `text`: 需要合成语音的文字
- `reference_audio`: 需要克隆音色的参考音频路径
- `reference_text`: 参考音频对应的文字内容
- `speed`: 语速，范围 0.5-2.0，默认 1.0
- `version`: 模型版本，可选 v1 或 v2，默认 v2

### 注意事项
1. 参考音频需要是清晰的单人声音
2. 参考音频与目标文本必须是相同语言
3. 必须提供参考音频对应的文本内容
4. 参考音频最好是 3-10 秒的短音频
5. v1 版本为较小模型，速度快但质量较低
6. v2 版本为较大模型，质量好但速度较慢
7. 参考音频路径相对于 api.py 的路径，例如引用1.wav，该文件和api.py在同一文件夹内，则填写 `1.wav`

### 示例代码
```python
import requests

data = {
    "text": "你好啊亲爱的朋友们。",
    "reference_audio": "10.wav",
    "reference_text": "希望你过的比我更好哟。",
    "speed": 1.0,
    "version": "v2"  # 可选，默认为 v2
}

response = requests.post("http://127.0.0.1:9933/clone_eq", json=data, timeout=3600)
with open("output.wav", "wb") as f:
    f.write(response.content)
```

## 跨语言音色克隆

- 接口地址：`/clone` 或 `/clone_mul`
- 请求方法: POST
- 请求类型: Content-Type: application/json

### 参数说明

- `text`: 需要合成语音的文字
- `reference_audio`: 需要克隆音色的参考音频路径
- `speed`: 语速，范围 0.5-2.0，默认 1.0
- `version`: 模型版本，可选 v1 或 v2，默认 v2

### 注意事项
1. 参考音频需要是清晰的单人声音
2. 支持不同语言间的克隆，如用中文音频克隆英文/日文等
3. 参考音频最好是 3-10 秒的短音频
4. v1 版本为较小模型，速度快但质量较低
5. v2 版本为较大模型，质量好但速度较慢
6. 参考音频路径相对于 api.py 的路径，例如引用1.wav，该文件和api.py在同一文件夹内，则填写 `1.wav`

### 示例代码
```python
import requests

data = {
    "text": "親友からの誕生日プレゼントを遠くから受け取り、思いがけないサプライズと深い祝福に、私の心は甘い喜びで満たされた！。",
    "reference_audio": "10.wav",
    "speed": 1.0,
    "version": "v2"  # 可选，默认为 v2
}

response = requests.post("http://127.0.0.1:9933/clone", json=data, timeout=3600)
with open("output.wav", "wb") as f:
    f.write(response.content)
```

## OpenAI TTS API 兼容接口

- 接口地址: `/v1/audio/speech`
- 请求方法: POST
- 请求类型: Content-Type: application/json

### 参数说明
- `input`: 要合成的文字
- `model`: 固定为 tts-1
- `speed`: 语速，范围 0.5-2.0，默认 1.0
- `response_format`: 返回格式，固定为 wav
- `voice`: 角色名称或参考音频路径
  - 使用内置角色时，可选值: '中文女', '中文男', '日语男', '粤语女', '英文女', '英文男', '韩语女'
  - 用于克隆时，填写参考音频路径

### 注意事项
1. 使用内置角色时默认使用 v2 版本
2. 使用参考音频克隆时默认使用 v2 版本
3. 参考音频路径相对于 api.py 的路径，例如引用1.wav，该文件和api.py在同一文件夹内，则填写 `1.wav`

### 示例代码
```python
from openai import OpenAI

# 使用内置角色
client = OpenAI(api_key='12314', base_url='http://127.0.0.1:9933/v1')
with client.audio.speech.with_streaming_response.create(
    model='tts-1',
    voice='中文女',
    input='你好啊，亲爱的朋友们',
    speed=1.0                    
) as response:
    with open('./test.wav', 'wb') as f:
        for chunk in response.iter_bytes():
            f.write(chunk)

# 使用音色克隆
with client.audio.speech.with_streaming_response.create(
    model='tts-1',
    voice='example.wav',  # 参考音频路径
    input='你好啊，亲爱的朋友们',
    speed=1.0                    
) as response:
    with open('./test.wav', 'wb') as f:
        for chunk in response.iter_bytes():
            f.write(chunk)
```
