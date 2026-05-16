import aiofiles
from config import PROMO_FILE


async def get_promo() -> str | None:
    try:
        async with aiofiles.open(PROMO_FILE, 'r', encoding='utf-8') as f:
            text = (await f.read()).strip()
        return text if text else None
    except FileNotFoundError:
        return None


async def set_promo(text: str):
    async with aiofiles.open(PROMO_FILE, 'w', encoding='utf-8') as f:
        await f.write(text.strip())


async def clear_promo():
    async with aiofiles.open(PROMO_FILE, 'w', encoding='utf-8') as f:
        await f.write("")
