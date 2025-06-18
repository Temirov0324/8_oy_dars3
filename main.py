import asyncio
import logging
import sys
import sqlite3
import random
from dotenv import load_dotenv
from os import getenv
from aiogram import Bot, Dispatcher, html
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardMarkup, \
    KeyboardButton, BotCommand
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties


load_dotenv()
TOKEN = getenv("BOT_TOKEN")


def init_db():
    try:
        conn = sqlite3.connect('capitals.db')
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS capitals
                     (id INTEGER PRIMARY KEY, country TEXT, capital TEXT)''')
        c.execute("SELECT COUNT(*) FROM capitals")
        if c.fetchone()[0] == 0:
            countries = [
                ("O'zbekiston", "Toshkent"),
                ("Qozog'iston", "Astana"),
                ("Rossiya", "Moskva"),
                ("Xitoy", "Pekin"),
                ("AQSh", "Vashington"),
                ("Fransiya", "Parij"),
                ("Yaponiya", "Tokio"),
                ("Germaniya", "Berlin"),
                ("Buyuk Britaniya", "London"),
                ("Italiya", "Rim")
            ]
            c.executemany("INSERT INTO capitals (country, capital) VALUES (?, ?)", countries)
            conn.commit()
        conn.close()
    except sqlite3.Error as e:
        logging.error(f"SQLite xatosi: {e}")


init_db()



class QuizState(StatesGroup):
    SELECT_COUNT = State()
    QUIZ = State()


# Dispatcher va storage
storage = MemoryStorage()
dp = Dispatcher(storage=storage)



async def set_bot_commands(bot: Bot):
    commands = [
        BotCommand(command="/start", description="Botni ishga tushirish"),
        BotCommand(command="/test", description="Poytaxtlar testini boshlash"),
        BotCommand(command="/stop", description="Botni to'xtatish"),
        BotCommand(command="/info", description="Foydalanuvchi haqida ma'lumot")
    ]
    await bot.set_my_commands(commands)


@dp.message(CommandStart())
async def start(message: Message):
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="/test"), KeyboardButton(text="/info")],
        [KeyboardButton(text="/stop")]
    ], resize_keyboard=True)
    await message.answer(
        f"Assalomu alaykum, {html.bold(message.from_user.first_name)}! Poytaxtlar o'yiniga xush kelibsiz! 🎮\n"
        f"Testni boshlash uchun /test buyrug'ini yuboring yoki menyudan tanlang.",
        reply_markup=kb
    )


@dp.message(Command("info"))
async def info_command_handler(message: Message):
    info = f"Username: {html.bold(message.from_user.username or 'N/A')}\n"
    info += f"ID: {html.bold(message.from_user.id)}"
    await message.answer(text=info)


@dp.message(Command('test'))
async def test_command_handler(message: Message, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="5 ta test", callback_data="count_5"),
         InlineKeyboardButton(text="10 ta test", callback_data="count_10"),
         InlineKeyboardButton(text="15 ta test", callback_data="count_15")]
    ])
    await message.answer("Necha ta test yechmoqchisiz? 🤔", reply_markup=kb)
    await state.set_state(QuizState.SELECT_COUNT)


@dp.callback_query(lambda c: c.data and c.data.startswith('count_'), QuizState.SELECT_COUNT)
async def process_count(callback_query: CallbackQuery, state: FSMContext):
    try:
        count = int(callback_query.data.split('_')[1])
        await state.update_data(quiz_count=count, current_question=0, correct_answers=0)
        await send_question(callback_query.message, state)
        await state.set_state(QuizState.QUIZ)
        await callback_query.answer()
    except Exception as e:
        logging.error(f"Count tanlashda xato: {e}")
        await callback_query.message.answer("Xatolik yuz berdi, iltimos qayta urinib ko'ring.")
        await state.clear()


async def send_question(message: Message, state: FSMContext):
    data = await state.get_data()
    current_question = data.get('current_question', 0)
    quiz_count = data.get('quiz_count', 0)

    try:
        conn = sqlite3.connect('capitals.db')
        c = conn.cursor()
        c.execute("SELECT country, capital FROM capitals")
        countries = c.fetchall()
        conn.close()

        if not countries:
            await message.answer("Ma'lumotlar bazasida savollar yo'q! 😔")
            await state.clear()
            return

        correct_country = random.choice(countries)
        correct_answer = correct_country[1]
        other_capitals = [cap[1] for cap in countries if cap[1] != correct_answer]
        wrong_answers = random.sample(other_capitals, min(3, len(other_capitals)))
        answers = wrong_answers + [correct_answer]
        random.shuffle(answers)

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=answers[i], callback_data=f"ans_{answers[i]}_{correct_answer}") for i in
             range(0, 2)],
            [InlineKeyboardButton(text=answers[i], callback_data=f"ans_{answers[i]}_{correct_answer}") for i in
             range(2, 4)]
        ])

        await message.answer(
            f"{html.bold(current_question + 1)}-savol: {correct_country[0]}ning poytaxti qaysi shahar? 🏙️",
            reply_markup=kb)

        await state.update_data(current_question=current_question + 1, correct_answer=correct_answer)
    except Exception as e:
        logging.error(f"Savol yuborishda xato: {e}")
        await message.answer("Xatolik yuz berdi, iltimos qayta urinib ko'ring.")
        await state.clear()


@dp.callback_query(lambda c: c.data and c.data.startswith('ans_'), QuizState.QUIZ)
async def process_answer(callback_query: CallbackQuery, state: FSMContext):
    try:
        data = callback_query.data.split('_')
        user_answer = data[1]
        correct_answer = data[2]

        state_data = await state.get_data()
        correct_answers = state_data.get('correct_answers', 0)
        current_question = state_data.get('current_question', 0)
        quiz_count = state_data.get('quiz_count', 0)

        if user_answer == correct_answer:
            await state.update_data(correct_answers=correct_answers + 1)
            await callback_query.message.answer("To'g'ri javob! ✅")
        else:
            await callback_query.message.answer(f"Noto'g'ri! 😔 To'g'ri javob: {html.bold(correct_answer)}")

        if current_question < quiz_count:
            await send_question(callback_query.message, state)
        else:
            state_data = await state.get_data()
            correct = state_data.get('correct_answers', 0)
            await callback_query.message.answer(
                f"O'yin tugadi! 🎉\n"
                f"Siz {html.bold(quiz_count)} ta savoldan {html.bold(correct)} tasiga to'g'ri javob berdingiz.\n"
                f"Foiz: {html.bold(f'{correct / quiz_count * 100:.1f}%')}"
            )
            await state.clear()

        await callback_query.answer()
    except Exception as e:
        logging.error(f"Javobni qayta ishlashda xato: {e}")
        await callback_query.message.answer("Xatolik yuz berdi, iltimos qayta urinib ko'ring.")
        await state.clear()


@dp.message(Command('stop'))
async def stop_command_handler(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Bot to'xtatildi! Qayta ishga tushirish uchun /start buyrug'ini yuboring.")
    sys.exit(0)


@dp.message()
async def basic_handler(message: Message):
    await message.answer("Iltimos, /test buyrug'ini ishlatib o'yinni boshlang yoki /stop bilan to'xtating! 😊")


async def main():
    if not TOKEN:
        logging.error("BOT_TOKEN .env faylida topilmadi!")
        sys.exit(1)
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await set_bot_commands(bot)
    await dp.start_polling(bot)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())