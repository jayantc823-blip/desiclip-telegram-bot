"""Avatar asset storage and safe image validation."""
import asyncio
from pathlib import Path
import cv2

async def validate_and_store(source: Path, target: Path):
    def work():
        image = cv2.imread(str(source), cv2.IMREAD_COLOR)
        if image is None or image.shape[0] < 64 or image.shape[1] < 64:
            raise ValueError("Please send a valid image at least 64x64 pixels.")
        h, w = image.shape[:2]
        # Limit the stored image size to keep overlay processing light.
        scale = min(1.0, 512 / max(h, w))
        if scale < 1:
            image = cv2.resize(image, (int(w*scale), int(h*scale)), interpolation=cv2.INTER_AREA)
        if not cv2.imwrite(str(target), image):
            raise ValueError("Could not save this image.")
    await asyncio.to_thread(work)
    return target
