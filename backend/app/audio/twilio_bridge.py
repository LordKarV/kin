"""Zero-install phone path: Twilio ConversationRelay (plan §3.4, Phase 5).

VERIFIED 2026-10-24 (twilio.com/docs/voice/twiml/connect/conversationrelay + websocket-messages):
  TwiML  <Connect><ConversationRelay url="wss://…" welcomeGreeting interruptible dtmfDetection ttsProvider transcriptionProvider>
           <Language code="ta-IN" …/> <Parameter name value/>
  Relay → app: setup{sessionId,callSid,from,to,customParameters} · prompt{voicePrompt,lang,last} · interrupt · dtmf{digit} · error
  App → relay: text{token,last,lang,interruptible} · play · sendDigits · language{ttsLanguage,transcriptionLanguage} · end
Relay does STT (Deepgram nova-3) and TTS (ElevenLabs) itself; KIN supplies grounded text. Two legs = two independent
relay sessions (or one relay leg + one laptop WebSocket) bridged through CallSession, as in Twilio's own
human-to-human translation tutorial. VERIFY Tamil code `ta-IN` in the Relay voice-configuration page before the demo."""
from __future__ import annotations

from xml.sax.saxutils import quoteattr

from .pipeline import CallSession, Side


def relay_twiml(ws_url: str, role: str, language: str = "ta-IN", welcome: str = "", other_language: str = "en-US", voice: str = "") -> str:
    v = f" voice={quoteattr(voice)}" if voice else ""
    greet = f" welcomeGreeting={quoteattr(welcome)}" if welcome else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<Response>\n  <Connect>\n'
        f'    <ConversationRelay url={quoteattr(ws_url)}{greet} language={quoteattr(language)} interruptible="any" dtmfDetection="true" '
        f'ttsProvider="ElevenLabs" transcriptionProvider="Deepgram" speechModel="nova-3-general">\n'
        f'      <Language code={quoteattr(language)} ttsProvider="ElevenLabs" transcriptionProvider="Deepgram"{v}/>\n'
        f'      <Language code={quoteattr(other_language)} ttsProvider="ElevenLabs" transcriptionProvider="Deepgram"/>\n'
        f'      <Parameter name="role" value={quoteattr(role)}/>\n'
        "    </ConversationRelay>\n  </Connect>\n</Response>\n"
    )


def relay_lang(lang: str, heritage_code: str = "ta-IN") -> str:
    """Pipeline language ('ta'/'en') → ConversationRelay BCP-47 code."""
    return "en-US" if lang == "en" else heritage_code


class PhoneLeg:
    """Adapts a ConversationRelay WebSocket to CallSession's send_json/send_bytes.
    Transcripts addressed to this leg become Relay `text` messages (Relay speaks them); audio bytes are not needed."""

    def __init__(self, ws, role: str, person: str, heritage_code: str = "ta-IN"):
        self.ws, self.role, self.person, self.heritage_code = ws, role, person, heritage_code
        self.side: Side | None = None

    async def send_json(self, msg: dict) -> None:
        if msg.get("type") == "transcript" and msg.get("listener") == self.person and msg.get("translation"):
            await self.ws.send_json({"type": "text", "token": msg["translation"], "last": True,
                                     "lang": relay_lang(msg.get("target_lang", "en"), self.heritage_code), "interruptible": True})

    async def send_bytes(self, b: bytes) -> None:  # Relay does its own TTS
        return None

    async def attach(self, session: CallSession) -> Side:
        self.side = await session.join(self.role, self.person, self.send_json, self.send_bytes, wants_audio=False)
        return self.side
