# Kod qo‘llanmasi

Bu hujjat Voice Agency 404 kodini fayl va funksiya bo‘yicha tushuntiradi. Oxirida kelajakdagi kengaytirish rejasi bor. Umumiy tavsif va ishga tushirish [README](../README.md) faylida.

## Umumiy oqim

```
Mijoz (Telegram qo‘ng‘irog‘i)
   │  48 kHz PCM
   ▼
telegram_call_test.py ── pytgcalls ── ovozni qabul qiladi va uzatadi
   │  16 kHz PCM                 ▲ 24 kHz → 48 kHz PCM
   ▼                             │
gemini_voice.py ── Gemini Live (gemini-3.8-live) ── nutq, til, vositalar
   │  quote / save_details / finish_call
   ▼
service_desk.py ── SQLite (.data/service.sqlite3) ── bo‘sh vaqt, bron, navbat
   │  HTTP 127.0.0.1:8744
   ▼
dashboard.html ── xodim: qabul / rad / boshqa vaqt / usta tayinlash
   │
   └─► Telegram xabari mijozga (tasdiq, taklif, eslatma)
```

Robot va dashboard bitta Python jarayonida ishlaydi. Telegram sessiyasi, kalitlar va baza faqat shu kompyuterda saqlanadi. Suhbat paytida audio Gemini Live’ga uzatiladi.

## Qo‘ng‘iroq bosqichlari

1. **Qo‘ng‘iroq keladi.** `on_update` kiruvchi qo‘ng‘iroqni ko‘radi va `start_inbound` ni chaqiradi.
2. **Salom oldindan tayyorlanadi.** Telefon jiringlab turganda `run_voice` Gemini Live’ga ulanadi. Model salomni aytadi, audio `outgoing` buferiga yig‘iladi. Salom to‘liq tayyor bo‘lgach `greeting_ready` belgilanadi. Robot ko‘pi bilan `GREETING_WAIT` soniya kutadi.
3. **Go‘shak ko‘tariladi.** `calls.play` va `calls.record` chaqiriladi, `playback_gate` ochiladi. Tayyor salom darhol eshitiladi.
4. **Suhbat.** `upload` mijoz ovozini 16 kHz’ga o‘tkazib Gemini’ga yuboradi. Mijoz gapira boshlasa, AI ovozi to‘xtatiladi. `receive` model javoblarini, matn transkriptini va vosita chaqiruvlarini qabul qiladi. `playback` AI ovozini 10 ms kadrlar bilan Telegram’ga uzatadi.
5. **Bo‘sh vaqt tekshiruvi.** Model `quote` vositasini chaqiradi. `check_slot` va `available_slots` aniq vaqt bo‘shligini va muqobil vaqtlarni qaytaradi.
6. **Bron.** Model tafsilotlarni qayta o‘qiydi, mijoz tasdiqlagach `save_details` yoki `finish_call` ni chaqiradi. `save_request` murojaatni SQLite’ga yozadi.
7. **Xayrlashuv va go‘shak.** `finish_call` yoki AI aytgan xayrlashuv iborasi (`says_goodbye`) `ending` ni yoqadi. Oxirgi audio ijro etilgach, `HANGUP_DELAY` dan so‘ng qo‘ng‘iroq yopiladi.
8. **Xodim qarori.** Dashboard `POST /api/decision` yuboradi. `decide` holatni o‘zgartiradi va Telegram xabarini navbatga qo‘yadi. `send_notices` uni mijozga jo‘natadi.

## `start-demo.bat`

Windows uchun bitta tugmali ishga tushirgich.

| Bosqich | Nima qiladi |
| --- | --- |
| 1/4 | `.venv` yo‘q bo‘lsa, `py -3.14 -m venv .venv` bilan yaratadi. |
| 2/4 | `requirements-telegram.txt` o‘zgargan bo‘lsa, paketlarni o‘rnatadi. O‘rnatilgan nusxa `.venv\requirements.installed` da saqlanadi. |
| 3/4 | `telegram_login.py --check` bilan kalitlar va sessiyani tekshiradi. Yetishmasa `--setup` ni ochadi. |
| 4/4 | `telegram_call_test.py` ni ishga tushiradi. Telegram aloqasi uzilsa, 5 soniyadan keyin qayta ulanadi. Ketma-ket 3 ta xato yoki 20 dan ortiq qayta ulanishda to‘xtaydi. |

`start-demo.bat --check` faqat sozlamalarni tekshiradi. Qayta ulanishda `VOICE404_NO_BROWSER=1` o‘rnatiladi, shuning uchun brauzer qayta ochilmaydi.

## `telegram_login.py`

- **`main()`**: `--check` rejimida `.env` dagi `GEMINI_API_KEY` borligini, `TELEGRAM_API_ID` musbat son va `TELEGRAM_API_HASH` 32 belgili hex ekanini tekshiradi. Login qilinmaydi. `--setup` rejimida yetishmagan kalitlarni so‘raydi, `.env` ga yozadi va Telethon orqali `.telegram/voice-agency.session` sessiyasini yaratadi: telefon raqami, login kodi va kerak bo‘lsa ikki bosqichli parol.

## `telegram_call_test.py`

Robotning asosiy jarayoni. Hamma narsa `main()` ichida.

- **`main()`**: `.env` ni o‘qiydi, Telegram sessiyasiga ulanadi, `PyTgCalls` ni ishga tushiradi, dashboard serverini alohida oqimda ochadi va brauzerni ochadi. Kutish musiqasi `.data/hold-music.pcm` va e’lon `.data/hold-announcement.pcm` bo‘lsa yuklanadi.
- **`run_voice(peer_id, playback_gate, greeting_ready)`**: mijozning username’ini oladi, bo‘sh murojaat yaratadi (`save_request`), jonli qo‘ng‘iroqni belgilaydi (`set_live_call`) va `talk()` ni chaqiradi. Suhbat tugagach yoki xato bo‘lsa, qo‘ng‘iroqni yopadi va jonli holatni tozalaydi.
- **`start_inbound(peer_id, already_joined=False)`**: kiruvchi qo‘ng‘iroqni boshlaydi. Salom tayyor bo‘lishini kutadi. Gemini ulanmasa, mijozni jim qoldirmaslik uchun qo‘ng‘iroqni rad etadi. Keyin ovoz uzatish va yozishni yoqadi.
- **`hold_caller(peer_id)`**: birinchi suhbat davom etayotganda ikkinchi qo‘ng‘iroqni qabul qiladi va `play_hold` orqali e’lon va musiqani ijro etadi. Birinchi suhbat tugasa, kutayotgan mijozni `start_inbound(..., already_joined=True)` bilan AI ga ulaydi.
- **`on_update(app, update)`**: pytgcalls hodisalari: yangi qo‘ng‘iroq, mijoz audio kadri (`incoming` navbatiga), qo‘ng‘iroq tugashi. Faol qo‘ng‘iroq bo‘lsa, yangisi kutishga yuboriladi.
- **`handle_reply(event)`**: mijozning Telegram matnli javoblarini o‘qiydi. Taklif kodiga javob (`confirm_offer`) va `KOCHIR` kodi bilan vaqtni ko‘chirish so‘rovi (`request_move`) shu yerda.
- **`outbound_call(job, greeting, answer)`**: rozilik bergan mijozga robot o‘zi qo‘ng‘iroq qiladi. Masalan, tashrif vaqtida “kelyapsizmi?” deb so‘rash yoki bo‘shagan vaqtni taklif qilish.
- **`scheduled_calls()`**: fonda aylanadi. `claim_attendance_call` bilan tashrif vaqti kelgan bronni oladi, mijozga qo‘ng‘iroq qiladi. Javob “kela olmayman” bo‘lsa (`attendance_result`), `waitlist_candidates` dagi mijozlarga navbat bilan qo‘ng‘iroq qilib, `book_opening` bilan bo‘sh vaqtni band qiladi.
- **`send_notices()`**: fonda aylanadi. `pending_messages` dagi tasdiq, taklif va eslatmalarni Telegram orqali yuboradi va natijani `delivery_result` bilan yozadi.
- **`Tee`**: konsol chiqishini bir vaqtda faylga ham yozadi (`write`, `flush`). Log `.data/robot.log` faylida saqlanadi.

## `gemini_voice.py`

Gemini Live bilan real vaqtdagi suhbat.

| Nom | Vazifasi |
| --- | --- |
| `VOICE_STYLE` | Ovoz uslubi: samimiy, qisqa jumlalar, bir navbatda bitta savol, narx va soatni aniq aytish. |
| `LANGUAGE_STYLE` | Faqat o‘zbek, rus va ingliz tillari. Mijozning tiliga moslashadi. |
| `END_OF_SPEECH_SAMPLES` | 520 ms jimlikdan keyin mijoz gapi tugagan hisoblanadi. |
| `PLAYBACK_BUFFER_FRAMES` | Ijrodan oldin 8 kadr (80 ms) bufer, ovoz uzilmasligi uchun. |
| `GOODBYES`, `HANGUP_DELAY` | Xayrlashuv iboralari va go‘shak qo‘yishdan oldingi 1.2 s pauza. |

- **`says_goodbye(text)`**: AI gapining oxirgi 80 belgisida xayrlashuv iborasi borligini tekshiradi. Apostrof turlari olib tashlanadi, shuning uchun “sog‘ bo‘ling” va “sog bo‘ling” bir xil topiladi.
- **`to_gemini(pcm)`**: Telegram’ning 48 kHz ovozini o‘rtacha qiymat bilan 16 kHz’ga tushiradi.
- **`to_telegram(pcm)`**: Gemini’ning 24 kHz ovozini chiziqli interpolyatsiya bilan Telegram’ga moslaydi va 1.10 marta tezlashtiradi.
- **`booking_fields(args, business)`**: bron maydonlarini tekshiradi. Kelajakdagi aniq sana va vaqt, mijoz tafsilotlarni tasdiqlagani, restoranda mehmonlar soni va tugash vaqti talab qilinadi. Yetishmasa, modelga nima so‘rash kerakligi qaytariladi.
- **`talk(calls, caller_id, incoming, config, ...)`**: Gemini Live sessiyasini ochadi va suhbatni boshqaradi. Ichki funksiyalar:
  - `save_transcript()` — bron saqlanmagan bo‘lsa, mijoz gapini murojaatga izoh sifatida yozadi.
  - `upload()` — mijoz ovozini energiya bo‘yicha aniqlaydi, gap boshlanganda AI ovozini to‘xtatadi va `ActivityStart`/`ActivityEnd` bilan Gemini’ga yuboradi.
  - `handle_tool(call)` — vositalarni bajaradi. Alohida oqimda ishlaydi, shuning uchun SQLite ovozni to‘xtatmaydi.
  - `receive()` — model audiosi, transkriptlar, uzilish va vosita chaqiruvlarini qabul qiladi. Salom tayyor bo‘lganda `greeting_ready` ni belgilaydi.
  - `playback()` — buferdagi ovozni 10 ms kadrlar bilan uzatadi. `ending` bo‘lsa, oxirgi ovozdan keyin suhbatni yopadi.

Model vositalari:

| Vosita | Qachon | Natija |
| --- | --- | --- |
| `quote` | Narx yoki vaqt so‘ralganda | Xizmat, narx oralig‘i, usta, davomiylik, omonat, so‘ralgan vaqt bo‘shmi, 36 tagacha bo‘sh vaqt |
| `save_details` | Muammo ma’lum bo‘lganda va vaqt kelishilganda | Murojaat saqlanadi yoki yangilanadi |
| `finish_call` | Mijoz suhbatni tugatganda | Saqlaydi va “Say goodbye now” ko‘rsatmasini beradi |
| `outbound_result` | Faqat chiquvchi qo‘ng‘iroqda | Mijoz javobi: `yes`, `no`, `unclear` |

`GEMINI_LIVE_MODEL` (standart `gemini-3.8-live`) va `GEMINI_LIVE_VOICE` (standart `Puck`) `.env` orqali o‘zgartiriladi.

## `service_desk.py`

Baza, jadval, Telegram xabar navbati va lokal HTTP API.

**Jonli qo‘ng‘iroq (xotirada):**
- `set_live_call(caller_id, request_id, direction)` — hozir kim bilan gaplashilayotganini yozadi.
- `clear_live_call(caller_id)` — qo‘ng‘iroq tugaganda tozalaydi.
- `live_call()` — dashboard uchun jonli qo‘ng‘iroq va davomiyligini qaytaradi.

**Baza:**
- `database()` — SQLite ulanishini ochadi. Jadval tuzilishi jarayonda bir marta tekshiriladi.
- `open_connection()` — WAL rejimi va `Row` bilan ulanish.
- `migrate(connection)` — jadvallarni yaratadi va eski bazaga yangi ustunlarni qo‘shadi.
- `active_business()` / `set_business(business)` — dashboard tanlagan yo‘nalish. Keyingi qo‘ng‘iroqlarga ta’sir qiladi.
- `business_for(service)`, `deposit_for(service)` — xizmat qaysi yo‘nalishga tegishli va omonat summasi.

**Murojaatlar:**
- `save_request(...)` — murojaatni yaratadi yoki yangilaydi: mijoz, model, muammo, xizmat, sana va vaqt, telefon, restoranda mehmonlar, tugash vaqti va menyu.
- `clean_menu(items)` — menyu ro‘yxatini tozalaydi va uzunligini cheklaydi.
- `save_transcript_note(request_id, text)` — suhbat matnini izoh sifatida saqlaydi.
- `request_rows()` — dashboard uchun barcha murojaatlar, qarorlar va holatlar.

**Xodim qarorlari:**
- `decide(request_id, action, slot)` — dashboard amali. `accept` (qabul), `reject` (rad), `offer` (boshqa vaqt), `assign` (usta tayinlash), `set_service`, `save_menu`, `deposit_paid`, `callback_done`, `retry` (yuborilmagan xabarni qayta yuborish). Har amal tranzaksiya ichida bajariladi va kerak bo‘lsa Telegram xabari navbatga qo‘yiladi.
- `booking_notice(request_id, slot, worker, service)` — tasdiq matni: usta, sana, soat va `KOCHIR` kodi.

**Jadval:**
- `staff(service)`, `assigned_staff(connection, service, request_id)` — xizmatga mas’ul usta yoki xona va davomiylik.
- `reserved_intervals(connection, exclude)` — band vaqtlar ro‘yxati.
- `slot_available(...)` — vaqt ish soatiga to‘g‘ri kelishi va ustaning boshqa broni bilan to‘qnashmasligini tekshiradi.
- `booking_error(...)` — vaqt band bo‘lsa, sababini matn bilan qaytaradi.
- `check_slot(service, slot, request_id)` — AI uchun qisqa tekshiruv.
- `available_slots(service, requested_date, request_id)` — tanlangan kun yoki yaqin kunlardagi bo‘sh vaqtlar.

**Telegram navbati:**
- `pending_messages()` — yuborilishi kerak bo‘lgan tasdiq, taklif va eslatmalar.
- `delivery_result(request_id, message_id, kind)` — xabar yuborildimi, yozib qo‘yadi.
- `confirm_offer(caller_id, message_id, offer_code)` — mijoz taklifga “Bo‘ladi” desa, kod va jo‘natuvchini tekshirib vaqtni band qiladi.
- `request_move(caller_id, message_id, request_id)` — `KOCHIR` kodi bilan vaqtni o‘zgartirish so‘rovi.
- `queue_callback(request_id, reason)` — xodim qayta qo‘ng‘iroq qilishi uchun vazifa.
- `record_contact_preferences(request_id, consent, waitlist, language)` — qo‘ng‘iroqqa rozilik, kutish navbati va til.

**Tashrif va kutish navbati:**
- `claim_attendance_call()` — tashrif vaqti kelgan va rozilik bergan mijozni oladi.
- `attendance_result(job, answer)` — mijoz keladimi yoki yo‘qmi, yozadi. Kelmasa vaqt bo‘shaydi.
- `waitlist_candidates(job)` — shu xizmat bo‘yicha ertaroq kelishga rozi mijozlar.
- `book_opening(candidate, job)` — bo‘shagan vaqtni yangi mijozga band qiladi va tasdiq yuboradi.

**HTTP API (`Dashboard`):**

| So‘rov | Javob |
| --- | --- |
| `GET /` | `dashboard.html` |
| `GET /api/requests` | Murojaatlar va kalendar |
| `GET /api/live` | Jonli qo‘ng‘iroq |
| `GET /api/business` | Faol yo‘nalish, xizmatlar, ustalar va ish vaqti |
| `POST /api/decision` | `{id, action, slot | worker}` |
| `POST /api/business` | `{business}` |

Server faqat `127.0.0.1:8744` va `localhost:8744` Host nomlariga javob beradi. POST so‘rovlar uchun Origin ham tekshiriladi va tana 2 KB bilan cheklangan. Bu DNS rebinding va boshqa saytlardan so‘rov yuborishni to‘sadi.

## `business_profiles.py`

- **`Business`**: yo‘nalish nomi, resurs turi (Usta, Xona, Mutaxassis, Studiya), salom savoli, qo‘shimcha savollar va ish vaqti. `services(business)` shu yo‘nalish xizmatlarini qaytaradi.
- **`BUSINESSES`**: `auto`, `restaurant`, `beauty`, `repair`, `photo`.
- **`CATALOG`**: 13 ta demo xizmat: yo‘nalish, nom, eng kam va eng ko‘p narx (so‘m), mas’ul usta yoki xona, daqiqa, omonat.
- **`operator_prompt(business)`**: model ko‘rsatmasi. Avtoservis uchun `operator-prompt.md` o‘qiladi, boshqalari profil asosida yig‘iladi.

## `hold_audio.py`

- **`play_hold(calls, peer_id, announcement, music, is_waiting)`**: kutayotgan mijozga e’lonni bir marta, keyin musiqani takror ijro etadi. Kadr 960 bayt (48 kHz, 10 ms). `is_waiting()` false bo‘lganda to‘xtaydi.

## `dashboard.html`

Bitta fayldagi monochrome dashboard. Ma’lumotni davriy ravishda `/api/requests` dan oladi, jonli qo‘ng‘iroq panelini har soniyada yangilaydi.

| Funksiya | Vazifasi |
| --- | --- |
| `setTheme(mode)` | Kunduz va tun rejimi. |
| `setTitle()` | Brauzer sarlavhasida jonli qo‘ng‘iroq ● yoki kutayotgan murojaatlar soni. |
| `editing()` | Xodim kartada yozayotgan bo‘lsa, fon yangilanishi to‘xtatiladi. |
| `matches(row, query)` | Ism, model, telefon, muammo, taom bo‘yicha qidiruv. |
| `loadBusiness()` / `show(next)` | Yo‘nalish tablari va tanlov. |
| `node(tag, text, className)` | Xavfsiz DOM element yaratish, HTML kiritilmaydi. |
| `decide(row, action, output, slot)` | `POST /api/decision` yuboradi va natijani ko‘rsatadi. |
| `actions(row)` | Karta tugmalari: qabul, rad, bo‘sh vaqt, usta, omonat, qayta yuborish. |
| `restaurantMenu(row)` | Restoran menyusini tahrirlash. |
| `render(openId)` / `safeRender(openId)` | Kalendar, tarix va ko‘rsatkichlarni chizadi. Xato bo‘lsa sahifa buzilmaydi. |
| `openLive()` / `showLive()` | Jonli qo‘ng‘iroq paneli va “Kartani ochish”. |
| `pull(openId)` / `refresh()` | Ma’lumotni serverdan olish va davriy yangilash. |

## `test_service_desk.py`

`py -3.14 -m unittest test_service_desk` bilan ishga tushadi. Vaqtinchalik bazada 10 ta holat tekshiriladi: eski taklif kodi yangi taklifni tasdiqlamasligi, band qilingan xizmat o‘zgarmasligi, vaqtsiz murojaatni qabul qilish, banket omonati va xona to‘qnashuvi, transkriptdan xona tanlash, aniq kun va banket vaqti, KOCHIR faqat o‘sha mijozdan, jonli qo‘ng‘iroqni faqat o‘sha mijoz tozalashi, begona Host rad etilishi va tanlangan yo‘nalish saqlanishi.

## Sozlamalar (`.env`)

| Kalit | Majburiy | Izoh |
| --- | --- | --- |
| `GEMINI_API_KEY` | ha | Google AI Studio kaliti |
| `TELEGRAM_API_ID`, `TELEGRAM_API_HASH` | ha | my.telegram.org dan |
| `GEMINI_LIVE_MODEL` | yo‘q | Standart `gemini-3.8-live` |
| `GEMINI_LIVE_VOICE` | yo‘q | Standart `Puck` |

`.env`, `.telegram/`, `.data/` va `*.session` Git’ga qo‘shilmaydi.

## Kelajakda nimalar qilish mumkin

**Yaqin reja (pilot):**
- Bitta haqiqiy biznesda 2–4 hafta pilot. Qo‘ng‘iroqdan bronga o‘tish, bo‘shagan vaqtni to‘ldirish va xodim vaqtini o‘lchash.
- Narx va xizmatlarni koddan emas, dashboard’dan tahrirlash.
- Har bir biznes uchun alohida Telegram akkaunt va alohida baza.
- O‘zbekcha nutqni yaxshiroq tanish uchun barqaror ovoz modeli va suhbatlarni baholash to‘plami.

**O‘rta muddat:**
- Oddiy telefon raqamlari: SIP yoki mahalliy operator orqali qo‘ng‘iroq qabul qilish.
- Onlayn to‘lov: omonatni Click yoki Payme orqali olish va avtomatik tasdiqlash.
- CRM va kalendarlar bilan ulanish: Google Calendar, amoCRM, Bitrix24. Workflow uchun n8n.
- SMS va Telegram bot orqali eslatma va fikr so‘rash.
- Bir nechta filial va xodim rollari: administrator, usta, menejer.
- Ko‘rsatkichlar sahifasi: kunlik qo‘ng‘iroqlar, konversiya, o‘tkazib yuborilgan vaqtlar.

**Uzoq muddat:**
- Bulutli xizmat (SaaS): biznes ro‘yxatdan o‘tadi, yo‘nalish tanlaydi va bir kunda ishga tushiradi.
- Yangi yo‘nalishlar: klinika, o‘quv markazi, mehmonxona, taksi va yetkazib berish.
- Qoraqalpoq, tojik va qozoq tillari.
- Suhbat tahlili: mijozlar eng ko‘p nimani so‘raydi, qayerda bron yo‘qotiladi.
- Murakkab holatlarda qo‘ng‘iroqni jonli xodimga o‘tkazish.

**404 jamoasi** · [MIT litsenziyasi](../LICENSE)
