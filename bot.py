import telebot
import logging
from config import LOGS, MAX_USERS, MAX_USER_GPT_TOKENS, COUNT_LAST_MSG
import math  # математический модуль для округления
from database import (create_database, add_message, count_users, select_n_last_messages,
                      select_n_last_messages, count_all_limits)
from validators import check_number_of_users, is_gpt_token_limit, is_stt_block_limit, is_tts_symbol_limit
from yandex_gpt import ask_gpt, count_gpt_tokens
from speech_kit import speech_to_text, text_to_speech
from creds import get_bot_token
# настраиваем запись логов в файл
logging.basicConfig(
    filename=LOGS,
    level=logging.NOTSET,
    format="%(asctime)s FILE: %(filename)s IN: %(funcName)s MESSAGE: %(message)s",
    filemode="w",
    datefmt="%Y-%m-%d %H:%M:%S"
    )
bot = telebot.TeleBot(get_bot_token())  # создаём объект бота

create_database()


# обрабатываем команду /start
@bot.message_handler(commands=['start'])
def start_command(message):
    bot.send_message(message.from_user.id, "Привет! Отправь мне голосовое сообщение или текст, и я тебе отвечу!")


# обрабатываем команду /help
@bot.message_handler(commands=['help'])
def help_command(message):
    bot.send_message(message.from_user.id, "Чтобы приступить к общению, отправь мне голосовое сообщение или текст")


# обрабатываем команду /debug - отправляем файл с логами
@bot.message_handler(commands=['debug'])
def debug_command(message):
    with open(LOGS, "rb") as f:
        bot.send_document(message.chat.id, f)


# тут пока что пусто, заходи сюда в следующем уроке =)


@bot.message_handler(commands=['test_tts'])
def tts_handler(message):
    user_id = message.from_user.id
    bot.send_message(user_id,
                     'Отправь следующим сообщеним текст, чтобы я его озвучил!')
    bot.register_next_step_handler(message, tts)


def tts(message):
    user_id = message.from_user.id
    try:
        text = message.text
        tts_symbols, error_message = is_tts_symbol_limit(message=message, text=text)
        if error_message:
            bot.send_message(user_id, error_message)
            return
        add_message(user_id=user_id, full_message=[text, 'test', 0, tts_symbols, 0])
        status_tts, voice_response = text_to_speech(text)
        if status_tts:
            bot.send_voice(user_id, voice_response, reply_to_message_id=message.id)
        else:
            bot.send_message(user_id, "Возникла ошибка", reply_to_message_id=message.id)
    except Exception as e:
        logging.error(e)
        bot.send_message(message.from_user.id, "Не получилось ответить. Попробуй написать другое сообщение")


@bot.message_handler(commands=['test_stt'])
def stt_handler(message):
    user_id = message.from_user.id
    bot.send_message(user_id,
                     'Отправь голосовое сообщение, чтобы я его распознал!')
    bot.register_next_step_handler(message, stt)


def stt(message):
    user_id = message.from_user.id
    try:
        if not message.voice:
            bot.send_message(user_id, 'Неверный тип данный. Повторите попытку, введя /stt снова')
            return
        stt_blocks, error_message = is_stt_block_limit(message, message.voice.duration)
        if error_message:
            bot.send_message(user_id, error_message)
            return
        file_id = message.voice.file_id
        file_info = bot.get_file(file_id)
        file = bot.download_file(file_info.file_path)
        status_stt, stt_text = speech_to_text(file)
        if not status_stt:
            bot.send_message(user_id, stt_text)
            return
        add_message(user_id=user_id, full_message=[stt_text, 'test', 0, 0, stt_blocks])
        bot.send_message(user_id, stt_text)
    except Exception as e:
        logging.error(e)
        bot.send_message(user_id, "Не получилось ответить. Попробуй записать "
                                  "другое сообщение, введя /stt снова")


# обрабатываем текстовые сообщения
@bot.message_handler(content_types=['text'])
def handle_text(message):
    try:
        user_id = message.from_user.id

        # ВАЛИДАЦИЯ: проверяем, есть ли место для ещё одного пользователя (если пользователь новый)
        status_check_users, error_message = check_number_of_users(user_id)
        if not status_check_users:
            bot.send_message(user_id, error_message)  # мест нет =(
            return

        # БД: добавляем сообщение пользователя и его роль в базу данных
        full_user_message = [message.text, 'user', 0, 0, 0]
        add_message(user_id=user_id, full_message=full_user_message)

        # ВАЛИДАЦИЯ: считаем количество доступных пользователю GPT-токенов
        # получаем последние 4 (COUNT_LAST_MSG) сообщения и количество уже потраченных токенов
        last_messages, total_spent_tokens = select_n_last_messages(user_id, COUNT_LAST_MSG)
        # получаем сумму уже потраченных токенов + токенов в новом сообщении и оставшиеся лимиты пользователя
        total_gpt_tokens, error_message = is_gpt_token_limit(last_messages, total_spent_tokens)
        if error_message:
            # если что-то пошло не так — уведомляем пользователя и прекращаем выполнение функции
            bot.send_message(user_id, error_message)
            return

        # GPT: отправляем запрос к GPT
        status_gpt, answer_gpt, tokens_in_answer = ask_gpt(last_messages)
        # GPT: обрабатываем ответ от GPT
        if not status_gpt:
            # если что-то пошло не так — уведомляем пользователя и прекращаем выполнение функции
            bot.send_message(user_id, answer_gpt)
            return
        # сумма всех потраченных токенов + токены в ответе GPT
        total_gpt_tokens += tokens_in_answer

        # БД: добавляем ответ GPT и потраченные токены в базу данных
        full_gpt_message = [answer_gpt, 'assistant', total_gpt_tokens, 0, 0]
        add_message(user_id=user_id, full_message=full_gpt_message)

        bot.send_message(user_id, answer_gpt, reply_to_message_id=message.id)  # отвечаем пользователю текстом
    except Exception as e:
        logging.error(e)  # если ошибка — записываем её в логи
        bot.send_message(message.from_user.id, "Не получилось ответить. Попробуй написать другое сообщение")


@bot.message_handler(content_types=['voice'])
def handle_voice(message: telebot.types.Message):
    try:
        user_id = message.from_user.id
        file_id = message.voice.file_id
        file_info = bot.get_file(file_id)
        file = bot.download_file(file_info.file_path)

        # Проверки, что пользователь есть в базе данных, лимиты токенов,
        status_check_users, error_message = check_number_of_users(user_id)
        if not status_check_users:
            bot.send_message(user_id, error_message)
            return
        stt_blocks, error_message = is_stt_block_limit(message, message.voice.duration)
        if error_message:
            bot.send_message(user_id, error_message)
            return
        status_stt, stt_text = speech_to_text(file)
        if not status_stt:
            bot.send_message(user_id, stt_text)
            return
        # записть потраченных сст токенов
        add_message(user_id=user_id, full_message=[stt_text, 'user', 0, 0, stt_blocks])
        # Получение всех сообщений пользователя
        last_messages, total_spent_tokens = select_n_last_messages(user_id, COUNT_LAST_MSG)
        # сколько потратил пользователь токенов
        total_gpt_tokens, error_message = is_gpt_token_limit(last_messages, total_spent_tokens)
        if error_message:
            bot.send_message(user_id, error_message)
            return
        # Обращение к ГПТ
        status_gpt, answer_gpt, tokens_in_answer = ask_gpt(last_messages)
        if not status_gpt:
            bot.send_message(user_id, answer_gpt)
            return
        # сумма всех потраченных токенов + токены в ответе GPT
        total_gpt_tokens += tokens_in_answer
        # Лимиты ттс
        tts_symbols, error_message = is_tts_symbol_limit(message=message, text=answer_gpt)
        # запись в таблицу текста, роли, GPT токенов и ттс символов
        add_message(user_id=user_id, full_message=[answer_gpt, 'assistant', total_gpt_tokens, tts_symbols, 0])
        if error_message:
            bot.send_message(user_id, error_message)
            return
        status_tts, voice_response = text_to_speech(answer_gpt)
        if status_tts:
            bot.send_voice(user_id, voice_response, reply_to_message_id=message.id)
        else:
            bot.send_message(user_id, answer_gpt, reply_to_message_id=message.id)
    except Exception as e:
        logging.error(e)
        bot.send_message(user_id, "Не получилось ответить. Попробуй записать другое сообщение")


# запускаем бота
if __name__ == "__main__":
    bot.polling()
    logging.info("Бот запущен")
