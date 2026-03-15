# main.py
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
import uuid
import random
import os
import logging
import json
from datetime import datetime
from typing import Dict, List, Optional
import hashlib
import secrets

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('storyauth.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==================== МОДЕЛИ ДАННЫХ ====================

class UserRegistrationRequest:
    def __init__(self, user_id: str, personal_names: List[str] = None, card_number: str = ""):
        self.user_id = user_id
        self.personal_names = personal_names or []
        self.card_number = card_number

class StoryResponse:
    def __init__(self, story_id: int, story_text: str, template_id: int, story_data: Dict = None):
        self.story_id = story_id
        self.story_text = story_text
        self.template_id = template_id
        self.story_data = story_data or {}

class VerificationQuestion:
    def __init__(self, question_id: int, question_text: str, category: str, session_token: str):
        self.question_id = question_id
        self.question_text = question_text
        self.category = category
        self.session_token = session_token

class VerificationAnswer:
    def __init__(self, answer_text: str, session_token: str):
        self.answer_text = answer_text
        self.session_token = session_token

class VerificationResult:
    def __init__(self, success: bool, message: str):
        self.success = success
        self.message = message

class EditStoryRequest:
    def __init__(self, user_id: str, element: str, new_value: str):
        self.user_id = user_id
        self.element = element
        self.new_value = new_value

class SecureStoryStorage:
    def __init__(self, user_id: str, card_number: str = ""):
        self.user_id = user_id
        self.salt = secrets.token_hex(16)
        self.template_id: Optional[int] = None
        self.story_data: Dict = {}
        self.verification_hashes: Dict[str, str] = {}
        self.created_at = datetime.now().isoformat()
        self.updated_at = self.created_at
        self.is_blocked = False
        self.blocked_reason = ""
        self.card_number = card_number if card_number else self._generate_card_number()
        self.save_attempts = 0
        self.reminder_attempts = 0
        self.reminder_fails = 0
        self.is_saved = False  # Флаг сохранения истории
        
    def _generate_card_number(self):
        return ''.join([str(random.randint(0, 9)) for _ in range(6)])
        
    def set_story_data(self, template_id: int, story_data: Dict):
        self.template_id = template_id
        self.story_data = story_data
        self.updated_at = datetime.now().isoformat()
        self._generate_hashes()
        self._save_to_json()
    
    def _generate_hashes(self):
        self.verification_hashes = {}
        correct_answers = self.get_correct_answers()
        
        for key, value in correct_answers.items():
            hashed = hashlib.sha256((str(value) + self.salt).encode()).hexdigest()
            self.verification_hashes[key] = hashed
    
    def get_correct_answers(self) -> Dict[str, str]:
        answers = {}
        
        for i, name in enumerate(self.story_data.get("names", [])):
            if f"imya_{i}" in self.story_data.get("custom", {}):
                answers[f"imya_{i}"] = self.story_data["custom"][f"imya_{i}"]
            else:
                answers[f"imya_{i}"] = name
        
        if "personag" in self.story_data["elements"]:
            if "personag" in self.story_data.get("custom", {}):
                answers["personag"] = self.story_data["custom"]["personag"]
            else:
                answers["personag"] = self.story_data["elements"]["personag"]["data"]["text"]
        
        if "deystvie" in self.story_data["elements"]:
            if "deystvie" in self.story_data.get("custom", {}):
                answers["deystvie"] = self.story_data["custom"]["deystvie"]
            else:
                if "personag" in self.story_data["elements"]:
                    rod = self.story_data["elements"]["personag"]["data"]["rod"]
                    answers["deystvie"] = self.story_data["elements"]["deystvie"]["data"][rod]
        
        if "mesto" in self.story_data["elements"]:
            if "mesto" in self.story_data.get("custom", {}):
                answers["mesto"] = self.story_data["custom"]["mesto"]
            else:
                answers["mesto"] = self.story_data["elements"]["mesto"]["data"]["text"]
        
        if "pomosh" in self.story_data["elements"]:
            if "pomosh" in self.story_data.get("custom", {}):
                answers["pomosh"] = self.story_data["custom"]["pomosh"]
            else:
                answers["pomosh"] = self.story_data["elements"]["pomosh"]["data"]["text"]
        
        if "predmet" in self.story_data["elements"]:
            if "predmet" in self.story_data.get("custom", {}):
                answers["predmet"] = self.story_data["custom"]["predmet"]
            else:
                answers["predmet"] = self.story_data["elements"]["predmet"]["data"]["text"]
        
        return answers
    
    def verify_answer(self, category: str, answer: str) -> bool:
        if category not in self.verification_hashes:
            return False
        hashed = hashlib.sha256((answer + self.salt).encode()).hexdigest()
        return hashed == self.verification_hashes[category]
    
    def get_correct_answer_text(self, category: str) -> str:
        """Возвращает правильный ответ для логирования"""
        if category in self.story_data.get("custom", {}):
            return self.story_data["custom"][category]
        elif category == "personag":
            return self.story_data["elements"]["personag"]["data"]["text"]
        elif category.startswith("imya_"):
            idx = int(category.split("_")[1])
            if idx < len(self.story_data.get("names", [])):
                return self.story_data["names"][idx]
        elif category == "deystvie":
            if "personag" in self.story_data["elements"]:
                rod = self.story_data["elements"]["personag"]["data"]["rod"]
                return self.story_data["elements"]["deystvie"]["data"][rod]
        elif category == "mesto":
            return self.story_data["elements"]["mesto"]["data"]["text"]
        elif category == "pomosh":
            return self.story_data["elements"]["pomosh"]["data"]["text"]
        elif category == "predmet":
            return self.story_data["elements"]["predmet"]["data"]["text"]
        return "?"
    
    def _save_to_json(self):
        os.makedirs("data", exist_ok=True)
        
        data = {
            "user_id": self.user_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "template_id": self.template_id,
            "story_text": self.story_data.get("full_text", ""),
            "story_data": self.story_data,
            "correct_answers": self.get_correct_answers(),
            "hashes": self.verification_hashes,
            "is_blocked": self.is_blocked,
            "blocked_reason": self.blocked_reason,
            "card_number": self.card_number,
            "is_saved": self.is_saved
        }
        
        filename = f"data/user_{self.user_id}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"💾 Данные сохранены в {filename}")
    
    def to_dict(self):
        return {
            "user_id": self.user_id,
            "story_text": self.story_data.get("full_text", ""),
            "correct_answers": self.get_correct_answers(),
            "hashes": self.verification_hashes,
            "custom": self.story_data.get("custom", {}),
            "is_blocked": self.is_blocked,
            "blocked_reason": self.blocked_reason,
            "card_number": self.card_number,
            "is_saved": self.is_saved
        }

# ==================== КОНФИГУРАЦИЯ ====================

PERSONAGI = {
    1: {"text": "мудрый старик", "rod": "m", "name": "старик"},
    2: {"text": "добрая старушка", "rod": "f", "name": "старушка"},
    3: {"text": "смелый мальчик", "rod": "m", "name": "мальчик"},
    4: {"text": "веселая девочка", "rod": "f", "name": "девочка"},
    5: {"text": "отважный рыцарь", "rod": "m", "name": "рыцарь"},
    6: {"text": "прекрасная принцесса", "rod": "f", "name": "принцесса"},
    7: {"text": "хитрый кот", "rod": "m", "name": "кот"},
    8: {"text": "умная сова", "rod": "f", "name": "сова"},
    9: {"text": "сильный медведь", "rod": "m", "name": "медведь"},
    10: {"text": "добрая фея", "rod": "f", "name": "фея"},
}

DEYSTVIYA = {
    1: {"m": "отправился", "f": "отправилась", "text": "отправился"},
    2: {"m": "пошел", "f": "пошла", "text": "пошел"},
    3: {"m": "решил", "f": "решила", "text": "решил"},
    4: {"m": "захотел", "f": "захотела", "text": "захотел"},
    5: {"m": "побежал", "f": "побежала", "text": "побежал"},
    6: {"m": "полетел", "f": "полетела", "text": "полетел"},
}

MESTA = {
    1: {"text": "в дремучий лес", "short": "лес"},
    2: {"text": "на высокую гору", "short": "гору"},
    3: {"text": "в синее море", "short": "море"},
    4: {"text": "в темную пещеру", "short": "пещеру"},
    5: {"text": "в старый замок", "short": "замок"},
    6: {"text": "в волшебный лес", "short": "лес"},
}

POMOCHNIKI = {
    1: {"text": "фея-крестная", "rod": "f"},
    2: {"text": "мудрый волшебник", "rod": "m"},
    3: {"text": "добрый гном", "rod": "m"},
    4: {"text": "золотая рыбка", "rod": "f"},
    5: {"text": "старый филин", "rod": "m"},
}

PREDMETY = {
    1: {"text": "волшебную палочку", "short": "палочку"},
    2: {"text": "золотой ключик", "short": "ключик"},
    3: {"text": "ковер-самолет", "short": "ковер"},
    4: {"text": "живую воду", "short": "воду"},
    5: {"text": "молодильное яблоко", "short": "яблоко"},
}

STORY_TEMPLATES = {
    1: {
        "name": "Волшебное приключение",
        "template": [
            ("personag", None),
            ("imya", None),
            ("deystvie", None),
            ("mesto", None),
            ("pomosh", None),
            ("predmet", None),
        ],
        "text": "{imya_1} был {personag}. Однажды он {deystvie} {mesto}. "
                "Там встретил {pomosh}, который подарил {predmet}. "
                "С этим подарком случилось чудо."
    },
    2: {
        "name": "Сказочное путешествие",
        "template": [
            ("personag", None),
            ("imya", None),
            ("deystvie", None),
            ("mesto", None),
            ("pomosh", None),
            ("predmet", None),
        ],
        "text": "{imya_1} была {personag}. Однажды она {deystvie} {mesto}. "
                "Там встретила {pomosh}, которая подарила {predmet}. "
                "Жизнь изменилась к лучшему."
    },
    3: {
        "name": "Друзья",
        "template": [
            ("personag", None),
            ("imya", None),
            ("imya", None),
            ("deystvie", None),
            ("mesto", None),
            ("pomosh", None),
        ],
        "text": "{imya_1} был {personag}. У него был друг {imya_2}. "
                "Они {deystvie} {mesto}. Там им помог {pomosh}. "
                "С тех пор они не расставались."
    }
}

# ==================== ГЕНЕРАТОР ИСТОРИЙ ====================

class StoryGenerator:
    def __init__(self):
        self.templates = STORY_TEMPLATES
        self.personagi = PERSONAGI
        self.deystviya = DEYSTVIYA
        self.mesta = MESTA
        self.pomoshniki = POMOCHNIKI
        self.predmety = PREDMETY
        
    def generate_story(self, user_id: str, personal_names: List[str]) -> tuple:
        template_id = random.choice(list(self.templates.keys()))
        template = self.templates[template_id]
        
        if not personal_names:
            personal_names = ["Герой"]
        
        story_data = {
            "template_id": template_id,
            "elements": {},
            "custom": {},
            "names": personal_names.copy()
        }
        
        personag_id = random.choice(list(self.personagi.keys()))
        story_data["elements"]["personag"] = {
            "id": personag_id,
            "data": self.personagi[personag_id]
        }
        
        deystvie_id = random.choice(list(self.deystviya.keys()))
        story_data["elements"]["deystvie"] = {
            "id": deystvie_id,
            "data": self.deystviya[deystvie_id]
        }
        
        mesto_id = random.choice(list(self.mesta.keys()))
        story_data["elements"]["mesto"] = {
            "id": mesto_id,
            "data": self.mesta[mesto_id]
        }
        
        pomosh_id = random.choice(list(self.pomoshniki.keys()))
        story_data["elements"]["pomosh"] = {
            "id": pomosh_id,
            "data": self.pomoshniki[pomosh_id]
        }
        
        predmet_id = random.choice(list(self.predmety.keys()))
        story_data["elements"]["predmet"] = {
            "id": predmet_id,
            "data": self.predmety[predmet_id]
        }
        
        for i, name in enumerate(story_data["names"]):
            story_data["elements"][f"imya_{i}"] = name
        
        story_text = self._build_story_text(template, story_data)
        story_data["full_text"] = story_text
        
        return template_id, story_text, story_data
    
    def _build_story_text(self, template: Dict, story_data: Dict) -> str:
        replacements = {}
        
        if "personag" in story_data["elements"]:
            if "personag" in story_data.get("custom", {}):
                replacements["personag"] = story_data["custom"]["personag"]
            else:
                replacements["personag"] = story_data["elements"]["personag"]["data"]["text"]
        
        for i, name in enumerate(story_data.get("names", [])):
            key = f"imya_{i}"
            if key in story_data.get("custom", {}):
                replacements[f"imya_{i+1}"] = story_data["custom"][key]
            else:
                replacements[f"imya_{i+1}"] = name
            if i == 0:
                replacements["imya"] = replacements[f"imya_1"]
        
        if "deystvie" in story_data["elements"]:
            if "deystvie" in story_data.get("custom", {}):
                replacements["deystvie"] = story_data["custom"]["deystvie"]
            else:
                rod = story_data["elements"]["personag"]["data"]["rod"]
                replacements["deystvie"] = story_data["elements"]["deystvie"]["data"][rod]
        
        if "mesto" in story_data["elements"]:
            if "mesto" in story_data.get("custom", {}):
                replacements["mesto"] = story_data["custom"]["mesto"]
            else:
                replacements["mesto"] = story_data["elements"]["mesto"]["data"]["text"]
        
        if "pomosh" in story_data["elements"]:
            if "pomosh" in story_data.get("custom", {}):
                replacements["pomosh"] = story_data["custom"]["pomosh"]
            else:
                replacements["pomosh"] = story_data["elements"]["pomosh"]["data"]["text"]
        
        if "predmet" in story_data["elements"]:
            if "predmet" in story_data.get("custom", {}):
                replacements["predmet"] = story_data["custom"]["predmet"]
            else:
                replacements["predmet"] = story_data["elements"]["predmet"]["data"]["text"]
        
        try:
            return template["text"].format(**replacements)
        except KeyError:
            return f"История про {story_data['names'][0]}"
    
    def edit_story(self, story_data: Dict, element: str, new_value: str) -> Dict:
        if "custom" not in story_data:
            story_data["custom"] = {}
        story_data["custom"][element] = new_value
        
        template = self.templates[story_data["template_id"]]
        story_data["full_text"] = self._build_story_text(template, story_data)
        return story_data
    
    def get_question(self, story_data: Dict, last_category: str = None, exclude_categories: List[str] = None) -> tuple:
        exclude = exclude_categories or []
        
        available = []
        
        if "personag" in story_data["elements"] and "personag" not in exclude:
            available.append(("personag", "Кем был главный герой?"))
        
        for i in range(len(story_data.get("names", []))):
            key = f"imya_{i}"
            if key not in exclude:
                if i == 0:
                    available.append((key, "Как звали первого героя?"))
                else:
                    available.append((key, f"Как звали {i+1}-го героя?"))
        
        if "deystvie" in story_data["elements"] and "deystvie" not in exclude:
            available.append(("deystvie", "Что сделал герой?"))
        
        if "mesto" in story_data["elements"] and "mesto" not in exclude:
            available.append(("mesto", "Куда отправился герой?"))
        
        if "pomosh" in story_data["elements"] and "pomosh" not in exclude:
            available.append(("pomosh", "Кого встретил первый герой?"))
        
        if "predmet" in story_data["elements"] and "predmet" not in exclude:
            available.append(("predmet", "Что подарили герою?"))
        
        if not available:
            return "imya_0", "Как звали героя?"
        
        if last_category:
            available = [a for a in available if a[0] != last_category]
        
        if not available:
            return random.choice([("imya_0", "Как звали героя?")])
        
        return random.choice(available)

# ==================== ИНИЦИАЛИЗАЦИЯ ====================

generator = StoryGenerator()
user_stories: Dict[str, SecureStoryStorage] = {}
active_sessions: Dict[str, tuple] = {}
failed_attempts: Dict[str, int] = {}
last_question: Dict[str, str] = {}
save_sessions: Dict[str, Dict] = {}
reminder_sessions: Dict[str, Dict] = {}

# Загружаем сохраненные данные
os.makedirs("data", exist_ok=True)
for filename in os.listdir("data"):
    if filename.startswith("user_") and filename.endswith(".json"):
        try:
            with open(os.path.join("data", filename), "r", encoding="utf-8") as f:
                data = json.load(f)
                storage = SecureStoryStorage(data["user_id"], data.get("card_number", ""))
                storage.created_at = data["created_at"]
                storage.updated_at = data["updated_at"]
                storage.template_id = data["template_id"]
                storage.story_data = data["story_data"]
                storage.verification_hashes = data["hashes"]
                storage.is_blocked = data.get("is_blocked", False)
                storage.blocked_reason = data.get("blocked_reason", "")
                storage.card_number = data.get("card_number", storage._generate_card_number())
                storage.is_saved = data.get("is_saved", False)
                user_stories[data["user_id"]] = storage
                logger.info(f"📂 Загружены данные для {data['user_id']}")
        except Exception as e:
            logger.error(f"Ошибка загрузки {filename}: {e}")

# Создаем папку templates
os.makedirs("templates", exist_ok=True)

# HTML шаблон
html_content = '''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>StoryAuth - Безопасная аутентификация</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }

        body {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
        }

        h1 {
            color: white;
            text-align: center;
            margin-bottom: 30px;
            font-size: 2.5em;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.2);
        }

        .grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 20px;
        }

        .card {
            background: white;
            border-radius: 15px;
            padding: 20px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            transition: transform 0.3s ease;
        }

        .card:hover {
            transform: translateY(-5px);
        }

        .card-header {
            display: flex;
            align-items: center;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid #f0f0f0;
        }

        .step-icon {
            width: 35px;
            height: 35px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            margin-right: 10px;
        }

        .step-title {
            font-size: 1.1em;
            font-weight: 600;
            color: #333;
        }

        .input-group {
            margin-bottom: 10px;
        }

        input, select {
            width: 100%;
            padding: 10px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 14px;
        }

        input:focus, select:focus {
            outline: none;
            border-color: #667eea;
        }

        button {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            width: 100%;
            margin: 5px 0;
        }

        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
        }

        button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }

        .button-group {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
        }

        .log-box {
            background: #1e1e2f;
            color: #00ff88;
            padding: 15px;
            border-radius: 10px;
            font-family: 'Courier New', monospace;
            height: 300px;
            overflow-y: auto;
            font-size: 12px;
            line-height: 1.4;
        }

        .log-entry {
            margin: 3px 0;
            padding: 3px;
            border-left: 2px solid #00ff88;
        }

        .log-time {
            color: #888;
            margin-right: 8px;
        }

        .success {
            background: #d4edda;
            color: #155724;
            padding: 10px;
            border-radius: 5px;
            margin-top: 10px;
            font-size: 13px;
        }

        .error {
            background: #f8d7da;
            color: #721c24;
            padding: 10px;
            border-radius: 5px;
            margin-top: 10px;
            font-size: 13px;
        }

        .warning {
            background: #fff3cd;
            color: #856404;
            padding: 10px;
            border-radius: 5px;
            margin-top: 10px;
            font-size: 13px;
        }

        .counter {
            font-size: 36px;
            font-weight: bold;
            text-align: center;
            color: #dc3545;
        }

        .question-box {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 15px;
            border-radius: 8px;
            margin: 10px 0;
            font-size: 16px;
            text-align: center;
        }

        .blocked {
            background: #dc3545;
            color: white;
            padding: 10px;
            border-radius: 5px;
            text-align: center;
            font-weight: bold;
        }

        .card-number {
            font-size: 24px;
            font-weight: bold;
            text-align: center;
            color: #28a745;
            padding: 10px;
            background: #e8f5e9;
            border-radius: 8px;
            margin: 10px 0;
        }

        .modal {
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0,0,0,0.5);
        }

        .modal-content {
            background: white;
            margin: 15% auto;
            padding: 20px;
            border-radius: 15px;
            width: 400px;
            max-width: 90%;
            animation: slideIn 0.3s ease;
        }

        @keyframes slideIn {
            from { transform: translateY(-50px); opacity: 0; }
            to { transform: translateY(0); opacity: 1; }
        }

        pre {
            white-space: pre-wrap;
            word-wrap: break-word;
            background: #f8f9fa;
            padding: 10px;
            border-radius: 5px;
            font-size: 11px;
            max-height: 200px;
            overflow-y: auto;
        }

        @media (max-width: 1024px) {
            .grid {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>📖 StoryAuth - Безопасная аутентификация</h1>
        
        <!-- Модальное окно для ввода ответа -->
        <div id="answerModal" class="modal">
            <div class="modal-content">
                <h3 id="modalTitle">Ответ на вопрос</h3>
                <div id="modalQuestion" class="question-box"></div>
                <input type="text" id="modalAnswer" placeholder="Ваш ответ" style="margin:10px 0;">
                <input type="hidden" id="modalToken">
                <input type="hidden" id="modalType">
                <input type="hidden" id="modalUserId">
                <div class="button-group">
                    <button onclick="submitModalAnswer()" style="background:#28a745;">✅ Ответить</button>
                    <button onclick="closeModal()" style="background:#dc3545;">❌ Отмена</button>
                </div>
            </div>
        </div>
        
        <div class="grid">
            <!-- Колонка 1: Регистрация и создание -->
            <div>
                <div class="card">
                    <div class="card-header">
                        <div class="step-icon">1</div>
                        <div class="step-title">Регистрация</div>
                    </div>
                    <div class="input-group">
                        <input type="text" id="newUserId" placeholder="ID клиента" value="test_user">
                    </div>
                    <div class="input-group">
                        <input type="text" id="personalNames" placeholder="Имена (через запятую)" value="Маша, Петя">
                    </div>
                    <div class="input-group">
                        <input type="text" id="cardNumber" placeholder="Номер карты (6 цифр)" maxlength="6">
                    </div>
                    <button onclick="registerUser()">📝 Создать историю</button>
                    <div id="registerResult"></div>
                </div>

                <div class="card">
                    <div class="card-header">
                        <div class="step-icon">2</div>
                        <div class="step-title">Сохранение истории (3 верных ответа)</div>
                    </div>
                    <div class="input-group">
                        <input type="text" id="saveUserId" placeholder="ID клиента" value="test_user">
                    </div>
                    <div class="button-group">
                        <button onclick="startSaveStory()">💾 Начать сохранение</button>
                        <button onclick="cancelSave()" style="background:#dc3545;">❌ Отмена</button>
                    </div>
                    <div id="saveStatus"></div>
                </div>
            </div>

            <!-- Колонка 2: Верификация и номер карты -->
            <div>
                <div class="card">
                    <div class="card-header">
                        <div class="step-icon">3</div>
                        <div class="step-title">Верификация</div>
                    </div>
                    <div class="input-group">
                        <input type="text" id="userId" placeholder="ID клиента" value="test_user">
                    </div>
                    <button onclick="getQuestion()">❓ Получить вопрос</button>
                    <div id="questionDisplay" class="question-box"></div>
                    
                    <input type="hidden" id="sessionToken">
                    <input type="hidden" id="currentCategory">
                    <input type="hidden" id="currentUserId">
                    
                    <div class="input-group" style="margin-top:10px;">
                        <input type="text" id="answerInput" placeholder="Ответ">
                    </div>
                    <button onclick="verifyAnswer()">✅ Проверить</button>
                    <div id="resultArea"></div>
                </div>

                <div class="card">
                    <div class="card-header">
                        <div class="step-icon">4</div>
                        <div class="step-title">Получить номер карты</div>
                    </div>
                    <div class="input-group">
                        <input type="text" id="cardUserId" placeholder="ID клиента" value="test_user">
                    </div>
                    <button onclick="getCardNumber()">🎫 Получить номер</button>
                    <div id="cardDisplay" class="card-number"></div>
                </div>

                <div class="card">
                    <div class="card-header">
                        <div class="step-icon">⚠️</div>
                        <div class="step-title">Статус</div>
                    </div>
                    <div id="userStatus"></div>
                    <div class="counter" id="counterDisplay">0</div>
                </div>
            </div>

            <!-- Колонка 3: Управление и отладка -->
            <div>
                <div class="card">
                    <div class="card-header">
                        <div class="step-icon">5</div>
                        <div class="step-title">Редактирование</div>
                    </div>
                    <div class="input-group">
                        <select id="editElement">
                            <option value="personag">👤 Кем был герой</option>
                            <option value="imya_0">📝 Имя 1-го героя</option>
                            <option value="imya_1">📝 Имя 2-го героя</option>
                            <option value="deystvie">🏃 Что сделал</option>
                            <option value="mesto">🗺️ Куда пошел</option>
                            <option value="pomosh">🧙 Кого встретил</option>
                            <option value="predmet">🎁 Что получил</option>
                        </select>
                    </div>
                    <div class="input-group">
                        <input type="text" id="editValue" placeholder="Новое значение">
                    </div>
                    <div class="input-group">
                        <input type="text" id="editUserId" placeholder="ID клиента" value="test_user">
                    </div>
                    <button onclick="editStory()">✏️ Применить</button>
                    <div id="editResult"></div>
                </div>

                <div class="card">
                    <div class="card-header">
                        <div class="step-icon">6</div>
                        <div class="step-title">Напоминание</div>
                    </div>
                    <div class="input-group">
                        <input type="text" id="remindUserId" placeholder="ID клиента" value="test_user">
                    </div>
                    <button onclick="startReminder()">🔔 Начать напоминание</button>
                    <div id="reminderStatus"></div>
                </div>

                <div class="card">
                    <div class="card-header">
                        <div class="step-icon">🔧</div>
                        <div class="step-title">Отладка</div>
                    </div>
                    <div class="input-group">
                        <input type="text" id="debugUserId" placeholder="ID клиента" value="test_user">
                    </div>
                    <div class="button-group">
                        <button onclick="debugStory()">📊 Показать данные</button>
                        <button onclick="clearDebug()" style="background:#6c757d;">🗑️ Очистить</button>
                    </div>
                    <div id="debugResult"></div>
                </div>

                <div class="card">
                    <div class="card-header">
                        <div class="step-icon">📋</div>
                        <div class="step-title">Лог событий</div>
                    </div>
                    <div id="logBox" class="log-box"></div>
                </div>
            </div>
        </div>
    </div>

    <script>
        let logBox = document.getElementById('logBox');
        
        function addToLog(message, type = 'info') {
            const timestamp = new Date().toLocaleTimeString();
            const entry = document.createElement('div');
            entry.className = 'log-entry';
            entry.innerHTML = '<span class="log-time">[' + timestamp + ']</span> ' + message;
            logBox.appendChild(entry);
            logBox.scrollTop = logBox.scrollHeight;
        }

        function showModal(title, question, token, type, userId) {
            document.getElementById('modalTitle').innerHTML = title;
            document.getElementById('modalQuestion').innerHTML = question;
            document.getElementById('modalToken').value = token;
            document.getElementById('modalType').value = type;
            document.getElementById('modalUserId').value = userId;
            document.getElementById('modalAnswer').value = '';
            document.getElementById('answerModal').style.display = 'block';
        }

        function closeModal() {
            document.getElementById('answerModal').style.display = 'none';
        }

        function checkBlocked(userId, callback) {
            fetch('/check-blocked/' + encodeURIComponent(userId))
                .then(r => r.json())
                .then(data => {
                    if (data.blocked) {
                        addToLog('⛔ Пользователь заблокирован: ' + data.reason, 'error');
                        alert('Пользователь заблокирован: ' + data.reason);
                        return false;
                    }
                    callback();
                });
        }

        async function registerUser() {
            const userId = document.getElementById('newUserId').value;
            const namesStr = document.getElementById('personalNames').value;
            const cardNumber = document.getElementById('cardNumber').value;
            const personalNames = namesStr.split(',').map(s => s.trim()).filter(s => s);
            
            try {
                const response = await fetch('/register', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        user_id: userId, 
                        personal_names: personalNames,
                        card_number: cardNumber
                    })
                });
                
                const data = await response.json();
                
                if (!response.ok) {
                    throw new Error(data.detail || 'Ошибка');
                }
                
                addToLog('✅ Зарегистрирован: ' + userId, 'success');
                document.getElementById('registerResult').innerHTML = 
                    '<div class="success">📖 ' + data.story_text + '<br>🎫 Номер: ' + data.card_number + '</div>';
                
            } catch (error) {
                addToLog('❌ ' + error.message, 'error');
                document.getElementById('registerResult').innerHTML = 
                    '<div class="error">❌ ' + error.message + '</div>';
            }
        }

        async function startSaveStory() {
            const userId = document.getElementById('saveUserId').value;
            
            const response = await fetch('/start-save/' + encodeURIComponent(userId));
            const data = await response.json();
            
            if (data.error) {
                alert(data.error);
                return;
            }
            
            document.getElementById('saveStatus').innerHTML = 
                '<div class="warning">❓ Осталось вопросов: ' + data.remaining + '</div>';
            
            showModal('Сохранение истории', data.question, data.token, 'save', userId);
        }

        async function submitModalAnswer() {
            const token = document.getElementById('modalToken').value;
            const answer = document.getElementById('modalAnswer').value;
            const type = document.getElementById('modalType').value;
            const userId = document.getElementById('modalUserId').value;
            
            if (type === 'save') {
                const response = await fetch('/submit-save-answer', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({token: token, answer: answer})
                });
                
                const data = await response.json();
                closeModal();
                
                if (data.completed) {
                    document.getElementById('saveStatus').innerHTML = 
                        '<div class="success">✅ История сохранена!</div>';
                    addToLog('✅ История сохранена', 'success');
                } else if (data.error) {
                    document.getElementById('saveStatus').innerHTML = 
                        '<div class="error">❌ ' + data.error + '</div>';
                    addToLog('❌ Ошибка сохранения: ' + data.error, 'error');
                } else {
                    document.getElementById('saveStatus').innerHTML = 
                        '<div class="warning">❓ Осталось вопросов: ' + data.remaining + '</div>';
                    
                    if (data.question) {
                        showModal('Сохранение истории', data.question, data.new_token || token, 'save', userId);
                    }
                }
            } else if (type === 'card') {
                const response = await fetch('/verify-card-answer', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        user_id: userId,
                        answer: answer,
                        token: token
                    })
                });
                
                const data = await response.json();
                closeModal();
                
                if (data.success) {
                    document.getElementById('cardDisplay').innerHTML = '🎫 ' + data.card_number;
                    addToLog('✅ Номер карты получен: ' + data.card_number, 'success');
                } else {
                    document.getElementById('cardDisplay').innerHTML = '⛔ ОШИБКА';
                    addToLog('❌ Ошибка получения номера: ' + data.error, 'error');
                }
            } else if (type === 'reminder') {
                const response = await fetch('/verify-reminder', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        user_id: userId,
                        answer: answer,
                        token: token
                    })
                });
                
                const data = await response.json();
                closeModal();
                
                if (data.success) {
                    document.getElementById('reminderStatus').innerHTML = 
                        '<div class="success">✅ Напоминание успешно</div>';
                    addToLog('✅ Напоминание успешно', 'success');
                } else if (data.blocked) {
                    document.getElementById('reminderStatus').innerHTML = 
                        '<div class="error">⛔ ' + data.error + '</div>';
                    addToLog('⛔ Пользователь заблокирован', 'error');
                } else {
                    document.getElementById('reminderStatus').innerHTML = 
                        '<div class="warning">❌ Неверно. Осталось попыток: ' + data.remaining + '</div>';
                    
                    if (data.question) {
                        showModal('Напоминание', data.question, data.new_token || token, 'reminder', userId);
                    }
                }
            }
        }

        function cancelSave() {
            document.getElementById('saveStatus').innerHTML = '';
            addToLog('❌ Сохранение отменено', 'info');
        }

        async function getQuestion() {
            const userId = document.getElementById('userId').value;
            
            const response = await fetch('/request-question?user_id=' + encodeURIComponent(userId));
            const data = await response.json();
            
            if (data.error) {
                alert(data.error);
                return;
            }
            
            document.getElementById('questionDisplay').innerHTML = data.question_text;
            document.getElementById('sessionToken').value = data.session_token;
            document.getElementById('currentCategory').value = data.category;
            document.getElementById('currentUserId').value = userId;
            
            addToLog('❓ ' + data.question_text, 'question');
        }

        async function verifyAnswer() {
            const answer = document.getElementById('answerInput').value;
            const token = document.getElementById('sessionToken').value;
            const userId = document.getElementById('currentUserId').value;
            
            const response = await fetch('/verify', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({answer_text: answer, session_token: token})
            });
            
            const data = await response.json();
            
            if (data.success) {
                document.getElementById('resultArea').innerHTML = 
                    '<div class="success">✅ GREEN - Верно</div>';
                addToLog('✅ GREEN - Верно (ответ: ' + answer + ', правильный: ' + data.correct + ')', 'success');
            } else {
                document.getElementById('resultArea').innerHTML = 
                    '<div class="error">❌ RED - Неверно</div>';
                addToLog('❌ RED - Неверно (ответ: ' + answer + ', правильный: ' + data.correct + ')', 'error');
            }
            
            updateCounter(userId);
        }

        async function getCardNumber() {
            const userId = document.getElementById('cardUserId').value;
            
            const response = await fetch('/get-card-number/' + encodeURIComponent(userId));
            const data = await response.json();
            
            if (data.error) {
                document.getElementById('cardDisplay').innerHTML = '❌ ' + data.error;
            } else {
                document.getElementById('cardDisplay').innerHTML = '❓ Ожидание ответа';
                showModal('Получение номера карты', data.question, data.token, 'card', userId);
            }
        }

        async function startReminder() {
            const userId = document.getElementById('remindUserId').value;
            
            const response = await fetch('/start-reminder/' + encodeURIComponent(userId));
            const data = await response.json();
            
            if (data.error) {
                document.getElementById('reminderStatus').innerHTML = 
                    '<div class="error">❌ ' + data.error + '</div>';
            } else {
                document.getElementById('reminderStatus').innerHTML = 
                    '<div class="warning">❓ Напоминание...</div>';
                showModal('Напоминание', data.question, data.token, 'reminder', userId);
            }
        }

        async function editStory() {
            const userId = document.getElementById('editUserId').value;
            const element = document.getElementById('editElement').value;
            const value = document.getElementById('editValue').value;
            
            const response = await fetch('/edit-story', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({user_id: userId, element: element, new_value: value})
            });
            
            const data = await response.json();
            
            if (data.error) {
                document.getElementById('editResult').innerHTML = 
                    '<div class="error">❌ ' + data.error + '</div>';
            } else {
                document.getElementById('editResult').innerHTML = 
                    '<div class="success">📖 ' + data.story_text + '</div>';
                addToLog('✏️ История изменена', 'info');
            }
        }

        async function debugStory() {
            const userId = document.getElementById('debugUserId').value;
            
            const response = await fetch('/debug/' + encodeURIComponent(userId));
            const data = await response.json();
            
            if (data.error) {
                document.getElementById('debugResult').innerHTML = 
                    '<div class="error">❌ ' + data.error + '</div>';
            } else {
                document.getElementById('debugResult').innerHTML = 
                    '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
            }
        }

        function clearDebug() {
            document.getElementById('debugResult').innerHTML = '';
        }

        async function updateCounter(userId) {
            const response = await fetch('/get-failed-count/' + encodeURIComponent(userId));
            const data = await response.json();
            document.getElementById('counterDisplay').innerHTML = data.count;
            
            const statusResponse = await fetch('/check-blocked/' + encodeURIComponent(userId));
            const statusData = await statusResponse.json();
            
            if (statusData.blocked) {
                document.getElementById('userStatus').innerHTML = 
                    '<div class="blocked">⛔ ЗАБЛОКИРОВАН: ' + statusData.reason + '</div>';
            } else {
                document.getElementById('userStatus').innerHTML = '';
            }
        }
    </script>
</body>
</html>'''

with open("templates/operator.html", "w", encoding="utf-8") as f:
    f.write(html_content)

templates = Jinja2Templates(directory="templates")

# ==================== FASTAPI APP ====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("="*60)
    logger.info("🚀 СЕРВИС АУТЕНТИФИКАЦИИ ПО ИСТОРИЯМ ЗАПУЩЕН")
    logger.info("="*60)
    logger.info(f"📊 Доступно шаблонов: {len(generator.templates)}")
    logger.info(f"📁 Данные сохраняются в папку data/")
    logger.info("🌐 http://127.0.0.1:8000/operator.html")
    logger.info("="*60)
    yield
    logger.info("🛑 Сервис остановлен")

app = FastAPI(lifespan=lifespan)

@app.get("/operator.html", response_class=HTMLResponse)
async def operator_page(request: Request):
    return templates.TemplateResponse("operator.html", {"request": request})

@app.get("/")
async def root():
    return {"message": "StoryAuth работает", "url": "/operator.html"}

@app.post("/register")
async def register(request: Request):
    data = await request.json()
    user_id = data.get("user_id")
    personal_names = data.get("personal_names", [])
    card_number = data.get("card_number", "")
    
    if user_id in user_stories:
        raise HTTPException(400, "Пользователь с таким именем уже существует")
    
    template_id, story_text, story_data = generator.generate_story(user_id, personal_names)
    
    storage = SecureStoryStorage(user_id, card_number)
    storage.set_story_data(template_id, story_data)
    user_stories[user_id] = storage
    failed_attempts[user_id] = 0
    
    return {
        "story_id": template_id, 
        "story_text": story_text, 
        "template_id": template_id,
        "card_number": storage.card_number
    }

@app.get("/check-blocked/{user_id}")
async def check_blocked(user_id: str):
    if user_id not in user_stories:
        return {"blocked": False}
    storage = user_stories[user_id]
    return {"blocked": storage.is_blocked, "reason": storage.blocked_reason}

@app.get("/start-save/{user_id}")
async def start_save(user_id: str):
    if user_id not in user_stories:
        return {"error": "Пользователь не найден"}
    
    storage = user_stories[user_id]
    if storage.is_blocked:
        return {"error": f"Пользователь заблокирован: {storage.blocked_reason}"}
    
    if storage.is_saved:
        return {"error": "История уже сохранена"}
    
    token = str(uuid.uuid4())
    storage.save_attempts = 0
    asked = []
    
    category, question = generator.get_question(storage.story_data, exclude_categories=asked)
    asked.append(category)
    
    save_sessions[token] = {
        "user_id": user_id,
        "correct": 0,
        "asked": asked,
        "current_category": category
    }
    
    return {
        "token": token,
        "question": question,
        "category": category,
        "remaining": 3
    }

@app.post("/submit-save-answer")
async def submit_save_answer(request: Request):
    data = await request.json()
    token = data.get("token")
    answer = data.get("answer")
    
    if token not in save_sessions:
        return {"error": "Сессия истекла"}
    
    session = save_sessions[token]
    user_id = session["user_id"]
    storage = user_stories[user_id]
    category = session["current_category"]
    
    correct_answer = storage.get_correct_answer_text(category)
    is_correct = storage.verify_answer(category, answer)
    
    if is_correct:
        logger.info(f"✅ Сохранение: верный ответ на {category} ('{answer}')")
        session["correct"] += 1
        if session["correct"] >= 3:
            # История сохранена
            storage.is_saved = True
            storage._save_to_json()
            del save_sessions[token]
            return {"completed": True}
        else:
            # Следующий вопрос
            category, question = generator.get_question(
                storage.story_data, 
                exclude_categories=session["asked"]
            )
            session["asked"].append(category)
            session["current_category"] = category
            # Создаем новый токен для следующего вопроса
            new_token = str(uuid.uuid4())
            save_sessions[new_token] = session
            del save_sessions[token]
            return {
                "question": question,
                "category": category,
                "remaining": 3 - session["correct"],
                "completed": False,
                "new_token": new_token
            }
    else:
        logger.warning(f"❌ Сохранение: неверный ответ на {category} (ответ: '{answer}', правильный: '{correct_answer}')")
        del save_sessions[token]
        return {"error": f"Неверный ответ. Правильный: {correct_answer}"}

@app.post("/edit-story")
async def edit_story(request: Request):
    data = await request.json()
    user_id = data.get("user_id")
    element = data.get("element")
    new_value = data.get("new_value")
    
    if user_id not in user_stories:
        raise HTTPException(404, "Пользователь не найден")
    
    storage = user_stories[user_id]
    if storage.is_blocked:
        raise HTTPException(403, f"Пользователь заблокирован: {storage.blocked_reason}")
    
    new_story_data = generator.edit_story(storage.story_data, element, new_value)
    storage.set_story_data(storage.template_id, new_story_data)
    
    return {"story_text": new_story_data["full_text"]}

@app.get("/request-question")
async def request_question(user_id: str):
    if user_id not in user_stories:
        raise HTTPException(404, "Пользователь не найден")
    
    storage = user_stories[user_id]
    if storage.is_blocked:
        return {"error": f"Пользователь заблокирован: {storage.blocked_reason}"}
    
    last_cat = last_question.get(user_id)
    category, question = generator.get_question(storage.story_data, last_cat)
    last_question[user_id] = category
    
    session_token = str(uuid.uuid4())
    active_sessions[session_token] = (user_id, category)
    
    return {
        "question_text": question,
        "category": category,
        "session_token": session_token
    }

@app.get("/get-failed-count/{user_id}")
async def get_failed_count(user_id: str):
    if user_id not in user_stories:
        return {"count": 0}
    storage = user_stories[user_id]
    if storage.is_blocked:
        return {"count": "⛔"}
    return {"count": failed_attempts.get(user_id, 0)}

@app.post("/verify")
async def verify(request: Request):
    data = await request.json()
    answer = data.get("answer_text")
    token = data.get("session_token")
    
    if token not in active_sessions:
        raise HTTPException(400, "Сессия истекла")
    
    user_id, category = active_sessions[token]
    del active_sessions[token]
    
    if user_id not in user_stories:
        raise HTTPException(404, "Пользователь не найден")
    
    storage = user_stories[user_id]
    if storage.is_blocked:
        return {"success": False, "message": "BLOCKED", "correct": "???"}
    
    correct_answer = storage.get_correct_answer_text(category)
    is_correct = storage.verify_answer(category, answer)
    
    if is_correct:
        failed_attempts[user_id] = 0
        logger.info(f"✅ Верификация: верный ответ на {category} (ответ: '{answer}')")
    else:
        failed_attempts[user_id] = failed_attempts.get(user_id, 0) + 1
        logger.warning(f"❌ Верификация: неверный ответ на {category} (ответ: '{answer}', правильный: '{correct_answer}')")
    
    return {
        "success": is_correct, 
        "message": "GREEN" if is_correct else "RED",
        "correct": correct_answer if not is_correct else None
    }

@app.get("/get-card-number/{user_id}")
async def get_card_number(user_id: str):
    if user_id not in user_stories:
        return {"error": "Пользователь не найден"}
    
    storage = user_stories[user_id]
    if storage.is_blocked:
        return {"error": f"Пользователь заблокирован: {storage.blocked_reason}"}
    
    if not storage.is_saved:
        return {"error": "История еще не сохранена"}
    
    category, question = generator.get_question(storage.story_data)
    token = str(uuid.uuid4())
    active_sessions[token] = (user_id, category)
    
    return {
        "card_number": storage.card_number,
        "question": question,
        "token": token
    }

@app.post("/verify-card-answer")
async def verify_card_answer(request: Request):
    data = await request.json()
    user_id = data.get("user_id")
    answer = data.get("answer")
    token = data.get("token")
    
    if token not in active_sessions:
        return {"error": "Сессия истекла"}
    
    user_id_check, category = active_sessions[token]
    del active_sessions[token]
    
    if user_id != user_id_check:
        return {"error": "Несоответствие пользователя"}
    
    storage = user_stories[user_id]
    if storage.is_blocked:
        return {"error": f"Пользователь заблокирован"}
    
    correct_answer = storage.get_correct_answer_text(category)
    is_correct = storage.verify_answer(category, answer)
    
    if is_correct:
        logger.info(f"✅ Получение номера: верный ответ от {user_id}")
        return {"success": True, "card_number": storage.card_number}
    else:
        logger.warning(f"❌ Получение номера: неверный ответ от {user_id} (ответ: '{answer}', правильный: '{correct_answer}')")
        storage.is_blocked = True
        storage.blocked_reason = "Неверный ответ при получении номера карты"
        storage._save_to_json()
        return {"success": False, "error": "Неверный ответ. Доступ заблокирован"}

@app.get("/start-reminder/{user_id}")
async def start_reminder(user_id: str):
    if user_id not in user_stories:
        return {"error": "Пользователь не найден"}
    
    storage = user_stories[user_id]
    if storage.is_blocked:
        return {"error": f"Пользователь заблокирован"}
    
    if not storage.is_saved:
        return {"error": "История еще не сохранена"}
    
    storage.reminder_attempts = 0
    storage.reminder_fails = 0
    
    category, question = generator.get_question(storage.story_data)
    token = str(uuid.uuid4())
    reminder_sessions[token] = {
        "user_id": user_id,
        "category": category,
        "fails": 0,
        "asked": [category]
    }
    
    return {"token": token, "question": question}

@app.post("/verify-reminder")
async def verify_reminder(request: Request):
    data = await request.json()
    user_id = data.get("user_id")
    answer = data.get("answer")
    token = data.get("token")
    
    if token not in reminder_sessions:
        return {"error": "Сессия истекла"}
    
    session = reminder_sessions[token]
    if session["user_id"] != user_id:
        return {"error": "Несоответствие пользователя"}
    
    storage = user_stories[user_id]
    if storage.is_blocked:
        return {"error": "Пользователь заблокирован", "blocked": True}
    
    category = session["category"]
    correct_answer = storage.get_correct_answer_text(category)
    is_correct = storage.verify_answer(category, answer)
    
    if is_correct:
        logger.info(f"✅ Напоминание: верный ответ от {user_id}")
        del reminder_sessions[token]
        return {"success": True}
    else:
        session["fails"] += 1
        storage.reminder_fails += 1
        logger.warning(f"❌ Напоминание: неверный ответ от {user_id} (ответ: '{answer}', правильный: '{correct_answer}')")
        
        if session["fails"] >= 3 or storage.reminder_fails >= 3:
            storage.is_blocked = True
            storage.blocked_reason = "3 неверных ответа в напоминании"
            storage._save_to_json()
            del reminder_sessions[token]
            return {
                "success": False,
                "blocked": True,
                "error": "3 неверных ответа. Доступ заблокирован"
            }
        else:
            category, question = generator.get_question(
                storage.story_data,
                exclude_categories=session["asked"]
            )
            session["asked"].append(category)
            session["category"] = category
            new_token = str(uuid.uuid4())
            reminder_sessions[new_token] = session
            del reminder_sessions[token]
            return {
                "success": False,
                "blocked": False,
                "remaining": 3 - session["fails"],
                "question": question,
                "new_token": new_token
            }

@app.get("/debug/{user_id}")
async def debug(user_id: str):
    if user_id not in user_stories:
        raise HTTPException(404, "Не найден")
    
    storage = user_stories[user_id]
    
    json_path = f"data/user_{user_id}.json"
    json_data = None
    if os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            json_data = json.load(f)
    
    return {
        "memory": storage.to_dict(),
        "json_file": json_data,
        "failed_attempts": failed_attempts.get(user_id, 0)
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
