# Hybrid Cache System API Documentation

## Overview

The Hybrid Cache System provides REST API endpoints for per-user cache management. The system combines django-cacheops automatic ORM-level caching with per-user namespace versioning for instant O(1) cache invalidation.

**Base URL**: `/api/cache/`

**Authentication**: All endpoints require authentication via Bearer token (JWT) or session authentication.

**Authorization**: Users can only manage their own cache. Attempting to manage another user's cache will result in a 403 Forbidden response.

## Table of Contents

1. [Authentication](#authentication)
2. [Cache Control API Endpoints](#cache-control-api-endpoints)
   - [Get Cache Status](#get-cache-status)
   - [Enable Cache](#enable-cache)
   - [Disable Cache](#disable-cache)
   - [Clear Cache](#clear-cache)
3. [Server Management API Endpoints](#server-management-api-endpoints)
   - [Clear Cache (Admin)](#clear-cache-admin)
4. [Error Responses](#error-responses)
5. [Examples](#examples)

---

## Authentication

All API endpoints require authentication. The system supports two authentication methods:

### 1. Bearer Token (JWT)

Include the JWT token in the Authorization header:

```http
Authorization: Bearer <your-jwt-token>
```

### 2. Session Authentication

Use Django session authentication (cookie-based). Useful for browser-based clients.

**Example - Obtaining JWT Token**:

```bash
curl -X POST https://api.example.com/api/token/ \
  -H "Content-Type: application/json" \
  -d '{
    "username": "your-username",
    "password": "your-password"
  }'
```

**Response**:
```json
{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

---

## Cache Control API Endpoints

### Get Cache Status

Retrieve the current cache status for the authenticated user.

**Endpoint**: `GET /api/cache/status/`

**Authentication**: Required

**Authorization**: User can only view their own cache status

#### Request

**Headers**:
```http
Authorization: Bearer <token>
```

**Query Parameters**: None

**Request Body**: None

#### Response

**Success Response** (200 OK):

```json
{
  "enabled": true,
  "version": 5,
  "message": "Cache is enabled"
}
```

**Response Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `enabled` | boolean | Whether caching is enabled for the user |
| `version` | integer | Current cache version (≥1) |
| `message` | string | Human-readable status message |

#### Example

```bash
curl -X GET https://api.example.com/api/cache/status/ \
  -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc..."
```

**Response**:
```json
{
  "enabled": true,
  "version": 5,
  "message": "Cache is enabled"
}
```

---

### Enable Cache

Enable caching for the authenticated user. When enabled, API responses will be cached according to the configured TTL values.

**Endpoint**: `POST /api/cache/enable/`

**Authentication**: Required

**Authorization**: User can only enable their own cache

#### Request

**Headers**:
```http
Authorization: Bearer <token>
Content-Type: application/json
```

**Query Parameters**: None

**Request Body**: None

#### Response

**Success Response** (200 OK):

```json
{
  "enabled": true,
  "version": 5,
  "message": "Cache enabled successfully"
}
```

**Response Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `enabled` | boolean | Always `true` after successful enable |
| `version` | integer | Current cache version |
| `message` | string | Success message |

#### Example

```bash
curl -X POST https://api.example.com/api/cache/enable/ \
  -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc..." \
  -H "Content-Type: application/json"
```

**Response**:
```json
{
  "enabled": true,
  "version": 5,
  "message": "Cache enabled successfully"
}
```

---

### Disable Cache

Disable caching for the authenticated user. When disabled, all cache operations are bypassed and queries execute directly against the database.

**Endpoint**: `POST /api/cache/disable/`

**Authentication**: Required

**Authorization**: User can only disable their own cache

#### Request

**Headers**:
```http
Authorization: Bearer <token>
Content-Type: application/json
```

**Query Parameters**: None

**Request Body**: None

#### Response

**Success Response** (200 OK):

```json
{
  "enabled": false,
  "version": 5,
  "message": "Cache disabled successfully"
}
```

**Response Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `enabled` | boolean | Always `false` after successful disable |
| `version` | integer | Current cache version (unchanged) |
| `message` | string | Success message |

#### Example

```bash
curl -X POST https://api.example.com/api/cache/disable/ \
  -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc..." \
  -H "Content-Type: application/json"
```

**Response**:
```json
{
  "enabled": false,
  "version": 5,
  "message": "Cache disabled successfully"
}
```

---

### Clear Cache

Clear all cached data for the authenticated user via O(1) version increment. This operation increments the user's cache version, making all previous cache entries inaccessible without requiring key deletion or iteration.

**Performance**: O(1) operation regardless of cache size (uses Redis INCR).

**Endpoint**: `POST /api/cache/clear/`

**Authentication**: Required

**Authorization**: User can only clear their own cache

#### Request

**Headers**:
```http
Authorization: Bearer <token>
Content-Type: application/json
```

**Query Parameters**: None

**Request Body**: None

#### Response

**Success Response** (200 OK):

```json
{
  "version": 6,
  "cleared": true,
  "message": "Cache cleared successfully (new version: 6)"
}
```

**Response Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `version` | integer | New cache version after increment |
| `cleared` | boolean | Always `true` after successful clear |
| `message` | string | Success message with new version |

#### Example

```bash
curl -X POST https://api.example.com/api/cache/clear/ \
  -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc..." \
  -H "Content-Type: application/json"
```

**Response**:
```json
{
  "version": 6,
  "cleared": true,
  "message": "Cache cleared successfully (new version: 6)"
}
```

**Note**: After clearing cache, the frontend should also clear its IndexedDB cache to stay synchronized with the backend version.

---

## Server Management API Endpoints

### Clear Cache (Admin)

Administrative endpoint for clearing cache. Supports both global cache clearing and per-user cache clearing.

**Endpoint**: `POST /api/server-management/clear-cache/`

**Authentication**: Required

**Authorization**: Superuser or Admin group membership required

#### Request

**Headers**:
```http
Authorization: Bearer <token>
Content-Type: application/json
```

**Query Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `user_id` | integer | No | User ID for per-user cache clearing. If omitted, clears global cache. |

**Request Body**: None

#### Response

**Success Response - Per-User Clear** (200 OK):

```json
{
  "ok": true,
  "message": "Cache cleared for user 123",
  "user_id": 123,
  "new_version": 7
}
```

**Success Response - Global Clear** (200 OK):

```json
{
  "ok": true,
  "message": "Cache cleared"
}
```

**Response Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `ok` | boolean | Whether operation succeeded |
| `message` | string | Success or error message |
| `user_id` | integer | User ID (per-user clear only) |
| `new_version` | integer | New cache version (per-user clear only) |

#### Examples

**Per-User Cache Clear**:

```bash
curl -X POST "https://api.example.com/api/server-management/clear-cache/?user_id=123" \
  -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc..." \
  -H "Content-Type: application/json"
```

**Response**:
```json
{
  "ok": true,
  "message": "Cache cleared for user 123",
  "user_id": 123,
  "new_version": 7
}
```

**Global Cache Clear**:

```bash
curl -X POST https://api.example.com/api/server-management/clear-cache/ \
  -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc..." \
  -H "Content-Type: application/json"
```

**Response**:
```json
{
  "ok": true,
  "message": "Cache cleared"
}
```

---

## Error Responses

All endpoints follow consistent error response formats.

### 401 Unauthorized

Returned when authentication credentials are missing or invalid.

```json
{
  "detail": "Authentication credentials were not provided."
}
```

**Example**:
```bash
curl -X GET https://api.example.com/api/cache/status/
```

**Response** (401):
```json
{
  "detail": "Authentication credentials were not provided."
}
```

---

### 403 Forbidden

Returned when the authenticated user lacks permission for the requested operation.

**Cache Control API** (attempting to manage another user's cache):
```json
{
  "detail": "You do not have permission to perform this action."
}
```

**Server Management API** (non-admin user):
```json
{
  "error": "Superuser or Admin group membership required"
}
```

**Example**:
```bash
# Non-admin user attempting admin endpoint
curl -X POST https://api.example.com/api/server-management/clear-cache/ \
  -H "Authorization: Bearer <non-admin-token>"
```

**Response** (403):
```json
{
  "error": "Superuser or Admin group membership required"
}
```

---

### 400 Bad Request

Returned when request parameters are invalid.

**Invalid user_id parameter**:
```json
{
  "ok": false,
  "message": "Invalid user_id parameter"
}
```

**Example**:
```bash
curl -X POST "https://api.example.com/api/server-management/clear-cache/?user_id=invalid" \
  -H "Authorization: Bearer <admin-token>"
```

**Response** (400):
```json
{
  "ok": false,
  "message": "Invalid user_id parameter"
}
```

---

### 500 Internal Server Error

Returned when an unexpected server error occurs (e.g., Redis connection failure).

```json
{
  "error": "Failed to retrieve cache status"
}
```

**Example** (Redis unavailable):
```bash
curl -X GET https://api.example.com/api/cache/status/ \
  -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc..."
```

**Response** (500):
```json
{
  "error": "Failed to retrieve cache status"
}
```

**Note**: When Redis is unavailable, the system gracefully degrades to uncached database queries. Cache operations will fail, but application functionality remains intact.

---

## Examples

### Complete Workflow Example

This example demonstrates a complete cache management workflow.

#### 1. Check Initial Cache Status

```bash
curl -X GET https://api.example.com/api/cache/status/ \
  -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc..."
```

**Response**:
```json
{
  "enabled": true,
  "version": 5,
  "message": "Cache is enabled"
}
```

#### 2. Make API Request (Cached)

```bash
curl -X GET https://api.example.com/api/posts/ \
  -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc..."
```

**Response Headers**:
```http
X-Cache-Version: 5
X-Cache-Enabled: true
```

**Response Body**:
```json
{
  "results": [
    {"id": 1, "title": "Post 1", "content": "..."},
    {"id": 2, "title": "Post 2", "content": "..."}
  ]
}
```

#### 3. Clear Cache

```bash
curl -X POST https://api.example.com/api/cache/clear/ \
  -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc..." \
  -H "Content-Type: application/json"
```

**Response**:
```json
{
  "version": 6,
  "cleared": true,
  "message": "Cache cleared successfully (new version: 6)"
}
```

#### 4. Make API Request Again (Cache Miss)

```bash
curl -X GET https://api.example.com/api/posts/ \
  -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc..."
```

**Response Headers**:
```http
X-Cache-Version: 6
X-Cache-Enabled: true
```

**Note**: This request will execute against the database and cache the result with version 6.

#### 5. Disable Cache

```bash
curl -X POST https://api.example.com/api/cache/disable/ \
  -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc..." \
  -H "Content-Type: application/json"
```

**Response**:
```json
{
  "enabled": false,
  "version": 6,
  "message": "Cache disabled successfully"
}
```

#### 6. Make API Request (Uncached)

```bash
curl -X GET https://api.example.com/api/posts/ \
  -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc..."
```

**Response Headers**:
```http
X-Cache-Enabled: false
```

**Note**: No `X-Cache-Version` header when cache is disabled. All requests go directly to the database.

#### 7. Re-enable Cache

```bash
curl -X POST https://api.example.com/api/cache/enable/ \
  -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc..." \
  -H "Content-Type: application/json"
```

**Response**:
```json
{
  "enabled": true,
  "version": 6,
  "message": "Cache enabled successfully"
}
```

---

### Admin Workflow Example

Administrative cache management for troubleshooting or maintenance.

#### 1. Clear Specific User's Cache

```bash
curl -X POST "https://api.example.com/api/server-management/clear-cache/?user_id=123" \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json"
```

**Response**:
```json
{
  "ok": true,
  "message": "Cache cleared for user 123",
  "user_id": 123,
  "new_version": 8
}
```

#### 2. Clear Global Cache

```bash
curl -X POST https://api.example.com/api/server-management/clear-cache/ \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json"
```

**Response**:
```json
{
  "ok": true,
  "message": "Cache cleared"
}
```

**Note**: Global cache clear removes all cache entries across all users. Use with caution in production.

---

### Frontend Integration Example

Example Angular service integration with the cache API.

```typescript
import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

interface CacheStatus {
  enabled: boolean;
  version: number;
  message: string;
}

interface CacheClearResponse {
  version: number;
  cleared: boolean;
  message: string;
}

@Injectable({
  providedIn: 'root'
})
export class CacheApiService {
  private baseUrl = '/api/cache';

  constructor(private http: HttpClient) {}

  getStatus(): Observable<CacheStatus> {
    return this.http.get<CacheStatus>(`${this.baseUrl}/status/`);
  }

  enable(): Observable<CacheStatus> {
    return this.http.post<CacheStatus>(`${this.baseUrl}/enable/`, {});
  }

  disable(): Observable<CacheStatus> {
    return this.http.post<CacheStatus>(`${this.baseUrl}/disable/`, {});
  }

  clear(): Observable<CacheClearResponse> {
    return this.http.post<CacheClearResponse>(`${this.baseUrl}/clear/`, {});
  }
}
```

**Usage in Component**:

```typescript
export class CacheControlsComponent implements OnInit {
  cacheStatus: CacheStatus | null = null;

  constructor(private cacheApi: CacheApiService) {}

  ngOnInit() {
    this.loadStatus();
  }

  loadStatus() {
    this.cacheApi.getStatus().subscribe({
      next: (status) => {
        this.cacheStatus = status;
      },
      error: (error) => {
        console.error('Failed to load cache status:', error);
      }
    });
  }

  clearCache() {
    this.cacheApi.clear().subscribe({
      next: (response) => {
        console.log('Cache cleared:', response);
        this.loadStatus(); // Refresh status
        // Clear IndexedDB cache to sync with backend
        this.clearIndexedDB();
      },
      error: (error) => {
        console.error('Failed to clear cache:', error);
      }
    });
  }

  private clearIndexedDB() {
    // Clear local IndexedDB cache
    // Implementation depends on your cache service
  }
}
```

---

## Cache Headers

The system includes cache-related headers in API responses to enable frontend synchronization.

### Response Headers

| Header | Type | Description |
|--------|------|-------------|
| `X-Cache-Version` | integer | Current cache version for the user |
| `X-Cache-Enabled` | boolean | Whether caching is enabled for the user |

**Example Response**:
```http
HTTP/1.1 200 OK
Content-Type: application/json
X-Cache-Version: 5
X-Cache-Enabled: true

{
  "results": [...]
}
```

### Frontend Cache Synchronization

The frontend should:

1. **Store cache version** from `X-Cache-Version` header
2. **Check version on each request** - if version changes, clear local IndexedDB cache
3. **Respect cache enabled flag** - if `X-Cache-Enabled: false`, bypass local cache

**Example Interceptor Logic**:

```typescript
intercept(req: HttpRequest<any>, next: HttpHandler): Observable<HttpEvent<any>> {
  return next.handle(req).pipe(
    tap(event => {
      if (event instanceof HttpResponse) {
        const newVersion = event.headers.get('X-Cache-Version');
        const cacheEnabled = event.headers.get('X-Cache-Enabled') === 'true';
        
        if (newVersion && newVersion !== this.currentVersion) {
          // Version changed - clear local cache
          this.clearLocalCache();
          this.currentVersion = newVersion;
        }
        
        if (!cacheEnabled) {
          // Cache disabled - bypass local caching
          return;
        }
        
        // Store in local cache
        this.storeInCache(req, event.body);
      }
    })
  );
}
```

---

## Rate Limiting

Currently, no rate limiting is applied to cache control endpoints. However, consider implementing rate limiting in production to prevent abuse:

**Recommended Limits**:
- Cache status: 100 requests/minute per user
- Enable/Disable: 10 requests/minute per user
- Clear cache: 10 requests/minute per user

**Implementation**: Use Django REST Framework throttling or a reverse proxy (e.g., Nginx) for rate limiting.

---

## Security Considerations

### Authentication & Authorization

1. **All endpoints require authentication** - Unauthenticated requests return 401
2. **Users can only manage their own cache** - Authorization enforced at the view level
3. **Admin endpoints require elevated permissions** - Superuser or Admin group membership

### Input Validation

1. **User ID validation** - Must be positive integer
2. **Version validation** - Must be ≥1
3. **No user-controlled cache keys** - All keys generated server-side

### Data Isolation

1. **Per-user namespace isolation** - Cache keys include user ID
2. **No cross-user cache access** - Enforced by namespace layer
3. **No cache key exposure** - Internal cache structure not exposed in API responses

### Error Handling

1. **Graceful degradation** - Redis failures don't break functionality
2. **No sensitive information in errors** - Error messages sanitized
3. **Detailed logging** - All errors logged with context for debugging

---

## Performance Characteristics

### Cache Clear Operation

- **Time Complexity**: O(1) - Uses Redis INCR operation
- **Space Complexity**: O(1) - Only increments version counter
- **Scalability**: Constant time regardless of cache size
- **No key iteration**: Never uses Redis KEYS or SCAN commands

### Cache Status Operation

- **Time Complexity**: O(1) - Single Redis GET operation
- **Response Time**: < 10ms typical

### Enable/Disable Operations

- **Time Complexity**: O(1) - Single Redis SET operation
- **Response Time**: < 10ms typical

---

## Troubleshooting

### Cache Not Clearing

**Symptom**: Cache clear returns success but old data still appears.

**Possible Causes**:
1. Frontend IndexedDB not synchronized
2. Multiple cache layers not cleared
3. Browser caching HTTP responses

**Solution**:
```bash
# 1. Clear backend cache
curl -X POST https://api.example.com/api/cache/clear/ \
  -H "Authorization: Bearer <token>"

# 2. Clear frontend IndexedDB (in browser console)
indexedDB.deleteDatabase('hybrid-cache');

# 3. Hard refresh browser (Ctrl+Shift+R)
```

### Redis Connection Errors

**Symptom**: 500 errors with "Failed to retrieve cache status" message.

**Possible Causes**:
1. Redis server down
2. Network connectivity issues
3. Redis authentication failure

**Solution**:
```bash
# Check Redis connection
redis-cli ping

# Check Django settings
python manage.py shell
>>> from django.core.cache import cache
>>> cache.set('test', 'value')
>>> cache.get('test')
```

### Permission Denied Errors

**Symptom**: 403 Forbidden when accessing admin endpoints.

**Possible Causes**:
1. User not in Admin group
2. User not superuser
3. Invalid authentication token

**Solution**:
```bash
# Check user permissions
python manage.py shell
>>> from django.contrib.auth import get_user_model
>>> User = get_user_model()
>>> user = User.objects.get(username='your-username')
>>> user.is_superuser
>>> user.groups.filter(name='Admin').exists()
```

---

## API Versioning

**Current Version**: v1 (implicit)

**Base URL**: `/api/cache/`

**Future Versioning**: If breaking changes are introduced, versioned URLs will be used:
- `/api/v2/cache/` for version 2
- `/api/v1/cache/` for version 1 (backward compatibility)

**Deprecation Policy**: Deprecated endpoints will be supported for at least 6 months with deprecation warnings in response headers.

---

## Additional Resources

- **Architecture Documentation**: `backend/cache/ARCHITECTURE.md`
- **Requirements Document**: `.kiro/specs/hybrid-cache-system/requirements.md`
- **Design Document**: `.kiro/specs/hybrid-cache-system/design.md`
- **Integration Notes**: `.kiro/specs/hybrid-cache-system/INTEGRATION_NOTES.md`

---

## Support

For issues or questions:

1. Check the troubleshooting section above
2. Review the architecture documentation
3. Check application logs for detailed error messages
4. Contact the development team

---

**Document Version**: 1.0  
**Last Updated**: 2025-01-31  
**Maintained By**: Backend Development Team
