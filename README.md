# Voice Agency 404

![404 Team](https://img.shields.io/badge/BUILT%20BY-404%20TEAM-black?style=flat-square)
![Hackathon Prototype](https://img.shields.io/badge/STATUS-HACKATHON%20PROTOTYPE-555?style=flat-square)
![Windows](https://img.shields.io/badge/DEMO-WINDOWS-black?style=flat-square)
![License MIT](https://img.shields.io/badge/LICENSE-MIT-555?style=flat-square)

**404 jamoasi yaratgan o‘zbekcha ovozli avtoservis yordamchisi.** Mijoz Telegram orqali qo‘ng‘iroq qiladi. AI muammoni eshitadi, ustaga kerakli tafsilotlarni so‘raydi va tashrif so‘rovini kalendarga yozadi. Usta sayt orqali so‘rovni qabul qiladi, rad etadi yoki boshqa vaqt taklif qiladi.

## 🎬 Bitta tugma bilan demo

1. **Python 3.14 x64** va Windows Python Launcher o‘rnatilgan bo‘lsin.
2. Repozitoriyni klonlang yoki **Code → Download ZIP** orqali yuklab, arxivdan chiqaring.
3. **`start-demo.bat`** faylini ikki marta bosing. Birinchi ishga tushirishda Python paketlari o‘rnatiladi. Oyna sizdan Gemini kaliti, Telegram API ID va API hash’ni so‘raydi. Telegram API ma’lumotlari [API development tools](https://my.telegram.org) orqali olinadi.
4. Telegram raqamingizni, kelgan login kodini va kerak bo‘lsa ikki bosqichli tasdiqlash parolini o‘sha oynaga kiriting. Keyingi startlarda lokal sessiya qayta ishlatiladi.
5. Robot avtomatik qo‘ng‘iroq kutadi va [ishchi dashboard’i](http://127.0.0.1:8744/) brauzerda ochiladi. Ishni tugatganda **Ctrl+C** bosing.

Ishga tushirgich kalitlarni lokal `.env` fayliga yozadi. Telegram sessiyasi va mijozlar bazasi ham kompyuterda saqlanadi. Uchala ma’lumot Git’dan chiqarilgan. Suhbat paytida audio Gemini Live’ga uzatiladi. Dashboard faqat lokal manzilda ishlaydi.

## ☎️ Hakamlar uchun sinov

1. Ikkinchi Telegram akkauntidan robot ulangan akkauntga qo‘ng‘iroq qiling. *“Cobalt’im tormoz bosganda chiyillayapti. Ertaga 14:30 da ko‘rib bera olasizlarmi?”*
2. AI yetishmagan savolni beradi va demo tarifidan narx aytadi. Qo‘ng‘iroq tarixi va tashrif so‘rovi dashboard’da ko‘rinadi. *“Bo‘ldi, rahmat”* deb suhbatni yakunlang.
3. **Qabul qilish** vaqtni band qiladi va mijozga Telegram’dan aniq sana va soatni yuboradi. **Rad etish** so‘ralgan vaqtda qabul qilib bo‘lmasligini bildiradi.
4. **Bo‘sh vaqt** orqali boshqa vaqt taklif qiling. Mijoz Telegram’dagi taklifga *“Bo‘ladi”* deb javob bergach, vaqt band qilinadi. Bitta ustaning 30 daqiqalik tashriflari to‘qnashmaydi. Xabar yuborilmasa kartadan qayta uriniladi.

Demo tariflari ko‘rik yoki ish haqi uchun. Detal va yakuniy ta’mir narxi ustaning ko‘rigidan keyin aniqlanadi.

## 🧩 Kod tuzilishi

| Fayl | Vazifasi |
| --- | --- |
| `start-demo.bat` | Lokal Python muhitini tayyorlaydi, paketlarni o‘rnatadi, login va demoni boshlaydi. |
| `telegram_login.py` | API qiymatlarini qabul qiladi va shaxsiy Telegram sessiyasini yaratadi. |
| `telegram_call_test.py` | Qo‘ng‘iroqni ko‘taradi, ovozni uzatadi, dashboard’ni ochadi va Telegram xabarlarini boshqaradi. |
| `gemini_voice.py` va `operator-prompt.md` | Jonli suhbat, mijoz gapirganda AI ovozini to‘xtatish, tarifni olish va so‘rovni yozish. |
| `service_desk.py` | SQLite, tariflar, vaqt tekshiruvi, Telegram xabar navbati va lokal HTTP API. |
| `dashboard.html` | Monochrome haftalik kalendar, qo‘ng‘iroqlar tarixi va usta amallari. |

`GET /api/requests` kalendar va tarixni yangilaydi. `POST /api/decision` usta qarorini saqlaydi. Telegram javobi jo‘natuvchi va taklif bo‘yicha tekshiriladi. Suhbat savollarini tuzishda mahalliy servisning ochiq yozilish jarayonidan foydalandik. [Olamavto](https://olamavto.uz/uz/service)

## 🚧 Prototipdan katta workflow’gacha

Bu **Voice Agency g‘oyasining bitta ishlaydigan prototipi**. Hozirgi demo bitta avtoservis va bitta usta jadvalini qamrab oladi. Keyinchalik n8n yoki boshqa workflow tizimlari bilan CRM, ombor, to‘lov, eslatma va vazifa taqsimotini ulash mumkin. Shu yondashuvni turli bizneslarga moslab, administratorning qo‘ng‘iroq qabul qilish, ma’lumot yig‘ish, jadval tuzish va mijozga javob berish kabi kundalik ishlarini avtomatlashtirishni ko‘zlayapmiz. Murakkab yoki istisno holatlarda qaror xodimga uzatiladi.

Hackathon demosi Gemini’ning bepul imkoniyatlariga tayanadi. Jonli qo‘ng‘iroqda javob kechikishi, ayrim so‘zlar noto‘g‘ri eshitilishi yoki ovoz uzilishi mumkin. Bunga model bilan birga aloqa sifati va audio integratsiya ham ta’sir qiladi. Moliyalashtirish bo‘lsa, 404 jamoasi barqarorroq ovoz modelini sinash, o‘zbekcha suhbatlarni baholash va audio sifatini yaxshilash ustida ishlaydi.

**404 jamoasi** · [MIT litsenziyasi](LICENSE)
