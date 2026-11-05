"""Every word Khurak ever says comes from this file.

The agent never generates free text for a patient. These templates are rendered with
Timbre v3.0 once, cached, and replayed. They MUST be reviewed by a clinician before any
real-world use. Kannada strings should be reviewed by a native speaker.
"""
from __future__ import annotations

LANG_NAMES = {"hi-IN": "Hindi", "mr-IN": "Marathi", "bn-IN": "Bengali", "kn-IN": "Kannada", "hi-en": "Hinglish"}


def prompt_lang(lang: str) -> str:
    """Hinglish patients are spoken to in Hindi (and understood as hi-IN + en-IN)."""
    return "hi-IN" if lang == "hi-en" else lang


TEMPLATES: dict[str, dict[str, str]] = {
    "hi-IN": {
        "greeting": "नमस्ते {name} जी, मैं खुराक बोल रही हूँ, आपके स्वास्थ्य केंद्र से।",
        "ask_dose": "क्या आपने आज की टीबी की दवा ले ली?",
        "followup_dose": "माफ़ कीजिए, मैं ठीक से समझ नहीं पाई। क्या आपने आज दवा ली? हाँ या नहीं बोलिए।",
        "ask_symptoms": "क्या कोई तकलीफ़ है? जैसे उल्टी, पेट दर्द, या आँखों में पीलापन?",
        "confirm_symptom": "बस पक्का करने के लिए, क्या आपको {symptom} है? हाँ या नहीं बोलिए।",
        "reassure_orange_urine": "पेशाब का रंग नारंगी या लाल होना इस दवा की वजह से होता है, यह सामान्य है। घबराइए मत, दवा जारी रखिए।",
        "reassure_mild_nausea": "दवा से थोड़ा जी मिचलाना आम है। दवा खाना खाने के बाद लेकर देखिए। अगर उल्टी बार बार हो, तो हमें ज़रूर बताइए।",
        "reassure_tiredness": "शुरुआत में थोड़ी थकान होना आम है। आराम कीजिए और दवा जारी रखिए।",
        "complete_course": "आप बेहतर महसूस कर रहे हैं, यह अच्छी बात है! लेकिन टीबी की दवा का पूरा कोर्स लेना ज़रूरी है, नहीं तो बीमारी वापस आ सकती है और दवा असर करना बंद कर सकती है। आपकी स्वास्थ्य कार्यकर्ता आपसे बात करेंगी।",
        "missed_ack": "ठीक है, मैंने नोट कर लिया है। आपकी स्वास्थ्य कार्यकर्ता आपसे बात करेंगी।",
        "unclear_close": "कोई बात नहीं। आपकी स्वास्थ्य कार्यकर्ता आज आपसे बात करेंगी।",
        "symptom_ack": "ठीक है, मैंने आपकी तकलीफ़ नोट कर ली है। आपकी स्वास्थ्य कार्यकर्ता आज आपसे बात करेंगी। दवा जारी रखिए।",
        "red_advice": "मैंने यह बात आपकी स्वास्थ्य कार्यकर्ता को बता दी है, वो आज ही आपसे संपर्क करेंगी। अगर हालत ज़्यादा ख़राब लगे, तो तुरंत नज़दीकी अस्पताल जाइए या एक सौ आठ पर कॉल कीजिए।",
        "thanks": "बहुत अच्छे! धन्यवाद, कल फिर इसी समय बात करेंगे।",
        "family_check": "नमस्ते, मैं खुराक, {name} जी के स्वास्थ्य केंद्र से बोल रही हूँ। हम दो बार कोशिश करके भी उनसे बात नहीं कर पाए। क्या वो ठीक हैं और अपनी दवा ले रहे हैं?",
        "family_close": "धन्यवाद। मैंने यह जानकारी स्वास्थ्य कार्यकर्ता को दे दी है, वो जल्द संपर्क करेंगी।",
    },
    "mr-IN": {
        "greeting": "नमस्कार {name}, मी खुराक बोलतेय, तुमच्या आरोग्य केंद्रातून.",
        "ask_dose": "आजची टीबीची गोळी घेतली का?",
        "followup_dose": "माफ करा, मला नीट समजलं नाही. आज गोळी घेतली का? हो किंवा नाही सांगा.",
        "ask_symptoms": "काही त्रास होतोय का? उलटी, पोटदुखी, किंवा डोळे पिवळे झालेत का?",
        "confirm_symptom": "खात्री करण्यासाठी विचारते, तुम्हाला {symptom} आहे का? हो किंवा नाही सांगा.",
        "reassure_orange_urine": "लघवी नारिंगी किंवा लाल दिसणं हे या औषधामुळे होतं, हे सामान्य आहे. घाबरू नका, गोळ्या चालू ठेवा.",
        "reassure_mild_nausea": "औषधामुळे थोडं मळमळणं सामान्य आहे. जेवणानंतर गोळी घेऊन बघा. वारंवार उलटी झाली तर नक्की सांगा.",
        "reassure_tiredness": "सुरुवातीला थोडा थकवा येणं सामान्य आहे. आराम करा आणि गोळ्या चालू ठेवा.",
        "complete_course": "तुम्हाला बरं वाटतंय हे छान आहे! पण टीबीच्या गोळ्यांचा पूर्ण कोर्स घेणं गरजेचं आहे, नाहीतर आजार परत येऊ शकतो. तुमची आरोग्य सेविका तुमच्याशी बोलेल.",
        "missed_ack": "ठीक आहे, मी नोंद केली आहे. तुमची आरोग्य सेविका तुमच्याशी बोलेल.",
        "unclear_close": "काही हरकत नाही. तुमची आरोग्य सेविका आज तुमच्याशी बोलेल.",
        "symptom_ack": "ठीक आहे, मी तुमचा त्रास नोंदवला आहे. तुमची आरोग्य सेविका आज तुमच्याशी बोलेल. गोळ्या चालू ठेवा.",
        "red_advice": "मी हे तुमच्या आरोग्य सेविकेला कळवलं आहे, त्या आजच तुमच्याशी संपर्क करतील. तब्येत जास्त बिघडल्यास लगेच जवळच्या रुग्णालयात जा किंवा एकशे आठ वर फोन करा.",
        "thanks": "छान! धन्यवाद, उद्या याच वेळी पुन्हा बोलू.",
        "family_check": "नमस्कार, मी खुराक, {name} यांच्या आरोग्य केंद्रातून बोलतेय. दोन वेळा प्रयत्न करूनही त्यांच्याशी बोलणं झालं नाही. ते ठीक आहेत का आणि गोळ्या घेत आहेत का?",
        "family_close": "धन्यवाद. मी ही माहिती आरोग्य सेविकेला दिली आहे, त्या लवकरच संपर्क करतील.",
    },
    "bn-IN": {
        "greeting": "নমস্কার {name}, আমি খুরাক বলছি, আপনার স্বাস্থ্যকেন্দ্র থেকে।",
        "ask_dose": "আজকের টিবির ওষুধ খেয়েছেন কি?",
        "followup_dose": "দুঃখিত, আমি ঠিক বুঝতে পারিনি। আজ ওষুধ খেয়েছেন? হ্যাঁ বা না বলুন।",
        "ask_symptoms": "কোনো অসুবিধা হচ্ছে কি? যেমন বমি, পেটব্যথা, বা চোখ হলুদ হয়ে যাওয়া?",
        "confirm_symptom": "নিশ্চিত হওয়ার জন্য জিজ্ঞেস করছি, আপনার কি {symptom} হচ্ছে? হ্যাঁ বা না বলুন।",
        "reassure_orange_urine": "এই ওষুধের জন্য প্রস্রাবের রং কমলা বা লাল হতে পারে, এটা স্বাভাবিক। ভয় পাবেন না, ওষুধ চালিয়ে যান।",
        "reassure_mild_nausea": "ওষুধে একটু গা গোলানো স্বাভাবিক। খাবারের পরে ওষুধ খেয়ে দেখুন। বারবার বমি হলে আমাদের অবশ্যই জানাবেন।",
        "reassure_tiredness": "শুরুতে একটু ক্লান্তি স্বাভাবিক। বিশ্রাম নিন আর ওষুধ চালিয়ে যান।",
        "complete_course": "আপনি ভালো বোধ করছেন, এটা খুব ভালো কথা! কিন্তু টিবির ওষুধের পুরো কোর্স শেষ করা জরুরি, না হলে রোগ ফিরে আসতে পারে আর ওষুধ কাজ করা বন্ধ করে দিতে পারে। আপনার স্বাস্থ্যকর্মী আপনার সাথে কথা বলবেন।",
        "missed_ack": "ঠিক আছে, আমি লিখে রেখেছি। আপনার স্বাস্থ্যকর্মী আপনার সাথে কথা বলবেন।",
        "unclear_close": "কোনো অসুবিধা নেই। আপনার স্বাস্থ্যকর্মী আজ আপনার সাথে কথা বলবেন।",
        "symptom_ack": "ঠিক আছে, আমি আপনার অসুবিধার কথা লিখে রেখেছি। আপনার স্বাস্থ্যকর্মী আজ আপনার সাথে কথা বলবেন। ওষুধ চালিয়ে যান।",
        "red_advice": "আমি এটা আপনার স্বাস্থ্যকর্মীকে জানিয়ে দিয়েছি, উনি আজই আপনার সাথে যোগাযোগ করবেন। শরীর বেশি খারাপ লাগলে এখনই কাছের হাসপাতালে যান বা একশো আট নম্বরে ফোন করুন।",
        "thanks": "খুব ভালো! ধন্যবাদ, কাল আবার এই সময়ে কথা হবে।",
        "family_check": "নমস্কার, আমি খুরাক, {name}-এর স্বাস্থ্যকেন্দ্র থেকে বলছি। দুবার চেষ্টা করেও ওনার সাথে কথা বলা যায়নি। উনি কি ঠিক আছেন আর ওষুধ খাচ্ছেন?",
        "family_close": "ধন্যবাদ। আমি এই খবর স্বাস্থ্যকর্মীকে জানিয়ে দিয়েছি, উনি শিগগিরই যোগাযোগ করবেন।",
    },
    "kn-IN": {
        "greeting": "ನಮಸ್ಕಾರ {name} ಅವರೇ, ನಾನು ಖುರಾಕ್, ನಿಮ್ಮ ಆರೋಗ್ಯ ಕೇಂದ್ರದಿಂದ ಕರೆ ಮಾಡುತ್ತಿದ್ದೇನೆ.",
        "ask_dose": "ಇವತ್ತಿನ ಟಿಬಿ ಮಾತ್ರೆ ತೆಗೆದುಕೊಂಡಿರಾ?",
        "followup_dose": "ಕ್ಷಮಿಸಿ, ನನಗೆ ಸರಿಯಾಗಿ ಅರ್ಥವಾಗಲಿಲ್ಲ. ಇವತ್ತು ಮಾತ್ರೆ ತೆಗೆದುಕೊಂಡಿರಾ? ಹೌದು ಅಥವಾ ಇಲ್ಲ ಎಂದು ಹೇಳಿ.",
        "ask_symptoms": "ಏನಾದರೂ ತೊಂದರೆ ಇದೆಯಾ? ವಾಂತಿ, ಹೊಟ್ಟೆ ನೋವು, ಅಥವಾ ಕಣ್ಣು ಹಳದಿ ಆಗಿದೆಯಾ?",
        "confirm_symptom": "ಖಚಿತಪಡಿಸಿಕೊಳ್ಳಲು ಕೇಳುತ್ತಿದ್ದೇನೆ, ನಿಮಗೆ {symptom} ಇದೆಯಾ? ಹೌದು ಅಥವಾ ಇಲ್ಲ ಎಂದು ಹೇಳಿ.",
        "reassure_orange_urine": "ಮೂತ್ರ ಕಿತ್ತಳೆ ಅಥವಾ ಕೆಂಪು ಬಣ್ಣಕ್ಕೆ ತಿರುಗುವುದು ಈ ಮಾತ್ರೆಯಿಂದ ಆಗುತ್ತದೆ, ಇದು ಸಾಮಾನ್ಯ. ಗಾಬರಿಯಾಗಬೇಡಿ, ಮಾತ್ರೆ ಮುಂದುವರಿಸಿ.",
        "reassure_mild_nausea": "ಮಾತ್ರೆಯಿಂದ ಸ್ವಲ್ಪ ವಾಕರಿಕೆ ಸಾಮಾನ್ಯ. ಊಟದ ನಂತರ ಮಾತ್ರೆ ತೆಗೆದುಕೊಳ್ಳಿ. ಪದೇ ಪದೇ ವಾಂತಿ ಆದರೆ ತಿಳಿಸಿ.",
        "reassure_tiredness": "ಆರಂಭದಲ್ಲಿ ಸ್ವಲ್ಪ ಸುಸ್ತು ಸಾಮಾನ್ಯ. ವಿಶ್ರಾಂತಿ ತೆಗೆದುಕೊಳ್ಳಿ, ಮಾತ್ರೆ ಮುಂದುವರಿಸಿ.",
        "complete_course": "ನಿಮಗೆ ಹುಷಾರಾಗಿರುವುದು ಸಂತೋಷ! ಆದರೆ ಟಿಬಿ ಮಾತ್ರೆಯ ಪೂರ್ತಿ ಕೋರ್ಸ್ ಮುಗಿಸುವುದು ಅಗತ್ಯ, ಇಲ್ಲದಿದ್ದರೆ ಕಾಯಿಲೆ ಮತ್ತೆ ಬರಬಹುದು. ನಿಮ್ಮ ಆರೋಗ್ಯ ಕಾರ್ಯಕರ್ತೆ ನಿಮ್ಮೊಂದಿಗೆ ಮಾತನಾಡುತ್ತಾರೆ.",
        "missed_ack": "ಸರಿ, ನಾನು ಇದನ್ನು ದಾಖಲಿಸಿದ್ದೇನೆ. ನಿಮ್ಮ ಆರೋಗ್ಯ ಕಾರ್ಯಕರ್ತೆ ನಿಮ್ಮೊಂದಿಗೆ ಮಾತನಾಡುತ್ತಾರೆ.",
        "unclear_close": "ಪರವಾಗಿಲ್ಲ. ನಿಮ್ಮ ಆರೋಗ್ಯ ಕಾರ್ಯಕರ್ತೆ ಇವತ್ತು ನಿಮ್ಮೊಂದಿಗೆ ಮಾತನಾಡುತ್ತಾರೆ.",
        "symptom_ack": "ಸರಿ, ನಿಮ್ಮ ತೊಂದರೆಯನ್ನು ದಾಖಲಿಸಿದ್ದೇನೆ. ನಿಮ್ಮ ಆರೋಗ್ಯ ಕಾರ್ಯಕರ್ತೆ ಇವತ್ತು ನಿಮ್ಮೊಂದಿಗೆ ಮಾತನಾಡುತ್ತಾರೆ. ಮಾತ್ರೆ ಮುಂದುವರಿಸಿ.",
        "red_advice": "ನಾನು ಇದನ್ನು ನಿಮ್ಮ ಆರೋಗ್ಯ ಕಾರ್ಯಕರ್ತೆಗೆ ತಿಳಿಸಿದ್ದೇನೆ, ಅವರು ಇವತ್ತೇ ನಿಮ್ಮನ್ನು ಸಂಪರ್ಕಿಸುತ್ತಾರೆ. ತುಂಬಾ ಹುಷಾರಿಲ್ಲದಿದ್ದರೆ ತಕ್ಷಣ ಹತ್ತಿರದ ಆಸ್ಪತ್ರೆಗೆ ಹೋಗಿ ಅಥವಾ ನೂರ ಎಂಟಕ್ಕೆ ಕರೆ ಮಾಡಿ.",
        "thanks": "ಧನ್ಯವಾದಗಳು, ನಾಳೆ ಇದೇ ಸಮಯಕ್ಕೆ ಮತ್ತೆ ಮಾತನಾಡೋಣ.",
        "family_check": "ನಮಸ್ಕಾರ, ನಾನು ಖುರಾಕ್, {name} ಅವರ ಆರೋಗ್ಯ ಕೇಂದ್ರದಿಂದ ಮಾತನಾಡುತ್ತಿದ್ದೇನೆ. ಎರಡು ಬಾರಿ ಪ್ರಯತ್ನಿಸಿದರೂ ಅವರೊಂದಿಗೆ ಮಾತನಾಡಲು ಆಗಲಿಲ್ಲ. ಅವರು ಚೆನ್ನಾಗಿದ್ದಾರಾ, ಮಾತ್ರೆ ತೆಗೆದುಕೊಳ್ಳುತ್ತಿದ್ದಾರಾ?",
        "family_close": "ಧನ್ಯವಾದಗಳು. ಈ ಮಾಹಿತಿಯನ್ನು ಆರೋಗ್ಯ ಕಾರ್ಯಕರ್ತೆಗೆ ತಿಳಿಸಿದ್ದೇನೆ, ಅವರು ಬೇಗ ಸಂಪರ್ಕಿಸುತ್ತಾರೆ.",
    },
}

# How each red-flag symptom is named inside `confirm_symptom`.
SYMPTOM_NAMES: dict[str, dict[str, str]] = {
    "hi-IN": {
        "yellow_eyes": "आँखों या त्वचा में पीलापन", "blood_cough": "खांसी में खून",
        "persistent_vomit": "बार बार उल्टी", "breathless": "सांस फूलना",
        "vision": "धुंधला दिखना", "rash": "शरीर पर दाने या खुजली",
    },
    "mr-IN": {
        "yellow_eyes": "डोळे किंवा त्वचा पिवळी", "blood_cough": "खोकल्यातून रक्त",
        "persistent_vomit": "वारंवार उलटी", "breathless": "दम लागणं",
        "vision": "धूसर दिसणं", "rash": "अंगावर पुरळ किंवा खाज",
    },
    "bn-IN": {
        "yellow_eyes": "চোখ বা চামড়া হলুদ", "blood_cough": "কাশির সাথে রক্ত",
        "persistent_vomit": "বারবার বমি", "breathless": "শ্বাসকষ্ট",
        "vision": "ঝাপসা দেখা", "rash": "গায়ে র‍্যাশ বা চুলকানি",
    },
    "kn-IN": {
        "yellow_eyes": "ಕಣ್ಣು ಅಥವಾ ಚರ್ಮ ಹಳದಿ", "blood_cough": "ಕೆಮ್ಮಿನಲ್ಲಿ ರಕ್ತ",
        "persistent_vomit": "ಪದೇ ಪದೇ ವಾಂತಿ", "breathless": "ಉಸಿರಾಟದ ತೊಂದರೆ",
        "vision": "ಮಸುಕಾದ ದೃಷ್ಟಿ", "rash": "ಚರ್ಮದ ಮೇಲೆ ಗುಳ್ಳೆ ಅಥವಾ ತುರಿಕೆ",
    },
}

# English glosses so the dashboard / video can subtitle every line.
ENGLISH: dict[str, str] = {
    "greeting": "Hello {name}, this is Khurak calling from your health centre.",
    "ask_dose": "Did you take today's TB medicine?",
    "followup_dose": "Sorry, I didn't quite understand. Did you take your medicine today? Please say yes or no.",
    "ask_symptoms": "Any problems? Like vomiting, stomach pain, or yellowness in the eyes?",
    "confirm_symptom": "Just to confirm, do you have {symptom}? Please say yes or no.",
    "reassure_orange_urine": "Orange or red urine is caused by this medicine. It is normal. Don't worry, keep taking it.",
    "reassure_mild_nausea": "Mild nausea is common. Try taking the tablets after food. If you vomit repeatedly, tell us.",
    "reassure_tiredness": "Some tiredness early on is common. Rest and keep taking the medicine.",
    "complete_course": "Great that you feel better! But completing the full TB course is essential, or the disease can come back and the medicine can stop working. Your health worker will talk to you.",
    "missed_ack": "Okay, I've noted it. Your health worker will talk to you.",
    "unclear_close": "No problem. Your health worker will talk to you today.",
    "symptom_ack": "Okay, I've noted your problem. Your health worker will talk to you today. Please continue the medicine.",
    "red_advice": "I've informed your health worker; she will contact you today. If you feel much worse, go to the nearest hospital or call 108 immediately.",
    "thanks": "Very good! Thank you, we'll talk again tomorrow at the same time.",
    "family_check": "Hello, this is Khurak from {name}'s health centre. We couldn't reach them after two tries. Are they okay and taking their medicine?",
    "family_close": "Thank you. I've passed this to the health worker; she will contact you soon.",
}

SYMPTOM_EN = {
    "yellow_eyes": "yellow eyes or skin", "blood_cough": "blood in cough",
    "persistent_vomit": "repeated vomiting", "breathless": "breathlessness",
    "vision": "blurred vision", "rash": "rash or itching",
    "orange_urine": "orange/red urine", "mild_nausea": "mild nausea", "tiredness": "tiredness",
}

# Templates that contain per-patient variables are rendered per patient.
PERSONALISED = {"greeting", "family_check"}


def render(key: str, lang: str, **vars) -> str:
    pl = prompt_lang(lang)
    text = TEMPLATES[pl][key]
    if "{symptom}" in text and "symptom" in vars:
        vars = {**vars, "symptom": SYMPTOM_NAMES[pl].get(vars["symptom"], vars["symptom"])}
    return text.format(**vars)


def render_en(key: str, **vars) -> str:
    if "symptom" in vars:
        vars = {**vars, "symptom": SYMPTOM_EN.get(vars["symptom"], vars["symptom"])}
    return ENGLISH[key].format(**vars)


def all_static() -> list[tuple[str, str, str]]:
    """(lang, key, text) for every non-personalised template, for pre-generation."""
    out = []
    for lang, table in TEMPLATES.items():
        for key, text in table.items():
            if key in PERSONALISED or "{symptom}" in text:
                continue
            out.append((lang, key, text))
        for sym in SYMPTOM_NAMES[lang]:
            out.append((lang, f"confirm_symptom:{sym}", render("confirm_symptom", lang, symptom=sym)))
    return out
