# story_generator.py
import random
from typing import List, Dict, Tuple
from config import STORY_TEMPLATES, PERSONAGI, DEYSTVIYA, MESTA, POMOCHNIKI, PREDMETY

class StoryGenerator:
    def __init__(self):
        self.templates = STORY_TEMPLATES
        self.personagi = PERSONAGI
        self.deystviya = DEYSTVIYA
        self.mesta = MESTA
        self.pomoshniki = POMOCHNIKI
        self.predmety = PREDMETY
        
    def generate_story(self, user_id: str, personal_names: List[str]) -> Tuple[int, str, Dict]:
        template_id = random.choice(list(self.templates.keys()))
        template = self.templates[template_id]
        
        story_data = {
            "template_id": template_id,
            "elements": {},
            "custom": {},
            "names": personal_names.copy() if personal_names else ["Герой"]
        }
        
        # Если имен меньше чем нужно, добавляем
        while len(story_data["names"]) < 3:
            story_data["names"].append(f"Персонаж_{len(story_data['names'])+1}")
        
        name_counter = 0
        
        for item in template["template"]:
            elem_type, default_id = item
            
            if elem_type == "imya":
                # Берем имя из списка
                if name_counter < len(story_data["names"]):
                    story_data["elements"][f"imya_{name_counter}"] = story_data["names"][name_counter]
                else:
                    story_data["elements"][f"imya_{name_counter}"] = f"Герой_{name_counter+1}"
                name_counter += 1
                
            elif elem_type == "personag":
                idx = default_id if default_id else random.choice(list(self.personagi.keys()))
                story_data["elements"]["personag"] = {
                    "id": idx,
                    "data": self.personagi[idx]
                }
                
            elif elem_type == "deystvie":
                idx = default_id if default_id else random.choice(list(self.deystviya.keys()))
                story_data["elements"]["deystvie"] = {
                    "id": idx,
                    "data": self.deystviya[idx]
                }
                
            elif elem_type == "mesto":
                idx = default_id if default_id else random.choice(list(self.mesta.keys()))
                story_data["elements"]["mesto"] = {
                    "id": idx,
                    "data": self.mesta[idx]
                }
                
            elif elem_type == "pomosh":
                idx = default_id if default_id else random.choice(list(self.pomoshniki.keys()))
                story_data["elements"]["pomosh"] = {
                    "id": idx,
                    "data": self.pomoshniki[idx]
                }
                
            elif elem_type == "predmet":
                idx = default_id if default_id else random.choice(list(self.predmety.keys()))
                story_data["elements"]["predmet"] = {
                    "id": idx,
                    "data": self.predmety[idx]
                }
        
        story_text = self._build_story_text(template, story_data)
        story_data["full_text"] = story_text
        
        return template_id, story_text, story_data
    
    def _build_story_text(self, template: Dict, story_data: Dict) -> str:
        replacements = {}
        
        if "personag" in story_data["elements"]:
            p = story_data["elements"]["personag"]["data"]
            if "personag" in story_data.get("custom", {}):
                replacements["personag"] = story_data["custom"]["personag"]
            else:
                replacements["personag"] = p["text"]
        
        # Имена
        name_count = 0
        for key, value in story_data["elements"].items():
            if key.startswith("imya_"):
                name_count += 1
                num = key.split("_")[1]
                if key in story_data.get("custom", {}):
                    replacements[f"imya_{int(num)+1}"] = story_data["custom"][key]
                else:
                    replacements[f"imya_{int(num)+1}"] = value
                if int(num) == 0:
                    replacements["imya"] = replacements[f"imya_1"]
        
        if "deystvie" in story_data["elements"]:
            d = story_data["elements"]["deystvie"]["data"]
            if "deystvie" in story_data.get("custom", {}):
                replacements["deystvie"] = story_data["custom"]["deystvie"]
            else:
                if "personag" in story_data["elements"]:
                    rod = story_data["elements"]["personag"]["data"]["rod"]
                    replacements["deystvie"] = d[rod]
                else:
                    replacements["deystvie"] = d["m"]
        
        if "mesto" in story_data["elements"]:
            m = story_data["elements"]["mesto"]["data"]
            if "mesto" in story_data.get("custom", {}):
                replacements["mesto"] = story_data["custom"]["mesto"]
            else:
                replacements["mesto"] = m["text"]
        
        if "pomosh" in story_data["elements"]:
            pom = story_data["elements"]["pomosh"]["data"]
            if "pomosh" in story_data.get("custom", {}):
                replacements["pomosh"] = story_data["custom"]["pomosh"]
            else:
                replacements["pomosh"] = pom["text"]
        
        if "predmet" in story_data["elements"]:
            pred = story_data["elements"]["predmet"]["data"]
            if "predmet" in story_data.get("custom", {}):
                replacements["predmet"] = story_data["custom"]["predmet"]
            else:
                replacements["predmet"] = pred["text"]
        
        try:
            return template["text"].format(**replacements)
        except KeyError as e:
            return f"История про {story_data.get('names', ['героя'])[0]}"
    
    def edit_story(self, story_data: Dict, element: str, new_value: str) -> Dict:
        if "custom" not in story_data:
            story_data["custom"] = {}
        story_data["custom"][element] = new_value
        
        template = self.templates[story_data["template_id"]]
        story_data["full_text"] = self._build_story_text(template, story_data)
        return story_data
    
    def get_question(self, story_data: Dict) -> Tuple[str, str]:
        # Сначала пытаемся задать вопрос про имена (они самые важные)
        if "imya_0" in story_data["elements"] and "imya_0" not in story_data.get("custom", {}):
            return "imya_0", "Как звали первого героя?"
        
        # Потом про персонажа
        if "personag" in story_data["elements"] and "personag" not in story_data.get("custom", {}):
            p = story_data["elements"]["personag"]["data"]["name"]
            return "personag", f"Кем был главный герой (в истории это {p})?"
        
        # Потом про действие
        if "deystvie" in story_data["elements"] and "deystvie" not in story_data.get("custom", {}):
            if "personag" in story_data["elements"]:
                rod = story_data["elements"]["personag"]["data"]["rod"]
                action = story_data["elements"]["deystvie"]["data"][rod]
                return "deystvie", f"Что сделал герой (в истории он {action})?"
        
        # Если всё уже заменено, выбираем случайный элемент
        elements = []
        if "personag" in story_data["elements"]:
            elements.append("personag")
        for i in range(len(story_data.get("names", []))):
            elements.append(f"imya_{i}")
        if "deystvie" in story_data["elements"]:
            elements.append("deystvie")
        if "mesto" in story_data["elements"]:
            elements.append("mesto")
        if "pomosh" in story_data["elements"]:
            elements.append("pomosh")
        if "predmet" in story_data["elements"]:
            elements.append("predmet")
        
        if not elements:
            return "imya_0", "Как звали героя?"
        
        elem = random.choice(elements)
        
        questions = {
            "personag": "Кем был главный герой?",
            "imya_0": "Как звали первого героя?",
            "imya_1": "Как звали второго героя?",
            "deystvie": "Что сделал герой?",
            "mesto": "Куда отправился герой?",
            "pomosh": "Кто помог герою?",
            "predmet": "Что подарили герою?"
        }
        
        return elem, questions.get(elem, "Что было в истории?")
