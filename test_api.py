from openai import OpenAI

client = OpenAI(api_key="12314", base_url="http://127.0.0.1:9933/v1")
with client.audio.speech.with_streaming_response.create(
    model="tts-1", voice="中文女", input="你好啊，亲爱的朋友们", speed=1.0
) as response:
    with open("./test.wav", "wb") as f:
        for chunk in response.iter_bytes():
            f.write(chunk)
