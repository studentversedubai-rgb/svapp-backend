/**
 * Orbit Chat API Endpoint
 * 
 * Main streaming chat endpoint using Vercel AI SDK.
 * Handles chat requests with intent analysis, offer retrieval, and response generation.
 */

import { Request, Response } from 'express';
import { streamText } from 'ai';
import { createOpenAI } from '@ai-sdk/openai';
import { v4 as uuidv4 } from 'uuid';
import { config } from '../config';
import { getFullSystemPrompt, getIntentSystemPrompt } from '../core/prompts';
import { getConversationManager } from '../core/conversation';
import { getOfferRetrieval } from '../core/retrieval';
import { calculateDistance, sortOffersByDistance } from '../core/distance';
import { getCircuitBreaker } from '../middleware/circuitBreaker';
import { getRateLimiter } from '../middleware/rateLimiter';
import { OrbitMode, OrbitChatRequest, IntentAnalysis, Offer } from '../types';

/**
 * Analyze user intent
 */
async function analyzeIntent(message: string): Promise<IntentAnalysis> {
  const messageLower = message.toLowerCase().trim();
  
  const greetingPatterns = ['hi', 'hello', 'hey', 'yo', 'sup', "what's up", 'whats up', 'how are you', 'how r u', 'thanks', 'thank you', 'who are you'];
  const vaguePatterns = ['celebrate', 'recommendation', 'recommend', 'surprise me', 'show me something', 'what do you have', "i'm hungry", 'im hungry', 'looking for something', 'want something', 'any suggestions'];
  const offerPatterns = ['coffee', 'burger', 'pizza', 'gym', 'food', 'drink', 'restaurant', 'sushi', 'pasta', 'fitness', 'cinema', 'movie', 'spa'];
  
  if (greetingPatterns.some(word => messageLower.includes(word)) && messageLower.length < 30) {
    return { intent: 'chat', needs_retrieval: false, confidence: 0.85 };
  }
  
  if (vaguePatterns.some(phrase => messageLower.includes(phrase))) {
    return { intent: 'offers_vague', needs_retrieval: true, confidence: 0.8 };
  }
  
  if (offerPatterns.some(word => messageLower.includes(word))) {
    return { intent: 'offers', needs_retrieval: true, confidence: 0.75 };
  }
  
  if (['want', 'need', 'looking'].some(word => messageLower.includes(word))) {
    return { intent: 'offers_vague', needs_retrieval: true, confidence: 0.7 };
  }
  
  if (messageLower.length < 10) {
    return { intent: 'chat', needs_retrieval: false, confidence: 0.7 };
  }
  
  return { intent: 'chat', needs_retrieval: false, confidence: 0.6 };
}

/**
 * Build user prompt with offers context
 */
function buildUserPrompt(message: string, offers: Offer[]): string {
  const offersContext = offers.map(offer => ({
    id: offer.id,
    title: offer.title,
    description: offer.description,
    merchant_name: offer.merchant?.name || 'Unknown',
    category: offer.category?.name || 'General',
    discount_value: offer.discount_value || '',
    original_price: offer.original_price,
    discounted_price: offer.discounted_price,
    address: offer.merchant?.address,
    distance_km: offer.distance_km,
  }));

  const offersJson = JSON.stringify(offersContext, null, 2);

  return `User Query: "${message}"

Context Data (Real Database Results):
${offersJson}

Task:
1. Select the best offers from the Context Data above (up to 3) that best match the User Query.
2. Write a warm, enthusiastic intro message (2-3 sentences) — react to what they're looking for, express genuine excitement, and make them feel like you found something great for them. Sound like a friend, not a search result.
3. Return ONLY a JSON object in this EXACT format (no markdown, no code blocks):

{
  "content": "Your warm, excited intro text here...",
  "plans": [
     {
       "id": "OFFER_ID_FROM_CONTEXT",
       "title": "Merchant Name",
       "description": "Offer Title (e.g., 50% Off Coffee)",
       "tags": {"budget": "$", "time": "Open Now", "dietary": []},
       "highlights": ["50% OFF", "Student Friendly"]
     }
  ]
}

Remember: Use ONLY offer IDs from the Context Data above. Return clean JSON only.`;
}

/**
 * Parse LLM JSON response
 */
function parseLLMResponse(response: string): { content: string; plans: any[] } {
  try {
    let cleaned = response.trim();
    
    if (cleaned.startsWith('```json')) {
      cleaned = cleaned.slice(7);
    }
    if (cleaned.startsWith('```')) {
      cleaned = cleaned.slice(3);
    }
    if (cleaned.endsWith('```')) {
      cleaned = cleaned.slice(0, -3);
    }
    cleaned = cleaned.trim();

    const parsed = JSON.parse(cleaned);
    
    return {
      content: parsed.content || "Here's what I found for you! 🎯",
      plans: Array.isArray(parsed.plans) ? parsed.plans : [],
    };
  } catch (error) {
    console.error('Failed to parse LLM response:', error);
    return {
      content: "I found some offers but had trouble formatting them. Let me try again!",
      plans: [],
    };
  }
}

/**
 * Main chat handler
 */
export async function chatHandler(req: Request, res: Response): Promise<void> {
  const circuitBreaker = getCircuitBreaker();
  const rateLimiter = getRateLimiter();
  const conversationManager = getConversationManager();
  const retrieval = getOfferRetrieval();

  try {
    // Check feature flag
    if (!config.features.svOrbitEnabled) {
      res.status(503).json({ error: 'Service Unavailable', message: 'Orbit is currently unavailable' });
      return;
    }

    // Check circuit breaker
    if (circuitBreaker.isOpen()) {
      const remaining = circuitBreaker.getRemainingSeconds();
      res.status(503).json({ error: 'Service Unavailable', message: `Orbit temporarily unavailable. Retry in ${remaining}s.` });
      return;
    }

    // Parse request
    const body = req.body as OrbitChatRequest;
    const userId = req.user?.id;

    if (!userId) {
      res.status(401).json({ error: 'Unauthorized', message: 'User authentication required' });
      return;
    }

    if (!body.message?.trim()) {
      res.status(400).json({ error: 'Bad Request', message: 'Message is required' });
      return;
    }

    if (body.message.length > 500) {
      res.status(400).json({ error: 'Bad Request', message: 'Message must be less than 500 characters' });
      return;
    }

    // Rate limiting
    const rateCheck = await rateLimiter.checkLimits(userId);
    if (!rateCheck.allowed) {
      res.status(429).json({ error: 'Too Many Requests', message: rateCheck.reason });
      return;
    }

    // Generate session ID
    const sessionId = body.session_id || uuidv4();
    const mode = body.mode || OrbitMode.CHAT;

    // Load conversation history
    const history = await conversationManager.formatHistoryForLLM(userId, sessionId, 10);

    // Determine intent and retrieval needs
    let intent = 'offers';
    let needsRetrieval = true;
    
    if (mode === OrbitMode.CHAT) {
      const analysis = await analyzeIntent(body.message);
      intent = analysis.intent;
      needsRetrieval = analysis.needs_retrieval;
    }

    // Save user message
    await conversationManager.addMessage(userId, sessionId, 'user', body.message);

    // Setup OpenRouter
    const openrouter = createOpenAI({
      baseURL: config.openrouter.baseUrl,
      apiKey: config.openrouter.apiKey,
    });

    let responseContent = '';
    let plans: any[] = [];
    let totalRetrieved = 0;

    if (needsRetrieval && (intent === 'offers' || intent === 'offers_vague')) {
      // Determine search query
      let searchQuery = body.message;
      if (intent === 'offers_vague') {
        searchQuery = `${body.message} food drinks entertainment`;
      } else if (mode === OrbitMode.PLAN) {
        searchQuery = `${body.message} food drinks coffee entertainment activities beauty salon fitness`;
      }

      // Retrieve offers
      const offers = await retrieval.retrieveOffers(searchQuery, undefined, config.orbit.maxResults);
      totalRetrieved = offers.length;

      if (offers.length > 0) {
        // Calculate distances if user location provided
        let processedOffers = offers;
        if (body.latitude && body.longitude) {
          processedOffers = offers.map(offer => {
            if (offer.merchant?.latitude && offer.merchant?.longitude) {
              const dist = calculateDistance(body.latitude!, body.longitude!, offer.merchant.latitude, offer.merchant.longitude);
              return { ...offer, distance_km: dist };
            }
            return offer;
          });
          processedOffers = sortOffersByDistance(processedOffers);
        }

        // Build user prompt with offers
        const userPrompt = buildUserPrompt(body.message, processedOffers);
        const systemPrompt = getFullSystemPrompt(mode);

        // Stream response with offers
        const messages = [
          { role: 'system' as const, content: systemPrompt },
          ...history.slice(-6).map(msg => ({ role: msg.role, content: msg.content })),
          { role: 'user' as const, content: userPrompt },
        ];

        const model = openrouter.languageModel(config.openrouter.model);
        const result = streamText({ model, messages, temperature: 0.7, maxOutputTokens: 900 });

        res.setHeader('Content-Type', 'text/plain; charset=utf-8');
        res.setHeader('Transfer-Encoding', 'chunked');
        res.setHeader('X-Session-ID', sessionId);

        for await (const chunk of result.textStream) {
          responseContent += chunk;
          res.write(chunk);
        }

        // Parse the response
        const parsed = parseLLMResponse(responseContent);
        responseContent = parsed.content;
        plans = parsed.plans;

        // Validate plans against retrieved offers
        const offersById = new Map(processedOffers.map(o => [o.id, o]));
        const validatedPlans = [];
        for (const plan of plans) {
          const realOffer = offersById.get(plan.id);
          if (realOffer) {
            validatedPlans.push({
              ...plan,
              merchant_name: realOffer.merchant?.name || 'Unknown',
              address: realOffer.merchant?.address,
              latitude: realOffer.merchant?.latitude,
              longitude: realOffer.merchant?.longitude,
              distance_km: realOffer.distance_km,
            });
          }
        }
        plans = validatedPlans;

        // Send JSON with plans at the end of the stream
        res.write('\n__JSON__\n');
        res.write(JSON.stringify({ plans: validatedPlans }));
        res.end();
      } else {
        // No offers found
        responseContent = "Hmm, I couldn't find any offers matching that right now. 🤔 Want to try asking about something else? Like coffee, food, or entertainment?";
        res.json({
          content: responseContent,
          plans: [],
          session_id: sessionId,
          metadata: { intent, total_retrieved: 0, total_recommended: 0 },
        });
      }
    } else {
      // Pure conversation - no offers needed
      const systemPrompt = getFullSystemPrompt(mode);
      const messages = [
        { role: 'system' as const, content: systemPrompt },
        ...history.map(msg => ({ role: msg.role, content: msg.content })),
        { role: 'user' as const, content: body.message },
      ];

      const model = openrouter.languageModel(config.openrouter.model);
      const result = streamText({ model, messages, temperature: 0.85, maxOutputTokens: 200 });

      res.setHeader('Content-Type', 'text/plain; charset=utf-8');
      res.setHeader('Transfer-Encoding', 'chunked');
      res.setHeader('X-Session-ID', sessionId);

      for await (const chunk of result.textStream) {
        responseContent += chunk;
        res.write(chunk);
      }

      // Send empty JSON for chat mode
      res.write('\n__JSON__\n');
      res.write(JSON.stringify({ plans: [] }));
      res.end();
    }

    // Save assistant response
    await conversationManager.addMessage(userId, sessionId, 'assistant', responseContent);

    // Reset circuit breaker on success
    circuitBreaker.recordSuccess();

  } catch (error) {
    console.error('Chat handler error:', error);
    circuitBreaker.recordFailure();

    if (!res.headersSent) {
      res.status(500).json({
        error: 'Internal Server Error',
        message: error instanceof Error ? error.message : 'Unknown error',
      });
    } else {
      res.end();
    }
  }
}

/**
 * Health check handler
 */
export function healthHandler(req: Request, res: Response): void {
  const circuitBreaker = getCircuitBreaker();
  
  if (!config.features.svOrbitEnabled) {
    res.status(503).json({ status: 'unavailable', service: 'orbit', message: 'Orbit is currently disabled' });
    return;
  }

  if (circuitBreaker.isOpen()) {
    const remaining = circuitBreaker.getRemainingSeconds();
    res.status(503).json({ status: 'unavailable', service: 'orbit', message: `Circuit breaker open. Retry in ${remaining}s.` });
    return;
  }

  res.json({ status: 'ok', service: 'orbit' });
}
