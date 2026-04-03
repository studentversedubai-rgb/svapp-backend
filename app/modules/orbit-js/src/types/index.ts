/**
 * SV Orbit TypeScript Types
 * 
 * Ported from Python schemas.py
 */

// Orbit AI behavior modes
export enum OrbitMode {
  CHAT = 'chat',  // Casual conversation, witty persona
  FIND = 'find',  // Focused discovery, specific recommendations
  PLAN = 'plan',  // Structured itinerary creation
}

// Offer card in Orbit response
export interface OrbitOfferCard {
  id: string;
  title: string;
  description: string;
  merchant_name: string;
  address?: string;
  latitude?: number;
  longitude?: number;
  distance_km?: number;
  tags: Record<string, any>;
  highlights: string[];
}

// Chat request
export interface OrbitChatRequest {
  message: string;
  session_id?: string;
  latitude?: number;
  longitude?: number;
  mode: OrbitMode;
}

// Chat response
export interface OrbitChatResponse {
  content: string;
  plans: OrbitOfferCard[];
  session_id: string;
  metadata?: {
    intent?: string;
    total_retrieved?: number;
    total_recommended?: number;
    conversation_length?: number;
    error?: string;
  };
}

// Intent analysis result
export interface IntentAnalysis {
  intent: 'chat' | 'offers' | 'offers_vague';
  needs_retrieval: boolean;
  confidence: number;
}

// Conversation message
export interface ConversationMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
}

// LLM response format
export interface LLMResponse {
  content: string;
  plans: Array<{
    id: string;
    title: string;
    description: string;
    tags: Record<string, any>;
    highlights: string[];
  }>;
}

// Offer from database
export interface Offer {
  id: string;
  title: string;
  description: string;
  merchant: {
    name: string;
    address?: string;
    latitude?: number;
    longitude?: number;
  };
  category?: {
    name: string;
  };
  discount_value?: string;
  original_price?: number;
  discounted_price?: number;
  is_active: boolean;
  _relevance_score?: number;
  distance_km?: number;
}

// Ticket from database
export interface Ticket {
  id: string;
  merchant_name: string;
  location?: string;
  latitude?: number;
  longitude?: number;
  ticket_details?: string;
  market_price_adult?: number;
  our_price?: number;
  is_active: boolean;
}

// User context for auth
export interface UserContext {
  id: string;
  email?: string;
  [key: string]: any;
}

// Rate limit info
export interface RateLimitInfo {
  allowed: boolean;
  remaining: number;
  resetAt: Date;
}

// Circuit breaker state
export interface CircuitBreakerState {
  failures: number;
  openUntil: number;
  isOpen: boolean;
}
