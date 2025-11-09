# FILE: ./src/tools/web_extractor_tool.py
"""
Web Extraction Tool for parsing arbitrary web pages and extracting structured data.
Supports property listings, LinkedIn profiles, and general web content.
"""
import json
import re
from typing import Dict, Any, Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class WebExtractorInput(BaseModel):
    url: str = Field(..., description="The URL to fetch and extract data from")
    extract_type: str | None = Field(
        default="auto",
        description="Type of extraction: 'auto', 'property', 'profile', or 'general'"
    )


class WebExtractorTool(BaseTool):
    name: str = "web_extractor_tool"
    description: str = (
        "Fetches and extracts structured data from web pages. "
        "Supports property listings (location, price, size), "
        "LinkedIn profiles (job title, company), and general content extraction. "
        "Returns a JSON summary that should be confirmed by the user before proceeding."
    )
    args_schema: type[BaseModel] = WebExtractorInput

    def _run(self, url: str, extract_type: str | None = "auto") -> str:
        """
        Fetches the URL and extracts structured data.
        
        Args:
            url: The URL to fetch
            extract_type: Type of extraction ('auto', 'property', 'profile', 'general')
            
        Returns:
            JSON string with extracted data
        """
        try:
            # Fetch the page
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            
            with httpx.Client(timeout=30.0, follow_redirects=True) as client:
                response = client.get(url, headers=headers)
                response.raise_for_status()
            
            # Parse HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Detect page type if auto
            if extract_type == "auto":
                extract_type = self._detect_page_type(url, soup)
            
            # Extract based on type
            if extract_type == "property":
                result = self._extract_property_data(url, soup, response.text)
            elif extract_type == "profile":
                result = self._extract_profile_data(url, soup, response.text)
            else:
                result = self._extract_general_data(url, soup, response.text)
            
            # Add metadata
            result["url"] = url
            result["extract_type"] = extract_type
            result["confirmed"] = False
            result["status"] = "success"
            
            return json.dumps(result, indent=2, ensure_ascii=False)
            
        except httpx.HTTPError as e:
            error_result = {
                "url": url,
                "status": "error",
                "error": f"HTTP error: {str(e)}",
                "confirmed": False
            }
            return json.dumps(error_result, indent=2)
        except Exception as e:
            error_result = {
                "url": url,
                "status": "error",
                "error": f"Extraction error: {str(e)}",
                "confirmed": False
            }
            return json.dumps(error_result, indent=2)

    def _detect_page_type(self, url: str, soup: BeautifulSoup) -> str:
        """Auto-detect the type of page based on URL and content."""
        url_lower = url.lower()
        text_lower = soup.get_text().lower()
        
        # Check for property listing indicators
        property_keywords = ['rent', 'rental', 'apartment', 'house', 'property', 
                            'real estate', 'pararius', 'funda', 'huurwoningen']
        if any(kw in url_lower or kw in text_lower for kw in property_keywords):
            return "property"
        
        # Check for profile/LinkedIn indicators
        profile_keywords = ['linkedin', 'profile', 'resume', 'cv']
        if any(kw in url_lower for kw in profile_keywords):
            return "profile"
        
        return "general"

    def _extract_property_data(self, url: str, soup: BeautifulSoup, html: str) -> Dict[str, Any]:
        """Extract structured data from property listing pages."""
        result = {}
        
        # Extract title
        title = None
        if soup.title:
            title = soup.title.string
        elif soup.find('h1'):
            title = soup.find('h1').get_text(strip=True)
        result["title"] = title
        
        # Extract price
        price = self._extract_price(soup, html)
        result["price"] = price
        
        # Extract size
        size_m2 = self._extract_size(soup, html)
        result["size_m2"] = size_m2
        
        # Extract location
        location = self._extract_location(soup, html)
        result["location"] = location
        
        # Extract address details
        result["street"] = self._extract_street(soup, html)
        result["city"] = self._extract_city(soup, html, location)
        result["postal_code"] = self._extract_postal_code(soup, html)
        
        # Extract property type
        result["housing_type"] = self._extract_housing_type(soup, html)
        
        # Extract bedrooms
        result["bedrooms"] = self._extract_bedrooms(soup, html)
        
        # Extract furnished status
        result["furnished"] = self._extract_furnished(soup, html)
        
        # Extract pets policy
        result["pets_allowed"] = self._extract_pets_policy(soup, html)
        
        # Extract description
        result["description"] = self._extract_description(soup)
        
        # Commute target (default null, user can fill)
        result["commute_target"] = None
        
        return result

    def _extract_profile_data(self, url: str, soup: BeautifulSoup, html: str) -> Dict[str, Any]:
        """Extract structured data from profile pages (LinkedIn, etc.)."""
        result = {}
        
        # Extract name
        result["name"] = self._extract_name(soup)
        
        # Extract job title
        result["job_title"] = self._extract_job_title(soup, html)
        
        # Extract company
        result["company"] = self._extract_company(soup, html)
        
        # Extract location
        result["location"] = self._extract_location(soup, html)
        
        # Estimate salary (heuristic-based)
        result["estimated_salary_range"] = self._estimate_salary(
            result.get("job_title"),
            result.get("company"),
            result.get("location")
        )
        
        # Extract skills
        result["skills"] = self._extract_skills(soup, html)
        
        # Extract experience
        result["experience_years"] = self._extract_experience(soup, html)
        
        return result

    def _extract_general_data(self, url: str, soup: BeautifulSoup, html: str) -> Dict[str, Any]:
        """Extract general structured data from any page."""
        result = {}
        
        # Extract title
        result["title"] = soup.title.string if soup.title else None
        
        # Extract meta description
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        result["description"] = meta_desc.get('content', '') if meta_desc else None
        
        # Extract headings
        headings = [h.get_text(strip=True) for h in soup.find_all(['h1', 'h2', 'h3'])[:5]]
        result["headings"] = headings
        
        # Extract main text (first 500 chars)
        text = soup.get_text(separator=' ', strip=True)
        result["text_preview"] = text[:500] + "..." if len(text) > 500 else text
        
        # Extract links
        links = [a.get('href') for a in soup.find_all('a', href=True)[:10]]
        result["links"] = links
        
        return result

    # Helper extraction methods
    
    def _extract_price(self, soup: BeautifulSoup, html: str) -> Optional[int]:
        """Extract price from page."""
        # Common price patterns
        patterns = [
            r'€\s*([0-9.,]+)',
            r'([0-9.,]+)\s*€',
            r'price["\s:]+([0-9.,]+)',
            r'rent["\s:]+([0-9.,]+)',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, html, re.IGNORECASE)
            for match in matches:
                try:
                    # Clean and convert
                    cleaned = match.replace('.', '').replace(',', '').strip()
                    price = int(cleaned)
                    # Reasonable rent range: 500-5000 EUR
                    if 500 <= price <= 5000:
                        return price
                except (ValueError, AttributeError):
                    continue
        return None

    def _extract_size(self, soup: BeautifulSoup, html: str) -> Optional[int]:
        """Extract size in square meters."""
        patterns = [
            r'([0-9]+)\s*m[²2]',
            r'([0-9]+)\s*square\s*meters',
            r'size["\s:]+([0-9]+)',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, html, re.IGNORECASE)
            for match in matches:
                try:
                    size = int(match)
                    # Reasonable size range: 20-300 m²
                    if 20 <= size <= 300:
                        return size
                except (ValueError, AttributeError):
                    continue
        return None

    def _extract_location(self, soup: BeautifulSoup, html: str) -> Optional[str]:
        """Extract location/address."""
        # Try meta tags first
        meta_location = soup.find('meta', attrs={'property': 'og:locality'})
        if meta_location:
            return meta_location.get('content', '').strip()
        
        # Try common location patterns
        location_elem = soup.find(['span', 'div', 'p'], class_=re.compile(r'location|address|city', re.I))
        if location_elem:
            return location_elem.get_text(strip=True)
        
        # Pattern matching
        patterns = [
            r'(?:in|at)\s+([A-Z][a-zA-Z\s]+(?:Amsterdam|Rotterdam|Utrecht|The Hague|Leiden|Delft|Eindhoven))',
            r'(Amsterdam|Rotterdam|Utrecht|The Hague|Leiden|Delft|Eindhoven)[,\s]',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                return match.group(1).strip()
        
        return None

    def _extract_street(self, soup: BeautifulSoup, html: str) -> Optional[str]:
        """Extract street address."""
        street_elem = soup.find(['span', 'div'], class_=re.compile(r'street', re.I))
        if street_elem:
            return street_elem.get_text(strip=True)
        return None

    def _extract_city(self, soup: BeautifulSoup, html: str, location: Optional[str]) -> Optional[str]:
        """Extract city name."""
        if location:
            # Extract city from location
            cities = ['Amsterdam', 'Rotterdam', 'Utrecht', 'The Hague', 'Leiden', 'Delft', 'Eindhoven']
            for city in cities:
                if city.lower() in location.lower():
                    return city
        return location

    def _extract_postal_code(self, soup: BeautifulSoup, html: str) -> Optional[str]:
        """Extract postal code."""
        pattern = r'\b([0-9]{4}\s*[A-Z]{2})\b'
        match = re.search(pattern, html)
        return match.group(1) if match else None

    def _extract_housing_type(self, soup: BeautifulSoup, html: str) -> Optional[str]:
        """Extract housing type."""
        types = ['apartment', 'house', 'studio', 'room', 'flat']
        text_lower = html.lower()
        for housing_type in types:
            if housing_type in text_lower:
                return housing_type.capitalize()
        return None

    def _extract_bedrooms(self, soup: BeautifulSoup, html: str) -> Optional[int]:
        """Extract number of bedrooms."""
        patterns = [
            r'([0-9]+)\s*bedroom',
            r'([0-9]+)\s*bed',
            r'bedroom[s]?\s*[:\s]+([0-9]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1))
                except (ValueError, AttributeError):
                    continue
        return None

    def _extract_furnished(self, soup: BeautifulSoup, html: str) -> Optional[str]:
        """Extract furnished status."""
        text_lower = html.lower()
        if 'unfurnished' in text_lower:
            return 'Unfurnished'
        elif 'semi-furnished' in text_lower or 'semi furnished' in text_lower:
            return 'Semi-furnished'
        elif 'furnished' in text_lower:
            return 'Furnished'
        return None

    def _extract_pets_policy(self, soup: BeautifulSoup, html: str) -> Optional[bool]:
        """Extract pets policy."""
        text_lower = html.lower()
        if 'pets allowed' in text_lower or 'pet friendly' in text_lower:
            return True
        elif 'no pets' in text_lower or 'pets not allowed' in text_lower:
            return False
        return None

    def _extract_description(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract property description."""
        desc_elem = soup.find(['div', 'p'], class_=re.compile(r'description|summary', re.I))
        if desc_elem:
            text = desc_elem.get_text(strip=True)
            return text[:500] + "..." if len(text) > 500 else text
        return None

    def _extract_name(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract person name."""
        name_elem = soup.find(['h1', 'span'], class_=re.compile(r'name', re.I))
        if name_elem:
            return name_elem.get_text(strip=True)
        return None

    def _extract_job_title(self, soup: BeautifulSoup, html: str) -> Optional[str]:
        """Extract job title."""
        title_elem = soup.find(['h2', 'span', 'div'], class_=re.compile(r'title|position|role', re.I))
        if title_elem:
            return title_elem.get_text(strip=True)
        return None

    def _extract_company(self, soup: BeautifulSoup, html: str) -> Optional[str]:
        """Extract company name."""
        company_elem = soup.find(['span', 'div'], class_=re.compile(r'company|employer', re.I))
        if company_elem:
            return company_elem.get_text(strip=True)
        return None

    def _extract_skills(self, soup: BeautifulSoup, html: str) -> list[str]:
        """Extract skills list."""
        skills = []
        skills_section = soup.find(['section', 'div'], class_=re.compile(r'skills', re.I))
        if skills_section:
            skill_items = skills_section.find_all(['li', 'span'])
            skills = [item.get_text(strip=True) for item in skill_items[:10]]
        return skills

    def _extract_experience(self, soup: BeautifulSoup, html: str) -> Optional[int]:
        """Extract years of experience."""
        pattern = r'([0-9]+)\+?\s*years?\s*(?:of\s*)?experience'
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                pass
        return None

    def _estimate_salary(self, job_title: Optional[str], company: Optional[str], 
                        location: Optional[str]) -> Optional[Dict[str, int]]:
        """
        Heuristic-based salary estimation.
        Returns a range: {min: X, max: Y} in EUR per year.
        """
        if not job_title:
            return None
        
        title_lower = job_title.lower()
        
        # Base ranges by seniority and role
        if any(keyword in title_lower for keyword in ['senior', 'lead', 'principal', 'architect']):
            base_min, base_max = 70000, 100000
        elif any(keyword in title_lower for keyword in ['junior', 'associate', 'entry']):
            base_min, base_max = 35000, 50000
        else:
            base_min, base_max = 50000, 70000
        
        # Adjust by role type
        if any(keyword in title_lower for keyword in ['engineer', 'developer', 'programmer']):
            base_min += 5000
            base_max += 10000
        elif any(keyword in title_lower for keyword in ['manager', 'director']):
            base_min += 10000
            base_max += 20000
        
        # Location adjustment (Netherlands)
        if location and 'amsterdam' in location.lower():
            base_min += 5000
            base_max += 8000
        
        return {"min": base_min, "max": base_max, "currency": "EUR"}


# Create singleton instance
web_extractor_tool = WebExtractorTool()
