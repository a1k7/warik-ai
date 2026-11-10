export interface User {
  id: number;
  email: string;
  name: string;
  created_at: string;
}

export interface ToolCall {
  tool_name: string;
  args: Record<string, any>;
  success: boolean;
  message: string;
}

export interface HotelItem {
  name: string;
  address: string;
  map_url: string;
  price: string | null;
}

export interface FlightItem {
  airline: string;
  flight_number: string;
  departure: string;
  arrival: string;
  price: string;
  url: string;
  status: string;
}

export interface FoodItem {
  name: string;
  address: string;
  cuisine: string;
  rating: number | null;
  distance_km: number | null;
  maps_url: string;
  zomato_url: string;
  swiggy_url: string;
  status: string;
}

// ... (keep existing User, ToolCall, HotelItem, FlightItem, FoodItem)

export type DaySlot = 'morning' | 'afternoon' | 'evening';
export type BudgetClass = 'VERIFIED_QUOTE' | 'USER_PROVIDED' | 'ESTIMATE' | 'UNAVAILABLE';

export interface VerificationFlags {
  place_exists: boolean;
  location_verified: boolean;
  category_verified: boolean;
  tourism_suitability_verified: boolean;
  hours_verified: boolean;
  price_verified: boolean;
}

export interface ItineraryActivity {
  name: string;
  description: string;
  slot: DaySlot;
  suggested_time?: string | null;
  duration_min?: number | null;
  opening_hours?: string | null;
  entry_fee?: string | null;
  lat?: number | null;
  lon?: number | null;
  source?: string;
  map_url?: string | null;
  category?: string | null;
  verification: VerificationFlags;
}

// ... (keep MealSuggestion, ItineraryDay)

export interface TripBudget {
  items: BudgetItem[];
  user_budget?: number | null;
  travellers: number;
  total_estimate?: number | null;
  remaining?: number | null;
  per_person?: number | null;
  excludes: string[];
  is_partial: boolean;
}

// ... (keep AdvancedItinerary, StructuredData, AgentResponse, ChatMessage)

export interface MealSuggestion {
  name: string;
  category?: string | null;
  address?: string | null;
  map_url?: string | null;
  source?: string;
}

export interface ItineraryDay {
  day: number;
  date?: string | null;
  title: string;
  morning: ItineraryActivity[];
  afternoon: ItineraryActivity[];
  evening: ItineraryActivity[];
  meal_suggestions: MealSuggestion[];
  transport_notes: string[];
  daily_budget_note?: string | null;
}

export interface BudgetItem {
  category: string;
  amount?: number | null;
  currency: string;
  classification: BudgetClass;
  note?: string | null;
}



export interface AdvancedItinerary {
  type: 'advanced_itinerary';
  destination: string;
  travellers: number;
  days: ItineraryDay[];
  budget: TripBudget;
  notes: string[];
  generated_at: string;
}

export interface StructuredData {
  type:
    | 'hotel_list'
    | 'flight_list'
    | 'food_list'
    | 'cab_handoff'
    | 'advanced_itinerary';
  items?: (HotelItem | FlightItem | FoodItem)[];
  city?: string;
  search_context?: any;
  // advanced_itinerary fields
  destination?: string;
  travellers?: number;
  days?: ItineraryDay[];
  budget?: TripBudget;
  notes?: string[];
}

export interface AgentResponse {
  reply: string;
  tool_calls: ToolCall[];
  needs_confirmation: boolean;
  confirmation_token?: string;
  pending_tool?: string;
  pending_args?: Record<string, any>;
  structured_data?: StructuredData;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  agentData?: AgentResponse;
}
// ... existing types ...

export interface Conversation {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  structured_data?: StructuredData;
  created_at: string;
}
