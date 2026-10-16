import os

from dotenv import load_dotenv
load_dotenv()

import json
import requests
from bs4 import BeautifulSoup
import html as html_module



HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def fetch_html(url):
    """Fetch a URL and return the HTML as text. Returns None on failure."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as e:
        print(f"fetch failed: {e}")
        return None


def extract_jsonld_recipes(html):
    """Find all JSON-LD blocks with @type == 'Recipe'. Returns a list of dicts."""
    soup = BeautifulSoup(html, "html.parser")
    recipes = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue

        candidates = data if isinstance(data, list) else [data]

        for item in candidates:
            if not isinstance(item, dict):
                continue
            if item.get("@type") == "Recipe":
                recipes.append(item)
            elif "@graph" in item:
                for sub in item["@graph"]:
                    if isinstance(sub, dict) and sub.get("@type") == "Recipe":
                        recipes.append(sub)
    return recipes


def normalize_instructions(raw):
    """Instructions can be strings, objects, or nested lists. Normalize to list[str]."""
    if isinstance(raw, str):
        return [s.strip() for s in raw.split("\n") if s.strip()]

    if not isinstance(raw, list):
        return []

    steps = []
    for item in raw:
        if isinstance(item, str):
            steps.append(item.strip())
        elif isinstance(item, dict):
            if "text" in item:
                steps.append(item["text"].strip())
            elif "itemListElement" in item:
                for sub in item["itemListElement"]:
                    if isinstance(sub, dict) and "text" in sub:
                        steps.append(sub["text"].strip())
    return [s for s in steps if s]


def normalize_ingredients(raw):
    """Ingredients are usually a list of strings, but sometimes weird. Flatten to list[str]."""
    if isinstance(raw, str):
        return [s.strip() for s in raw.split("\n") if s.strip()]
    if not isinstance(raw, list):
        return []
    return [html_module.unescape(str(i).strip()) for i in raw if str(i).strip()]


def normalize_yield(raw):
    """recipeYield can be '4', '4 servings', or ['4', '4 servings']. Return a clean string."""
    if isinstance(raw, list):
        raw = raw[0] if raw else ""
    return str(raw).strip() if raw else ""


def extract_image(raw):
    """image can be a string, a list, or a dict with 'url'. Return a string URL."""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list) and raw:
        return extract_image(raw[0])
    if isinstance(raw, dict):
        return raw.get("url", "")
    return ""


def parse_recipe_with_llm(html, url):
    """Fallback: send cleaned page text to Gemini, ask for structured JSON."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("GEMINI_API_KEY not set; skipping LLM fallback")
        return None

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n", strip=True)[:8000]

    prompt = f"""You are a recipe extraction tool. Extract the recipe from the page text below.

Return ONLY a JSON object, no markdown code fences, no commentary. Use this exact shape:
{{
  "name": "Recipe name",
  "ingredients": ["ingredient 1", "ingredient 2"],
  "instructions": ["step 1", "step 2"],
  "servings": "4",
  "prep_time": "15 min",
  "cook_time": "20 min"
}}

If the text is not a recipe, return exactly: {{"error": "not a recipe"}}

PAGE TEXT:
{text}
"""

    endpoint = GEMINI_URL.format(model=GEMINI_MODEL)
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.2,
        },
    }

    try:
        resp = requests.post(
            f"{endpoint}?key={api_key}",
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"Gemini request failed: {e}")
        return None

    try:
        data = resp.json()
        raw = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, ValueError) as e:
        print(f"Unexpected Gemini response shape: {e}")
        return None

    try:
        recipe = json.loads(raw)
    except json.JSONDecodeError:
        print(f"Gemini returned non-JSON: {raw[:200]}")
        return None

    if "error" in recipe:
        return None

    return {
        "name": str(recipe.get("name", "")).strip(),
        "ingredients": [str(i).strip() for i in recipe.get("ingredients", []) if str(i).strip()],
        "instructions": [str(s).strip() for s in recipe.get("instructions", []) if str(s).strip()],
        "servings": str(recipe.get("servings") or "").strip(),
        "prep_time": str(recipe.get("prep_time") or "").strip(),
        "cook_time": str(recipe.get("cook_time") or "").strip(),
        "image_url": "",
        "source_url": url,
    }


def parse_recipe_from_url(url):
    """Main entry point. Returns a normalized recipe dict, or None."""
    html = fetch_html(url)
    if not html:
        return None

    recipes = extract_jsonld_recipes(html)

    if recipes:
        r = recipes[0]
        return {
            "name": r.get("name", "").strip(),
            "ingredients": normalize_ingredients(r.get("recipeIngredient", [])),
            "instructions": normalize_instructions(r.get("recipeInstructions", [])),
            "servings": normalize_yield(r.get("recipeYield", "")),
            "prep_time": r.get("prepTime", ""),
            "cook_time": r.get("cookTime", ""),
            "image_url": extract_image(r.get("image", "")),
            "source_url": url,
        }

    print(f"no JSON-LD at {url}, trying LLM")
    return parse_recipe_with_llm(html, url)