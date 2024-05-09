import requests
import logging
from config import LOGS
from creds import get_creds  # модуль для получения токенов
from validators import is_tts_symbol_limit, is_stt_block_limit
IAM_TOKEN, FOLDER_ID = get_creds()  # получаем iam_token и folder_id из файлов

# настраиваем запись логов в файл
logging.basicConfig(filename=LOGS,
                    level=logging.NOTSET,
                    format="%(asctime)s FILE: %(filename)s IN: %(funcName)s MESSAGE: %(message)s",
                    filemode="w")


def text_to_speech(text):
    # Аутентификация через IAM-токен
    headers = {
        'Authorization': f'Bearer {IAM_TOKEN}',
    }
    data = {
        'text': text,
        # текст, который нужно преобразовать в голосовое сообщение
        'lang': 'ru-RU',  # язык текста — русский
        'voice': 'alena',  # Женский голос Алёны
        'folderId': FOLDER_ID,
    }
    # Выполняем запрос
    response = requests.post(
        'https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize',
        headers=headers,
        data=data
    )
    if response.status_code == 200:
        return True, response.content, len(text)  # возвращаем статус и аудио
    else:
        return False, "При запросе в SpeechKit возникла ошибка", 0


def speech_to_text(data):
    # указываем параметры запроса
    params = "&".join([
        "topic=general",  # используем основную версию модели
        f"folderId={FOLDER_ID}",
        "lang=ru-RU"  # распознаём голосовое сообщение на русском языке
    ])
    url = f"https://stt.api.cloud.yandex.net/speech/v1/stt:recognize?{params}"
    # аутентификация через IAM-токен
    headers = {
        'Authorization': f'Bearer {IAM_TOKEN}',
    }
    # выполняем запрос
    response = requests.post(url=url, headers=headers, data=data)
    # преобразуем json в словарь
    decoded_data = response.json()
    # проверяем не произошла-ли ошибка при запросе
    if decoded_data.get("error_code") is None:
        logging.info("Успешно")
        return True, decoded_data.get(
            "result"),   # возвращаем статус и текст из аудио
    else:
        logging.error(decoded_data.get("error_code"))
        # возвращаем статус и сообщение об ошибке
        return False, "При запросе в SpeechKit возникла ошибка", 0
