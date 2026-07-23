import os, sys, json, time, shutil, requests
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────── CONFIG ───────────────────────────

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
HEYGEN_API_KEY     = os.getenv("HEYGEN_API_KEY") or os.getenv("HYGEN_API_KEY", "")

ELEVENLABS_BASE = "https://api.elevenlabs.io/v1"
HEYGEN_BASE     = "https://api.heygen.com"

# Fixed background — mobile vertical red stage curtain (9:16 aspect ratio for 360-412px x 800-915px mobile viewport)
PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_BACKGROUND_PATH = PROJECT_ROOT / "mobile_stage_red.jpg"
RED_STAGE_SRC = PROJECT_ROOT / "red.jpg"
BACKGROUND_TEXT = "Trufit Da Comedian"


def ensure_background_image(path: Path | None = None) -> Path:
    bg_path = (path or DEFAULT_BACKGROUND_PATH).resolve()
    if bg_path.exists() and bg_path.stat().st_size > 0:
        return bg_path

    bg_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image, ImageDraw, ImageFont

        target_w, target_h = 720, 1280

        if RED_STAGE_SRC.exists() and RED_STAGE_SRC.stat().st_size > 0:
            img_orig = Image.open(RED_STAGE_SRC).convert("RGB")
            w_orig, h_orig = img_orig.size
            target_aspect = target_w / target_h
            orig_aspect = w_orig / h_orig

            if orig_aspect > target_aspect:
                new_w = int(h_orig * target_aspect)
                left = (w_orig - new_w) // 2
                crop_box = (left, 0, left + new_w, h_orig)
            else:
                new_h = int(w_orig / target_aspect)
                top = (h_orig - new_h) // 2
                crop_box = (0, top, w_orig, top + new_h)

            img = img_orig.crop(crop_box).resize((target_w, target_h), Image.LANCZOS)
        else:
            import math
            img = Image.new("RGBA", (target_w, target_h), (20, 0, 5, 255))
            draw = ImageDraw.Draw(img)
            for x in range(target_w):
                fold = (math.sin(x * 0.045) + 1) / 2.0
                intensity = 0.4 * fold + 0.6
                for y in range(target_h):
                    v_grad = 1.0 - (y / target_h) * 0.35
                    r = int(140 * intensity * v_grad)
                    g = int(5 * v_grad)
                    b = int(15 * v_grad)
                    draw.point((x, y), fill=(r, g, b, 255))

        # Add Marquee Sign for 'Trufit Da Comedian' at top of mobile frame
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 42)
        except Exception:
            font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), BACKGROUND_TEXT, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

        px1, py1 = (target_w - tw) // 2 - 30, 140
        px2, py2 = (target_w + tw) // 2 + 30, 140 + th + 30

        plate = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
        plate_draw = ImageDraw.Draw(plate)
        plate_draw.rounded_rectangle((px1, py1, px2, py2), radius=16, fill=(30, 5, 10, 220), outline=(230, 180, 50, 255), width=3)
        plate_draw.rounded_rectangle((px1 - 2, py1 - 2, px2 + 2, py2 + 2), radius=18, fill=None, outline=(255, 225, 120, 180), width=2)

        img = Image.alpha_composite(img.convert("RGBA"), plate).convert("RGB")
        draw = ImageDraw.Draw(img)

        tx = (target_w - tw) // 2
        ty = py1 + (py2 - py1 - th) // 2 - 2

        draw.text((tx + 2, ty + 2), BACKGROUND_TEXT, fill=(10, 0, 0, 220), font=font)
        draw.text((tx, ty), BACKGROUND_TEXT, fill="#FFD700", font=font)

        img.save(bg_path, format="JPEG" if bg_path.suffix.lower() in [".jpg", ".jpeg"] else "PNG", quality=95)
    except Exception:
        bg_path.write_bytes(b"")

    return bg_path

    return bg_path


FIXED_BACKGROUND_URL = str(ensure_background_image(DEFAULT_BACKGROUND_PATH))

OUTPUT_DIR = Path("test_output")
OUTPUT_DIR.mkdir(exist_ok=True)

# Public preset photo-avatar looks
DEFAULT_AVATARS = {
    "1": {"name": "Angela", "avatar_id": "Angela-inblackskirt-20220820"},
    "2": {"name": "Daniel", "avatar_id": "Daniel_standing_casual20240408"},
    "3": {"name": "Kayla",  "avatar_id": "Kayla-incasualsuit-20220818"},
}

# Fixed System Prompt for Cartoon Avatar Generation (Standup Comedy)
# CARTOON_AVATAR_SYSTEM_PROMPT = """
# Transform this person's photo into an expressive cartoon avatar for standup comedy performances.

# Requirements:
# - Convert the realistic face into a vibrant, animated cartoon style
# - Exaggerate facial features (eyes, smile) to enhance comedic expression
# - Use bright, saturated colors with bold outlines
# - Style: Modern cartoon animation (similar to animated sitcoms or comedy specials)
# - Include stage-ready attire appropriate for standup comedy
# - Make the avatar appear confident, energetic, and performance-ready
# - Ensure high expressiveness to convey comedy emotions and punchlines
# - Keep proportions recognizable but distinctly cartoon-like
# - Use warm, friendly color palette to appeal to comedy audiences

# Context: This avatar will perform standup comedy material with lip-sync video. 
# Prioritize expressions that convey humor, timing, and stage presence.
# """
CARTOON_AVATAR_SYSTEM_PROMPT = """
Transform this person's photo into a friendly, 2D vector-style cartoon avatar for a standup comedy lip-sync performance. Maintain the subject's exact identity, Attire, skin tone, and hair, but apply the following specific style constraints:
 
Style & Rendering:
 
Create a 2D vector art illustration with a modern digital cartoon aesthetic.
 
Use flat, vibrant colors with crisp, clean bold black outlines.
 
Apply smooth, sharp cel-shaded lighting. Strictly avoid harsh, dark, or dramatic shadows.
 
Keep the background simple, solid, and minimalist.
 
Expression & Vibe (Crucial):
 
The avatar must look incredibly warm, cheerful, energetic, and approachable.
 
Enhance the smile and eyes to be bright and positive for comedy, but strictly avoid over-exaggerating facial features.
 
Do not use sharp angles, heavily arched eyebrows, or overly wide grins. Ensure the character looks kind, not sinister or villainous.
 
Keep facial proportions recognizable, soft, and distinctly human.
"""
SUMMARY = {
    "run_time":    datetime.now().isoformat(),
    "avatar":      {},
    "audio":       {},
    "video":       {},
    "local_files": {},
    "status":      "running",
}

# ══════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════

def ph(t):      print(f"\n{'═'*60}\n  {t}\n{'═'*60}")
def ok(m):      print(f"      ✅ {m}")
def fail(m):    print(f"      ❌ {m}")
def info(m):    print(f"      ℹ  {m}")
def step(n, m): print(f"\n  [{n}] {m}")

READY_STATUSES = {"completed", "active"}


def check_heygen_quota_error(response_or_text) -> str | None:
    text = ""
    status_code = None
    if isinstance(response_or_text, requests.Response):
        status_code = response_or_text.status_code
        text = response_or_text.text
    else:
        text = str(response_or_text)

    low_text = text.lower()
    quota_keywords = [
        "quota", "credit", "payment", "limit", "exhausted",
        "insufficient", "not enough", "expired", "sub_required", "402", "trial"
    ]
    if status_code in (402, 429) or any(k in low_text for k in quota_keywords):
        return "Heygen quota is finished"
    return None


def heygen_headers(json_body: bool = False) -> dict:
    h = {"X-Api-Key": HEYGEN_API_KEY, "accept": "application/json"}
    if json_body:
        h["Content-Type"] = "application/json"
    return h


def save_summary():
    p = OUTPUT_DIR / "run_summary.json"
    p.write_text(json.dumps(SUMMARY, indent=2))
    info(f"Summary → {p.resolve()}")


def download_file(url: str, dest: Path, label: str) -> bool:
    try:
        r = requests.get(url, timeout=120, stream=True)
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        ok(f"{label} → {dest.resolve()}  ({dest.stat().st_size // 1024} KB)")
        return True
    except Exception as e:
        fail(f"Download failed ({label}): {e}")
        return False


def find_default_avatar_image(base_dir: Path | None = None) -> Path | None:
    base_dir = (base_dir or Path(__file__).resolve().parent).resolve()
    candidates = [
        Path("media/avatars/default_avatar.jpeg"),
        Path("media/avatars/default_avatar.jpg"),
        Path("media/avatars/default_avatar.png"),
        Path("assets/avatars/default_avatar.jpeg"),
        Path("assets/avatars/default_avatar.jpg"),
        Path("assets/avatars/default_avatar.png"),
    ]
    for candidate in candidates:
        path = (base_dir / candidate).resolve()
        if path.exists():
            return path
    return None


def resolve_background_input(background_source: str | None, base_dir: Path | None = None) -> str | None:
    if not background_source:
        return None

    if background_source.startswith(("http://", "https://")):
        return background_source

    base_dir = (base_dir or Path(__file__).resolve().parent).resolve()
    raw_path = Path(background_source).expanduser()
    if not raw_path.is_absolute():
        raw_path = (base_dir / raw_path).resolve()

    if raw_path.exists() and raw_path.is_file():
        asset_id, asset_url = _upload_image_to_heygen(raw_path)
        if asset_url:
            SUMMARY["video"]["background"] = {
                "source": "local_path",
                "path": str(raw_path),
                "asset_id": asset_id,
                "url": asset_url,
            }
            SUMMARY["local_files"]["background"] = str(raw_path)
            return asset_url
        fail(f"Background upload failed for local image: {raw_path}")
        return None

    return background_source


# ══════════════════════════════════════════════════════════════
#  STEP 0 — API KEY CHECK
# ══════════════════════════════════════════════════════════════

def check_api_keys() -> bool:
    ph("STEP 0 — API Key Validation")
    good = True
    if ELEVENLABS_API_KEY:
        ok(f"ElevenLabs : {ELEVENLABS_API_KEY[:8]}...")
    else:
        info("ELEVENLABS_API_KEY not set (only needed for TTS mode)")
    if HEYGEN_API_KEY:
        ok(f"HeyGen     : {HEYGEN_API_KEY[:8]}...")
    else:
        info("HEYGEN_API_KEY not set (optional for the local-image video path)")
    return good




def choose_avatar() -> dict:
    ph("STEP 1 — Avatar Setup")
    print("\n  [1] Use a preset HeyGen avatar (no upload)")
    print("  [2] Upload your photo → convert to cartoon avatar")
    print("  [3] Reuse a previously generated avatar (paste avatar_id)")
    print("  [4] Use the default local avatar image from media/avatars")
    c = input("\n  Enter 1, 2, 3, or 4: ").strip()
    if c == "2":
        return _upload_custom_avatar()
    elif c == "3":
        return _reuse_existing_avatar()
    elif c == "4":
        return _use_default_local_avatar()
    return _pick_default_avatar()


def _reuse_existing_avatar() -> dict:
    print("\n  Paste your previous avatar_id (look_id from a past run).")
    print("  You can find it in test_output/run_summary.json under avatar.look_id")
    print("  Example: 3e3832c2cc6c4982a308a8adf7afca48")
    avatar_id = input("\n  Avatar ID: ").strip()
    if not avatar_id:
        fail("No avatar_id entered — falling back to default.")
        return _pick_default_avatar()

    # Verify the avatar exists and is ready
    step("🔍", f"Fetching avatar info → GET /v3/avatars/looks/{avatar_id}")
    try:
        r = requests.get(
            f"{HEYGEN_BASE}/v3/avatars/looks/{avatar_id}",
            headers=heygen_headers(),
            timeout=20,
        )
        if r.status_code == 404:
            fail(f"Avatar not found (404). Check the ID and try again.")
            return _pick_default_avatar()
        if r.status_code != 200:
            fail(f"HTTP {r.status_code}: {r.text[:200]}")
            return _pick_default_avatar()

        item        = r.json().get("data") or {}
        name        = item.get("name", "Unknown")
        status      = item.get("status", "unknown")
        engines     = item.get("supported_api_engines", ["avatar_iv"])
        engine      = engines[0] if engines else "avatar_iv"
        preview_url = item.get("preview_image_url", "")
        avatar_type = item.get("avatar_type", "unknown")

        info(f"Avatar found:")
        info(f"  Name        : {name}")
        info(f"  Type        : {avatar_type}")
        info(f"  Status      : {status}")
        info(f"  Engine      : {engine}")
        info(f"  Preview URL : {preview_url or 'none'}")

        if status not in READY_STATUSES:
            fail(f"Avatar status is '{status}' — not ready yet.")
            info("Wait for it to finish processing and try again.")
            return _pick_default_avatar()

        ok(f"Avatar '{name}' is ready")

        # Optionally download preview so user can visually confirm
        if preview_url:
            ans = input("\n  Download preview image to confirm? [y/n]: ").strip().lower()
            if ans == "y":
                _download_avatar_preview(preview_url)

        SUMMARY["avatar"] = {
            "source":       "reused",
            "avatar_id":    avatar_id,
            "name":         name,
            "status":       status,
            "engine":       engine,
            "preview_url":  preview_url,
        }
        return {
            "source":      "reused",
            "avatar_id":   avatar_id,
            "name":        name,
            "preview_url": preview_url,
            "engine":      engine,
        }

    except requests.RequestException as e:
        fail(f"Request error: {e}")
        return _pick_default_avatar()


def _pick_default_avatar() -> dict:
    print("\n  Available preset avatars:")
    for k, v in DEFAULT_AVATARS.items():
        print(f"    [{k}] {v['name']}")
    pick = input("\n  Pick number: ").strip()
    av = DEFAULT_AVATARS.get(pick, DEFAULT_AVATARS["1"])
    ok(f"Selected: {av['name']}  (avatar_id: {av['avatar_id']})")
    SUMMARY["avatar"] = {"source": "default", **av}
    # Preset studio avatars use avatar_iv engine
    return {"source": "default", "avatar_id": av["avatar_id"],
            "name": av["name"], "preview_url": "", "engine": "avatar_iv"}


def _upload_asset(file_path: str, mime: str) -> str | None:
    """Upload any file to POST /v3/assets. Returns asset_id or None."""
    asset_id, _ = _upload_asset_with_url(file_path, mime)
    return asset_id


def _upload_asset_with_url(file_path: str, mime: str) -> tuple[str | None, str | None]:
    with open(file_path, "rb") as f:
        r = requests.post(
            f"{HEYGEN_BASE}/v3/assets",
            headers=heygen_headers(),
            files={"file": (Path(file_path).name, f, mime)},
            timeout=120,
        )
    if r.status_code not in (200, 201):
        fail(f"Asset upload HTTP {r.status_code}: {r.text[:400]}")
        return None, None
    d = r.json()
    info(f"Asset upload response:\n{json.dumps(d, indent=4)}")
    data = d.get("data") or {}
    asset_id = data.get("asset_id", "")
    asset_url = data.get("url") or ""
    if not asset_id:
        fail("No asset_id in response")
    return (asset_id or None), (asset_url or None)


def _upload_image_to_heygen(image_path: Path) -> tuple[str | None, str | None]:
    mime = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"
    step("📤", f"Uploading {image_path.name} to HeyGen asset store…")
    return _upload_asset_with_url(str(image_path), mime)


def _remove_background(img_path: str) -> str:
    """
    Remove background from image using rembg (local AI, no API needed).
    Returns path to new PNG with transparent background.
    Falls back to original image if removal fails.
    """
    step("🎨", "Removing background from image…")
    out_path = str(OUTPUT_DIR / "avatar_no_bg.png")
    try:
        from rembg import remove
        from PIL import Image
        import io

        with open(img_path, "rb") as f:
            img_bytes = f.read()

        info("Running AI background removal (first run downloads ~170MB model)…")
        result_bytes = remove(img_bytes)

        # Save as PNG to preserve transparency
        img = Image.open(io.BytesIO(result_bytes)).convert("RGBA")
        img.save(out_path, "PNG")
        size_kb = Path(out_path).stat().st_size // 1024
        ok(f"Background removed → {out_path}  ({size_kb} KB)")
        info("Transparent PNG will be passed to HeyGen — avatar has no background.")
        SUMMARY["avatar"]["bg_removed"] = True
        SUMMARY["local_files"]["avatar_no_bg"] = str(Path(out_path).resolve())
        return out_path

    except ImportError:
        fail("rembg not installed. Run: pip install rembg pillow")
        info("Proceeding with original image (background NOT removed).")
        SUMMARY["avatar"]["bg_removed"] = False
        return img_path
    except Exception as e:
        fail(f"Background removal failed: {e}")
        info("Proceeding with original image (background NOT removed).")
        SUMMARY["avatar"]["bg_removed"] = False
        return img_path


def _use_default_local_avatar() -> dict:
    img_path = find_default_avatar_image()
    if not img_path:
        fail("No default avatar image found in media/avatars or assets/avatars — falling back to preset avatar.")
        return _pick_default_avatar()

    ok(f"Using default avatar image → {img_path}")
    cleaned_path = _remove_background(str(img_path))
    return {
        "source": "default_local",
        "avatar_id": "",
        "name": "DefaultAvatar",
        "preview_url": "",
        "engine": "avatar_iv",
        "use_local_video": True,
        "image_path": str(cleaned_path),
    }


def _create_avatar_from_image(img_path: str, avatar_name: str, do_rembg: bool, prompt: str, avatar_type: str = "prompt") -> dict:
    img_path = Path(img_path)
    if not img_path.exists():
        fail("File not found — falling back to default avatar.")
        return _pick_default_avatar()

    if do_rembg:
        img_path = Path(_remove_background(str(img_path)))

    step(2, "Uploading image to HeyGen asset store…")
    asset_id, _ = _upload_image_to_heygen(img_path)
    if not asset_id:
        return _pick_default_avatar()
    ok(f"Image asset_id: {asset_id}")
    SUMMARY["avatar"]["image_asset_id"] = asset_id

    if avatar_type == "photo":
        step(3, "Creating PHOTO avatar via POST /v3/avatars (type: photo)…")
        payload = {
            "type": "photo",
            "name": avatar_name,
            "file": {"type": "asset_id", "asset_id": asset_id},
        }
        info("Creating a photo avatar directly from the uploaded image")
    else:
        step(3, "Creating CARTOON avatar via POST /v3/avatars (type: prompt)…")
        style_prompt = prompt or CARTOON_AVATAR_SYSTEM_PROMPT.strip()
        info("Using fixed comedy avatar system prompt for cartoon generation")
        payload = {
            "type": "prompt",
            "name": avatar_name,
            "prompt": style_prompt,
            "reference_images": [
                {"type": "asset_id", "asset_id": asset_id}
            ],
        }

    info(f"Request payload:\n{json.dumps(payload, indent=4)}")

    try:
        r = requests.post(
            f"{HEYGEN_BASE}/v3/avatars",
            headers=heygen_headers(json_body=True),
            json=payload,
            timeout=60,
        )
        info(f"HTTP {r.status_code}")
        d = r.json()
        info(f"Create avatar response:\n{json.dumps(d, indent=4)}")

        if r.status_code not in (200, 201):
            fail(f"Avatar creation failed (HTTP {r.status_code}): {r.text[:400]}")
            return _pick_default_avatar()

        avatar_item = (d.get("data") or {}).get("avatar_item") or {}
        avatar_group = (d.get("data") or {}).get("avatar_group") or {}
        look_id = avatar_item.get("id", "")
        group_id = avatar_group.get("id", "")
        status = avatar_item.get("status", "unknown")
        preview_url = avatar_item.get("preview_image_url", "")
        engines = avatar_item.get("supported_api_engines", ["avatar_iv"])
        engine = engines[0] if engines else "avatar_iv"

        if not look_id:
            fail("No look_id returned — falling back to default.")
            return _pick_default_avatar()

        ok(f"Avatar submitted!  look_id={look_id}  status={status}  engine={engine}")
        ok(f"group_id: {group_id}")

        SUMMARY["avatar"].update({
            "source": "cartoon" if avatar_type != "photo" else "photo",
            "name": avatar_name,
            "look_id": look_id,
            "group_id": group_id,
            "initial_status": status,
            "engine": engine,
        })

        if status in READY_STATUSES:
            ok(f"Avatar already ready (status='{status}') — skipping poll.")
            SUMMARY["avatar"]["final_status"] = status
            SUMMARY["avatar"]["preview_url"] = preview_url
            _download_avatar_preview(preview_url)
            return {"source": "cartoon" if avatar_type != "photo" else "photo", "avatar_id": look_id, "name": avatar_name, "preview_url": preview_url, "engine": engine}

        poll_timeout = 600
        look_id, preview_url = _wait_for_avatar(look_id, preview_url, max_wait=poll_timeout, is_cartoon=(avatar_type != "photo"))
        return {"source": "custom", "avatar_id": look_id, "name": avatar_name, "preview_url": preview_url, "engine": engine}

    except requests.RequestException as e:
        fail(f"Request error: {e}")
        return _pick_default_avatar()


def _upload_custom_avatar() -> dict:
    img_path = input("\n  Path to your image (jpg/png): ").strip()
    if not Path(img_path).exists():
        fail("File not found — falling back to default avatar.")
        return _pick_default_avatar()

    print("\n  Remove background from image before creating avatar?")
    print("  (Recommended — avoids your photo BG bleeding into the video)")
    do_rembg = input("  Remove background? [Y/n]: ").strip().lower()
    return _create_avatar_from_image(
        img_path=img_path,
        avatar_name=input("  Name for this avatar [MyAvatar]: ").strip() or "MyAvatar",
        do_rembg=do_rembg != "n",
        prompt=CARTOON_AVATAR_SYSTEM_PROMPT.strip(),
        avatar_type="prompt",
    )


def _wait_for_avatar(look_id: str, fallback_url: str,
                     max_wait: int = 300,
                     is_cartoon: bool = False) -> tuple[str, str]:
    """
    Poll GET /v3/avatars/looks/{look_id} until avatar is ready.
    Photo avatars      -> status becomes "completed"  (~15-60s)
    Cartoon/prompt     -> status becomes "completed"  (~2-10 mins)
    Studio/digital twin-> status becomes "active"
    Both "completed" and "active" mean: ready to use.
    """
    kind = "Cartoon/prompt" if is_cartoon else "Photo"
    step("⏳", f"Waiting for {kind} avatar (max {max_wait}s)…")
    if is_cartoon:
        info("Stylized/prompt avatars take 2-10 minutes to generate — please be patient!")
        info("HeyGen is generating a new cartoon character based on your prompt + photo.")
    else:
        info("Photo avatars typically reach 'completed' within 15-60s.")
    url = f"{HEYGEN_BASE}/v3/avatars/looks/{look_id}"
    # Use longer interval for cartoon (no need to hammer the API every 10s)
    elapsed, interval = 0, 20 if is_cartoon else 10
    preview_url = fallback_url

    while elapsed < max_wait:
        try:
            r = requests.get(url, headers=heygen_headers(), timeout=20)
            if r.status_code == 200:
                item        = r.json().get("data") or {}
                status      = item.get("status", "unknown")
                preview_url = item.get("preview_image_url") or preview_url
                print(f"[{elapsed:>3}s] avatar status = {status}")

                if status in READY_STATUSES:
                    ok(f"Avatar READY (status='{status}')")
                    SUMMARY["avatar"]["final_status"] = status
                    SUMMARY["avatar"]["preview_url"]  = preview_url
                    _download_avatar_preview(preview_url)
                    return look_id, preview_url

                if status in ("failed", "error"):
                    fail(f"Avatar failed (status='{status}')")
                    SUMMARY["avatar"]["final_status"] = "failed"
                    return look_id, preview_url

            elif r.status_code == 404:
                print(f" [{elapsed:>3}s] not indexed yet (404)…")
            else:
                print(f" [{elapsed:>3}s] HTTP {r.status_code}")

        except requests.RequestException as e:
            info(f"Poll error: {e}")

        time.sleep(interval)
        elapsed += interval

    info(f"Avatar still processing after {max_wait}s — proceeding anyway.")
    SUMMARY["avatar"]["final_status"] = "still_processing"
    return look_id, preview_url


def _download_avatar_preview(preview_url: str):
    if not preview_url:
        return
    step("📷", "Downloading avatar preview image…")
    dest = OUTPUT_DIR / "avatar_preview.png"
    if download_file(preview_url, dest, "Avatar preview"):
        SUMMARY["local_files"]["avatar_preview"] = str(dest.resolve())
        info(f"Open to check your avatar looks right: {dest.resolve()}")


# ══════════════════════════════════════════════════════════════
#  STEP 2 — AUDIO
# ══════════════════════════════════════════════════════════════

def get_audio() -> tuple[Path | None, str | None]:
    ph("STEP 2 — Audio / Script Input")
    print("\n  [1] Type a text script  → ElevenLabs TTS → uploaded to HeyGen")
    print("  [2] Use a raw audio file (mp3 / wav / m4a)")
    c = input("\n  Enter 1 or 2: ").strip()
    if c == "1":
        if not ELEVENLABS_API_KEY:
            fail("ELEVENLABS_API_KEY not set. Cannot use TTS mode.")
            return None, None
        return _text_to_speech()
    else:
        local = _use_raw_audio()
        if local:
            asset_id = _upload_audio_to_heygen(local)
            return local, asset_id
        return None, None


def _pick_elevenlabs_voice() -> str:
    try:
        r = requests.get(
            f"{ELEVENLABS_BASE}/voices",
            headers={"xi-api-key": ELEVENLABS_API_KEY},
            timeout=15,
        )
        r.raise_for_status()
        voices = r.json().get("voices", [])
        ok(f"Found {len(voices)} ElevenLabs voices.")
        for i, v in enumerate(voices[:10], 1):
            print(f"    [{i:2}] {v['name']:25} {v['voice_id']}")
        if len(voices) > 10:
            print(f"         … +{len(voices) - 10} more")
        pick = input("\n  Enter number or paste voice_id directly: ").strip()
        if pick.isdigit() and 1 <= int(pick) <= len(voices):
            return voices[int(pick) - 1]["voice_id"]
        return pick
    except Exception as e:
        fail(f"Could not fetch voices: {e}")
        return input("  Paste voice_id: ").strip()


def _text_to_speech() -> tuple[Path | None, str | None]:
    voice_id = _pick_elevenlabs_voice()
    if not voice_id:
        return None, None
    print("\n  Enter your script (type END on its own line to finish):")
    lines = []
    while True:
        line = input()
        if line.strip().upper() == "END":
            break
        lines.append(line)
    script = "\n".join(lines).strip()
    if not script:
        fail("Empty script."); return None, None

    info("Converting text to speech via ElevenLabs…")
    try:
        r = requests.post(
            f"{ELEVENLABS_BASE}/text-to-speech/{voice_id}",
            json={
                "text": script,
                "model_id": "eleven_monolingual_v1",
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
            },
            headers={
                "xi-api-key": ELEVENLABS_API_KEY,
                "Content-Type": "application/json",
            },
            timeout=60,
        )
        r.raise_for_status()
        out = OUTPUT_DIR / "tts_output.mp3"
        out.write_bytes(r.content)
        ok(f"TTS saved → {out.resolve()}  ({len(r.content) // 1024} KB)")
        SUMMARY["audio"] = {"source": "elevenlabs_tts", "voice_id": voice_id}
        SUMMARY["local_files"]["audio"] = str(out.resolve())
        asset_id = _upload_audio_to_heygen(out)
        return out, asset_id
    except requests.RequestException as e:
        fail(f"ElevenLabs TTS failed: {e}")
        if hasattr(e, "response") and e.response is not None:
            info(e.response.text[:300])
        return None, None


def _use_raw_audio() -> Path | None:
    raw = input("\n  Path to audio file (mp3/wav/m4a): ").strip()
    p = Path(raw)
    if not p.exists():
        fail(f"Not found: {raw}"); return None
    dest = OUTPUT_DIR / ("raw_audio" + p.suffix)
    shutil.copy(p, dest)
    ok(f"Audio copied → {dest.resolve()}")
    SUMMARY["audio"] = {"source": "raw_file", "original": str(p)}
    SUMMARY["local_files"]["audio"] = str(dest.resolve())
    return dest


def _convert_to_mp3(audio_path: Path) -> Path:
    """
    Convert m4a/aac/wav to mp3 using pydub (ffmpeg backend).
    HeyGen rejects m4a uploaded as video/mp4 — mp3 is the safest format.
    Returns the mp3 path (may be same path if already mp3).
    """
    if audio_path.suffix.lower() == ".mp3":
        return audio_path
    mp3_path = OUTPUT_DIR / "converted_audio.mp3"
    try:
        from pydub import AudioSegment
        info(f"Converting {audio_path.suffix} → .mp3 via pydub…")
        seg = AudioSegment.from_file(str(audio_path))
        seg.export(str(mp3_path), format="mp3", bitrate="128k")
        ok(f"Converted → {mp3_path}  ({mp3_path.stat().st_size // 1024} KB)")
        return mp3_path
    except ImportError:
        info("pydub not installed — trying ffmpeg directly…")
        import subprocess
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", str(audio_path), "-vn",
             "-acodec", "libmp3lame", "-ab", "128k", str(mp3_path)],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            ok(f"ffmpeg converted → {mp3_path}  ({mp3_path.stat().st_size // 1024} KB)")
            return mp3_path
        else:
            fail(f"ffmpeg failed: {result.stderr[-300:]}")
            info("Uploading original file (may fail if HeyGen rejects it).")
            return audio_path
    except Exception as e:
        fail(f"Conversion failed: {e}")
        info("Uploading original file anyway.")
        return audio_path


def _upload_audio_to_heygen(audio_path: Path) -> str | None:
    # HeyGen only accepts true audio assets — m4a gets flagged as video/mp4
    # Convert to mp3 first to guarantee acceptance
    audio_path = _convert_to_mp3(audio_path)

    step("📤", f"Uploading {audio_path.name} to HeyGen asset store…")
    # Always upload as audio/mpeg (mp3) — safest format HeyGen accepts
    asset_id = _upload_asset(str(audio_path), "audio/mpeg")
    if asset_id:
        ok(f"Audio asset_id: {asset_id}")
        SUMMARY["audio"]["heygen_asset_id"] = asset_id
        SUMMARY["audio"]["uploaded_file"]   = str(audio_path)
    else:
        fail("Audio upload failed — cannot generate video.")
    return asset_id


# ══════════════════════════════════════════════════════════════
#  STEP 3 — VIDEO GENERATION  (HeyGen v3)
# ══════════════════════════════════════════════════════════════

def generate_video(avatar: dict, audio_asset_id: str, audio_path: Path | None = None) -> str | None:
    if avatar.get("use_local_video"):
        return _generate_local_video(avatar, audio_path)

    ph("STEP 3 — HeyGen Photo Avatar Video Generation")
    step(1, "Submitting video job → POST /v3/videos")

    # Engine reported by the avatar look (photo avatars → "avatar_iv")
    engine_type = avatar.get("engine", "avatar_iv")

    # ── POST /v3/videos required fields ───────────────────────
    # "type": "avatar"   ← REQUIRED discriminator (was missing — caused the 400 error)
    # "avatar_id"        ← look_id from avatar creation
    # "audio_asset_id"   ← top-level; tells HeyGen to lip-sync your audio (not TTS)
    # "engine"           ← must match what the avatar look supports
    background_url = resolve_background_input(FIXED_BACKGROUND_URL)
    payload = {
        "type":           "avatar",           # ← REQUIRED — this was the 400 error cause
        "avatar_id":      avatar["avatar_id"],
        "audio_asset_id": audio_asset_id,     # ← your audio drives the lip-sync
        "engine": {
            "type": engine_type,              # "avatar_iv" for photo avatars
        },
        "background": {
            "type": "image",
            "url":  background_url,
        },
        "dimension": {
            "width": 720,
            "height": 1280,
        },
        "scale": 0.8,
        "offset": {
            "x": 0.0,
            "y": 0.15,
        },
        "resolution":    "720p",
        "aspect_ratio":  "9:16",             # ← Mobile vertical phone view (360-412px x 800-915px viewport)
        "title":         f"LipSync_{avatar['name']}_{datetime.now().strftime('%H%M%S')}",
        "remove_background": True,   # strip any residual bg from the avatar layer
    }
    info(f"Payload:\n{json.dumps(payload, indent=4)}")

    try:
        r = requests.post(
            f"{HEYGEN_BASE}/v3/videos",
            headers=heygen_headers(json_body=True),
            json=payload,
            timeout=60,
        )
        info(f"HTTP {r.status_code}")
        d = r.json()
        info(f"Submit response:\n{json.dumps(d, indent=4)}")

        if r.status_code not in (200, 201):
            fail(f"Video submit failed (HTTP {r.status_code}):\n{r.text[:600]}")
            return None

        video_id = (d.get("data") or {}).get("video_id") or d.get("video_id", "")
        if not video_id:
            fail("No video_id in response."); return None

        ok(f"Video job submitted!  video_id: {video_id}")
        SUMMARY["video"]["video_id"] = video_id

    except requests.RequestException as e:
        fail(f"Video submit request error: {e}")
        return None

    # ── Poll until done ────────────────────────────────────────
    step(2, f"Polling video status → GET /v3/videos/{video_id}")
    info("Photo avatar videos typically take 1–5 minutes…")
    video_url = _poll_video(video_id)
    if not video_url:
        return None

    # ── Download final video ───────────────────────────────────
    step(3, "Downloading final video…")
    ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = OUTPUT_DIR / f"final_video_{ts}.mp4"
    if download_file(video_url, out, "Final lip-sync video"):
        SUMMARY["video"].update({
            "local_path": str(out.resolve()),
            "video_url":  video_url,
            "status":     "completed",
        })
        SUMMARY["local_files"]["video"] = str(out.resolve())
        return str(out.resolve())
    else:
        info(f"Manual download URL:\n  {video_url}")
        return video_url


def _generate_local_video(avatar: dict, audio_path: Path | None) -> str | None:
    ph("STEP 3 — Local Image + Audio Video Generation")
    if not audio_path or not audio_path.exists():
        fail("No local audio file available for local video generation.")
        return None

    image_path = Path(avatar.get("image_path") or "")
    if not image_path or not image_path.exists():
        fail("No local image available for local video generation.")
        return None

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = OUTPUT_DIR / f"final_video_{ts}.mp4"
    ok(f"Creating local video from image → {image_path} and audio → {audio_path}")

    try:
        from PIL import Image
        import subprocess

        bg_path = ensure_background_image(DEFAULT_BACKGROUND_PATH)
        bg_image = Image.open(bg_path).convert("RGBA")
        avatar_image = Image.open(image_path).convert("RGBA")
        avatar_width = int(bg_image.width * 0.32)
        avatar_height = int(avatar_width * avatar_image.height / max(avatar_image.width, 1))
        avatar_image = avatar_image.resize((avatar_width, avatar_height), Image.LANCZOS)
        # Position character small in lower-middle of mobile stage frame below title sign
        x = (bg_image.width - avatar_image.width) // 2
        y = int(bg_image.height * 0.50)
        composite_path = OUTPUT_DIR / f"composite_{ts}.png"
        bg_image_copy = bg_image.copy()
        bg_image_copy.paste(avatar_image, (x, y), avatar_image)
        bg_image_copy.save(composite_path, format="PNG")

        cmd = [
            "ffmpeg", "-y", "-loop", "1", "-i", str(composite_path),
            "-i", str(audio_path), "-c:v", "libx264", "-preset", "medium",
            "-pix_fmt", "yuv420p", "-shortest", str(out)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            fail(f"ffmpeg failed: {result.stderr[-500:]}")
            return None

        ok(f"Local video created → {out.resolve()}")
        SUMMARY["video"].update({
            "local_path": str(out.resolve()),
            "status": "completed",
            "method": "local_ffmpeg",
        })
        SUMMARY["local_files"]["video"] = str(out.resolve())
        return str(out.resolve())
    except FileNotFoundError:
        fail("ffmpeg not found. Install ffmpeg to generate local videos.")
        return None
    except Exception as e:
        fail(f"Local video generation failed: {e}")
        return None


def _poll_video(video_id: str, max_wait: int = 600) -> str | None:
    url = f"{HEYGEN_BASE}/v3/videos/{video_id}"
    elapsed, interval = 0, 15
    while elapsed < max_wait:
        try:
            r = requests.get(url, headers=heygen_headers(), timeout=20)
            if r.status_code != 200:
                print(f" [{elapsed:>3}s] HTTP {r.status_code} — retrying…")
            else:
                data   = r.json().get("data") or {}
                status = data.get("status", "unknown")
                print(f" [{elapsed:>3}s] video status = {status}")
                if status == "completed":
                    video_url = data.get("video_url", "")
                    ok(f"Video READY  URL: {video_url}")
                    SUMMARY["video"]["url"] = video_url
                    return video_url
                if status in ("failed", "error"):
                    msg = data.get("failure_message", "no details")
                    fail(f"Video failed: {msg}")
                    SUMMARY["video"]["status"] = "failed"
                    SUMMARY["video"]["error"]  = msg
                    return None
        except requests.RequestException as e:
            info(f"Poll error: {e}")
        time.sleep(interval)
        elapsed += interval

    fail(f"Timed out after {max_wait}s.")
    info(f"Check manually: GET {HEYGEN_BASE}/v3/videos/{video_id}")
    SUMMARY["video"]["status"] = "timeout"
    return None


# ══════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════

def main():
    ph("AI VIDEO GENERATION PIPELINE")
    print("  Flow: Custom/Cartoon/Preset Avatar + ElevenLabs TTS or Raw Audio → Lip-Sync Video")
    print(f"  Output directory: {OUTPUT_DIR.resolve()}\n")

    if not check_api_keys():
        print("\n  Create a .env file:\n"
              "    HEYGEN_API_KEY=your_key\n"
              "    ELEVENLABS_API_KEY=your_key  (TTS mode only)\n")
        sys.exit(1)

    avatar = choose_avatar()
    info(f"Avatar ready: {avatar['name']} / avatar_id={avatar['avatar_id']} / engine={avatar.get('engine','avatar_iv')}")

    audio_path, audio_asset_id = get_audio()
    if not audio_asset_id:
        fail("No audio asset ID obtained. Cannot generate video.")
        SUMMARY["status"] = "failed — no audio"
        save_summary()
        sys.exit(1)

    result = generate_video(avatar, audio_asset_id, audio_path=audio_path)
    SUMMARY["status"] = "completed" if result else "failed"
    save_summary()

    ph("RESULT")
    if result:
        ok("Pipeline completed successfully! 🎉")
        print("\n  LOCAL FILES:")
        for label, path in SUMMARY.get("local_files", {}).items():
            print(f"      {label:20} → {path}")
        print(f"\n  Full run log → {(OUTPUT_DIR / 'run_summary.json').resolve()}")
    else:
        fail("Pipeline did not complete — see errors above.")
        info(f"Log → {(OUTPUT_DIR / 'run_summary.json').resolve()}")
    print()


if __name__ == "__main__":
    main()