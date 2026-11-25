"""Hindi/ Hinglish clip metadata generation: Gemini, Ollama, then offline fallback."""
import asyncio
import json
import logging
import re

log = logging.getLogger(__name__)

FALLBACK = {
    "voiceover": "भाई साहब, ये सीन तो सच में गजब का है! आखिर तक देखो, आगे जो हुआ उसकी उम्मीद किसी को नहीं थी।",
    "caption": "BHAI SAHAB, YE SCENE TO GAZAB HAI! AAKHIR TAK DEKHO!",
    "hook": "भाई साहब, ये क्या सीन हो गया!",
    "title": "आखिर तक देखो, गजब का सीन!",
    "hashtags": "#DesiClip #HindiShorts #Viral",
}

PROMPT = """Create concise metadata for a short vertical video. Return ONLY JSON with keys voiceover (natural spicy Devanagari Hindi, 1-2 sentences, don't invent facts), caption (short Romanized Hinglish in uppercase), hook (Devanagari, max 8 words), title (Hindi), hashtags (3-5 tags). Use this transcript if present, otherwise be generic and truthful. Transcript: """

def _clean_json(text: str):
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError("No JSON in model response")
    obj = json.loads(match.group(0))
    return {key: str(obj.get(key, FALLBACK[key]))[:500] for key in FALLBACK}

async def make_script(transcript: str, gemini_key: str = "", ollama_model: str = "", ollama_url: str = ""):
    prompt = PROMPT + (transcript or "No transcript available.")
    if gemini_key:
        try:
            def call_gemini():
                from google import genai
                client = genai.Client(api_key=gemini_key)
                response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
                return _clean_json(response.text or "")
            return await asyncio.to_thread(call_gemini)
        except Exception as exc:
            log.warning("Gemini failed; trying fallback: %s", exc)
    if ollama_model and ollama_url:
        try:
            def call_ollama():
                import urllib.request
                payload = json.dumps({"model": ollama_model, "prompt": prompt, "stream": False, "format": "json"}).encode()
                req = urllib.request.Request(ollama_url + "/api/generate", data=payload, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=45) as response:
                    return _clean_json(json.loads(response.read()).get("response", ""))
            return await asyncio.to_thread(call_ollama)
        except Exception as exc:
            log.warning("Ollama failed; using offline script: %s", exc)
    return FALLBACK.copy()
