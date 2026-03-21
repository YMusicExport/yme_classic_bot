from config import PROMO_FILE


def get_promo() -> str | None:
    try:
        with open(PROMO_FILE, 'r', encoding='utf-8') as f:
            text = f.read().strip()
        return text if text else None
    except FileNotFoundError:
        return None


def set_promo(text: str):
    with open(PROMO_FILE, 'w', encoding='utf-8') as f:
        f.write(text.strip())


def clear_promo():
    with open(PROMO_FILE, 'w', encoding='utf-8') as f:
        f.write("")
