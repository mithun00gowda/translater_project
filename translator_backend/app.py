import os
from flask import Flask, request, jsonify, send_file
import speech_recognition as sr
from deep_translator import GoogleTranslator
from gtts import gTTS
from pydub import AudioSegment
import uuid

app = Flask(__name__)

# ==========================================
# CONFIGURATION: Supported Indian Languages
# ==========================================
# We map the language name to the codes required by Google's APIs.
# Format: 'Name': {'speech_code': 'BCP-47 code', 'trans_code': 'ISO-639-1 code'}
LANGUAGES = {
    'Hindi': {'speech': 'hi-IN', 'trans': 'hi'},
    'Kannada': {'speech': 'kn-IN', 'trans': 'kn'},
    'Tamil': {'speech': 'ta-IN', 'trans': 'ta'},
    'Telugu': {'speech': 'te-IN', 'trans': 'te'},
    'Malayalam': {'speech': 'ml-IN', 'trans': 'ml'},
    'English': {'speech': 'en-US', 'trans': 'en'} # Added for testing
}

# Create a folder to store temporary audio files
UPLOAD_FOLDER = 'temp_audio'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ==========================================
# MODULE 1: SPEECH RECOGNITION (ASR)
# ==========================================
def recognize_speech_from_file(file_path, language_name):
    """
    Converts audio file to text using Google Speech Recognition.
    """
    recognizer = sr.Recognizer()
    
    # Get the specific language code for speech (e.g., 'kn-IN' for Kannada)
    lang_code = LANGUAGES.get(language_name, {}).get('speech', 'en-US')

    try:
        # Load the audio file
        with sr.AudioFile(file_path) as source:
            # record the audio data from the file
            audio_data = recognizer.record(source)
            
            # Recognize speech using Google's free API
            text = recognizer.recognize_google(audio_data, language=lang_code)
            return text, None
    except sr.UnknownValueError:
        return None, "Could not understand the audio."
    except sr.RequestError:
        return None, "Could not request results from Speech service."
    except Exception as e:
        return None, str(e)

# ==========================================
# MODULE 2: TRANSLATOR (NMT)
# ==========================================
def translate_text_content(text, source_lang_name, target_lang_name):
    """
    Translates text from source language to target language.
    """
    try:
        # Get ISO codes (e.g., 'kn' -> 'hi')
        src_code = LANGUAGES.get(source_lang_name, {}).get('trans', 'auto')
        tgt_code = LANGUAGES.get(target_lang_name, {}).get('trans', 'en')

        # Use Deep Translator
        translator = GoogleTranslator(source=src_code, target=tgt_code)
        translated_text = translator.translate(text)
        return translated_text
    except Exception as e:
        return f"Error: {str(e)}"

# ==========================================
# MODULE 3: TEXT TO SPEECH (TTS)
# ==========================================
def text_to_speech_file(text, target_lang_name):
    """
    Converts translated text to an MP3 file.
    """
    try:
        # Get ISO code for TTS
        lang_code = LANGUAGES.get(target_lang_name, {}).get('trans', 'en')
        
        # Generate Audio
        tts = gTTS(text=text, lang=lang_code, slow=False)
        
        # Save to a unique file
        filename = f"{uuid.uuid4()}.mp3"
        save_path = os.path.join(UPLOAD_FOLDER, filename)
        tts.save(save_path)
        
        return filename
    except Exception as e:
        print(f"TTS Error: {e}")
        return None

# ==========================================
# API ENDPOINT (The Bridge to Flutter)
# ==========================================
@app.route('/translate_voice', methods=['POST'])
def process_voice_translation():
    # 1. Check if audio file is present
    if 'audio' not in request.files:
        return jsonify({"error": "No audio file provided"}), 400
    
    file = request.files['audio']
    source_lang = request.form.get('source_lang', 'English')
    target_lang = request.form.get('target_lang', 'Hindi')

    # 2. Save the incoming file temporarily
    # Note: Flutter often sends .m4a or .wav. We convert to .wav for consistency if needed.
    input_path = os.path.join(UPLOAD_FOLDER, "input.wav")
    file.save(input_path)

    # 3. Converting Audio Format (Optional but recommended for compatibility)
    # Some speech recognizers fail with raw mobile audio. 
    # Here we load it and export as standard wav.
    try:
        audio = AudioSegment.from_file(input_path)
        wav_path = os.path.join(UPLOAD_FOLDER, "converted.wav")
        audio.export(wav_path, format="wav")
    except Exception as e:
        return jsonify({"error": f"Audio format error: {str(e)}"}), 500

    # -------------------------------------------------
    # STEP A: SPEECH TO TEXT
    # -------------------------------------------------
    original_text, error = recognize_speech_from_file(wav_path, source_lang)
    if error:
        return jsonify({"error": error}), 400

    # -------------------------------------------------
    # STEP B: TRANSLATION
    # -------------------------------------------------
    translated_text = translate_text_content(original_text, source_lang, target_lang)

    # -------------------------------------------------
    # STEP C: TEXT TO SPEECH
    # -------------------------------------------------
    output_audio_filename = text_to_speech_file(translated_text, target_lang)
    
    if not output_audio_filename:
        return jsonify({"error": "Failed to generate speech"}), 500

    # Return Result
    # In a real app, you might return a URL to download the file. 
    # For now, we return the data and can serve the file via another route.
    return jsonify({
        "original_text": original_text,
        "translated_text": translated_text,
        "audio_file": output_audio_filename
    })

@app.route('/get_audio/<filename>', methods=['GET'])
def get_audio(filename):
    return send_file(os.path.join(UPLOAD_FOLDER, filename))

if __name__ == '__main__':
    # Run the server on all interfaces so the emulator/phone can access it
    app.run(host='0.0.0.0', port=5000, debug=True)