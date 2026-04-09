#!/usr/bin/env python3
"""Generate AI hero images for STR Solutions newsletters.

Usage:
    python3 newsletter_hero_gen.py                    # Generate + save to assets
    python3 newsletter_hero_gen.py --prompt "custom"  # Custom prompt
    python3 newsletter_hero_gen.py --list              # List saved heroes

Saves images to /srv/str-stack-public/assets/newsletters/heroes/
Uses DALL-E 3 via OpenAI API. ~$0.08 per image (1792x1024 landscape).
"""

import argparse
import base64
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

HERO_DIR = Path('/srv/str-stack-public/assets/newsletters/heroes')
HERO_DIR.mkdir(parents=True, exist_ok=True)

REGISTRY = HERO_DIR / 'registry.json'

# Default prompt tuned for luxury vacation rentals
DEFAULT_PROMPT = (
    "A stunning luxury vacation rental property at golden hour. "
    "Modern architecture with floor-to-ceiling windows, infinity pool "
    "reflecting the sunset, lush tropical landscaping, warm ambient lighting. "
    "Professional real estate photography style, wide-angle lens, "
    "ultra high resolution, cinematic color grading. "
    "No text, no watermarks, no people."
)

VARIATIONS = [
    "A breathtaking oceanfront luxury villa at sunset with an infinity pool overlooking turquoise waters, modern minimalist architecture, warm golden light, professional real estate photography, ultra detailed, no text no watermarks no people.",
    "A stunning mountain retreat luxury cabin with floor-to-ceiling windows revealing snow-capped peaks, warm interior lighting spilling onto a timber deck, twilight sky with stars emerging, professional architectural photography, no text no watermarks no people.",
    "An elegant beachfront vacation home with white stucco walls and blue accents, private beach access, palm trees swaying in a gentle breeze, golden hour lighting, Mediterranean style, professional real estate photography, no text no watermarks no people.",
    "A modern luxury desert oasis home with clean lines, a glowing turquoise pool surrounded by desert landscaping, dramatic sunset sky in orange and purple, architectural photography style, no text no watermarks no people.",
    "A tropical luxury treehouse villa nestled in lush rainforest canopy, open-air design with infinity edge plunge pool, warm string lights at dusk, exotic birds of paradise flowers, professional travel photography, no text no watermarks no people.",
    "A contemporary lakeside luxury retreat with floor-to-ceiling glass reflecting calm mirror-like water, private dock with ambient lighting, pine forest backdrop, blue hour sky, Scandinavian design, professional photography, no text no watermarks no people.",
    "A sprawling Tuscan-style luxury estate with terracotta roof, vineyard views stretching to rolling hills, cypress tree-lined driveway, warm afternoon sunlight, olive groves, professional architectural photography, no text no watermarks no people.",
]


def load_registry():
    if REGISTRY.exists():
        with open(REGISTRY) as f:
            return json.load(f)
    return {"generated": []}


def save_registry(reg):
    with open(REGISTRY, 'w') as f:
        json.dump(reg, f, indent=2)


def get_next_prompt(reg):
    """Cycle through variations so each newsletter gets a different scene."""
    used = len(reg.get("generated", []))
    idx = used % len(VARIATIONS)
    return VARIATIONS[idx]


def generate_hero(prompt=None, save_name=None):
    api_key = os.environ.get('OPENAI_API_KEY', '')
    if not api_key:
        # Try loading from .env
        env_path = Path('/root/str-stack/.env')
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith('OPENAI_API_KEY='):
                    api_key = line.split('=', 1)[1].strip()
                    break
    if not api_key:
        print("ERROR: No OPENAI_API_KEY found")
        sys.exit(1)

    reg = load_registry()

    if prompt is None:
        prompt = get_next_prompt(reg)

    print(f"Generating hero image...")
    print(f"Prompt: {prompt[:100]}...")

    # Call DALL-E 3 API
    payload = json.dumps({
        "model": "dall-e-3",
        "prompt": prompt,
        "n": 1,
        "size": "1792x1024",
        "quality": "standard",
        "response_format": "url"
    }).encode()

    req = urllib.request.Request(
        "https://api.openai.com/v1/images/generations",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"API Error {e.code}: {body}")
        sys.exit(1)

    image_url = result["data"][0]["url"]
    revised_prompt = result["data"][0].get("revised_prompt", prompt)

    # Download the image
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    if save_name is None:
        save_name = f"hero-{timestamp}.png"

    save_path = HERO_DIR / save_name

    print(f"Downloading to {save_path}...")
    urllib.request.urlretrieve(image_url, str(save_path))

    file_size = save_path.stat().st_size
    print(f"Saved: {save_path} ({file_size:,} bytes)")

    # Update registry
    reg["generated"].append({
        "file": save_name,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "prompt": prompt[:200],
        "revised_prompt": revised_prompt[:300],
        "size": "1792x1024",
        "model": "dall-e-3",
        "cost_usd": 0.08
    })
    reg["latest"] = save_name
    save_registry(reg)

    # Return the public URL
    public_url = f"https://dashboard.strsolutionsusa.com/assets/newsletters/heroes/{save_name}"
    print(f"Public URL: {public_url}")
    return public_url, save_path


def list_heroes():
    reg = load_registry()
    if not reg.get("generated"):
        print("No hero images generated yet.")
        return
    total_cost = 0
    for entry in reg["generated"]:
        cost = entry.get("cost_usd", 0.08)
        total_cost += cost
        print(f"  {entry['file']}  |  {entry['timestamp']}  |  ${cost:.2f}")
    print(f"\nTotal: {len(reg['generated'])} images | ${total_cost:.2f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Newsletter Hero Image Generator")
    parser.add_argument("--prompt", help="Custom prompt")
    parser.add_argument("--list", action="store_true", help="List generated images")
    parser.add_argument("--name", help="Custom filename")
    args = parser.parse_args()

    if args.list:
        list_heroes()
    else:
        url, path = generate_hero(prompt=args.prompt, save_name=args.name)
        print(f"\nDone! Use this URL in the newsletter hero:\n{url}")
