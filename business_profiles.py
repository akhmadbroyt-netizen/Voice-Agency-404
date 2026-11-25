from pathlib import Path
from dataclasses import dataclass


@dataclass(frozen=True)
class Business:
    name: str
    resource: str
    greeting: str
    questions: str
    opens: int = 9
    closes: int = 18

    def services(self, business):
        return [key for key, value in CATALOG.items() if value[0] == business]


BUSINESSES = {
    "auto": Business("Avtoservis", "Usta", "Mashinangizda nima muammo bo‘ldi?", ""),
    "restaurant": Business("Restoran", "Xona",
                           "Stol yoki banket uchun xona kerakmi?",
                           "Mehmonlar soni, stol yoki xona, tadbir turi, menyu va maxsus ovqat talablarini so‘rang. "
                           "car maydonida mijoz ismini, issue ichida maxsus izohlarni, menu_items ro‘yxatida esa mijoz aniq tanlagan har bir taom va aytilgan miqdorni yozing. Taomni o‘ylab topmang. "
                           "Omonat summasi quote javobidan olinadi. To‘lovni olganingizni aytmang. "
                           "Omonatni xodim tasdiqlaydi. Bank karta raqamini va SMS kodini so‘ramang.", 10, 23),
    "beauty": Business("Go‘zallik saloni", "Mutaxassis", "Qaysi xizmat kerak?",
                       "Soch turmagi yoki manikyur turini, mijoz ismini va qulay vaqtni so‘rang."),
    "repair": Business("Texnika ta’miri", "Usta", "Qaysi qurilmangizda muammo bor?",
                       "Qurilma modeli, nosozlik va qulay vaqtni so‘rang. car maydoniga qurilma modelini yozing."),
    "photo": Business("Fotostudiya", "Studiya", "Qanday fotosessiya rejalashtiryapsiz?",
                      "Fotosessiya turi, ishtirokchilar soni va kerakli sanani so‘rang.", 9, 21),
}

# Business, service label, min/max UZS, resource, minutes, booking deposit UZS.
CATALOG = {
    "diagnostic": ("auto", "Umumiy diagnostika", 100000, 150000, "Aziz", 30, 0),
    "brakes": ("auto", "Tormoz tekshiruvi", 100000, 180000, "Aziz", 45, 0),
    "oil": ("auto", "Moy almashtirish (ish haqi)", 80000, 120000, "Bekzod", 30, 0),
    "electrical": ("auto", "Elektr tizimi diagnostikasi", 120000, 220000, "Bekzod", 60, 0),
    "table": ("restaurant", "Stol broni", 0, 0, "Asosiy zal", 90, 0),
    "private_room": ("restaurant", "Alohida xona", 300000, 300000, "Oila xonasi", 120, 100000),
    "banquet": ("restaurant", "Banket", 1500000, 3000000, "Banket zali", 180, 500000),
    "hair": ("beauty", "Soch turmagi", 80000, 150000, "Malika", 60, 0),
    "nails": ("beauty", "Manikyur", 100000, 180000, "Dilnoza", 60, 0),
    "phone": ("repair", "Telefon diagnostikasi", 50000, 90000, "Kamol", 30, 0),
    "laptop": ("repair", "Noutbuk diagnostikasi", 80000, 130000, "Sardor", 60, 0),
    "portrait": ("photo", "Portret fotosessiyasi", 250000, 450000, "Oq studiya", 60, 0),
    "group": ("photo", "Guruh fotosessiyasi", 450000, 800000, "Katta studiya", 120, 0),
}
BY_LABEL = {item[1]: item for item in CATALOG.values()}
AUTO_PROMPT = Path(__file__).with_name("operator-prompt.md")


def operator_prompt(business):
    if business == "auto":
        detail = AUTO_PROMPT.read_text(encoding="utf-8-sig")
    else:
        profile = BUSINESSES[business]
        detail = (
            f"Siz {profile.name} xizmatining AI yordamchisisiz. {profile.questions}\n"
            "Aniq so‘rovni save_details orqali saqlang. Qaydga keyingi javoblarda oldingi tafsilotlarni ham qo‘shing. "
            "Narx va bo‘sh vaqtni quote orqali tekshiring. Faqat katalogdagi narxni ayting. "
            "Aniq sana va soatni mijozdan tasdiqlatib maydonlarga alohida yozing. "
            "Bu so‘rov, vaqtni xodim tasdiqlaydi. Faqat keyingi ovozli qo‘ng‘iroq uchun rozilik so‘rang. Telegram xulosasini yuborish haqida savol bermang. "
            "Xodim kerak bo‘lsa callback_reason yozing. Mijoz xayrlashsa finish_call orqali qayd qiling va xayrlashing."
        )
    return detail + (
        "\nToshkentcha kundalik o‘zbek nutqini, shevani va ruscha aralash so‘zlarni tushunishga harakat qiling. "
        "Xizmat va muammo ma’lum bo‘lsa, keyingi savol yoki narxdan oldin save_details ni chaqiring. "
        "Aniq soat bo‘lmasa ham muammoni saqlang. Mijozning asosiy tilida gapiring. Bir javobda bitta qisqa savol bering. "
        "Ism, vaqt, odam soni yoki xizmat noaniq eshitilsa taxmin qilmang, bir marta qayta so‘rang."
    )
