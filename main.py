import hashlib
import math
import sqlite3
import time

import requests
import telebot
from telebot import types

waitingToColorChoose = list()

bot = telebot.TeleBot('СЮДА ТОКЕН')

conn = sqlite3.connect('accounts.sqlite', check_same_thread=False)
cursor = conn.cursor()
cursor.execute(
    "CREATE TABLE IF NOT EXISTS accounts (`tg_id` BIGINT NOT NULL, `player` VARCHAR(255) NOT NULL, `password` TEXT NOT NULL, `paintHistory` BOOLEAN NOT NULL, UNIQUE (`tg_id`), UNIQUE (`player`))")
conn.commit()


@bot.callback_query_handler(func=lambda call: True)
def answer(call):
    player = getAccountName(call.message.chat.id)
    hashedPassword = getAccountPassword(call.message.chat.id)
    if call.data.startswith("paint@") and player in waitingToColorChoose:
        waitingToColorChoose.remove(player)
        bot.delete_message(call.message.chat.id, call.message.message_id)
        if call.data == "paint@cancel":
            bot.send_message(call.message.chat.id, "Закрашивание отменено")
            return
        msgID = bot.send_message(call.message.chat.id, "Обработка закрашивания...").message_id
        data = call.data.split("@")
        answer = paintPixelViaAPI(player, hashedPassword, data[2], data[3], data[4])
        bot.delete_message(call.message.chat.id, msgID)
        if answer == "NO_PLAYER":
            bot.send_message(call.message.chat.id, "Некорректные авторизационные данные для игрока " + player)
        elif answer == "SAME_PIXEL":
            bot.send_message(call.message.chat.id, "Вы не можете закрасить пиксель тем же цветом")
        elif answer == "SUCCESS":
            bot.send_message(call.message.chat.id, "Успех! Пиксель закрашен на (" + data[2] + ";" + data[3] + ")")
        elif answer == "INCORRECT_COORDS":
            bot.send_message(call.message.chat.id, "Координат (" + data[2] + ";" + data[3] + ") нет на поле")
        elif answer.startswith("DELAY:"):
            seconds = answer.split(":")[1]
            bot.send_message(call.message.chat.id,
                             "Не так быстро! Вы сможете закрасить пиксель через " + seconds + " сек.")
    elif call.data == "paintHistory@update":
        bot.edit_message_text("Обновление данных...", call.message.chat.id, call.message.message_id)
        sendPaintHistoryMessage(call.message.chat.id)
        bot.delete_message(call.message.chat.id, call.message.message_id)
    else:
        bot.delete_message(call.message.chat.id, call.message.message_id)


def createOrUpdateAccount(tg_id, player, hashedPassword):
    tg_id = str(tg_id)
    cursor.execute("DELETE FROM accounts WHERE tg_id=? OR player=?;", (tg_id, player))
    cursor.execute("INSERT INTO accounts (`player`, `tg_id`, `password`, `paintHistory`) VALUES (?, ?, ?, ?)",
                   (player, tg_id, hashedPassword, False))
    conn.commit()


def getAccountName(tg_id):
    tg_id = str(tg_id)
    cursor.execute("SELECT * FROM accounts WHERE tg_id=" + tg_id)
    data = cursor.fetchall()
    result = None
    for n in data:
        result = n[1]
    return result


def updatePlayerValue(tg_id, key, value):
    tg_id = str(tg_id)
    cursor.execute("UPDATE accounts SET " + str(key) + " = " + str(value) + " WHERE tg_id = " + tg_id)
    conn.commit()


def isPaintHistoryBuyed(tg_id):
    tg_id = str(tg_id)
    cursor.execute("SELECT * FROM accounts WHERE tg_id=" + tg_id)
    data = cursor.fetchall()
    result = False
    for n in data:
        result = bool(n[3])
    return result


def getAccountPassword(tg_id):
    tg_id = str(tg_id)
    cursor.execute("SELECT * FROM accounts WHERE tg_id=" + tg_id)
    data = cursor.fetchall()
    result = None
    for n in data:
        result = n[2]
    return result


def getValuesFromAPI(player, value):
    return requests.get('https://pbtusur.ru/PBP/api/getPlayerData.php?player=' + player + '&parameter=' + value).text


def getPaintHistoryFromAPI(player):
    return requests.get(
        'https://pbtusur.ru/PBP/api/getPaintHistory.php?player=' + player + '&secret=KFl9d3dKDK32L&replaceColorWithString').text


def isPlayerCorrect(player, hashedPassword):
    return requests.get(
        'https://pbtusur.ru/PBP/api/checkPlayerAuth.php?player=' + player + '&hashedPassword=' + hashedPassword).text


def paintPixelViaAPI(player, hashedPassword, x, y, color):
    return requests.get(
        'https://pbtusur.ru/PBP/api/paintPixel.php?player=' + player + '&hashedPassword=' + hashedPassword + '&x=' + x + '&y=' + y + '&color=' + color).text


def current_milli_time():
    return round(time.time() * 1000)


def removePaintHistoryAPIWaste(source):
    source = source.replace("</font>", "").replace("<font color='", "")

    while '>' in source:
        source = source[1:]

    return source


def sendPaintHistoryMessage(userID):
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton(text='Обновить',
                                      callback_data='paintHistory@update'))
    text = ""
    counter = 1
    for line in getPaintHistoryFromAPI(getAccountName(userID)).split("@!@"):
        data = line.split(";")
        if len(data) == 4:
            previousColor = removePaintHistoryAPIWaste(data[3])
            newColor = removePaintHistoryAPIWaste(data[2])
            text += str(counter) + ") (" + data[0] + ";" + data[1] + "): " + previousColor + " -> " + newColor + "\n"
            counter += 1
    bot.send_message(userID, "Ваши последние закрашивания:\n" + text,
                     reply_markup=kb)


@bot.message_handler(content_types=['text'])
def get_text_messages(message):
    player = getAccountName(message.from_user.id)
    if message.text.startswith("/auth "):
        data = message.text.replace("/auth ", "").split(" ")
        if len(data) != 2:
            bot.send_message(message.from_user.id, "Команда использована некорректно")
            return
        name = data[0]
        hashedPassword = hashlib.md5(data[1].encode()).hexdigest()
        if len(name) < 3 or len(name) > 10 or len(name) < 3 or len(name) > 10:
            bot.send_message(message.from_user.id, "Ник и пароль не могут быть короче 3-х символов и длиннее 10-ти")
        else:
            apiAnswer = isPlayerCorrect(name, hashedPassword)
            if apiAnswer == "YES":
                createOrUpdateAccount(message.from_user.id, name, hashedPassword)
                bot.send_message(message.from_user.id,
                                 "Вы успешно привязали аккаунт " + name + " к этому Телеграмм аккаунту")
                print("Игрок " + name + " успешно авторизован")
            elif apiAnswer == "INCORRECT_PASSWORD":
                bot.send_message(message.from_user.id,
                                 "Вы указали неверный пароль")

            elif apiAnswer == "NO_PLAYER":
                bot.send_message(message.from_user.id,
                                 "Такого игрока не существует. Зарегистрируйтесь в приложении")
        return
    if player is None:
        bot.send_message(message.from_user.id,
                         "Вы не авторизованы. Чтобы авторизоваться - напишите /auth <НИК> <ПАРОЛЬ>")
        return

    if message.text.startswith("/paint "):
        nextPixel = int(getValuesFromAPI(player, "nextPixel"))
        if nextPixel > current_milli_time():
            bot.send_message(message.from_user.id, "Вы сможете закрасить следующий пиксель через: " + str(
                math.floor((nextPixel - current_milli_time()) / 1000)) + " сек.")
            return
        coords = message.text.replace("/paint ", "")
        xyData = coords.split(";")
        if len(xyData) != 2:
            bot.send_message(message.from_user.id, "Команда использована некорректно")
            return

        try:
            x = xyData[0]
            y = xyData[1]
            if int(x) < 0 or int(y) < 0:
                bot.send_message(message.from_user.id, "Указаны несуществующие координаты")
                return
        except:
            bot.send_message(message.from_user.id, "Координаты указаны не по формату")
            return

        waitingToColorChoose.append(player)
        kb = types.InlineKeyboardMarkup(row_width=3)
        kb.add(types.InlineKeyboardButton(text='Красный',
                                          callback_data='paint@' + player + '@' + x + '@' + y + '@-65536'))
        kb.add(types.InlineKeyboardButton(text='Зелёный',
                                          callback_data='paint@' + player + '@' + x + '@' + y + '@-14390489'))
        kb.add(types.InlineKeyboardButton(text='Голубой',
                                          callback_data='paint@' + player + '@' + x + '@' + y + '@-16711681'))
        kb.add(types.InlineKeyboardButton(text='Отменить',
                                          callback_data='paint@cancel'))
        bot.send_message(message.from_user.id, "Выбраны координаты (" + coords + "). Теперь выберите цвет:",
                         reply_markup=kb)
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
                         "Помощь:\n\n1) /auth <НИК> <ПАРОЛЬ> - Сменить аккаунт\n2) /profile - Ваш профиль\n3) /canvas - Получить изображение полотна\n4) /paint <x;y> - Закрасить пиксель\n5) /paintHistory - Ваши последние закрашивания")
        return

    if message.text == "/paintHistory":
        if isPaintHistoryBuyed(message.from_user.id):
            sendPaintHistoryMessage(message.from_user.id)
        else:
            keyboard = types.InlineKeyboardMarkup()
            button = types.InlineKeyboardButton(text="Оплатить", pay=True)
            keyboard.add(button)
            prices = [types.LabeledPrice(label="XTR", amount=1)]  # 1 XTR
            bot.send_invoice(
                message.from_user.id,
                title="История закрашиваний",
                description="Функция просмотра истории закрашиваний является платной. Вы можете приобрести её раз и навсегда",
                invoice_payload="paintHistory_purchase_payload",
                provider_token="",
                currency="XTR",
                prices=prices,
                reply_markup=keyboard
            )
        return


@bot.pre_checkout_query_handler(func=lambda query: True)
def handle_pre_checkout_query(pre_checkout_query):
    bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


@bot.message_handler(content_types=['successful_payment'])
def handle_successful_payment(message):
    user_id = message.from_user.id
    if isPaintHistoryBuyed(user_id):
        print(message.successful_payment.provider_payment_charge_id)
        # bot.refund_star_payment(user_id, message.successful_payment.provider_payment_charge_id)
        bot.send_message(message.chat.id, "У вас уже приобретена эта услуга")
    else:
        updatePlayerValue(user_id, "paintHistory", True)
        bot.send_message(message.chat.id, "✅ Вы успешно оплатили доступ к истории закрашиваний. Введите /paintHistory")


print("Бот запущен")
bot.polling(none_stop=True, interval=0)
conn.close()
