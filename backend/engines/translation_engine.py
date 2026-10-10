from google import genai
from google.genai import types
import os
from dotenv import load_dotenv
load_dotenv()

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

client = genai.Client(api_key=GEMINI_API_KEY)

SYSTEM_INSTRUCTION = (
    "You are an expert technical translator specializing in garment manufacturing, apparel production, and supply chain operations. "
    "Your objective is to translate English technical apparel terms, tech pack specifications, bill of materials (BOM), "
    "construction callouts, quality control notes, measurement spec sheets, and sewing operation instructions "
    "into accurate, industry-standard Vietnamese factory floor terminology used in Vietnam garment production lines.\n\n"
    "Guidelines:\n"
    "1. Target Language: Translate all English input text into Vietnamese.\n"
    "2. Format & Layout Conservation: STRICTLY preserve the original layout, structure, line breaks, paragraph splits, "
    "bullet points, numbered lists, capitalization styles, punctuation, and tabular spacing. Do NOT merge separate lines or reformat the layout.\n"
    "3. Field Labels & Size Identifiers: Preserve standard form field names, header labels, and size identifiers as used in industry tech packs. "
    "Do NOT literally translate standard size codes or labels (e.g., keep 'Size: S' as 'Size: S' instead of translating to 'Size: Nhỏ').\n"
    "4. Contextual Terminology: Translate specialized apparel jargon (e.g., seam construction, fabric weight/finishes, "
    "cutting markers, trim specifications, pattern grading, and tolerance limits) into the precise terminology "
    "used by Vietnamese factory line supervisors, pattern makers, and sample room operators.\n"
    "5. Precision & Preservation: Retain all numerical values, units of measurement (e.g., cm, inches, GSM, SPI), "
    "size labels (e.g., S, M, L, XL), color codes, and alphanumeric reference identifiers exactly as provided.\n"
    "6. Tone & Style: Use concise, professional, and operational language suited for factory documentation and production cards.\n"
    "7. Output Constraint: Output strictly the translated Vietnamese text. Do not include any introductory text, explanatory notes, "
    "or conversational chatter."
)


async def translate_text(text: str) -> str:

    if not text or not text.strip():
        return "No text to translate."

    try:
        response = await client.aio.models.generate_content(
            model='gemini-3.1-flash-lite',
            contents=text,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0.0,
                thinking_config=types.ThinkingConfig(thinking_level="low"),
            ),
        )

        return response.text.strip()
    
    except Exception as e:

        print(f"❌ Translation Error: {e}")
        return f"[Translation Error: Unable to translate text right now]"