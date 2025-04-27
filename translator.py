import requests
import eng_to_ipa as ipa

def translate_word(word):
    try:
        url = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=uk&dt=t&q=" + word
        response = requests.get(url)
        if response.status_code == 200:
            result = response.json()
            return result[0][0][0]
        else:
            return "-"
    except:
        return "-"

def get_transcription(word):
    try:
        transcription = ipa.convert(word)
        return transcription if transcription else "-"
    except:
        return "-"