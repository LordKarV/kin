"""Write the Phase 1 eval test sets to backend/eval/testset/.

Authored for the Krishnan demo family (see backend/app/db/seed.py). Speaker is Kamala Paatti,
listener is Arjun, unless stated. Tamil script is what the ASR emits; romanization is for readers.
Drafted by Claude; REVIEW BY A NATIVE SPEAKER on the team before the demo (plan Phase 1).

Run: python scripts/make_testset.py
"""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "backend" / "eval" / "testset"

# ---- expected renderings (groups of alternatives; one per group must appear) -------------------
RAVI_MAMA = [["Ravi"], ["Mom's brother", "mother's brother", "maternal uncle", "Mom's younger brother", "mum's brother"]]
RAVI_PERIYAPPA = [["Ravi"], ["Dad's elder brother", "Dad's older brother", "father's elder brother", "father's older brother", "paternal uncle", "Dad's big brother"]]
LAKSHMI = [["Lakshmi"], ["Ravi", "Mom's brother's wife", "maternal uncle's wife", "aunt"]]
MEENA = [["Meena"], ["Dad's sister", "father's sister", "paternal aunt", "Dad's younger sister"]]
DIVYA = [["Divya", "Chinnu"], ["sister"]]
KARTHIK = [["Karthik"], ["cousin", "Ravi"]]
VISHNU = [["Vishnu"], ["cousin", "Ravi"]]
KAMALA = [["Paatti", "Kamala", "grandmother", "Grandma", "granny"]]
RAGHAVAN = [["Thatha", "Raghavan", "grandfather", "Grandpa"]]
PRIYA = [["Mom", "mother", "Priya", "mum"]]
SENTHIL = [["Dad", "father", "Senthil"]]
SAROJA = [["Saroja"], ["younger sister", "great-aunt", "grand-aunt", "grandaunt"]]
ARJUN = [["you", "Arjun", "grandson"]]

P = {  # node → (type, must_include)
    "p_ravi_mama": ("person", RAVI_MAMA), "p_ravi_periyappa": ("person", RAVI_PERIYAPPA), "p_lakshmi": ("person", LAKSHMI),
    "p_meena": ("person", MEENA), "p_divya": ("person", DIVYA), "p_karthik": ("person", KARTHIK), "p_vishnu": ("person", VISHNU),
    "p_kamala": ("person", KAMALA), "p_raghavan": ("person", RAGHAVAN), "p_priya": ("person", PRIYA), "p_senthil": ("person", SENTHIL),
    "p_saroja": ("person", SAROJA), "p_arjun": ("person", ARJUN),
    "d_rasam": ("dish", [["rasam"]]), "d_sambar": ("dish", [["sambar", "sambhar"]]), "d_pongal": ("dish", [["pongal"]]),
    "d_murukku": ("dish", [["murukku"]]), "d_payasam": ("dish", [["payasam"]]), "d_kozhukattai": ("dish", [["kozhukattai", "kolukattai"]]),
    "pl_madurai_house": ("place", [["Madurai"]]), "pl_meenakshi_kovil": ("place", [["Meenakshi"]]),
    "pl_adyar": ("place", [["Adyar", "Chennai", "Ravi"]]), "pl_coimbatore": ("place", [["Coimbatore", "Kovai"]]), "pl_austin": ("place", [["Austin"]]),
    "ev_pongal": ("event", [["Pongal"]]), "ev_deepavali": ("event", [["Deepavali", "Diwali"]]),
    "ev_thatha_thithi": ("event", [["thithi", "anniversary", "remembrance", "death anniversary"], ["Thatha", "Raghavan", "grandfather", "Grandpa"]]),
    "ev_vishnu_wedding": ("event", [["Vishnu"], ["wedding", "marriage"]]),
}
FLATTEN = {  # typical generic flattenings, used for the flattening-rate statistic
    "d_rasam": ["soup", "broth"], "d_sambar": ["stew", "lentil soup"], "d_pongal": ["porridge"], "d_murukku": ["pretzel", "crackers"],
    "d_payasam": ["pudding", "kheer"], "d_kozhukattai": ["dumpling"], "pl_madurai_house": ["town", "village", "hometown"],
    "pl_meenakshi_kovil": ["the temple"], "p_ravi_mama": ["uncle"], "p_ravi_periyappa": ["uncle"], "p_meena": ["aunt"], "p_lakshmi": ["aunt"],
    "p_saroja": ["grandmother", "aunt"], "p_divya": ["sister"], "p_karthik": ["brother", "boy"], "p_vishnu": ["brother"],
}


def ent(source: str, node: str) -> dict:
    typ, inc = P[node]
    return {"source": source, "node": node, "type": typ, "must_include": inc, "must_not_include": FLATTEN.get(node, [])}


# (id, category, tamil, roman, gloss, [(source, node), ...], context)
G = [
    # ---------------- kin terms (42) ----------------
    ("K01", "kin", "உன் மாமா நேத்து போன் பண்ணான்.", "Un mama nethu phone pannaan.", "Your uncle Ravi (Mom's brother) called yesterday.", [("மாமா", "p_ravi_mama")]),
    ("K02", "kin", "பெரியப்பா கடைக்கு புது மெஷின் வாங்கிட்டாரு.", "Periyappa kadaikku pudhu machine vaangittaaru.", "Ravi periyappa (Dad's elder brother) bought a new machine for the shop.", [("பெரியப்பா", "p_ravi_periyappa")]),
    ("K03", "kin", "அத்தை சிங்கப்பூர்லேர்ந்து அடுத்த மாசம் வர்றா.", "Atthai Singapore-lerndhu adutha maasam varraa.", "Meena atthai (Dad's sister) is coming from Singapore next month.", [("அத்தை", "p_meena")]),
    ("K04", "kin", "மாமி கிளாஸ்ல நிறைய பசங்க சேர்ந்திருக்காங்களாம்.", "Mami class-la niraya pasanga sernthirukkaangalaam.", "Lots of kids have joined Lakshmi mami's (dance) class, apparently.", [("மாமி", "p_lakshmi")]),
    ("K05", "kin", "உன் அக்கா ஹாஸ்பிடல்ல ரொம்ப வேலையாம்.", "Un akka hospital-la romba velaiyaam.", "Your sister Divya is very busy at the hospital.", [("அக்கா", "p_divya")]),
    ("K06", "kin", "என் மகன் இந்த வாரம் மதுரைக்கு வர்றான்.", "En magan indha vaaram Madurai-kku varraan.", "My son (your uncle Ravi, Mom's brother) is coming to Madurai this week.", [("மகன்", "p_ravi_mama"), ("மதுரை", "pl_madurai_house")]),
    ("K07", "kin", "என் தங்கச்சி முழங்கால் வலின்னு படுத்திருக்கா.", "En thangachi muzhangaal valinnu paduthirukkaa.", "My younger sister (Saroja, your grand-aunt) is laid up with knee pain.", [("தங்கச்சி", "p_saroja")]),
    ("K08", "kin", "தாத்தா இருந்தா உனக்கு எவ்வளவு சந்தோஷப்பட்டிருப்பாரு.", "Thatha irundhaa unakku evvalavu sandhoshappattiruppaaru.", "If Thatha (Grandpa Raghavan) were here, how happy he'd have been for you.", [("தாத்தா", "p_raghavan")]),
    ("K09", "kin", "உங்க அப்பா சின்ன வயசுல ரொம்ப குறும்பு.", "Unga appa chinna vayasula romba kurumbu.", "Your dad was very naughty as a child.", [("அப்பா", "p_senthil")]),
    ("K10", "kin", "அம்மாகிட்ட சொல்லு, ஞாயித்துக்கிழமை போன் பண்ணச் சொல்லு.", "Amma-kitta sollu, nyaayithukkizhamai phone panna sollu.", "Tell your mom to call on Sunday.", [("அம்மா", "p_priya")]),
    ("K11", "kin", "சின்ன பாட்டி உனக்கு ஸ்வெட்டர் பின்னிட்டு இருக்கா.", "Chinna paatti unakku sweater pinnittu irukkaa.", "Saroja (your grand-aunt, Paatti's younger sister) is knitting you a sweater.", [("சின்ன பாட்டி", "p_saroja")]),
    ("K12", "kin", "மாமா பையன் கிரிக்கெட் மேட்ச்ல செஞ்சுரி அடிச்சான்.", "Mama paiyan cricket match-la century adichaan.", "Karthik (your cousin, Ravi mama's son) hit a century in the cricket match.", [("மாமா பையன்", "p_karthik")]),
    ("K13", "kin", "பெரியப்பா பையனுக்கு அடுத்த வருஷம் கல்யாணம்.", "Periyappa paiyanukku adutha varusham kalyaanam.", "Vishnu (your cousin, Ravi periyappa's son) is getting married next year.", [("பெரியப்பா பையனுக்கு", "p_vishnu"), ("கல்யாணம்", "ev_vishnu_wedding")]),
    ("K14", "kin", "உன் அண்ணன் விஷ்ணு உன்னை கல்யாணத்துக்கு கண்டிப்பா வரச் சொன்னான்.", "Un annan Vishnu unnai kalyaanathukku kandippaa vara sonnaan.", "Your cousin Vishnu said you must come to the wedding.", [("விஷ்ணு", "p_vishnu")]),
    ("K15", "kin", "தம்பி கார்த்திக் உன்னை மாதிரி தான் படிக்கவே மாட்டேங்கறான்.", "Thambi Karthik unnai maadhiri thaan padikkave maattengaraan.", "Karthik (your younger cousin) refuses to study, just like you.", [("கார்த்திக்", "p_karthik")]),
    ("K16", "kin", "மாமாவும் மாமியும் பொங்கலுக்கு இங்க வர்றாங்க.", "Mama-vum mami-yum Pongal-ukku inga varraanga.", "Ravi mama and Lakshmi mami are coming here for Pongal.", [("மாமா", "p_ravi_mama"), ("மாமி", "p_lakshmi"), ("பொங்கல்", "ev_pongal")]),
    ("K17", "kin", "உன் அப்பாவோட அண்ணன் தான் கோவையில கடை வச்சிருக்காரு.", "Un appa-voda annan thaan Kovai-la kadai vachirukkaaru.", "It's your dad's elder brother (Ravi periyappa) who has the shop in Coimbatore.", [("அப்பாவோட அண்ணன்", "p_ravi_periyappa"), ("கோவை", "pl_coimbatore")]),
    ("K18", "kin", "உன் அம்மாவோட தம்பிக்கு பேங்க்ல ப்ரமோஷன்.", "Un amma-voda thambikku bank-la promotion.", "Your mom's younger brother (Ravi mama) got a promotion at the bank.", [("அம்மாவோட தம்பி", "p_ravi_mama")]),
    ("K19", "kin", "பாப்பா சின்ன வயசுல ரசம் சாதம் மட்டும் தான் சாப்பிடுவா.", "Pappa chinna vayasula rasam saadham mattum thaan saappiduvaa.", "Pappa (your mom, Priya) would only eat rasam rice as a child.", [("பாப்பா", "p_priya"), ("ரசம்", "d_rasam")]),
    ("K20", "kin", "சின்னு எப்போ லீவு எடுத்து வர்றா?", "Chinnu eppo leave eduthu varraa?", "When is Chinnu (your sister Divya) taking leave and coming?", [("சின்னு", "p_divya")]),
    ("K21", "kin", "பேரா, நீ எப்போ ஊருக்கு வர்ற?", "Pera, nee eppo oorukku varra?", "Grandson, when are you coming home (to the Madurai house)?", [("பேரா", "p_arjun"), ("ஊரு", "pl_madurai_house")]),
    ("K22", "kin", "மாமா உனக்கு புது போன் வாங்கி தரேன்னு சொல்றான்.", "Mama unakku pudhu phone vaangi tharen-nu solraan.", "Ravi mama says he'll buy you a new phone.", [("மாமா", "p_ravi_mama")]),
    ("K23", "kin", "பெரியப்பாவுக்கு சுகர் அதிகமா இருக்காம், கவனமா இருக்கச் சொல்லு.", "Periyappa-vukku sugar adhigamaa irukkaam, kavanamaa irukka sollu.", "Ravi periyappa's sugar is high, apparently; tell him to be careful.", [("பெரியப்பா", "p_ravi_periyappa")]),
    ("K24", "kin", "அத்தை உனக்கு சிங்கப்பூர்லேர்ந்து சாக்லேட் அனுப்பியிருக்கா.", "Atthai unakku Singapore-lerndhu chocolate anuppiyirukkaa.", "Meena atthai has sent you chocolates from Singapore.", [("அத்தை", "p_meena")]),
    ("K25", "kin", "உன் அக்காவுக்கு நைட் ஷிஃப்ட், தூங்கவே மாட்டேங்கறா.", "Un akkavukku night shift, thoongave maattengaraa.", "Your sister has night shifts; she just doesn't sleep.", [("அக்கா", "p_divya")]),
    ("K26", "kin", "மாமி பாயசம் செஞ்சு அனுப்பினா, ரொம்ப நல்லா இருந்துச்சு.", "Mami payasam senju anuppinaa, romba nallaa irundhuchu.", "Lakshmi mami made and sent payasam; it was very good.", [("மாமி", "p_lakshmi"), ("பாயசம்", "d_payasam")]),
    ("K27", "kin", "தாத்தாவோட பழைய ரேடியோ இன்னும் வேலை செய்யுது.", "Thatha-voda pazhaya radio innum velai seyyudhu.", "Thatha's old radio still works.", [("தாத்தா", "p_raghavan")]),
    ("K28", "kin", "உங்க அம்மா சின்ன வயசுல கோவிலுக்கு என்கூட தினமும் வருவா.", "Unga amma chinna vayasula kovilukku en-kooda dhinamum varuvaa.", "Your mom used to come with me to the Meenakshi temple every day as a child.", [("அம்மா", "p_priya"), ("கோவில்", "pl_meenakshi_kovil")]),
    ("K29", "kin", "என் மருமகள் ரொம்ப நல்ல பொண்ணு, உனக்கு எப்பவும் சாப்பாடு போடுவா.", "En marumagal romba nalla ponnu, unakku eppavum saappaadu poduvaa.", "My daughter-in-law (Lakshmi mami) is a very good person; she'll always feed you.", [("மருமகள்", "p_lakshmi")]),
    ("K30", "kin", "என் மாப்பிள்ளைக்கு அடுத்த மாசம் பிறந்தநாள்.", "En maapillaikku adutha maasam pirandhanaal.", "My son-in-law (your dad) has his birthday next month.", [("மாப்பிள்ளை", "p_senthil")]),
    ("K31", "kin", "உன் சித்தப்பா இல்ல, பெரியப்பா தான் கோவையில இருக்காரு.", "Un chithappa illa, periyappa thaan Kovai-la irukkaaru.", "Not your chithappa; it's periyappa (Ravi, Dad's elder brother) who lives in Coimbatore.", [("பெரியப்பா", "p_ravi_periyappa")]),
    ("K32", "kin", "பேத்தி திவ்யா டாக்டர் ஆயிட்டா, நீயும் நல்லா படி.", "Pethi Divya doctor aayittaa, neeyum nallaa padi.", "Granddaughter Divya became a doctor; you study well too.", [("திவ்யா", "p_divya")]),
    ("K33", "kin", "மாமா பையன் கார்த்திக்குக்கு பதினாறு வயசு ஆச்சு.", "Mama paiyan Karthik-ukku padhinaaru vayasu aachu.", "Karthik (Ravi mama's son) has turned sixteen.", [("கார்த்திக்", "p_karthik")]),
    ("K34", "kin", "உன் அப்பாவோட தங்கச்சி மீனா உனக்கு விசா விஷயமா ஹெல்ப் பண்ணுவா.", "Un appa-voda thangachi Meena unakku visa vishayamaa help pannuvaa.", "Your dad's younger sister Meena will help you with the visa matter.", [("மீனா", "p_meena")]),
    ("K35", "kin", "அம்மம்மா சொல்றதை கேளு, தினமும் ரசம் குடி.", "Ammamma solradhai kelu, dhinamum rasam kudi.", "Listen to Ammamma (me, Paatti): drink rasam every day.", [("அம்மம்மா", "p_kamala"), ("ரசம்", "d_rasam")]),
    ("K36", "kin", "உன் மாமா சின்ன வயசுல தாத்தாகிட்ட நிறைய அடி வாங்கியிருக்கான்.", "Un mama chinna vayasula Thatha-kitta niraya adi vaangiyirukkaan.", "Your uncle Ravi got plenty of beatings from Thatha as a kid.", [("மாமா", "p_ravi_mama"), ("தாத்தா", "p_raghavan")]),
    ("K37", "kin", "பெரியப்பா வீட்ல எல்லாரும் நலமா?", "Periyappa veettula ellaarum nalamaa?", "Is everyone well at Ravi periyappa's house?", [("பெரியப்பா", "p_ravi_periyappa")]),
    ("K38", "kin", "அக்காவும் நீயும் ஒண்ணா வந்தா எனக்கு ரொம்ப சந்தோஷம்.", "Akkavum neeyum onnaa vandhaa enakku romba sandhosham.", "If you and your sister come together, I'll be very happy.", [("அக்கா", "p_divya")]),
    ("K39", "kin", "சின்ன பாட்டி வீடு பக்கத்து தெரு தான், தினமும் பாத்துக்குவா.", "Chinna paatti veedu pakkathu theru thaan, dhinamum paathukkuvaa.", "Saroja (your grand-aunt) lives on the next street; she checks on me daily.", [("சின்ன பாட்டி", "p_saroja")]),
    ("K40", "kin", "மாமி பரதநாட்டியம் க்ளாஸ்ல அரங்கேற்றம் வர்ற மாசம்.", "Mami Bharatanatyam class-la arangetram varra maasam.", "Lakshmi mami's dance class has its arangetram next month.", [("மாமி", "p_lakshmi")]),
    ("K41", "kin", "என் பொண்ணு உன்னை ரொம்ப செல்லம் கொடுத்து வளர்த்துட்டா.", "En ponnu unnai romba sellam koduthu valarthuttaa.", "My daughter (your mom) raised you spoiled with love.", [("பொண்ணு", "p_priya")]),
    ("K42", "kin", "உங்க அம்மாவோட அக்கா இல்ல, அம்மாவுக்கு தம்பி மட்டும் தான்.", "Unga amma-voda akka illa, amma-vukku thambi mattum thaan.", "Your mom has no elder sister; she only has a younger brother (Ravi mama).", [("தம்பி", "p_ravi_mama")]),
    # ---------------- name collisions (32): bare "Ravi" ----------------
    ("N01", "name_collision", "ரவி நேத்து அடையாறுலேர்ந்து போன் பண்ணான்.", "Ravi nethu Adyar-lerndhu phone pannaan.", "Ravi (Mom's brother) called from Adyar yesterday.", [("ரவி", "p_ravi_mama"), ("அடையாறு", "pl_adyar")]),
    ("N02", "name_collision", "ரவி கோவையில புது கடை திறந்திருக்காரு.", "Ravi Kovai-la pudhu kadai thirandhirukkaaru.", "Ravi (Dad's elder brother) has opened a new shop in Coimbatore.", [("ரவி", "p_ravi_periyappa"), ("கோவை", "pl_coimbatore")]),
    ("N03", "name_collision", "ரவியும் லட்சுமியும் பொங்கலுக்கு வர்றாங்க.", "Ravi-yum Lakshmi-yum Pongal-ukku varraanga.", "Ravi (Mom's brother) and Lakshmi are coming for Pongal.", [("ரவி", "p_ravi_mama"), ("லட்சுமி", "p_lakshmi")]),
    ("N04", "name_collision", "ரவியோட பையன் விஷ்ணுவுக்கு கல்யாணம் நிச்சயம் ஆச்சு.", "Ravi-yoda paiyan Vishnu-vukku kalyaanam nichayam aachu.", "Ravi's (Dad's elder brother's) son Vishnu's wedding is fixed.", [("ரவி", "p_ravi_periyappa"), ("விஷ்ணு", "p_vishnu")]),
    ("N05", "name_collision", "ரவி பேங்க்ல ரொம்ப வேலையாம், லீவே கிடைக்கலையாம்.", "Ravi bank-la romba velaiyaam, leave-e kidaikkalaiyaam.", "Ravi (Mom's brother) is swamped at the bank; can't get leave.", [("ரவி", "p_ravi_mama")]),
    ("N06", "name_collision", "ரவி துணிக்கடைக்கு தீபாவளி சீசன் பிஸியாம்.", "Ravi thunikkadaikku Deepavali season busy-aam.", "Ravi's (Dad's elder brother's) textile shop is busy for the Deepavali season.", [("ரவி", "p_ravi_periyappa"), ("தீபாவளி", "ev_deepavali")]),
    ("N07", "name_collision", "ரவி கார்த்திக்கை கிரிக்கெட் கோச்சிங்குக்கு சேர்த்துட்டான்.", "Ravi Karthik-ai cricket coaching-kku serthuttaan.", "Ravi (Mom's brother) enrolled Karthik in cricket coaching.", [("ரவி", "p_ravi_mama"), ("கார்த்திக்", "p_karthik")]),
    ("N08", "name_collision", "உங்க அப்பாவும் ரவியும் சின்ன வயசுல எப்பவும் சண்டை.", "Unga appa-vum Ravi-yum chinna vayasula eppavum sandai.", "Your dad and Ravi (Dad's elder brother) always fought as kids.", [("ரவி", "p_ravi_periyappa"), ("அப்பா", "p_senthil")]),
    ("N09", "name_collision", "ரவி என்னை சென்னைக்கு வந்து இருக்கச் சொல்றான்.", "Ravi ennai Chennai-kku vandhu irukka solraan.", "Ravi (my son, Mom's brother) tells me to come and live in Chennai.", [("ரவி", "p_ravi_mama"), ("சென்னை", "pl_adyar")]),
    ("N10", "name_collision", "ரவி உன்னை அடுத்த முறை கோவைக்கு வரச் சொன்னாரு.", "Ravi unnai adutha murai Kovai-kku vara sonnaaru.", "Ravi (Dad's elder brother) said you should come to Coimbatore next time.", [("ரவி", "p_ravi_periyappa"), ("கோவை", "pl_coimbatore")]),
    ("N11", "name_collision", "ரவி உனக்கு புது லேப்டாப் வாங்கி தரேன்னு சொன்னான்.", "Ravi unakku pudhu laptop vaangi tharen-nu sonnaan.", "Ravi (Mom's brother, from context) said he'd buy you a new laptop.", [("ரவி", "p_ravi_mama")], ["Un mama nethu phone pannaan."]),
    ("N12", "name_collision", "ரவிக்கு இப்போ கடையில ஆறு பேரு வேலை செய்யறாங்க.", "Ravikku ippo kadaiyila aaru peru velai seyyaraanga.", "Ravi (Dad's elder brother, from context) now has six people working in the shop.", [("ரவி", "p_ravi_periyappa")], ["Periyappa kadaikku pudhu machine vaangittaaru."]),
    ("N13", "name_collision", "ரவி என் பையன் தானே, அவன் சொன்னா கேட்பேன்.", "Ravi en paiyan thaane, avan sonnaa ketpen.", "Ravi is my son after all; if he says so I'll listen.", [("ரவி", "p_ravi_mama")]),
    ("N14", "name_collision", "ரவி மாமா உனக்கு ஃபோன் பண்ணினானா?", "Ravi mama unakku phone panninaanaa?", "Did Ravi mama (Mom's brother) call you?", [("ரவி மாமா", "p_ravi_mama")]),
    ("N15", "name_collision", "ரவி பெரியப்பா ஷுகர் டாக்டர்கிட்ட போனாரா?", "Ravi periyappa sugar doctor-kitta ponaaraa?", "Did Ravi periyappa (Dad's elder brother) go to the diabetes doctor?", [("ரவி பெரியப்பா", "p_ravi_periyappa")]),
    ("N16", "name_collision", "ரவி சொன்னான், லட்சுமி மாமி அரங்கேற்றத்துக்கு எல்லாரும் வரணும்னு.", "Ravi sonnaan, Lakshmi mami arangetrathukku ellaarum varanum-nu.", "Ravi (Mom's brother) said everyone must come to Lakshmi mami's arangetram.", [("ரவி", "p_ravi_mama"), ("லட்சுமி மாமி", "p_lakshmi")]),
    ("N17", "name_collision", "ரவி மீனாவை சிங்கப்பூர்ல போய் பாத்துட்டு வந்தாரு.", "Ravi Meena-vai Singapore-la poi paathuttu vandhaaru.", "Ravi (Dad's elder brother) went to Singapore to see Meena and came back.", [("ரவி", "p_ravi_periyappa"), ("மீனா", "p_meena")]),
    ("N18", "name_collision", "ரவி சின்ன வயசுல தாத்தாகிட்ட கணக்கு கத்துக்கிட்டான்.", "Ravi chinna vayasula Thatha-kitta kanakku kathukittaan.", "Ravi (Mom's brother) learned maths from Thatha as a kid.", [("ரவி", "p_ravi_mama"), ("தாத்தா", "p_raghavan")]),
    ("N19", "name_collision", "ரவிக்கு இந்த வருஷம் ஐம்பத்தேழு வயசு ஆகுது.", "Ravikku indha varusham aimbathezhu vayasu aagudhu.", "Ravi (Dad's elder brother, b. 1969) turns fifty-seven this year.", [("ரவி", "p_ravi_periyappa")]),
    ("N20", "name_collision", "ரவிக்கு நாப்பத்தாறு வயசு ஆச்சு, இன்னும் சின்ன பையன் மாதிரி.", "Ravikku naappathaaru vayasu aachu, innum chinna paiyan maadhiri.", "Ravi (Mom's brother, b. 1980) has turned forty-six and is still like a little boy.", [("ரவி", "p_ravi_mama")]),
    ("N21", "name_collision", "ரவியும் பிரியாவும் சின்ன வயசுல ஒரே ஸ்கூல்.", "Ravi-yum Priya-vum chinna vayasula ore school.", "Ravi (Mom's brother) and Priya went to the same school as kids.", [("ரவி", "p_ravi_mama"), ("பிரியா", "p_priya")]),
    ("N22", "name_collision", "ரவி செந்திலுக்கு அண்ணன் மாதிரி இல்ல, அப்பா மாதிரி.", "Ravi Senthil-ukku annan maadhiri illa, appa maadhiri.", "Ravi (Dad's elder brother) is like a father to Senthil, not just a brother.", [("ரவி", "p_ravi_periyappa"), ("செந்தில்", "p_senthil")]),
    ("N23", "name_collision", "ரவி வீட்ல தங்கிட்டு தான் மதுரைக்கு வருவீங்க இல்ல?", "Ravi veettula thangittu thaan Madurai-kku varuveenga illa?", "You'll stay at Ravi's (Mom's brother's, Adyar) place on the way to Madurai, won't you?", [("ரவி", "p_ravi_mama"), ("மதுரை", "pl_madurai_house")]),
    ("N24", "name_collision", "ரவி கடைல உனக்கு பொங்கலுக்கு வேட்டி எடுத்து வச்சிருக்காரு.", "Ravi kadaila unakku Pongal-ukku vetti eduthu vachirukkaaru.", "Ravi (Dad's elder brother) has set aside a veshti for you at the shop for Pongal.", [("ரவி", "p_ravi_periyappa"), ("பொங்கல்", "ev_pongal")]),
    ("N25", "name_collision", "ரவி தான் அதை கொண்டு வந்து கொடுத்தான்.", "Ravi thaan adhai kondu vandhu koduthaan.", "It was Ravi (Mom's brother, from context) who brought it over.", [("ரவி", "p_ravi_mama")], ["Mami payasam senju anuppinaa."]),
    ("N26", "name_collision", "ரவி ஹால் புக் பண்ணிட்டாரு.", "Ravi hall book pannittaaru.", "Ravi (Dad's elder brother, from context) has booked the hall.", [("ரவி", "p_ravi_periyappa")], ["Vishnu-vukku kalyaanam adutha varusham."]),
    ("N27", "name_collision", "ரவி, லட்சுமி, கார்த்திக் மூணு பேரும் வர்றாங்க.", "Ravi, Lakshmi, Karthik moonu perum varraanga.", "Ravi (Mom's brother), Lakshmi and Karthik, all three are coming.", [("ரவி", "p_ravi_mama"), ("லட்சுமி", "p_lakshmi"), ("கார்த்திக்", "p_karthik")]),
    ("N28", "name_collision", "உன் அப்பாவோட அண்ணன் ரவி தான் குடும்பத்துல பெரியவரு.", "Un appa-voda annan Ravi thaan kudumbathula periyavaru.", "Your dad's elder brother Ravi is the eldest in that family.", [("ரவி", "p_ravi_periyappa")]),
    ("N29", "name_collision", "ரவி இன்னும் என்கிட்ட சின்ன பையன் மாதிரி தான் பேசுவான்.", "Ravi innum en-kitta chinna paiyan maadhiri thaan pesuvaan.", "Ravi (my son, Mom's brother) still talks to me like a little boy.", [("ரவி", "p_ravi_mama")]),
    ("N30", "name_collision", "ரவி எப்பவும் உங்க அப்பாவை தம்பின்னு தான் கூப்பிடுவாரு.", "Ravi eppavum unga appa-vai thambi-nnu thaan kooppiduvaaru.", "Ravi (Dad's elder brother) always calls your dad 'thambi'.", [("ரவி", "p_ravi_periyappa")]),
    ("N31", "name_collision", "ரவிக்கு நான் செஞ்ச முறுக்கு தான் பிடிக்கும், லட்சுமி செஞ்சா சாப்பிட மாட்டான்.", "Ravikku naan senja murukku thaan pidikkum, Lakshmi senjaa saappida maattaan.", "Ravi (Mom's brother) only likes the murukku I make; won't eat Lakshmi's.", [("ரவி", "p_ravi_mama"), ("முறுக்கு", "d_murukku")]),
    ("N32", "name_collision", "ரவி உங்க அப்பாவை கோவை வந்து கடையை பாத்துக்கச் சொல்றாரு.", "Ravi unga appa-vai Kovai vandhu kadaiyai paathukka solraaru.", "Ravi (Dad's elder brother) tells your dad to come to Coimbatore and look after the shop.", [("ரவி", "p_ravi_periyappa")]),
    # ---------------- dishes / places / events (31) ----------------
    ("D01", "dish_place", "இன்னைக்கு ரசம் வச்சேன், உனக்கு பிடிச்ச மாதிரி மிளகு அதிகம்.", "Innaikku rasam vachen, unakku pidicha maadhiri milagu adhigam.", "I made rasam today, extra pepper the way you like it.", [("ரசம்", "d_rasam")]),
    ("D02", "dish_place", "ஞாயித்துக்கிழமை சாம்பார்ல முருங்கக்காய் போட்டேன்.", "Nyaayithukkizhamai sambar-la murungakkaai potten.", "I put drumstick in the Sunday sambar.", [("சாம்பார்", "d_sambar")]),
    ("D03", "dish_place", "பொங்கலுக்கு சக்கரை பொங்கல் உனக்காக தனியா செய்வேன்.", "Pongal-ukku sakkarai pongal unakkaaga thaniyaa seiven.", "For Pongal I'll make sakkarai pongal separately just for you.", [("சக்கரை பொங்கல்", "d_pongal")]),
    ("D04", "dish_place", "முறுக்கு டின் இந்த வாரம் ஆஸ்டினுக்கு அனுப்பிட்டேன்.", "Murukku tin indha vaaram Austin-ukku anuppitten.", "I sent the murukku tin to Austin this week.", [("முறுக்கு", "d_murukku"), ("ஆஸ்டின்", "pl_austin")]),
    ("D05", "dish_place", "தாத்தா திதிக்கு சேமியா பாயசம் செய்யணும்.", "Thatha thithikku semiya payasam seyyanum.", "For Thatha's thithi I must make semiya payasam.", [("தாத்தா திதி", "ev_thatha_thithi"), ("பாயசம்", "d_payasam")]),
    ("D06", "dish_place", "கொழுக்கட்டை மடிக்க அக்கா மட்டும் தான் லாயக்கு.", "Kozhukattai madikka akka mattum thaan laayakku.", "Only your sister is any good at pleating kozhukattai.", [("கொழுக்கட்டை", "d_kozhukattai"), ("அக்கா", "p_divya")]),
    ("D07", "dish_place", "கோவிலுக்கு வெள்ளிக்கிழமை போயிட்டு வந்தேன், உனக்கு பிரசாதம் வச்சிருக்கேன்.", "Kovilukku vellikkizhamai poittu vandhen, unakku prasaadham vachirukken.", "I went to the (Meenakshi) temple on Friday; I've kept prasadam for you.", [("கோவில்", "pl_meenakshi_kovil")]),
    ("D08", "dish_place", "ஊருக்கு எப்போ வர்ற? மொட்டை மாடில கறிவேப்பிலை நல்லா வளர்ந்திருக்கு.", "Oorukku eppo varra? Mottai maadila kariveppilai nallaa valarndhirukku.", "When are you coming home to Madurai? The curry leaves on the terrace have grown well.", [("ஊரு", "pl_madurai_house")]),
    ("D09", "dish_place", "அடையாறு வீட்ல ஒரு நாள் தங்கிட்டு வாங்க.", "Adyar veettula oru naal thangittu vaanga.", "Stay a day at the Adyar flat (Ravi mama's) and come.", [("அடையாறு", "pl_adyar")]),
    ("D10", "dish_place", "கோவையில கல்யாணம், எல்லாரும் அங்க தான் கூடுவோம்.", "Kovai-la kalyaanam, ellaarum anga thaan kooduvom.", "The wedding (Vishnu's) is in Coimbatore; we'll all gather there.", [("கோவை", "pl_coimbatore"), ("கல்யாணம்", "ev_vishnu_wedding")]),
    ("D11", "dish_place", "தீபாவளிக்கு எண்ணெய் குளியல் நாலு மணிக்கு, மறந்துடாத.", "Deepavalikku ennei kuliyal naalu manikku, marandhudaadha.", "Oil bath at four for Deepavali, don't forget.", [("தீபாவளி", "ev_deepavali")]),
    ("D12", "dish_place", "ரசம் சாதம் நெய் விட்டு சாப்பிட்டா சளி போயிடும்.", "Rasam saadham nei vittu saappittaa sali poyidum.", "Eat rasam rice with ghee and the cold will go.", [("ரசம்", "d_rasam")]),
    ("D13", "dish_place", "உங்க அம்மா செய்ற சாம்பார் ரொம்ப இனிப்பா இருக்கும்.", "Unga amma seyra sambar romba inippaa irukkum.", "The sambar your mom makes is too sweet.", [("சாம்பார்", "d_sambar"), ("அம்மா", "p_priya")]),
    ("D14", "dish_place", "பொங்கல் அன்னைக்கு மொட்டை மாடில சூரிய உதயத்துக்கு வீடியோ கால் பண்ணுவோம்.", "Pongal annaikku mottai maadila sooriya udhayathukku video call pannuvom.", "On Pongal day we'll video call from the terrace at sunrise.", [("பொங்கல்", "ev_pongal"), ("மொட்டை மாடி", "pl_madurai_house")]),
    ("D15", "dish_place", "முறுக்கு இந்த வருஷம் கொஞ்சம் காரமா ஆயிடுச்சு.", "Murukku indha varusham konjam kaaramaa aayiduchu.", "The murukku came out a bit spicy this year.", [("முறுக்கு", "d_murukku")]),
    ("D16", "dish_place", "உன் பிறந்தநாளுக்கு பால் பாயசம் செஞ்சு வீடியோல காட்டறேன்.", "Un pirandhanaalukku paal payasam senju video-la kaattaren.", "For your birthday I'll make paal payasam and show you on video.", [("பால் பாயசம்", "d_payasam")]),
    ("D17", "dish_place", "விநாயகர் சதுர்த்திக்கு கொழுக்கட்டை இருபத்தொண்ணு செய்யணும்.", "Vinayagar Chaturthikku kozhukattai irubathonnu seyyanum.", "For Vinayagar Chaturthi I need to make twenty-one kozhukattai.", [("கொழுக்கட்டை", "d_kozhukattai")]),
    ("D18", "dish_place", "மீனாட்சி கோவில் திருவிழாவுக்கு வா, கூட்டம் பாக்கலாம்.", "Meenakshi kovil thiruvizhaavukku vaa, koottam paakkalaam.", "Come for the Meenakshi temple festival; let's see the crowds.", [("மீனாட்சி கோவில்", "pl_meenakshi_kovil")]),
    ("D19", "dish_place", "கே.கே. நகர் வீட்டு கேட் ரிப்பேர் பண்ணணும்.", "K.K. Nagar veettu gate repair pannanum.", "The gate of the K.K. Nagar house (Madurai) needs repair.", [("கே.கே. நகர்", "pl_madurai_house")]),
    ("D20", "dish_place", "சென்னைல ரொம்ப வெயில், அடையாறுல கரண்ட் கட்.", "Chennai-la romba veyil, Adyar-la current cut.", "Very hot in Chennai; power cut in Adyar.", [("அடையாறு", "pl_adyar")]),
    ("D21", "dish_place", "ஆஸ்டின்ல குளிர் அதிகமா? ஸ்வெட்டர் போட்டுக்க.", "Austin-la kulir adhigamaa? Sweater pottukka.", "Is it very cold in Austin? Wear a sweater.", [("ஆஸ்டின்", "pl_austin")]),
    ("D22", "dish_place", "திதி அன்னைக்கு காலைல போன் பண்ணு, தாத்தாவை நினைச்சுக்கலாம்.", "Thithi annaikku kaalaila phone pannu, Thatha-vai ninaichukkalaam.", "Call on the morning of the thithi; we'll remember Thatha together.", [("திதி", "ev_thatha_thithi"), ("தாத்தா", "p_raghavan")]),
    ("D23", "dish_place", "ரசம் பொடி அரைச்சு வச்சிருக்கேன், அக்கா வர்றப்போ கொடுத்து விடறேன்.", "Rasam podi araichu vachirukken, akka varrappo koduthu vidaren.", "I've ground rasam powder; I'll send it when your sister visits.", [("ரசம்", "d_rasam"), ("அக்கா", "p_divya")]),
    ("D24", "dish_place", "சாம்பார் சாதத்துக்கு அப்பளம் இல்லாம சாப்பிடாத.", "Sambar saadhathukku appalam illaama saappidaadha.", "Don't eat sambar rice without appalam.", [("சாம்பார்", "d_sambar")]),
    ("D25", "dish_place", "வெண் பொங்கல்ல மிளகு ஜீரகம் தான் முக்கியம்.", "Ven pongal-la milagu jeeragam thaan mukkiyam.", "In ven pongal, pepper and cumin are what matter.", [("வெண் பொங்கல்", "d_pongal")]),
    ("D26", "dish_place", "கோவில் பக்கத்துல புது ஜவுளிக்கடை வந்திருக்கு.", "Kovil pakkathula pudhu javulikkadai vandhirukku.", "A new textile shop has come up next to the (Meenakshi) temple.", [("கோவில்", "pl_meenakshi_kovil")]),
    ("D27", "dish_place", "கோவைக்கு ட்ரெயின்ல போனா ஆறு மணி நேரம்.", "Kovai-kku train-la ponaa aaru mani neram.", "By train to Coimbatore it's six hours.", [("கோவை", "pl_coimbatore")]),
    ("D28", "dish_place", "தீபாவளிக்கு புது டிரஸ் எடுத்தியா?", "Deepavalikku pudhu dress eduthiyaa?", "Did you buy new clothes for Deepavali?", [("தீபாவளி", "ev_deepavali")]),
    ("D29", "dish_place", "கல்யாணத்துக்கு பட்டு வேட்டி கட்டணும், கத்துக்கோ.", "Kalyaanathukku pattu vetti kattanum, kathukko.", "You must wear a silk veshti for the wedding (Vishnu's); learn how.", [("கல்யாணம்", "ev_vishnu_wedding")]),
    ("D30", "dish_place", "பாயசம் செய்ய தாத்தா சொல்லிக் கொடுத்த மாதிரி தான் செய்வேன்.", "Payasam seyya Thatha sollik kodutha maadhiri thaan seiven.", "I make payasam exactly the way Thatha taught me.", [("பாயசம்", "d_payasam"), ("தாத்தா", "p_raghavan")]),
    ("D31", "dish_place", "ஊர்ல இப்போ மழை, மொட்டை மாடி முழுக்க தண்ணி.", "Oorla ippo mazhai, mottai maadi muzhukka thanni.", "It's raining at home (Madurai) now; the terrace is full of water.", [("ஊர்", "pl_madurai_house")]),
]

# (id, tamil, roman, gloss, kind, literal, meaning)   kind None → negative (no card expected)
I = [
    ("I01", "யானைக்கும் அடி சறுக்கும்.", "Yaanaikkum adi sarukkum.", "Anyone can slip up.", "proverb", "Even an elephant's foot slips.", "Anyone can make a mistake; don't be hard on yourself."),
    ("I02", "பசி வந்தா பத்தும் பறந்து போகும்.", "Pasi vandhaa paththum parandhu pogum.", "Eat first.", "proverb", "When hunger comes, the ten (virtues) fly away.", "Hunger overrides everything; eat before anything else."),
    ("I03", "அது உன் தலை எழுத்து.", "Adhu un thalai ezhuthu.", "That's your fate.", "idiom", "That is your head-writing.", "Fate; what is written on your forehead at birth."),
    ("I04", "நீ சொன்னதை கேட்டதும் வயித்துல பால் வார்த்த மாதிரி இருந்துச்சு.", "Nee sonnadhai kettadhum vayithula paal vaartha maadhiri irundhuchu.", "What you said was a huge relief.", "idiom", "It was like milk poured into my stomach.", "Deep relief and joy."),
    ("I05", "உன்னை கண்ணு குளிர பாத்துட்டேன்.", "Unnai kannu kulira paathutten.", "It did my heart good to see you.", "idiom", "I saw you until my eyes cooled.", "Seeing something heart-warming to full satisfaction."),
    ("I06", "கண்ணு பட்டுடும், திருஷ்டி சுத்தி போடணும்.", "Kannu pattudum, dhrishti suthi podanum.", "We must ward off the evil eye.", "cultural", "The eye will fall; must circle and cast it off.", "Admiration can attract the evil eye; a salt-and-chilli ritual wards it off."),
    ("I07", "போறதுக்கு முன்னாடி ஒரு வார்த்தை சொல்லிட்டு போ.", "Poradhukku munnaadi oru vaarthai sollittu po.", "Tell me before you leave.", "idiom", "Say one word and go.", "Let me know before you go; don't vanish without a word."),
    ("I08", "சாப்பிட்டியா?", "Saappittiyaa?", "How are you? (greeting)", "register", "Did you eat?", "The standard affectionate greeting; it means 'I care about you', not a literal question."),
    ("I09", "பல்லைக் கடிச்சுக்கிட்டு இருக்கேன்.", "Pallai kadichukittu irukken.", "I'm enduring it.", "idiom", "I'm biting my teeth.", "Enduring pain or hardship silently."),
    ("I10", "அப்பறம் மனசு கல்லா போயிடுச்சு.", "Appuram manasu kallaa poyiduchu.", "After that I went numb.", "idiom", "Then the heart became stone.", "Numbed by grief; hardened emotionally."),
    ("I11", "பொழுதே போகலை.", "Pozhudhe pogalai.", "I'm lonely.", "idiom", "The time isn't passing at all.", "I'm bored and lonely; a gentle plea for company."),
    ("I12", "மனசு கேக்கலை.", "Manasu kekkalai.", "I couldn't bring myself to.", "idiom", "The heart didn't listen.", "I couldn't bring myself to do it."),
    ("I13", "அவளுக்கு கை ராசி.", "Avalukku kai raasi.", "She has a lucky touch.", "idiom", "She has hand-luck.", "Whatever she cooks or starts turns out well."),
    ("I14", "அள்ளிக் கொடு, குறையாது.", "Allik kodu, kuraiyaadhu.", "Be generous.", "idiom", "Give by the scoopful; it won't run short.", "Be generous; giving freely doesn't diminish you."),
    ("I15", "நீ நூறு வயசு இருப்ப!", "Nee nooru vayasu iruppa!", "Speak of the devil (affectionately).", "cultural", "You will live a hundred years!", "Said when someone appears just as they were being talked about."),
    ("I16", "முழுப்பூசணிக்காயை சோத்துல மறைக்க முடியாது.", "Muzhu poosanikkaayai soththula maraikka mudiyaadhu.", "You can't hide the obvious.", "proverb", "You can't hide a whole pumpkin in rice.", "Big truths cannot be hidden."),
    ("I17", "நாய் வாலை நிமிர்த்த முடியாது.", "Naai vaalai nimirtha mudiyaadhu.", "People don't change.", "proverb", "You can't straighten a dog's tail.", "Some people never change."),
    ("I18", "கழுதைக்கு தெரியுமா கற்பூர வாசனை?", "Kazhudhaikku theriyumaa karpoora vaasanai?", "Wasted on him.", "proverb", "Does a donkey know the scent of camphor?", "Something fine is wasted on one who can't appreciate it."),
    ("I19", "ஆடு நனையுதுன்னு ஓநாய் அழுதுச்சாம்.", "Aadu nanaiyudhunnu onaai azhudhuchaam.", "Crocodile tears.", "proverb", "The wolf wept that the goat was getting wet.", "False sympathy; crocodile tears."),
    ("I20", "எலி வளையா இருந்தாலும் தனி வளையா இருக்கணும்.", "Eli valaiyaa irundhaalum thani valaiyaa irukkanum.", "Have your own home.", "proverb", "Even a rat hole should be your own hole.", "A home of your own matters more than its size."),
    ("I21", "கடைசியா ஆண்டவன் கண்ணைத் திறந்துட்டான்.", "Kadaisiyaa Aandavan kannai thirandhuttaan.", "Justice at last.", "idiom", "Finally God opened his eyes.", "At last, justice or good fortune has arrived."),
    ("I22", "வாழைப்பழத்துல ஊசி ஏத்துற மாதிரி சொல்லணும்.", "Vaazhaippazhathula oosi ethura maadhiri sollanum.", "Say it gently.", "idiom", "Say it like slipping a needle into a banana.", "Give advice so smoothly it isn't felt as criticism."),
    ("I23", "அதை நினைச்சா வயிறு எரியுது.", "Adhai ninaichaa vayiru eriyudhu.", "It pains me to think of it.", "idiom", "Thinking of it, my stomach burns.", "Burning anguish (or envy), depending on context."),
    ("I24", "ஒரு கை பாத்துடலாம்.", "Oru kai paathudalaam.", "Let's give it a go.", "idiom", "Let's see one hand.", "Let's try it / take them on."),
    ("I25", "உப்பு சப்பு இல்லாம பேசறான்.", "Uppu sappu illaama pesaraan.", "He talks without substance.", "idiom", "He talks with no salt, no taste.", "Bland talk with no substance."),
    ("I26", "அவனுக்கு நாக்கு நீளம் ஜாஸ்தி.", "Avanukku naakku neelam jaasthi.", "He's too cheeky.", "idiom", "His tongue is too long.", "Talks back; cheeky."),
    ("I27", "இப்போ அவரு பல்லு போன பாம்பு.", "Ippo avaru pallu pona paambu.", "He's harmless now.", "idiom", "Now he's a snake that lost its teeth.", "Someone once feared who is now harmless."),
    ("I28", "அவனுக்கு மூக்கு உடைஞ்சு போச்சு.", "Avanukku mookku odainju pochu.", "He was humiliated.", "idiom", "His nose broke.", "He lost face; was humiliated."),
    ("I29", "நான் கை கழுவிட்டேன்.", "Naan kai kazhuvitten.", "I'm done with it.", "idiom", "I washed my hands.", "I've disowned the matter; I'm done."),
    ("I30", "அடுத்த வாரம் பொண்ணு பாக்க போறாங்க.", "Adutha vaaram ponnu paakka poraanga.", "They're meeting a prospective bride.", "cultural", "Next week they're going to see a girl.", "The family is visiting a prospective bride, the arranged-marriage custom."),
    ("I31", "ராஜா மாதிரி இரு.", "Raajaa maadhiri iru.", "Live well (blessing).", "register", "Be like a king.", "A blessing: live comfortably and without struggle."),
    ("I32", "ஐயோ பாவம்!", "Aiyo paavam!", "Poor thing!", "register", "Oh, sin!", "Sympathy ('poor thing'), not an accusation."),
    ("I33", "அவனை செருப்பால அடிக்கணும்.", "Avanai seruppaala adikkanum.", "He deserves contempt.", "idiom", "He should be beaten with a slipper.", "An expression of strong contempt, not a literal threat."),
    ("I34", "பெரியவங்ககிட்ட 'நீ' இல்ல, 'நீங்க'ன்னு சொல்லு.", "Periyavanga-kitta 'nee' illa, 'neenga'-nnu sollu.", "Use the respectful 'you' with elders.", "honorific", "With elders, not 'nee', say 'neenga'.", "Tamil marks respect in the pronoun; use the plural form with elders."),
    ("I35", "காய்கறிக்கடை அக்கா உன்னை விசாரிச்சா.", "Kaaikari kadai akka unnai visaarichaa.", "The vegetable-seller lady asked after you.", "register", "The vegetable-shop elder-sister asked about you.", "'Akka' here is polite address to an unrelated woman, not your sister."),
    ("I36", "அரசன் அன்று கொல்வான், தெய்வம் நின்று கொல்லும்.", "Arasan andru kolvaan, dheivam nindru kollum.", "Divine justice is slow but sure.", "proverb", "The king kills at once; God kills standing by.", "Divine justice is slow but certain."),
    ("I37", "அந்த வார்த்தை ஆயிரம் பொன் பெறும்.", "Andha vaarthai aayiram pon perum.", "That was priceless.", "idiom", "That word is worth a thousand gold.", "Priceless; deeply valued."),
    ("I38", "கல்யாணம் பண்ணிப் பாரு, வீடு கட்டிப் பாரு.", "Kalyaanam pannip paaru, veedu kattip paaru.", "Both are harder than they look.", "proverb", "Try holding a wedding, try building a house.", "Both are far harder than they look."),
    ("I39", "அடி உதவுற மாதிரி அண்ணன் தம்பி உதவ மாட்டான்.", "Adi udhavura maadhiri annan thambi udhava maattaan.", "Discipline teaches best.", "proverb", "Even brothers won't help you like a beating does.", "Discipline teaches what kindness cannot. ('annan', 'thambi' are generic here, not your relatives.)"),
    ("I40", "அவன் தலையில துண்டு போட்டுக்கிட்டு திரியறான்.", "Avan thalaiyila thundu pottukittu thiriyaraan.", "He's hiding in shame.", "idiom", "He wanders with a towel over his head.", "Avoiding people out of shame."),
    ("I41", "கட்டை விரல் கூட அசைக்க மாட்டான்.", "Kattai viral kooda asaikka maattaan.", "He won't lift a finger.", "idiom", "He won't even move his thumb.", "He won't lift a finger to help."),
    ("I42", "இருட்டுல கருப்பு பூனை தேடுற மாதிரி.", "Iruttula karuppu poonai thedura maadhiri.", "A futile search.", "idiom", "Like searching for a black cat in the dark.", "A futile search."),
    # negatives: plain sentences, no card expected
    ("X01", "இன்னைக்கு மதுரைல ரொம்ப வெயில்.", "Innaikku Madurai-la romba veyil.", "It's very hot in Madurai today.", None, "", ""),
    ("X02", "நான் காலைல ஆறு மணிக்கு எழுந்துட்டேன்.", "Naan kaalaila aaru manikku ezhundhutten.", "I got up at six.", None, "", ""),
    ("X03", "முழங்கால் வலி கொஞ்சம் குறைஞ்சிருக்கு.", "Muzhangaal vali konjam kurainjirukku.", "The knee pain has eased a little.", None, "", ""),
    ("X04", "டாக்டர் புது மாத்திரை கொடுத்தாரு.", "Doctor pudhu maathirai koduthaaru.", "The doctor gave new tablets.", None, "", ""),
    ("X05", "படிப்பு எப்படி போகுது?", "Padippu eppadi pogudhu?", "How are studies going?", None, "", ""),
    ("X06", "இந்த வாரம் மழை வரும்னு சொல்றாங்க.", "Indha vaaram mazhai varum-nu solraanga.", "They say it'll rain this week.", None, "", ""),
    ("X07", "நான் நேத்து கோவிலுக்கு போனேன்.", "Naan nethu kovilukku ponen.", "I went to the temple yesterday.", None, "", ""),
    ("X08", "பால்காரன் இன்னைக்கு லேட்டா வந்தான்.", "Paalkaaran innaikku late-aa vandhaan.", "The milkman came late today.", None, "", ""),
    ("X09", "உனக்கு புது போன் நல்லா இருக்கா?", "Unakku pudhu phone nallaa irukkaa?", "Is your new phone good?", None, "", ""),
    ("X10", "நாளைக்கு பவர் கட் சொல்லியிருக்காங்க.", "Naalaikku power cut solliyirukkaanga.", "They've announced a power cut tomorrow.", None, "", ""),
    ("X11", "ரசம் வச்சேன், சாப்பிட்டேன்.", "Rasam vachen, saappitten.", "I made rasam and ate.", None, "", ""),
    ("X12", "உன் அம்மா போன் பண்ணினா.", "Un amma phone panninaa.", "Your mom called.", None, "", ""),
    ("X13", "மாமா அடுத்த வாரம் வர்றான்.", "Mama adutha vaaram varraan.", "Your uncle is coming next week.", None, "", ""),
    ("X14", "எனக்கு இப்போ தூக்கம் வருது.", "Enakku ippo thookkam varudhu.", "I'm getting sleepy now.", None, "", ""),
    ("X15", "டிவில செய்தி பாத்துட்டு இருக்கேன்.", "TV-la seidhi paathuttu irukken.", "I'm watching the news on TV.", None, "", ""),
    ("X16", "தண்ணி நிறைய குடி.", "Thanni niraya kudi.", "Drink plenty of water.", None, "", ""),
    ("X17", "நீ எப்போ ஊருக்கு வர்ற?", "Nee eppo oorukku varra?", "When are you coming home?", None, "", ""),
    ("X18", "இன்னைக்கு வெள்ளிக்கிழமை, விளக்கு ஏத்தினேன்.", "Innaikku vellikkizhamai, vilakku ethinen.", "It's Friday; I lit the lamp.", None, "", ""),
    ("X19", "பக்கத்து வீட்டு நாய் ராத்திரி முழுக்க குரைச்சுது.", "Pakkathu veettu naai raathiri muzhukka kuraichudhu.", "The neighbour's dog barked all night.", None, "", ""),
    ("X20", "கறிவேப்பிலை செடி நல்லா வளர்ந்திருக்கு.", "Kariveppilai sedi nallaa valarndhirukku.", "The curry-leaf plant has grown well.", None, "", ""),
    ("X21", "பரீட்சை எப்போ முடியுது?", "Pareetchai eppo mudiyudhu?", "When do exams finish?", None, "", ""),
    ("X22", "நான் கண்ணாடி மாத்தணும்.", "Naan kannaadi maathanum.", "I need to change my glasses.", None, "", ""),
    ("X23", "இந்த மாசம் கரண்ட் பில் அதிகம்.", "Indha maasam current bill adhigam.", "The power bill is high this month.", None, "", ""),
    ("X24", "உங்க அப்பா ஆபீஸ்லேர்ந்து வந்துட்டாரா?", "Unga appa office-lerndhu vandhuttaaraa?", "Has your dad come back from the office?", None, "", ""),
    ("X25", "நான் சீக்கிரம் தூங்கப் போறேன்.", "Naan seekkiram thoongap poren.", "I'm going to sleep early.", None, "", ""),
    ("X26", "பூக்காரி இன்னைக்கு மல்லிகைப்பூ கொண்டு வரலை.", "Pookkaari innaikku malligaippoo kondu varalai.", "The flower-seller didn't bring jasmine today.", None, "", ""),
    ("X27", "உன் அக்கா எப்படி இருக்கா?", "Un akka eppadi irukkaa?", "How is your sister?", None, "", ""),
    ("X28", "ஆட்டோ சார்ஜ் கூடிடுச்சு.", "Auto charge koodiduchu.", "Auto fares have gone up.", None, "", ""),
    ("X29", "எனக்கு காது கொஞ்சம் கேக்கலை, சத்தமா பேசு.", "Enakku kaadhu konjam kekkalai, sathamaa pesu.", "I can't hear well; speak louder.", None, "", ""),
    ("X30", "இந்த வாரம் தக்காளி விலை அதிகம்.", "Indha vaaram thakkaali vilai adhigam.", "Tomatoes are expensive this week.", None, "", ""),
    ("X31", "நான் தினமும் பேப்பர் படிக்கிறேன்.", "Naan dhinamum paper padikkiren.", "I read the paper every day.", None, "", ""),
    ("X32", "அடுத்த மாசம் கண் ஆபரேஷன் இருக்கு.", "Adutha maasam kan operation irukku.", "I have an eye operation next month.", None, "", ""),
    ("X33", "மொட்டை மாடில துணி காய வச்சிருக்கேன்.", "Mottai maadila thuni kaaya vachirukken.", "I've put clothes to dry on the terrace.", None, "", ""),
    ("X34", "உனக்கு ஜுரம் சரியாயிடுச்சா?", "Unakku juram sariyaayiduchaa?", "Has your fever gone?", None, "", ""),
    ("X35", "பேருந்து ஸ்டாப் வரைக்கும் நடந்து போனேன்.", "Perundhu stop varaikkum nadandhu ponen.", "I walked to the bus stop.", None, "", ""),
    ("X36", "பொங்கல் இந்த வருஷம் ஜனவரி பதினாலு.", "Pongal indha varusham January padhinaalu.", "Pongal is on January 14 this year.", None, "", ""),
    ("X37", "நான் உனக்கு வாழ்த்து சொல்ல மறந்துட்டேன்.", "Naan unakku vaazhthu solla marandhutten.", "I forgot to wish you.", None, "", ""),
    ("X38", "வீட்டுக்கு புது பெயிண்ட் அடிக்கணும்.", "Veettukku pudhu paint adikkanum.", "The house needs a new coat of paint.", None, "", ""),
    ("X39", "என் கைபேசி சார்ஜ் முடிஞ்சு போச்சு.", "En kaipesi charge mudinju pochu.", "My phone's battery died.", None, "", ""),
    ("X40", "இன்னைக்கு காய்கறி வாங்க போகலை.", "Innaikku kaaikari vaanga pogalai.", "I didn't go to buy vegetables today.", None, "", ""),
    ("X41", "சின்ன பாட்டி நேத்து வந்தா.", "Chinna paatti nethu vandhaa.", "Saroja came yesterday.", None, "", ""),
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "kinship_names_dishes.jsonl").open("w", encoding="utf-8") as f:
        for row in G:
            id_, cat, ta, rom, gloss, ents, *ctx = row
            f.write(json.dumps({
                "id": id_, "category": cat, "speaker": "p_kamala", "listener": "p_arjun",
                "context": ctx[0] if ctx else [], "src_text": ta, "src_roman": rom, "gloss": gloss,
                "entities": [ent(s, n) for s, n in ents],
            }, ensure_ascii=False) + "\n")
    with (OUT / "idioms.jsonl").open("w", encoding="utf-8") as f:
        for id_, ta, rom, gloss, kind, literal, meaning in I:
            f.write(json.dumps({
                "id": id_, "src_text": ta, "src_roman": rom, "gloss": gloss, "expect_card": kind is not None,
                "card": {"kind": kind, "source": ta, "literal": literal, "meaning": meaning} if kind else None,
            }, ensure_ascii=False) + "\n")
    print(f"wrote {len(G)} grounding items and {len(I)} idiom items to {OUT}")


if __name__ == "__main__":
    main()
