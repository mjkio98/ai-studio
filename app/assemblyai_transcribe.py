import os
from flask import Flask, request, jsonify
import assemblyai as aai

aai.settings.api_key = "b1dd1009103c492487aa79357c48e8d1"

app = Flask(__name__)

@app.route('/transcribe-arabic', methods=['POST'])
def transcribe_arabic():
    data = request.json
    audio_url = data.get('audio_url')
    if not audio_url:
        return jsonify({"error": "Missing audio_url"}), 400
    try:
        config = aai.TranscriptionConfig(speech_model=aai.SpeechModel.universal)
        transcript = aai.Transcriber(config=config).transcribe(audio_url)
        if transcript.status == "error":
            return jsonify({"error": transcript.error}), 500
        return jsonify({"text": transcript.text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
