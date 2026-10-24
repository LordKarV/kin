import asyncio
from app.audio.tts import MockTTS, elevenlabs_request


def test_elevenlabs_request_uses_pcm16k_and_api_key_header():
    url, headers, body = elevenlabs_request(voice_id="v1", text="Hello Arjun", model_id="eleven_flash_v2_5", api_key="K", language_code="en")
    assert url == "https://api.elevenlabs.io/v1/text-to-speech/v1/stream?output_format=pcm_16000"
    assert headers["xi-api-key"] == "K"
    assert body["text"] == "Hello Arjun" and body["model_id"] == "eleven_flash_v2_5" and body["language_code"] == "en"


def test_mock_tts_yields_pcm_bytes():
    async def run():
        chunks = [c async for c in MockTTS().stream("hello", voice_id="", language_code="en")]
        return b"".join(chunks)
    pcm = asyncio.run(run())
    assert len(pcm) > 0 and len(pcm) % 2 == 0
