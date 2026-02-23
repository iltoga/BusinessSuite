/**
 * Cache Configuration
 * 
 * Centralized configuration for the hybrid cache system.
 * This configuration is used by both CacheService and CacheInterceptor
 * to ensure consistent behavior across the frontend cache system.
 * 
 * Requirements: 17.4, 17.5
 */

export interface CacheEndpointConfig {
  [endpoint: string]: number;
}

export interface CacheConfig {
  // IndexedDB configuration
  dbName: string;
  dbVersion: number;
  
  // Cache TTL per endpoint (seconds)
  endpointTTL: CacheEndpointConfig;
  
  // Cache size limits
  maxCacheSize: number;  // in bytes
  maxEntries: number;
  
  // Cleanup configuration
  cleanupInterval: number;  // in milliseconds
  expiredCheckInterval: number;  // in milliseconds
  
  // Feature flags
  enableCache: boolean;
  enableLogging: boolean;
  enableMetrics: boolean;
}

/**
 * Default cache configuration
 * 
 * Configuration strategy:
 * - User data: 5 minutes (moderate change frequency)
 * - Content data: 1-2 minutes (frequent changes)
 * - Static/reference data: 5+ minutes (rarely changes)
 * - Default: 2 minutes (safe fallback)
 */
export const CACHE_CONFIG: CacheConfig = {
  // IndexedDB configuration
  dbName: 'hybrid-cache',
  dbVersion: 1,
  
  // Cache TTL per endpoint (seconds)
  endpointTTL: {
    '/api/users': 300,      // 5 minutes - user data
    '/api/posts': 60,       // 1 minute - frequently updated content
    '/api/comments': 30,    // 30 seconds - real-time content
    'default': 120,         // 2 minutes - safe default
  },
  
  // Cache size limits
  maxCacheSize: 50 * 1024 * 1024,  // 50 MB
  maxEntries: 1000,
  
  // Cleanup configuration
  cleanupInterval: 60 * 1000,  // 1 minute - periodic cleanup
  expiredCheckInterval: 5 * 60 * 1000,  // 5 minutes - check for expired entries
  
  // Feature flags
  enableCache: true,
  enableLogging: false,  // Set to true for debugging
  enableMetrics: true,
};
