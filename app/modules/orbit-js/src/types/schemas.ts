/**
 * Zod Schemas for Input Validation
 * 
 * Ported from Python Pydantic schemas
 */

import { z } from 'zod';
import { OrbitMode } from './index';

// Orbit chat request schema
export const OrbitChatRequestSchema = z.object({
  message: z.string()
    .min(1, 'Message is required')
    .max(500, 'Message must be less than 500 characters'),
  session_id: z.string().optional(),
  latitude: z.number().min(-90).max(90).optional(),
  longitude: z.number().min(-180).max(180).optional(),
  mode: z.enum([OrbitMode.CHAT, OrbitMode.FIND, OrbitMode.PLAN])
    .default(OrbitMode.CHAT),
});

// Orbit offer card schema
export const OrbitOfferCardSchema = z.object({
  id: z.string(),
  title: z.string(),
  description: z.string(),
  merchant_name: z.string(),
  address: z.string().optional(),
  latitude: z.number().optional(),
  longitude: z.number().optional(),
  distance_km: z.number().optional(),
  tags: z.record(z.any()).default({}),
  highlights: z.array(z.string()).default([]),
});

// Orbit chat response schema
export const OrbitChatResponseSchema = z.object({
  content: z.string(),
  plans: z.array(OrbitOfferCardSchema).default([]),
  session_id: z.string(),
  metadata: z.object({
    intent: z.string().optional(),
    total_retrieved: z.number().optional(),
    total_recommended: z.number().optional(),
    conversation_length: z.number().optional(),
    error: z.string().optional(),
  }).optional(),
});

// Intent analysis schema
export const IntentAnalysisSchema = z.object({
  intent: z.enum(['chat', 'offers', 'offers_vague']),
  needs_retrieval: z.boolean(),
  confidence: z.number().min(0).max(1),
});

// Conversation message schema
export const ConversationMessageSchema = z.object({
  role: z.enum(['user', 'assistant']),
  content: z.string(),
  timestamp: z.string(),
});

// LLM response schema
export const LLMResponseSchema = z.object({
  content: z.string(),
  plans: z.array(z.object({
    id: z.string(),
    title: z.string(),
    description: z.string(),
    tags: z.record(z.any()).default({}),
    highlights: z.array(z.string()).default([]),
  })).default([]),
});

// Offer retrieval filters
export const OfferFiltersSchema = z.object({
  categories: z.array(z.string()).optional(),
  maxPrice: z.number().optional(),
  minDiscount: z.number().optional(),
  location: z.string().optional(),
});

// Rate limit check result
export const RateLimitResultSchema = z.object({
  allowed: z.boolean(),
  remaining: z.number(),
  resetAt: z.date(),
  reason: z.string().optional(),
});

// Export types derived from schemas
export type OrbitChatRequestInput = z.infer<typeof OrbitChatRequestSchema>;
export type OrbitOfferCardInput = z.infer<typeof OrbitOfferCardSchema>;
export type OrbitChatResponseInput = z.infer<typeof OrbitChatResponseSchema>;
export type IntentAnalysisInput = z.infer<typeof IntentAnalysisSchema>;
