/**
 * SV Orbit Retrieval
 * 
 * Retrieval-only system for finding relevant partner offers.
 * CRITICAL: No hallucinations - only real partner data.
 * Ported from Python retrieval.py
 */

import { createClient, SupabaseClient } from '@supabase/supabase-js';
import { config } from '../config';
import { Offer, Ticket } from '../types';

/**
 * Retrieves partner offers based on user intent
 * 
 * IMPORTANT: Only retrieves real offers from database
 * Never generates or hallucinates offers
 */
export class OfferRetrieval {
  private supabase: SupabaseClient;

  constructor() {
    this.supabase = createClient(
      config.supabase.url,
      config.supabase.serviceKey
    );
  }

  /**
   * Extract keywords from user message
   * 
   * Simple extraction logic:
   * - Convert to lowercase
   * - Remove common stop words
   * - Split into words
   * - Filter short words
   * 
   * @param message - User's message
   * @returns List of keywords
   */
  extractKeywords(message: string): string[] {
    // Common stop words to filter out
    const stopWords = new Set([
      'i', 'want', 'need', 'looking', 'for', 'a', 'an', 'the', 'is', 'are',
      'can', 'you', 'me', 'my', 'in', 'on', 'at', 'to', 'from', 'with',
      'find', 'get', 'show', 'give', 'some', 'any', 'where', 'what', 'how'
    ]);

    // Convert to lowercase and extract words
    const words = message.toLowerCase().match(/\b[a-zA-Z]+\b/g) || [];

    // Filter stop words and short words
    const keywords = words.filter(
      (word) => !stopWords.has(word) && word.length > 2
    );

    return keywords;
  }

  /**
   * Calculate relevance score for offer based on keywords
   * 
   * Scoring:
   * - Title match: 3 points per keyword
   * - Description match: 2 points per keyword
   * - Merchant name match: 2 points per keyword
   * - Category name match: 1 point per keyword
   */
  private calculateRelevanceScore(offer: Offer, keywords: string[]): number {
    let score = 0;

    // Prepare searchable text
    const title = (offer.title || '').toLowerCase();
    const description = (offer.description || '').toLowerCase();
    const merchantName = (offer.merchant?.name || '').toLowerCase();
    const categoryName = (offer.category?.name || '').toLowerCase();

    for (const keyword of keywords) {
      const keywordLower = keyword.toLowerCase();
      
      // Title matches are most important
      if (title.includes(keywordLower)) {
        score += 3.0;
      }

      // Description matches
      if (description.includes(keywordLower)) {
        score += 2.0;
      }

      // Merchant name matches
      if (merchantName.includes(keywordLower)) {
        score += 2.0;
      }

      // Category name matches
      if (categoryName.includes(keywordLower)) {
        score += 1.0;
      }
    }

    return score;
  }

  /**
   * Retrieve relevant offers from database
   * 
   * @param intent - User's intent/query
   * @param filters - Optional filters
   * @param limit - Maximum number of offers to return
   * @returns List of relevant offers (REAL DATA ONLY)
   */
  async retrieveOffers(
    intent: string,
    filters?: Record<string, any>,
    limit: number = config.orbit.maxResults
  ): Promise<Offer[]> {
    try {
      // Extract keywords from user intent
      const keywords = this.extractKeywords(intent);

      // Build base query with merchant join
      const { data: offers, error } = await this.supabase
        .from('offers')
        .select('*, merchant:merchants(*), category:categories(*)')
        .eq('is_active', true)
        .eq('merchants.is_active', true);

      if (error) {
        console.error('Error fetching offers:', error);
        return [];
      }

      if (!offers || offers.length === 0) {
        console.info('No offers found in database');
        return [];
      }

      // Score offers based on keyword matching
      const scoredOffers: Offer[] = [];
      for (const offer of offers) {
        const score = this.calculateRelevanceScore(offer, keywords);
        if (score > 0) {
          offer._relevance_score = score;
          scoredOffers.push(offer);
        }
      }

      // Fetch tickets if keywords suggest tourist attractions or events
      const ticketKeywords = new Set([
        'tourist', 'attraction', 'attractions', 'ticket', 'tickets', 
        'show', 'event', 'events', 'activities', 'park', 'museum', 
        'aquarium', 'tour'
      ]);
      
      const hasTicketKeyword = keywords.some(kw => ticketKeywords.has(kw));
      
      if (hasTicketKeyword) {
        try {
          const { data: tickets, error: ticketError } = await this.supabase
            .from('tickets')
            .select('*')
            .eq('is_active', true);

          if (ticketError) {
            console.error('Error fetching tickets:', ticketError);
          } else if (tickets) {
            for (const ticket of tickets) {
              const ticketOffer: Offer = {
                id: ticket.id,
                title: ticket.merchant_name,
                description: ticket.ticket_details || 'Student Ticket',
                merchant: {
                  name: ticket.merchant_name,
                  address: ticket.location,
                  latitude: ticket.latitude,
                  longitude: ticket.longitude,
                },
                category: { name: 'Attractions & Events' },
                original_price: ticket.market_price_adult,
                discounted_price: ticket.our_price,
                is_active: ticket.is_active,
                _relevance_score: 100.0,
              };

              // Add any additional score if it matches specific keywords
              const score = this.calculateRelevanceScore(ticketOffer, keywords);
              ticketOffer._relevance_score = (ticketOffer._relevance_score || 0) + score;
              scoredOffers.push(ticketOffer);
            }
          }
        } catch (e) {
          console.error('Failed to retrieve tickets:', e);
        }
      }

      // Fallback: if keyword matching returned nothing, return all active offers
      if (scoredOffers.length === 0 && offers.length > 0) {
        console.info('No keyword matches found — using unfiltered fallback offers');
        for (const offer of offers) {
          offer._relevance_score = 0;
          scoredOffers.push(offer);
        }
      }

      // Sort by relevance score (highest first)
      scoredOffers.sort((a, b) => (b._relevance_score || 0) - (a._relevance_score || 0));

      // Return top N offers
      const topOffers = scoredOffers.slice(0, limit);

      console.info(`Retrieved ${topOffers.length} relevant offers for intent: ${intent}`);
      return topOffers;
    } catch (error) {
      console.error('Error retrieving offers:', error);
      throw error;
    }
  }

  /**
   * Search offers by category
   */
  async searchByCategory(categories: string[], limit: number = 10): Promise<Offer[]> {
    try {
      const { data: offers, error } = await this.supabase
        .from('offers')
        .select('*, merchant:merchants(*), category:categories(*)')
        .eq('is_active', true)
        .in('category.slug', categories)
        .limit(limit);

      if (error) {
        console.error('Error searching by category:', error);
        throw error;
      }

      return offers || [];
    } catch (error) {
      console.error('Error searching by category:', error);
      throw error;
    }
  }

  /**
   * Search offers by keywords
   */
  async searchByKeywords(keywords: string[], limit: number = 10): Promise<Offer[]> {
    const intent = keywords.join(' ');
    return this.retrieveOffers(intent, undefined, limit);
  }

  /**
   * Get personalized offer recommendations
   */
  async getUserRecommendedOffers(userId: string, limit: number = 10): Promise<Offer[]> {
    try {
      const { data: offers, error } = await this.supabase
        .from('offers')
        .select('*, merchant:merchants(*), category:categories(*)')
        .eq('is_active', true)
        .eq('is_featured', true)
        .limit(limit);

      if (error) {
        console.error('Error getting recommended offers:', error);
        throw error;
      }

      return offers || [];
    } catch (error) {
      console.error('Error getting recommended offers:', error);
      throw error;
    }
  }
}

// Singleton instance
let offerRetrievalInstance: OfferRetrieval | null = null;

export function getOfferRetrieval(): OfferRetrieval {
  if (!offerRetrievalInstance) {
    offerRetrievalInstance = new OfferRetrieval();
  }
  return offerRetrievalInstance;
}
