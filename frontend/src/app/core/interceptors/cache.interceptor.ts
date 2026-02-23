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

  const processVersionHeader = async (event: HttpResponse<unknown>) => {
    const cacheVersion = event.headers.get('X-Cache-Version');
    if (!cacheVersion) {
      return;
    }

    const currentVersion = await cacheService.getVersion();
    const newVersion = parseInt(cacheVersion, 10);

    // If version changed, invalidate old cache entries.
    if (!isNaN(newVersion) && newVersion !== currentVersion) {
      await cacheService.clearByVersion(currentVersion);
      await cacheService.setVersion(newVersion);
    }
  };

  // Non-GET requests are never cached, but still may carry cache-version headers
  // (e.g. POST /api/cache/clear).
  if (req.method !== 'GET') {
    return next(req).pipe(
      tap((event) => {
        if (event instanceof HttpResponse) {
          void processVersionHeader(event).catch((error) => {
            console.error('Cache version sync error:', error);
          });
        }
      }),
    );
  }

  // Check if endpoint is cacheable
  if (!isCacheable(req.urlWithParams)) {
    return next(req);
  }

  // Only cache for authenticated users
  if (!authService.isAuthenticated()) {
    return next(req);
  }

  const userScope = getUserScope(authService);
  const userId = getUserId(authService);

  // Generate cache key scoped by user and full request identity (path + query).
  const cacheKey = getCacheKey(req.urlWithParams, userScope);
  const ttl = getTTL(req.urlWithParams);

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
                await processVersionHeader(event);
                
                // Store response in cache
                if (event.body) {
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
  const path = getPath(url);
  return CACHEABLE_ENDPOINTS.some((endpoint) => endpoint.pattern.test(path));
}

/**
 * Generate cache key for a request URL + user scope.
 *
 * Includes:
 * - user scope (prevents cross-account collisions on same browser profile)
 * - full request identity (path + normalized query string)
 *
 * Example:
 *   cache:user:123:/api/users?page=1
 *   cache:user:123:/api/users?page=2
 *
 * These keys are distinct and won't collide.
 *
 * @param url Request URL
 * @param userScope User identity scope
 * @returns Cache key string
 */
function getCacheKey(url: string, userScope: string): string {
  const identity = getRequestIdentity(url);
  return `cache:user:${userScope}:${identity}`;
}

/**
 * Get TTL (time to live) for a request URL
 * @param url Request URL
 * @returns TTL in seconds
 */
function getTTL(url: string): number {
  const path = getPath(url);
  // Find matching endpoint configuration
  const endpoint = CACHEABLE_ENDPOINTS.find((e) => e.pattern.test(path));
  
  return endpoint ? endpoint.ttl : DEFAULT_TTL;
}

/**
 * Extract normalized request path (without query string).
 */
function getPath(url: string): string {
  try {
    return new URL(url, 'http://localhost').pathname;
  } catch {
    return url.split('?')[0] ?? url;
  }
}

/**
 * Extract request identity (path + normalized query string).
 */
function getRequestIdentity(url: string): string {
  try {
    const parsed = new URL(url, 'http://localhost');
    const params = new URLSearchParams(parsed.search);
    params.sort();
    const query = params.toString();
    return query ? `${parsed.pathname}?${query}` : parsed.pathname;
  } catch {
    return url;
  }
}

/**
 * Resolve stable user scope for cache key namespacing.
 */
function getUserScope(authService: AuthService): string {
  const claims = authService.claims() as { sub?: string | number } | null;
  const rawScope = claims?.sub ?? '0';
  return encodeURIComponent(String(rawScope));
}

/**
 * Resolve numeric user ID for metadata storage.
 */
function getUserId(authService: AuthService): number {
  const claims = authService.claims() as { sub?: string | number } | null;
  const raw = claims?.sub;
  const parsed = raw !== undefined ? parseInt(String(raw), 10) : NaN;
  return Number.isFinite(parsed) ? parsed : 0;
}
