import requests

def translate_word(word):
    try:
        url = f"https://api.mymemory.translated.net/get?q={word}&langpair=en|uk"
        response = requests.get(url)
        data = response.json()
        translation = data['responseData']['translatedText']
        return translation
    except Exception as e:
        print(f"Translation error: {e}")
        return "невідомо"

def get_transcription(word):
    try:
        url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
        response = requests.get(url)
        data = response.json()
        phonetics = data[0]['phonetics']
        if phonetics:
            transcription = phonetics[0].get('text', '')
            return transcription if transcription else "-"
        return "-"
    except Exception as e:
        print(f"Transcription error: {e}")
        return "-"