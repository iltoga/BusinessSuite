import { isPlatformBrowser } from '@angular/common';
import { Inject, Injectable, PLATFORM_ID } from '@angular/core';
import { CACHE_CONFIG } from '../../config/cache.config';

/**
 * Interface for cached response data stored in IndexedDB
 */
export interface CachedResponse {
  key: string;           // Cache key
  userId: number;        // User ID
  version: number;       // Cache version
  data: any;            // Response data
  timestamp: number;     // Storage timestamp
  expiresAt: number;    // Expiration timestamp
}

/**
 * CacheService manages browser-side cache storage using IndexedDB.
 * 
 * Key responsibilities:
 * - Store API response data in IndexedDB
 * - Retrieve cached responses by key
 * - Manage cache expiration
 * - Clear cache on version mismatch
 * - Handle IndexedDB errors gracefully
 * 
 * IndexedDB Schema:
 * - Database: hybrid-cache
 * - Object Store: responses (keyPath: 'key')
 * - Object Store: metadata (keyPath: 'key')
 * - Indexes: userId, version, expiresAt
 */
@Injectable({
  providedIn: 'root',
})
export class CacheService {
  private readonly DB_NAME = CACHE_CONFIG.dbName;
  private readonly DB_VERSION = CACHE_CONFIG.dbVersion;
  private readonly STORE_RESPONSES = 'responses';
  private readonly STORE_METADATA = 'metadata';
  private readonly VERSION_KEY = 'current_version';
  
  private db: IDBDatabase | null = null;
  private available = false;
  private initPromise: Promise<void> | null = null;
  private cleanupIntervalId: any = null;

  constructor(@Inject(PLATFORM_ID) private platformId: Object) {
    if (isPlatformBrowser(this.platformId)) {
      this.available = 'indexedDB' in window;
      if (!this.available) {
        console.warn('IndexedDB not available, caching disabled');
      } else {
        // Start periodic cleanup
        this.startPeriodicCleanup();
      }
    }
  }

  /**
   * Start periodic cleanup of expired entries
   * Runs at intervals defined in CACHE_CONFIG.expiredCheckInterval
   */
  private startPeriodicCleanup(): void {
    if (this.cleanupIntervalId) {
      return;
    }

    this.cleanupIntervalId = setInterval(() => {
      this.clearExpired().catch(err => {
        if (CACHE_CONFIG.enableLogging) {
          console.error('Periodic cleanup failed:', err);
        }
      });
    }, CACHE_CONFIG.expiredCheckInterval);
  }

  /**
   * Stop periodic cleanup
   * Called when service is destroyed
   */
  private stopPeriodicCleanup(): void {
    if (this.cleanupIntervalId) {
      clearInterval(this.cleanupIntervalId);
      this.cleanupIntervalId = null;
    }
  }

  /**
   * Check current cache size and entry count
   * Returns quota usage information
   */
  async checkQuota(): Promise<{ entryCount: number; estimatedSize: number; quotaExceeded: boolean }> {
    if (!this.available) {
      return { entryCount: 0, estimatedSize: 0, quotaExceeded: false };
    }

    try {
      await this.init();
      
      if (!this.db) {
        return { entryCount: 0, estimatedSize: 0, quotaExceeded: false };
      }

      return new Promise<{ entryCount: number; estimatedSize: number; quotaExceeded: boolean }>((resolve) => {
        const transaction = this.db!.transaction([this.STORE_RESPONSES], 'readonly');
        const store = transaction.objectStore(this.STORE_RESPONSES);
        const countRequest = store.count();

        countRequest.onsuccess = () => {
          const entryCount = countRequest.result;
          const quotaExceeded = entryCount >= CACHE_CONFIG.maxEntries;

          // Log warning if approaching quota
          if (entryCount >= CACHE_CONFIG.maxEntries * 0.8) {
            console.warn(`Cache quota warning: ${entryCount}/${CACHE_CONFIG.maxEntries} entries used (${Math.round(entryCount / CACHE_CONFIG.maxEntries * 100)}%)`);
          }

          resolve({
            entryCount,
            estimatedSize: 0, // Actual size calculation would require iterating all entries
            quotaExceeded,
          });
        };

        countRequest.onerror = () => {
          console.error('Failed to check quota:', countRequest.error);
          resolve({ entryCount: 0, estimatedSize: 0, quotaExceeded: false });
        };
      });
    } catch (error) {
      console.error('Quota check error:', error);
      return { entryCount: 0, estimatedSize: 0, quotaExceeded: false };
    }
  }

  /**
   * Initialize IndexedDB database and create object stores
   */
  private async init(): Promise<void> {
    if (!this.available) {
      return;
    }

    if (this.db) {
      return;
    }

    if (this.initPromise) {
      return this.initPromise;
    }

    this.initPromise = new Promise<void>((resolve, reject) => {
      const request = indexedDB.open(this.DB_NAME, this.DB_VERSION);

      request.onerror = () => {
        console.error('Failed to open IndexedDB:', request.error);
        this.available = false;
        reject(request.error);
      };

      request.onsuccess = () => {
        this.db = request.result;
        resolve();
      };

      request.onupgradeneeded = (event) => {
        const db = (event.target as IDBOpenDBRequest).result;

        // Create responses object store
        if (!db.objectStoreNames.contains(this.STORE_RESPONSES)) {
          const responsesStore = db.createObjectStore(this.STORE_RESPONSES, { keyPath: 'key' });
          responsesStore.createIndex('userId', 'userId', { unique: false });
          responsesStore.createIndex('version', 'version', { unique: false });
          responsesStore.createIndex('expiresAt', 'expiresAt', { unique: false });
        }

        // Create metadata object store
        if (!db.objectStoreNames.contains(this.STORE_METADATA)) {
          db.createObjectStore(this.STORE_METADATA, { keyPath: 'key' });
        }
      };
    });

    return this.initPromise;
  }

  /**
   * Get cached response by key
   * Returns null if not found or expired
   */
  async get(key: string): Promise<CachedResponse | null> {
    if (!this.available) {
      return null;
    }

    try {
      await this.init();
      
      if (!this.db) {
        return null;
      }

      return new Promise<CachedResponse | null>((resolve, reject) => {
        const transaction = this.db!.transaction([this.STORE_RESPONSES], 'readonly');
        const store = transaction.objectStore(this.STORE_RESPONSES);
        const request = store.get(key);

        request.onsuccess = () => {
          const cached = request.result as CachedResponse | undefined;
          
          if (!cached) {
            resolve(null);
            return;
          }

          // Check if expired
          if (Date.now() > cached.expiresAt) {
            // Delete expired entry
            this.delete(key).catch(err => console.error('Failed to delete expired entry:', err));
            resolve(null);
            return;
          }

          resolve(cached);
        };

        request.onerror = () => {
          console.error('Failed to get cached response:', request.error);
          resolve(null);
        };
      });
    } catch (error) {
      console.error('Cache get error:', error);
      return null;
    }
  }

  /**
   * Store response in cache with TTL
   * @param key Cache key
   * @param data Response data
   * @param ttl Time to live in seconds
   * @param userId User ID (optional)
   * @param version Cache version (optional)
   */
  async set(key: string, data: any, ttl: number, userId?: number, version?: number): Promise<void> {
    if (!this.available) {
      return;
    }

    try {
      await this.init();
      
      if (!this.db) {
        return;
      }

      // Check quota before storing
      const quota = await this.checkQuota();
      if (quota.quotaExceeded) {
        if (CACHE_CONFIG.enableLogging) {
          console.warn('Cache quota exceeded, clearing old entries before storing');
        }
        await this.clearExpired();
        await this.clearOldest(Math.floor(CACHE_CONFIG.maxEntries * 0.1)); // Clear 10% of entries
      }

      const now = Date.now();
      const cachedResponse: CachedResponse = {
        key,
        userId: userId ?? 0,
        version: version ?? await this.getVersion(),
        data,
        timestamp: now,
        expiresAt: now + (ttl * 1000),
      };

      return new Promise<void>((resolve, reject) => {
        const transaction = this.db!.transaction([this.STORE_RESPONSES], 'readwrite');
        const store = transaction.objectStore(this.STORE_RESPONSES);
        const request = store.put(cachedResponse);

        request.onsuccess = () => {
          if (CACHE_CONFIG.enableLogging) {
            console.log(`Cached response for key: ${key}, TTL: ${ttl}s`);
          }
          resolve();
        };

        request.onerror = () => {
          // Handle quota exceeded error
          if (request.error?.name === 'QuotaExceededError') {
            console.warn('IndexedDB quota exceeded during storage, attempting cleanup and retry');
            this.clearExpired().then(() => {
              this.clearOldest(Math.floor(CACHE_CONFIG.maxEntries * 0.2)).then(() => {
                // Retry once
                const retryTransaction = this.db!.transaction([this.STORE_RESPONSES], 'readwrite');
                const retryStore = retryTransaction.objectStore(this.STORE_RESPONSES);
                const retryRequest = retryStore.put(cachedResponse);
                
                retryRequest.onsuccess = () => {
                  if (CACHE_CONFIG.enableLogging) {
                    console.log(`Cached response after cleanup for key: ${key}`);
                  }
                  resolve();
                };
                retryRequest.onerror = () => {
                  console.error('Failed to cache after cleanup:', retryRequest.error);
                  resolve(); // Don't reject, just log
                };
              });
            });
          } else {
            console.error('Failed to cache response:', request.error);
            resolve(); // Don't reject, just log
          }
        };
      });
    } catch (error) {
      console.error('Cache set error:', error);
    }
  }

  /**
   * Delete a specific cache entry
   */
  private async delete(key: string): Promise<void> {
    if (!this.available || !this.db) {
      return;
    }

    return new Promise<void>((resolve, reject) => {
      const transaction = this.db!.transaction([this.STORE_RESPONSES], 'readwrite');
      const store = transaction.objectStore(this.STORE_RESPONSES);
      const request = store.delete(key);

      request.onsuccess = () => resolve();
      request.onerror = () => {
        console.error('Failed to delete cache entry:', request.error);
        resolve(); // Don't reject
      };
    });
  }

  /**
   * Clear all cached responses
   */
  async clear(): Promise<void> {
    if (!this.available) {
      return;
    }

    try {
      await this.init();
      
      if (!this.db) {
        return;
      }

      return new Promise<void>((resolve, reject) => {
        const transaction = this.db!.transaction([this.STORE_RESPONSES], 'readwrite');
        const store = transaction.objectStore(this.STORE_RESPONSES);
        const request = store.clear();

        request.onsuccess = () => {
          console.log('Cache cleared successfully');
          resolve();
        };

        request.onerror = () => {
          console.error('Failed to clear cache:', request.error);
          resolve(); // Don't reject
        };
      });
    } catch (error) {
      console.error('Cache clear error:', error);
    }
  }

  /**
   * Clear cache entries for a specific version
   * Used when backend cache version changes
   */
  async clearByVersion(version: number): Promise<void> {
    if (!this.available) {
      return;
    }

    try {
      await this.init();
      
      if (!this.db) {
        return;
      }

      return new Promise<void>((resolve, reject) => {
        const transaction = this.db!.transaction([this.STORE_RESPONSES], 'readwrite');
        const store = transaction.objectStore(this.STORE_RESPONSES);
        const index = store.index('version');
        const request = index.openCursor(IDBKeyRange.only(version));

        request.onsuccess = (event) => {
          const cursor = (event.target as IDBRequest<IDBCursorWithValue>).result;
          if (cursor) {
            cursor.delete();
            cursor.continue();
          } else {
            console.log(`Cleared cache entries for version ${version}`);
            resolve();
          }
        };

        request.onerror = () => {
          console.error('Failed to clear cache by version:', request.error);
          resolve(); // Don't reject
        };
      });
    } catch (error) {
      console.error('Cache clearByVersion error:', error);
    }
  }

  /**
   * Get current cache version from metadata store
   */
  async getVersion(): Promise<number> {
    if (!this.available) {
      return 1;
    }

    try {
      await this.init();
      
      if (!this.db) {
        return 1;
      }

      return new Promise<number>((resolve, reject) => {
        const transaction = this.db!.transaction([this.STORE_METADATA], 'readonly');
        const store = transaction.objectStore(this.STORE_METADATA);
        const request = store.get(this.VERSION_KEY);

        request.onsuccess = () => {
          const result = request.result;
          resolve(result?.value ?? 1);
        };

        request.onerror = () => {
          console.error('Failed to get version:', request.error);
          resolve(1);
        };
      });
    } catch (error) {
      console.error('Cache getVersion error:', error);
      return 1;
    }
  }

  /**
   * Set current cache version in metadata store
   */
  async setVersion(version: number): Promise<void> {
    if (!this.available) {
      return;
    }

    try {
      await this.init();
      
      if (!this.db) {
        return;
      }

      return new Promise<void>((resolve, reject) => {
        const transaction = this.db!.transaction([this.STORE_METADATA], 'readwrite');
        const store = transaction.objectStore(this.STORE_METADATA);
        const request = store.put({ key: this.VERSION_KEY, value: version });

        request.onsuccess = () => {
          resolve();
        };

        request.onerror = () => {
          console.error('Failed to set version:', request.error);
          resolve(); // Don't reject
        };
      });
    } catch (error) {
      console.error('Cache setVersion error:', error);
    }
  }

  /**
   * Clear expired cache entries
   * Public method that can be called manually or by periodic cleanup
   */
  async clearExpired(): Promise<void> {
    if (!this.available || !this.db) {
      return;
    }

    return new Promise<void>((resolve) => {
      const transaction = this.db!.transaction([this.STORE_RESPONSES], 'readwrite');
      const store = transaction.objectStore(this.STORE_RESPONSES);
      const index = store.index('expiresAt');
      const now = Date.now();
      const request = index.openCursor(IDBKeyRange.upperBound(now));
      let deletedCount = 0;

      request.onsuccess = (event) => {
        const cursor = (event.target as IDBRequest<IDBCursorWithValue>).result;
        if (cursor) {
          cursor.delete();
          deletedCount++;
          cursor.continue();
        } else {
          if (deletedCount > 0 && CACHE_CONFIG.enableLogging) {
            console.log(`Cleared ${deletedCount} expired cache entries`);
          }
          resolve();
        }
      };

      request.onerror = () => {
        console.error('Failed to clear expired entries:', request.error);
        resolve();
      };
    });
  }

  /**
   * Clear oldest N cache entries
   * Used when quota is exceeded
   */
  private async clearOldest(count: number): Promise<void> {
    if (!this.available || !this.db) {
      return;
    }

    return new Promise<void>((resolve) => {
      const transaction = this.db!.transaction([this.STORE_RESPONSES], 'readwrite');
      const store = transaction.objectStore(this.STORE_RESPONSES);
      const request = store.openCursor();
      let deleted = 0;

      request.onsuccess = (event) => {
        const cursor = (event.target as IDBRequest<IDBCursorWithValue>).result;
        if (cursor && deleted < count) {
          cursor.delete();
          deleted++;
          cursor.continue();
        } else {
          if (deleted > 0 && CACHE_CONFIG.enableLogging) {
            console.log(`Cleared ${deleted} oldest cache entries to free up space`);
          }
          resolve();
        }
      };

      request.onerror = () => {
        console.error('Failed to clear oldest entries:', request.error);
        resolve();
      };
    });
  }

  /**
   * Cleanup method to stop periodic cleanup
   * Should be called when the service is no longer needed
   */
  ngOnDestroy(): void {
    this.stopPeriodicCleanup();
  }
}
