# O‘zgarishlar tarixi

## v0.6.1 · To‘liq sozlash ustasi

- `start-demo.bat` Python 3.14 yo‘q bo‘lsa, `winget` bilan avtomatik o‘rnatadi.
- `telegram_login.py` o‘zbekcha sozlash ustasiga aylandi: Gemini va Telegram kalit sahifalarini brauzerda ochadi, har qadamni tushuntiradi, Gemini kalitini Google’da tekshiradi, noto‘g‘ri qiymatda yopilmasdan qayta so‘raydi va ulangan akkaunt nomini ko‘rsatadi.
- `start-demo.bat --reset` kalitlarni va Telegram akkauntini qaytadan kiritadi.
- README va kod qo‘llanmasida sozlash bosqichlari jadval bilan yozildi.

## v0.6 · Tezkor salom, avtomatik go‘shak va to‘liq hujjatlar

- Salom go‘shak ko‘tarilishidan oldin to‘liq tayyorlanadi. Telefon Gemini ulanguncha jiringlab turadi, mijoz ulanishi bilan salom darhol eshitiladi. Gemini ulanmasa, qo‘ng‘iroq jim qoldirilmaydi, rad etiladi.
- AI xayrlashgandan keyin o‘zi go‘shakni qo‘yadi. `finish_call` chaqirilmasa ham, xayrlashuv iborasi (o‘zbek, rus, ingliz) oxirgi bo‘g‘in eshitilgach qo‘ng‘iroqni yopadi.
- `start-demo.bat` endi kalitlarni faqat yetishmaganda so‘raydi, paketlarni faqat o‘zgarganda o‘rnatadi va Telegram aloqasi uzilsa avtomatik qayta ulanadi. Konsol logi `.data/robot.log` ga yoziladi.
- [Kod qo‘llanmasi](docs/CODE.md): har bir fayl va funksiya, qo‘ng‘iroq bosqichlari, API va kelajak rejasi.
- Yangi 3D video (1:28) va to‘liq tushuntirilgan taqdimot PDF.

## v0.5 · Jonli qo‘ng‘iroq paneli va xavfsizroq dashboard

- Dashboard tepasida jonli qo‘ng‘iroq paneli: kim gaplashayotgani, suhbat vaqti va «Kartani ochish» tugmasi. AI mijozga o‘zi qo‘ng‘iroq qilganda ham ko‘rinadi. Brauzer sarlavhasida ● belgisi yoki javob kutayotgan murojaatlar soni chiqadi.
- Murojaatlarni ism, model, telefon, muammo yoki taom bo‘yicha qidirish. Kartada mijoz tili ko‘rsatiladi. Yangi «Konversiya» ko‘rsatkichi bugungi qo‘ng‘iroqlarning tashrifga aylangan ulushini beradi.
- Xodim kartada yozib turganda fon yangilanishi tahrirni o‘chirmaydi. Amal bajarilgach kalendar darhol yangilanadi.
- Mijoz KOCHIR kodini yozsa, Telegramdan qabul qilingani haqida javob oladi. Noto‘g‘ri kod yuborilsa, kodni tekshirish so‘raladi. Oddiy «ha» xabarlariga javob qaytarilmaydi.
- Ovozli yordamchi ko‘rsatmalaridagi buzilgan belgilar («o?zbek» → «o‘zbek») tuzatildi, shu sababli model matnni to‘g‘ri o‘qiydi.
- Lokal server faqat `127.0.0.1` va `localhost` Host nomlariga javob beradi, bu DNS rebinding orqali mijoz ma’lumotlarini o‘qishni to‘sadi. Testlar 7 tadan 10 taga ko‘paydi.
- Tezroq: bo‘sh vaqtlarni hisoblash 11.5 ms dan 0.8 ms gacha tushdi (40 ta bron bilan o‘lchandi), baza ulanishi 0.64 ms dan 0.14 ms gacha. Jadval tekshiruvi har so‘rovda emas, bir marta bajariladi. AI vositalari bazaga alohida oqimda murojaat qiladi, shuning uchun jonli suhbatda ovoz to‘xtab qolmaydi.
- Yangi monochrome dizayn: Archivo shrifti, keng va katta yo‘nalish sarlavhasi, tab ko‘rinishidagi yo‘nalishlar, bitta chiziqdagi ko‘rsatkichlar paneli va jonli qo‘ng‘iroq uchun ovoz to‘lqini. Kalendarda holat shakl bilan ajraladi: tasdiqlangan to‘liq, taklif qilingan punktir, rad etilgan ustidan chizilgan. Hozirgi soat qatori belgilanadi. Taklif qilingan vaqt kalendarda o‘z vaqtida ko‘rinadi.

## v0.4 · Beshta xizmat va restoran bronlari

- Beshta yo‘nalish bitta dashboardda, har birining alohida kalendari, xizmatlari, narxlari va AI savollari bor.
- Restoranda xona, mehmonlar soni, kelish va tugash vaqti hamda taomlar ro‘yxati qayd qilinadi. Xodim menyuni tahrirlaydi va omonatni qayd qiladi.
- AI mijoz aytgan aniq soatni tekshiradi va saqlashdan oldin bron tafsilotlarini qayta o‘qiydi. Dashboardda vaqti yo‘q murojaatga xodim bo‘sh vaqt belgilay oladi.
- Gemini 3.8 Live, Puck ovozi, oldindan tayyorlanadigan salom va tezroq audio ijrosi. Suhbat tillari o‘zbekcha, ruscha va inglizcha bilan cheklandi.
- Kunduz va tun rejimlari, haqiqiy restoran dashboardi skrinshotlari va yangilangan demo materiallari.

Final video 2:00 davom etadi va 60 fps’da qayta montaj qilindi. Taqdimotning oxirgi slaydidan Full HD videoni ochish mumkin.

## v0.3 · Ko‘p tilli yordamchi va demo materiallari

- Gemini Live mijozning tilini suhbatdan aniqlaydi. Til suhbat davomida o‘zgarsa, javob ham moslashadi. Saqlangan til keyingi ovozli qo‘ng‘iroqlarda ishlatiladi. Inglizcha va ruscha javoblar sinov audiosi bilan tekshirildi.
- Har bir yangi vaqt taklifi o‘z tasdiqlash kodini oladi. Eski xabarga javob yangi taklifni band qilib yubormaydi. Suhbat qayta ishlanganda band qilingan xizmat va tarif saqlanadi.
- Lokal PCM musiqasi sozlangan bo‘lsa, ikkinchi kiruvchi qo‘ng‘iroq kutish rejimiga olinadi. Ixtiyoriy ovozli e’londan so‘ng musiqa takrorlanadi. Birinchi suhbat tugagach, Gemini kutayotgan mijozga ulanadi. Ikki telefon bilan jonli sinov hali o‘tkazilmagan.
- Respublika yoki biznes miqyosidagi natijalar pilotda o‘lchanadi. README’da qo‘ng‘iroqdan bronga o‘tish, bo‘shagan vaqtni to‘ldirish va xodim vaqti uchun hisoblash usullari bor.
- 404 jamoasining [pitch decki](docs/pitch-deck.html), [texnik taqdimoti](docs/technical-pitch.html) va [o‘zbekcha V2 videosi](https://github.com/akhmadbroyt-netizen/Voice-Agency-404/blob/82f94c2/docs/voice-agency-404-v2.mp4) qo‘shildi. Video 25-noyabr hakaton prototipini haqiqiy dashboard ekranlari va demo ma’lumotlari bilan ko‘rsatadi.

[GitHub’dagi v0.2 dan keyingi o‘zgarishlar](https://github.com/akhmadbroyt-netizen/Voice-Agency-404/compare/45dbebf...main)

## v0.2 · Ikki ustali jadval va tashrif nazorati

- Haftalik monochrome kalendar, qo‘ng‘iroqlar tarixi, usta filtri, tayinlash va ko‘rsatkichlar yangilandi. Har bir xizmatga davomiylik beriladi va bir ustaning ikki tashrifi to‘qnashishi tekshiriladi.
- Telegram tasdig‘iga usta, sana va soat qo‘shildi. Tashrifdan oldin eslatma yuboriladi. Yangi vaqt tasdiqlanguncha eski bron band turadi.
- Odam bilan gaplashish so‘rovi ustaga qayta qo‘ng‘iroq vazifasini ochadi. Rozilik bergan mijozga tashrif vaqtida AI qo‘ng‘iroq qiladi. Mijoz kela olmasa, bo‘shagan vaqt navbatdagi rozi mijozlarga taklif qilinadi.

[GitHub’dagi v0.1 va v0.2 farqi](https://github.com/akhmadbroyt-netizen/Voice-Agency-404/compare/672c636...45dbebf)

## v0.1 · Birinchi hackathon prototipi

- Telegram kiruvchi qo‘ng‘iroqlarini Gemini Live qabul qiladi. Yordamchi mashina va nosozlik haqida so‘raydi, demo tarifini aytadi va tashrif so‘rovini SQLite’ga yozadi.
- Dashboard yordamida so‘rovni ko‘rish, qabul qilish, rad etish yoki boshqa vaqt taklif qilish mumkin. Telegram tasdiqlari va mijoz javobi jadvalga bog‘langan.
- Windows uchun `start-demo.bat`, lokal sozlamalar namunasi va MIT litsenziyasi bilan chiqarildi.

[Birinchi prototip commiti](https://github.com/akhmadbroyt-netizen/Voice-Agency-404/commit/672c636)
