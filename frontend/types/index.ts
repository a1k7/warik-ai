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
  rating: number;
  review_count: number;
  price_range: string;
  image_url: string | null;
  maps_url: string;
  zomato_url: string;
  swiggy_url: string;
  status: string;
}

export interface StructuredData {
  type: 'hotel_list' | 'flight_list' | 'food_list';
  items: (HotelItem | FlightItem | FoodItem)[];
  city?: string;
  search_context?: any;
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
