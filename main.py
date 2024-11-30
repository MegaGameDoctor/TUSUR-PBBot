import math
import sqlite3
import time

import requests
import telebot
from telebot import types

waitingToColorChoose = list()

bot = telebot.TeleBot('7574868739:AAFvXmGBX6oVPeQ5Nyz4G9UpN7DNydhxap8')

conn = sqlite3.connect('accounts.sqlite', check_same_thread=False)
cursor = conn.cursor()
cursor.execute(
    "CREATE TABLE IF NOT EXISTS accounts (`tg_id` BIGINT NOT NULL, `player` VARCHAR(255) NOT NULL , UNIQUE (`tg_id`), UNIQUE (`player`))")
conn.commit()

@bot.callback_query_handler(func=lambda call: True)
def answer(call):
    player = getAccountName(call.message.chat.id)
    if call.data.startswith("paint@") and player in waitingToColorChoose:
        waitingToColorChoose.remove(player)
        bot.delete_message(call.message.chat.id, call.message.message_id)
        msgID = bot.send_message(call.message.chat.id, "Обработка закрашивания...").message_id
        data = call.data.split("@")
        answer = paintPixelViaAPI(player, data[2], data[3], data[4])
        bot.delete_message(call.message.chat.id, msgID)
        if answer == "SUCCESS":
            bot.send_message(call.message.chat.id, "Успех! Пиксель закрашен на (" + data[2] + ";" + data[3] + ")")
        if answer == "INCORRECT_COORDS":
            bot.send_message(call.message.chat.id, "Координат (" + data[2] + ";" + data[3] + ") нет на поле")
        if answer.startswith("DELAY:"):
            seconds = answer.split(":")[1]
            bot.send_message(call.message.chat.id, "Не так быстро! Вы сможете закрасить пиксель через " + seconds + " сек.")

def createOrUpdateAccount(tg_id, player):
    tg_id = str(tg_id)
    cursor.execute("DELETE FROM accounts WHERE tg_id=? OR player=?;", (tg_id, player))
    cursor.execute("INSERT INTO accounts (`player`, `tg_id`) VALUES (?, ?)", (player, tg_id))
    conn.commit()


def getAccountName(tg_id):
    tg_id = str(tg_id)
    cursor.execute("SELECT * FROM accounts WHERE tg_id=" + tg_id)
    data = cursor.fetchall()
    result = None
    for n in data:
        result = n[1]
    return result


def getValuesFromAPI(player, value):
    return requests.get('https://pbtusur.ru/PBP/api/getPlayerData.php?player=' + player + '&parameter=' + value).text

def paintPixelViaAPI(player, x, y, color):
    return requests.get('https://pbtusur.ru/PBP/api/paintPixel.php?player=' + player + '&x=' + x + '&y=' + y + '&color=' + color).text

def current_milli_time():
    return round(time.time() * 1000)


@bot.message_handler(content_types=['text'])
def get_text_messages(message):
    player = getAccountName(message.from_user.id)
    if message.text.startswith("/auth "):
        name = message.text.replace("/auth ", "")
        if len(name) < 3 or len(name) > 10:
            bot.send_message(message.from_user.id, "Ник не может быть короче 3-х символов и длиннее 10-ти")
        else:
            createOrUpdateAccount(message.from_user.id, name)
            bot.send_message(message.from_user.id,
                             "Вы успешно привязали аккаунт " + name + " к этому Телеграмм аккаунту")
        return
    if player is None:
        bot.send_message(message.from_user.id, "Вы не авторизованы. Чтобы авторизоваться - напишите /auth <НИК>")
        return

    if message.text.startswith("/paint "):
        nextPixel = int(getValuesFromAPI(player, "nextPixel"))
        if nextPixel > current_milli_time():
            bot.send_message(message.from_user.id, "Вы сможете закрасить следующий пиксель через: " + str(
                math.floor((nextPixel - current_milli_time()) / 1000)) + " сек.")
            return
        coords = message.text.replace("/paint ", "")
        x = coords.split(";")[0]
        y = coords.split(";")[1]
        waitingToColorChoose.append(player)
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(types.InlineKeyboardButton(text='Красный', callback_data='paint@' + player + '@' + x + '@' + y + '@-65536'))
        kb.add(types.InlineKeyboardButton(text='Зелёный', callback_data='paint@' + player + '@' + x + '@' + y + '@-14390489'))
        kb.add(types.InlineKeyboardButton(text='Голубой', callback_data='paint@' + player + '@' + x + '@' + y + '@-16711681'))
        bot.send_message(message.from_user.id, "Выбраны координаты (" + coords + "). Теперь выберите цвет:", reply_markup=kb)
        return

    if message.text == "/canvas":
        msgID = bot.send_message(message.from_user.id, "Формирование полотна...").message_id
        bot.send_photo(message.from_user.id, "https://pbtusur.ru/PBP/api/getCanvasImage.php")
        bot.delete_message(message.from_user.id, msgID)
        return

    if message.text == "/profile":
        bot.send_message(message.from_user.id,
                         "-= Ваш профиль =-\n\nНик: " + player + "\nЗакрашено: " + getValuesFromAPI(player, "painted"))
        return

    if message.text == "/help":
        bot.send_message(message.from_user.id,
                         "Помощь:\n\n1) /auth <НИК> - Сменить аккаунт\n2) /profile - Ваш профиль\n3) /canvas - Получить изображение полотна\n4) /paint <x;y> - Закрасить пиксель")
        return


bot.polling(none_stop=True, interval=0)
conn.close()
