from deep_translator import GoogleTranslator

# 1. Initialize the translator with target language 'vi' (Vietnamese)
# 'auto' lets Google figure out if the source text is English, Chinese, etc.
translator = GoogleTranslator(source='auto', target='vi')

# 2. Build a translation function.
def translate_text(text: str) -> str:
    # 1. Defensive guard clause for empty/whitespace-only text
    if not text or not text.strip():
        return "No text to translate."

    try:
        # 2. Execute the translation
        translated_text = translator.translate(text)
        return translated_text
        
    except Exception as e:
        # 3. Gracefully handle network drops, timeouts, or rate limits
        print(f"❌ Translation Error: {e}")
        return f"[Translation Error: Unable to translate text right now]"