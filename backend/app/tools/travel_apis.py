import httpx
import json
import subprocess
import re
from urllib.parse import quote
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from app.tools.base import BaseTool, ToolContext, ToolResult
from app.core.config import settings
from app.tools.travel_models import FlightResult, HotelResult, PlaceResult, CabResult

# Helper: Convert City Names to IATA Codes
CITY_TO_IATA = {
    "MUMBAI": "BOM", "DELHI": "DEL", "NEW DELHI": "DEL", "BENGALURU": "BLR",
    "BANGALORE": "BLR", "CHENNAI": "MAA", "KOLKATA": "CCU", "HYDERABAD": "HYD",
    "PUNE": "PNQ", "AHMEDABAD": "AMD", "GOA": "GOI", "JAIPUR": "JAI",
    "LUCKNOW": "LKO", "BHOPAL": "BHO", "INDORE": "IDR", "PATNA": "PAT",
    "COCHIN": "COK", "KOCHI": "COK", "TRIVANDRUM": "TRV", "GUWAHATI": "GAU",
}

def get_iata(city: str) -> str:
    city_upper = city.upper().strip()
    return CITY_TO_IATA.get(city_upper, city_upper)

# ==========================================
# 1. FLIGHTS - REAL GOOGLE FLIGHTS DATA (via trvl)
# ==========================================
class FlightInput(BaseModel):
    origin: str = Field(..., description="Origin city or IATA code")
    destination: str = Field(..., description="Destination city or IATA code")
    date: str = Field(..., description="YYYY-MM-DD")

class RealFlightSearchTool(BaseTool):
    name = "search_flights_real"
    description = "Find real-time flights from Google Flights with accurate airline names and schedules."
    input_schema = FlightInput
    requires_confirmation = False

    def execute(self, ctx: ToolContext, params: FlightInput) -> ToolResult:
        origin_iata = get_iata(params.origin)
        dest_iata = get_iata(params.destination)

        try:
            result = subprocess.run(
                ["trvl", "flights", origin_iata, dest_iata, params.date, "--format", "json"],
                capture_output=True, text=True, check=True, timeout=20.0
            )
            data = json.loads(result.stdout)
            
            if isinstance(data, list):
                flights = data
            else:
                flights = data.get("flights") or data.get("results") or data.get("itineraries") or []
            
            if not flights:
                return ToolResult(success=True, message=f"No flights found from {origin_iata} to {dest_iata} on {params.date}.")

            message = f"✈️ **Real Flights from {origin_iata} to {dest_iata}** ({params.date}):\n\n"
            results = []

            for f in flights[:5]:
                legs = f.get("legs", [])
                if not legs: continue
                
                first_leg = legs[0]
                last_leg = legs[-1]
                
                airline = first_leg.get("airline", "Unknown Airline")
                flight_num = first_leg.get("flight_number", "")
                dep_time = first_leg.get("departure_time", "").replace("T", " ")[5:16]
                arr_time = last_leg.get("arrival_time", "").replace("T", " ")[5:16]
                
                price = f.get("price", 0)
                currency = f.get("currency", "INR")
                price_str = f"₹{price:,.2f}" if price else "Check link"
                booking_url = f.get("booking_url", "")
                stops = f.get("stops", 0)
                stops_str = "Non-stop" if stops == 0 else f"{stops} stop(s)"

                results.append(FlightResult(
                    airline=airline, flight_number=flight_num,
                    departure_time=dep_time, arrival_time=arr_time,
                    price=price_str, currency=currency, booking_url=booking_url
                ))

                message += f"🛫 **{airline}** ({flight_num}) — {stops_str}\n"
                message += f"   Depart: {dep_time} | Arrive: {arr_time}\n"
                message += f"   Price: **{price_str}** | [Book Now]({booking_url})\n\n"

            return ToolResult(success=True, message=message, data={"flights": [r.model_dump() for r in results]})
        except subprocess.TimeoutExpired:
            return ToolResult(success=False, message="Flight search timed out. Please try again.")
        except subprocess.CalledProcessError as e:
            return ToolResult(success=False, message=f"trvl command failed: {e.stderr}")
        except Exception as e:
            return ToolResult(success=False, message=f"Flight search error: {str(e)}")


# ==========================================
# 2. HOTELS - STAYAPI
# ==========================================
class HotelInput(BaseModel):
    city: str = Field(..., description="City name")
    check_in: str = Field(..., description="YYYY-MM-DD")
    check_out: str = Field(..., description="YYYY-MM-DD")

class StayApiHotelTool(BaseTool):
    name = "search_hotels_stayapi"
    description = "Find real-time hotel prices with images and booking links."
    input_schema = HotelInput
    requires_confirmation = False

    def execute(self, ctx: ToolContext, params: HotelInput) -> ToolResult:
        if not settings.stayapi_key:
            return ToolResult(success=False, message="STAYAPI_KEY is missing in .env")
        if params.check_out <= params.check_in:
            return ToolResult(success=False, message="Check-out date must be after check-in date.")

        headers = {"Authorization": f"Bearer {settings.stayapi_key}"}
        params_dict = {"destination": params.city, "check_in": params.check_in, "check_out": params.check_out, "adults": 2}

        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.get("https://api.stayapi.com/v1/booking/search", headers=headers, params=params_dict)
                response.raise_for_status()
                data = response.json()

            hotels = data.get("hotels", []) or data.get("results", [])
            if not hotels:
                return ToolResult(success=True, message=f"No hotels found in {params.city} for those dates.")

            message = f"🏨 **Hotels in {params.city}** ({params.check_in} to {params.check_out}):\n\n"
            results = []

            for h in hotels[:5]:
                name = h.get("name", "Unknown Hotel")
                price = h.get("price", "N/A")
                currency = h.get("currency", "INR")
                rating = h.get("rating", "N/A")
                image = h.get("image_url", "")
                booking_url = h.get("booking_url", "")
                map_url = f"https://www.google.com/maps/search/?api=1&query={quote(name + ' ' + params.city)}"

                results.append(HotelResult(
                    name=name, price_per_night=f"{price} {currency}", rating=str(rating),
                    image_url=image, booking_url=booking_url, map_url=map_url
                ))

                message += f"🏨 **{name}** (Rating: {rating}⭐)\n"
                message += f"   Price: **{price} {currency}** / night\n"
                if image:
                    message += f"   [View Image]({image})\n"
                message += f"   [Book Now]({booking_url}) | [View on Map]({map_url})\n\n"

            return ToolResult(success=True, message=message, data={"hotels": [r.model_dump() for r in results]})
        except Exception as e:
            return ToolResult(success=False, message=f"StayAPI hotel search error: {str(e)}")

# ==========================================
# 3. GEOAPIFY - PLACES (Validated & Ranked)
# ==========================================
class PlacesInput(BaseModel):
    location: Optional[str] = Field(default=None, description="City or area, e.g., 'Mumbai' or 'Bhopal'")
    category: str = Field(default="restaurant", description="restaurant, cafe, hotel, or tourist_spot")
    query: Optional[str] = Field(default=None, description="Fallback if location is missing")

class GeoapifyPlacesTool(BaseTool):
    name = "search_places_geoapify"
    description = "Find real places, restaurants, and tourist spots in India using Geoapify."
    input_schema = PlacesInput
    requires_confirmation = False

    def execute(self, ctx: ToolContext, params: PlacesInput) -> ToolResult:
        if not settings.geoapify_api_key:
            return ToolResult(success=False, message="GEOAPIFY_API_KEY is missing in .env")

        # Fallback: If the LLM forgot to extract 'location', try to guess it from 'query'
        final_location = params.location
        if not final_location and params.query:
            clean_query = re.sub(r'(?i)(find|best|good|some|restaurants?|cafes?|hotels?|in|near)', '', params.query).strip()
            final_location = clean_query if clean_query else params.query

        if not final_location:
            return ToolResult(success=False, message="Please specify a city or location.")

        cat_map = {
            "restaurant": "catering.restaurant",
            "cafe": "catering.cafe",
            "hotel": "accommodation.hotel",
            "tourist_spot": "tourism.sights",
            "attraction": "tourism.attraction"
        }
        geo_cat = cat_map.get(params.category.lower().strip(), "catering.restaurant")

        try:
            # 1. Geocode location
            geo_url = f"https://api.geoapify.com/v1/geocode/search?text={quote(final_location)}&limit=1&apiKey={settings.geoapify_api_key}"
            with httpx.Client(timeout=10.0) as client:
                geo_res = client.get(geo_url).json()
                if not geo_res.get("features"):
                    return ToolResult(success=False, message=f"Could not find the location '{final_location}'.")
                
                feature = geo_res["features"][0]
                lat = feature["properties"]["lat"]
                lon = feature["properties"]["lon"]
                city_name = feature["properties"].get("city", final_location)

                # 2. Places search (strict radius = 10km to prevent New Panvel showing up for Mumbai)
                places_url = (
                    f"https://api.geoapify.com/v2/places?categories={geo_cat}"
                    f"&filter=circle:{lon},{lat},10000" 
                    f"&limit=20&apiKey={settings.geoapify_api_key}"
                )
                places_res = client.get(places_url).json()

            raw_features = places_res.get("features", [])
            
            # 3. Validation & Deduplication Layer
            seen_ids = set()
            valid_places = []
            invalid_names = {"unknown place", "null", "undefined", "n/a", ""}

            for p in raw_features:
                props = p.get("properties", {})
                name = props.get("name", "").strip()
                place_id = props.get("place_id")
                address = props.get("address_line2", "")
                
                # Reject bad data
                if not name or name.lower() in invalid_names:
                    continue
                if not place_id or place_id in seen_ids:
                    continue
                if not address:
                    continue
                if not props.get("lat") or not props.get("lon"):
                    continue

                seen_ids.add(place_id)
                
                # Check if category matches exactly
                categories = props.get("categories", [])
                if not any(geo_cat in c for c in categories):
                    continue
                    
                valid_places.append({
                    "name": name,
                    "address": address,
                    "place_id": place_id,
                    "categories": categories
                })

            # 4. Ranking Layer (Keyword + Completeness)
            query_lower = (params.query or "").lower()
            
            def score_place(place):
                score = 0
                name_lower = place["name"].lower()
                # Boost if the query keyword is in the name
                if "veg" in query_lower and "veg" in name_lower: score += 10
                if "cafe" in query_lower and "cafe" in name_lower: score += 10
                if "bar" in query_lower and "bar" in name_lower: score += 10
                # Boost if address contains the city name (data completeness)
                if city_name.lower() in place["address"].lower(): score += 5
                return score

            valid_places.sort(key=score_place, reverse=True)

            # 5. Handle Empty or Fewer Results
            if not valid_places:
                return ToolResult(
                    success=True, 
                    message=f"I searched for {params.category}s near {city_name}, but couldn't find any verified matches. You might want to try expanding the search area."
                )
            
            # 6. Format Premium Output
            if len(valid_places) < 3:
                message = f"I only found {len(valid_places)} verified {params.category} near {city_name}, so I've listed them below:\n\n"
            else:
                message = f"📍 **Top Verified {params.category.capitalize()}s in {city_name}:**\n\n"

            results = []
            for p in valid_places[:5]:
                name = p["name"]
                address = p["address"]
                map_url = f"https://www.google.com/maps/search/?api=1&query={quote(name + ' ' + address)}"
                
                results.append(PlaceResult(name=name, address=address, map_url=map_url))
                
                message += f"**{name}**\n"
                message += f"📍 {address}\n"
                message += f"🔗 [View on Google Maps]({map_url})\n\n"

            message += "*Note: These results are ranked by location and data accuracy. Live ratings and review counts are not available via this mapping provider.*"

            return ToolResult(success=True, message=message, data={"places": [r.model_dump() for r in results]})
            
        except Exception as e:
            return ToolResult(success=False, message=f"Geoapify error: {str(e)}")


# ==========================================
# 4. CABS (Deep Links)
# ==========================================
class CabInput(BaseModel):
    pickup_location: str = Field(..., description="E.g., 'Bhopal Railway Station'")
    dropoff_location: str = Field(..., description="E.g., 'DB City Mall'")

class CabDeepLinkTool(BaseTool):
    name = "get_cab_links"
    description = "Generate a direct deep-link to book an Uber or Ola cab."
    input_schema = CabInput
    requires_confirmation = False

    def execute(self, ctx: ToolContext, params: CabInput) -> ToolResult:
        try:
            uber_link = f"https://m.uber.com/ul/?action=setPickup&pickup=my_location&dropoff[formatted_address]={quote(params.dropoff_location)}"
            ola_link = f"https://book.olacabs.com/?pickup_name={quote(params.pickup_location)}&drop_name={quote(params.dropoff_location)}"

            message = f"🚕 **Book a ride from {params.pickup_location} to {params.dropoff_location}:**\n\n"
            message += f"🟢 [Open in Uber]({uber_link})\n"
            message += f"🟡 [Open in Ola]({ola_link})\n\n"
            message += "*Note: Prices will be calculated live inside the app based on your current location.*"

            return ToolResult(success=True, message=message, data={"uber_link": uber_link, "ola_link": ola_link})
        except Exception as e:
            return ToolResult(success=False, message=f"Cab error: {str(e)}")