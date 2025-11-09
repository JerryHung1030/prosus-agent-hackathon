"""Image downloading and caching utilities."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

import httpx
from PIL import Image
from io import BytesIO


class ImageDownloader:
    """Downloads and caches listing images as WEBP thumbnails."""
    
    def __init__(self, base_path: str = "images", quality: int = 85):
        """
        Initialize the image downloader.
        
        Args:
            base_path: Base directory for storing images
            quality: WEBP compression quality (1-100)
        """
        self.base_path = Path(base_path)
        self.quality = quality
        self.base_path.mkdir(parents=True, exist_ok=True)
    
    def get_thumbnail_path(self, listing_id: str) -> Path:
        """Get the full path for a listing's thumbnail."""
        listing_dir = self.base_path / listing_id
        return listing_dir / "thumbnail.webp"
    
    def thumbnail_exists(self, listing_id: str) -> bool:
        """Check if thumbnail already exists for this listing."""
        thumbnail_path = self.get_thumbnail_path(listing_id)
        return thumbnail_path.exists()
    
    async def download_and_save(
        self,
        listing_id: str,
        image_url: str,
        timeout: float = 30.0,
    ) -> Optional[str]:
        """
        Download an image and save as WEBP thumbnail.
        
        Args:
            listing_id: Unique identifier for the listing
            image_url: URL of the image to download
            timeout: Request timeout in seconds
            
        Returns:
            Relative path to the saved thumbnail, or None if failed
        """
        # Check if already cached
        thumbnail_path = self.get_thumbnail_path(listing_id)
        if thumbnail_path.exists():
            logging.info("Thumbnail already exists for listing %s, skipping download", listing_id)
            relative_path = str(thumbnail_path.relative_to(self.base_path.parent))
            return relative_path.replace(os.sep, "/")
        
        # Create listing directory
        listing_dir = thumbnail_path.parent
        listing_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Download the image
            async with httpx.AsyncClient() as client:
                response = await client.get(image_url, timeout=timeout, follow_redirects=True)
                response.raise_for_status()
                
                # Load image with PIL
                image_data = BytesIO(response.content)
                img = Image.open(image_data)
                
                # Convert to RGB if necessary (WEBP doesn't support RGBA well)
                if img.mode in ("RGBA", "LA", "P"):
                    # Create a white background
                    background = Image.new("RGB", img.size, (255, 255, 255))
                    if img.mode == "P":
                        img = img.convert("RGBA")
                    if img.mode in ("RGBA", "LA"):
                        background.paste(img, mask=img.split()[-1])  # Use alpha channel as mask
                        img = background
                    else:
                        img = img.convert("RGB")
                elif img.mode != "RGB":
                    img = img.convert("RGB")
                
                # Save as WEBP
                img.save(
                    thumbnail_path,
                    format="WEBP",
                    quality=self.quality,
                    method=6,  # Best compression
                )
                
                logging.info(
                    "Downloaded and saved thumbnail for listing %s (%.1f KB)",
                    listing_id,
                    thumbnail_path.stat().st_size / 1024,
                )
                
                # Return relative path with forward slashes
                relative_path = str(thumbnail_path.relative_to(self.base_path.parent))
                return relative_path.replace(os.sep, "/")
                
        except httpx.HTTPError as exc:
            logging.error("Failed to download image for listing %s: %s", listing_id, exc)
            return None
        except Exception as exc:
            logging.error("Failed to process image for listing %s: %s", listing_id, exc)
            return None
    
    async def download_from_og_meta(
        self,
        listing_id: str,
        html_content: str,
        timeout: float = 30.0,
    ) -> Optional[str]:
        """
        Extract og:image from HTML and download it.
        
        Args:
            listing_id: Unique identifier for the listing
            html_content: HTML content containing og:image meta tag
            timeout: Request timeout in seconds
            
        Returns:
            Relative path to the saved thumbnail, or None if failed
        """
        from bs4 import BeautifulSoup
        
        try:
            soup = BeautifulSoup(html_content, "html.parser")
            
            # Try to find og:image meta tag
            og_image = soup.find("meta", property="og:image")
            if not og_image:
                og_image = soup.find("meta", attrs={"property": "og:image"})
            
            if not og_image or not og_image.get("content"):
                logging.warning("No og:image found for listing %s", listing_id)
                return None
            
            image_url = og_image["content"]
            
            # Handle relative URLs
            if image_url.startswith("//"):
                image_url = "https:" + image_url
            elif image_url.startswith("/"):
                logging.warning("Relative og:image URL found, cannot download: %s", image_url)
                return None
            
            return await self.download_and_save(listing_id, image_url, timeout)
            
        except Exception as exc:
            logging.error("Failed to extract og:image for listing %s: %s", listing_id, exc)
            return None
