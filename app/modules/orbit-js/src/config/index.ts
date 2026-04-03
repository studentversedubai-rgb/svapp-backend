/**
 * Configuration Management
 * 
 * Loads environment variables and provides application settings
 * Ported from Python config.py
 */

import dotenv from 'dotenv';
import { z } from 'zod';

// Load environment variables
dotenv.config();

// Environment schema
const envSchema = z.object({
  // Server
  PORT: z.string().default('3000'),
  NODE_ENV: z.enum(['development', 'production', 'test']).default('development'),
  
  // OpenRouter
  OPENROUTER_API_KEY: z.string().min(1, 'OPENROUTER_API_KEY is required'),
  OPENROUTER_MODEL: z.string().default('google/gemini-2.0-flash-001'),
  
  // Supabase
  SUPABASE_URL: z.string().min(1, 'SUPABASE_URL is required'),
  SUPABASE_SERVICE_KEY: z.string().min(1, 'SUPABASE_SERVICE_KEY is required'),
  
  // Redis
  REDIS_URL: z.string().min(1, 'REDIS_URL is required'),
  REDIS_PASSWORD: z.string().default(''),
  REDIS_DB: z.string().default('0'),
  
  // JWT
  JWT_SECRET: z.string().min(1, 'JWT_SECRET is required'),
  JWT_ALGORITHM: z.string().default('HS256'),
  
  // Feature flags
  FEATURE_SV_ORBIT_ENABLED: z.enum(['true', 'false']).default('true'),
  FEATURE_ANALYTICS_ENABLED: z.enum(['true', 'false']).default('true'),
  
  // Orbit settings
  ORBIT_MAX_RESULTS: z.string().default('10'),
  DAILY_CHAT_LIMIT: z.string().default('150'),
  VELOCITY_LIMIT: z.string().default('10'),
  VELOCITY_WINDOW: z.string().default('60'),
  
  // Rate limiting
  RATE_LIMIT_ENABLED: z.enum(['true', 'false']).default('true'),
  
  // Circuit breaker
  CIRCUIT_BREAKER_THRESHOLD: z.string().default('5'),
  CIRCUIT_BREAKER_COOLDOWN: z.string().default('60'),
  
  // Conversation
  CONVERSATION_TTL_SECONDS: z.string().default('86400'), // 24 hours
  CONVERSATION_MAX_MESSAGES: z.string().default('20'),
});

// Parse and validate environment with better error messages
let env: z.infer<typeof envSchema>;
try {
  env = envSchema.parse(process.env);
} catch (error) {
  console.error('Configuration Error: Missing required environment variables');
  if (error instanceof z.ZodError) {
    error.errors.forEach((err) => {
      console.error(`  - ${err.path.join('.')}: ${err.message}`);
    });
  } else {
    console.error(error);
  }
  // Set a flag so the app can still start but will be disabled
  env = envSchema.parse({ ...process.env, FEATURE_SV_ORBIT_ENABLED: 'false' });
  console.log('Starting with features disabled due to missing configuration');
}

// Configuration object
export const config = {
  // Server
  port: parseInt(env.PORT, 10),
  nodeEnv: env.NODE_ENV,
  isDevelopment: env.NODE_ENV === 'development',
  isProduction: env.NODE_ENV === 'production',
  
  // OpenRouter
  openrouter: {
    apiKey: env.OPENROUTER_API_KEY,
    model: env.OPENROUTER_MODEL,
    baseUrl: 'https://openrouter.ai/api/v1',
  },
  
  // Supabase
  supabase: {
    url: env.SUPABASE_URL,
    serviceKey: env.SUPABASE_SERVICE_KEY,
  },
  
  // Redis
  redis: {
    url: env.REDIS_URL,
    password: env.REDIS_PASSWORD,
    db: parseInt(env.REDIS_DB, 10),
  },
  
  // JWT
  jwt: {
    secret: env.JWT_SECRET,
    algorithm: env.JWT_ALGORITHM,
  },
  
  // Features
  features: {
    svOrbitEnabled: env.FEATURE_SV_ORBIT_ENABLED === 'true',
    analyticsEnabled: env.FEATURE_ANALYTICS_ENABLED === 'true',
  },
  
  // Orbit
  orbit: {
    maxResults: parseInt(env.ORBIT_MAX_RESULTS, 10),
    dailyChatLimit: parseInt(env.DAILY_CHAT_LIMIT, 10),
    velocityLimit: parseInt(env.VELOCITY_LIMIT, 10),
    velocityWindow: parseInt(env.VELOCITY_WINDOW, 10),
  },
  
  // Rate limiting
  rateLimit: {
    enabled: env.RATE_LIMIT_ENABLED === 'true',
  },
  
  // Circuit breaker
  circuitBreaker: {
    failureThreshold: parseInt(env.CIRCUIT_BREAKER_THRESHOLD, 10),
    cooldownSeconds: parseInt(env.CIRCUIT_BREAKER_COOLDOWN, 10),
  },
  
  // Conversation
  conversation: {
    ttlSeconds: parseInt(env.CONVERSATION_TTL_SECONDS, 10),
    maxMessages: parseInt(env.CONVERSATION_MAX_MESSAGES, 10),
  },
} as const;

export default config;
