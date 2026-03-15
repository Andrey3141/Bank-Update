# models.py
from pydantic import BaseModel
from typing import List, Dict, Optional, Any
import hashlib
import secrets
import json

class UserRegistrationRequest(BaseModel):
    user_id: str
    personal_names: List[str] = []

class StoryResponse(BaseModel):
    story_id: int
    story_text: str
    template_id: int
    story_data: Optional[Dict] = None

class VerificationQuestion(BaseModel):
    question_id: int
    question_text: str
    category: str
    session_token: str

class VerificationAnswer(BaseModel):
    answer_text: str
    session_token: str

class VerificationResult(BaseModel):
    success: bool
    message: str

class EditStoryRequest(BaseModel):
    user_id: str
    element: str
    new_value: str

class SecureStoryStorage:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.salt = secrets.token_hex(16)
        self.template_id: Optional[int] = None
        self.story_data: Dict = {}
        self.verification_hashes: Dict[str, str] = {}
        
    def set_story_data(self, template_id: int, story_data: Dict):
        self.template_id = template_id
        self.story_data = story_data
        
        # Создаем хеши для верификации
        all_answers = {}
        
        if "personag" in story_data["elements"]:
            if "personag" in story_data.get("custom", {}):
                all_answers["personag"] = story_data["custom"]["personag"]
            else:
                all_answers["personag"] = story_data["elements"]["personag"]["data"]["text"]
        
        for i, name in enumerate(story_data.get("names", [])):
            all_answers[f"imya_{i}"] = name
        
        if "deystvie" in story_data["elements"]:
            if "deystvie" in story_data.get("custom", {}):
                all_answers["deystvie"] = story_data["custom"]["deystvie"]
            else:
                if "personag" in story_data["elements"]:
                    rod = story_data["elements"]["personag"]["data"]["rod"]
                    all_answers["deystvie"] = story_data["elements"]["deystvie"]["data"][rod]
        
        if "mesto" in story_data["elements"]:
            if "mesto" in story_data.get("custom", {}):
                all_answers["mesto"] = story_data["custom"]["mesto"]
            else:
                all_answers["mesto"] = story_data["elements"]["mesto"]["data"]["text"]
        
        if "pomosh" in story_data["elements"]:
            if "pomosh" in story_data.get("custom", {}):
                all_answers["pomosh"] = story_data["custom"]["pomosh"]
            else:
                all_answers["pomosh"] = story_data["elements"]["pomosh"]["data"]["text"]
        
        if "predmet" in story_data["elements"]:
            if "predmet" in story_data.get("custom", {}):
                all_answers["predmet"] = story_data["custom"]["predmet"]
            else:
                all_answers["predmet"] = story_data["elements"]["predmet"]["data"]["text"]
        
        for key, value in all_answers.items():
            hashed = hashlib.sha256((str(value) + self.salt).encode()).hexdigest()
            self.verification_hashes[key] = hashed
    
    def verify_answer(self, category: str, answer: str) -> bool:
        if category not in self.verification_hashes:
            return False
        hashed = hashlib.sha256((answer + self.salt).encode()).hexdigest()
        return hashed == self.verification_hashes[category]
