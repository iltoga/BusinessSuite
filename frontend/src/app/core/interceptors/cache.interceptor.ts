import { HttpInterceptorFn, HttpResponse } from '@angular/common/http';
import { inject } from '@angular/core';
import { from, of, Observable } from 'rxjs';
import { switchMap, tap } from 'rxjs/operators';

import { CacheService } from '@/core/services/cache.service';
import { AuthService } from '@/core/services/auth.service';
import { CACHE_CONFIG } from '../../config/cache.config';

/**
 * Configuration for cacheable endpoints
 * Maps URL patterns to their TTL (time to live) in seconds
 */
interface CacheableEndpoint {
  pattern: RegExp;
  ttl: number;
}

/**
 * Build cacheable endpoints list from CACHE_CONFIG
 * Converts endpoint string patterns to RegExp patterns
 */
function buildCacheableEndpoints(): CacheableEndpoint[] {
  const endpoints: CacheableEndpoint[] = [];
  
  for (const [endpoint, ttl] of Object.entries(CACHE_CONFIG.endpointTTL)) {
    if (endpoint === 'default') {
      continue; // Skip default entry
    }
    
    // Convert endpoint pattern to RegExp
    // Simple conversion: /api/users -> /^\/api\/users/
    const pattern = new RegExp(`^${endpoint.replace(/\//g, '\\/')}`);
    endpoints.push({ pattern, ttl });
  }
  
  return endpoints;
}

/**
 * List of cacheable endpoints with their TTL configurations
 * Only GET requests to these endpoints will be cached
 */
const CACHEABLE_ENDPOINTS: CacheableEndpoint[] = buildCacheableEndpoints();

/**
 * Default TTL for cacheable endpoints not explicitly configured
 */
const DEFAULT_TTL = CACHE_CONFIG.endpointTTL['default'];

/**
 * HTTP Interceptor for cache management
 * 
 * Key responsibilities:
 * - Check IndexedDB before making network requests
 * - Store responses in IndexedDB after successful requests
 * - Detect cache version changes from X-Cache-Version header
 * - Invalidate local cache on version mismatch
 * - Handle cache errors without breaking requests
 * 
 * Cache flow:
 * 1. Check if request is cacheable (GET request to configured endpoint)
 * 2. Check IndexedDB for cached response
 * 3. If cache hit and not expired, return cached response
 * 4. If cache miss, make network request
 * 5. Check X-Cache-Version header in response
 * 6. If version changed, invalidate old cache entries
 * 7. Store response in IndexedDB with TTL
 */
export const cacheInterceptor: HttpInterceptorFn = (req, next) => {
  const cacheService = inject(CacheService);
  const authService = inject(AuthService);

  // Only cache GET requests
  if (req.method !== 'GET') {
    return next(req);
  }

  // Check if endpoint is cacheable
  if (!isCacheable(req.url)) {
    return next(req);
  }

  // Only cache for authenticated users
  if (!authService.isAuthenticated()) {
    return next(req);
  }

  // Generate cache key
  const cacheKey = getCacheKey(req.url);
  const ttl = getTTL(req.url);

  // Check cache asynchronously
  const checkCache = async () => {
    try {
      const cached = await cacheService.get(cacheKey);
      
      if (cached && cached.data) {
        // Cache hit - return cached response
        return new HttpResponse({
          body: cached.data,
          status: 200,
          statusText: 'OK',
          headers: req.headers,
        });
      }
    } catch (error) {
      // Cache error - log and continue with network request
      console.error('Cache check error:', error);
    }
    
    return null;
  };

  // Try to get from cache first
  return from(checkCache()).pipe(
    switchMap((cachedResponse) => {
      if (cachedResponse) {
        return of(cachedResponse);
      } else {
        // Cache miss - make network request
        return next(req).pipe(
          tap(async (event) => {
            if (event instanceof HttpResponse) {
              try {
                // Check for cache version header
                const cacheVersion = event.headers.get('X-Cache-Version');
                
                if (cacheVersion) {
                  const currentVersion = await cacheService.getVersion();
                  const newVersion = parseInt(cacheVersion, 10);
                  
                  // If version changed, invalidate old cache entries
                  if (!isNaN(newVersion) && newVersion !== currentVersion) {
                    console.log(`Cache version changed: ${currentVersion} -> ${newVersion}`);
                    await cacheService.clearByVersion(currentVersion);
                    await cacheService.setVersion(newVersion);
                  }
                }
                
                // Store response in cache
                if (event.body) {
                  // Get user ID from claims (sub field contains user identifier)
                  const claims = authService.claims();
                  const userId = claims?.sub ? parseInt(claims.sub, 10) : 0;
                  const version = await cacheService.getVersion();
                  await cacheService.set(cacheKey, event.body, ttl, userId, version);
                }
              } catch (error) {
                // Cache storage error - log but don't break the request
                console.error('Cache storage error:', error);
              }
            }
          }),
        );
      }
    }),
  );
};

/**
 * Check if a URL is cacheable based on configured patterns
 * @param url Request URL
 * @returns true if URL matches any cacheable endpoint pattern
 */
function isCacheable(url: string): boolean {
  // Extract path from full URL if needed
  const path = url.startsWith('http') ? new URL(url).pathname : url;
  
  return CACHEABLE_ENDPOINTS.some((endpoint) => endpoint.pattern.test(path));
}

/**
 * Generate cache key for a request URL
 * @param url Request URL
 * @returns Cache key string
 */
function getCacheKey(url: string): string {
  // Extract path from full URL if needed
  const path = url.startsWith('http') ? new URL(url).pathname : url;
  
  // Use path as cache key (user ID and version are stored separately in CachedResponse)
  return `cache:${path}`;
}

/**
 * Get TTL (time to live) for a request URL
 * @param url Request URL
 * @returns TTL in seconds
 */
function getTTL(url: string): number {
  // Extract path from full URL if needed
  const path = url.startsWith('http') ? new URL(url).pathname : url;
  
  // Find matching endpoint configuration
  const endpoint = CACHEABLE_ENDPOINTS.find((e) => e.pattern.test(path));
  
  return endpoint ? endpoint.ttl : DEFAULT_TTL;
}
