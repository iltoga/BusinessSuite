import { TestBed } from '@angular/core/testing';
import { CacheService, CachedResponse } from './cache.service';
import * as fc from 'fast-check';
import 'fake-indexeddb/auto';

/**
 * Test suite for CacheService
 * 
 * Includes:
 * - Property-based tests using fast-check (Properties 20, 21, 23)
 * - Unit tests for core functionality
 * 
 * Requirements tested:
 * - 7.1: IndexedDB storage and retrieval
 * - 7.2: Cache keys include user identity and version
 * - 7.4: TTL expiration
 * - 7.6: Clear cache methods
 */
describe('CacheService', () => {
  let service: CacheService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(CacheService);
  });

  afterEach(async () => {
    // Clean up IndexedDB after each test
    await service.clear();
  });

  describe('Property-Based Tests', () => {
    /**
     * Property 20: IndexedDB storage and retrieval
     * Validates: Requirements 7.1
     * 
     * Test: Store data with key, retrieve by key, verify same data
     */
    it('Property 20: should store and retrieve data correctly', async () => {
      await fc.assert(
        fc.asyncProperty(
          fc.string({ minLength: 1, maxLength: 100 }), // key
          fc.anything(), // data
          fc.integer({ min: 1, max: 3600 }), // ttl in seconds
          async (key, data, ttl) => {
            // Store data
            await service.set(key, data, ttl);

            // Retrieve data
            const cached = await service.get(key);

            // Verify data matches
            expect(cached).not.toBeNull();
            expect(cached?.key).toBe(key);
            expect(cached?.data).toEqual(data);
            expect(cached?.expiresAt).toBeGreaterThan(Date.now());
          }
        ),
        { numRuns: 50 }
      );
    });

    /**
     * Property 21: IndexedDB key format
     * Validates: Requirements 7.2
     * 
     * Test: Verify cache keys include user identity and version
     */
    it('Property 21: should include user identity and version in cached response', async () => {
      await fc.assert(
        fc.asyncProperty(
          fc.string({ minLength: 1, maxLength: 100 }), // key
          fc.integer({ min: 1, max: 1000000 }), // userId
          fc.integer({ min: 1, max: 100 }), // version
          fc.anything(), // data
          fc.integer({ min: 60, max: 3600 }), // ttl
          async (key, userId, version, data, ttl) => {
            // Store data with userId and version
            await service.set(key, data, ttl, userId, version);

            // Retrieve data
            const cached = await service.get(key);

            // Verify userId and version are stored
            expect(cached).not.toBeNull();
            expect(cached?.userId).toBe(userId);
            expect(cached?.version).toBe(version);
          }
        ),
        { numRuns: 50 }
      );
    });

    /**
     * Property 23: IndexedDB TTL expiration
     * Validates: Requirements 7.4
     * 
     * Test: Store with TTL, advance time, verify not returned
     */
    it('Property 23: should not return expired entries', async () => {
      await fc.assert(
        fc.asyncProperty(
          fc.string({ minLength: 1, maxLength: 100 }), // key
          fc.anything(), // data
          async (key, data) => {
            // Store with very short TTL (1 second)
            const ttl = 1;
            await service.set(key, data, ttl);

            // Verify data is initially available
            let cached = await service.get(key);
            expect(cached).not.toBeNull();

            // Wait for expiration (1.5 seconds to ensure expiration)
            await new Promise(resolve => setTimeout(resolve, 1500));

            // Verify data is no longer returned
            cached = await service.get(key);
            expect(cached).toBeNull();
          }
        ),
        { numRuns: 5 } // Fewer runs due to time delays (5 runs * 1.5s = 7.5s)
      );
    }, 15000); // 15 second timeout for this test
  });

  describe('Unit Tests', () => {
    /**
     * Test: IndexedDB initialization and schema creation
     * Requirements: 7.1
     */
    it('should initialize IndexedDB with correct schema', async () => {
      const key = 'test-key';
      const data = { test: 'data' };
      const ttl = 300;

      // Trigger initialization by storing data
      await service.set(key, data, ttl);

      // Verify we can retrieve the data (confirms schema is correct)
      const cached = await service.get(key);
      expect(cached).not.toBeNull();
      expect(cached?.data).toEqual(data);
    });

    /**
     * Test: get returns null for non-existent keys
     * Requirements: 7.1
     */
    it('should return null for non-existent keys', async () => {
      const cached = await service.get('non-existent-key');
      expect(cached).toBeNull();
    });

    /**
     * Test: set stores data correctly
     * Requirements: 7.1
     */
    it('should store data with all required fields', async () => {
      const key = 'test-key';
      const data = { message: 'Hello, World!' };
      const ttl = 300;
      const userId = 123;
      const version = 5;

      await service.set(key, data, ttl, userId, version);

      const cached = await service.get(key);
      expect(cached).not.toBeNull();
      expect(cached?.key).toBe(key);
      expect(cached?.data).toEqual(data);
      expect(cached?.userId).toBe(userId);
      expect(cached?.version).toBe(version);
      expect(cached?.timestamp).toBeLessThanOrEqual(Date.now());
      expect(cached?.expiresAt).toBeGreaterThan(Date.now());
    });

    /**
     * Test: clear removes all entries
     * Requirements: 7.6
     */
    it('should clear all cache entries', async () => {
      // Store multiple entries
      await service.set('key1', 'data1', 300);
      await service.set('key2', 'data2', 300);
      await service.set('key3', 'data3', 300);

      // Verify entries exist
      expect(await service.get('key1')).not.toBeNull();
      expect(await service.get('key2')).not.toBeNull();
      expect(await service.get('key3')).not.toBeNull();

      // Clear cache
      await service.clear();

      // Verify all entries are gone
      expect(await service.get('key1')).toBeNull();
      expect(await service.get('key2')).toBeNull();
      expect(await service.get('key3')).toBeNull();
    });

    /**
     * Test: clearByVersion removes only matching version
     * Requirements: 7.6
     */
    it('should clear only entries matching the specified version', async () => {
      // Store entries with different versions
      await service.set('key1', 'data1', 300, 1, 5);
      await service.set('key2', 'data2', 300, 1, 5);
      await service.set('key3', 'data3', 300, 1, 6);

      // Clear version 5
      await service.clearByVersion(5);

      // Verify version 5 entries are gone
      expect(await service.get('key1')).toBeNull();
      expect(await service.get('key2')).toBeNull();

      // Verify version 6 entry still exists
      expect(await service.get('key3')).not.toBeNull();
    });

    /**
     * Test: expired entries not returned
     * Requirements: 7.4
     */
    it('should not return expired entries', async () => {
      const key = 'expiring-key';
      const data = 'expiring-data';
      const ttl = 1; // 1 second

      await service.set(key, data, ttl);

      // Verify data is initially available
      let cached = await service.get(key);
      expect(cached).not.toBeNull();

      // Wait for expiration
      await new Promise(resolve => setTimeout(resolve, 1500));

      // Verify data is no longer returned
      cached = await service.get(key);
      expect(cached).toBeNull();
    });

    /**
     * Test: version management
     * Requirements: 7.2
     */
    it('should get and set cache version', async () => {
      // Initial version should be 1
      let version = await service.getVersion();
      expect(version).toBe(1);

      // Set new version
      await service.setVersion(10);

      // Verify version was updated
      version = await service.getVersion();
      expect(version).toBe(10);
    });

    /**
     * Test: default userId and version when not provided
     * Requirements: 7.1, 7.2
     */
    it('should use default userId and current version when not provided', async () => {
      const key = 'test-key';
      const data = 'test-data';
      const ttl = 300;

      // Set version first
      await service.setVersion(7);

      // Store without userId and version
      await service.set(key, data, ttl);

      const cached = await service.get(key);
      expect(cached).not.toBeNull();
      expect(cached?.userId).toBe(0); // Default userId
      expect(cached?.version).toBe(7); // Current version
    });

    /**
     * Test: multiple entries with same key but different versions
     * Requirements: 7.2, 7.6
     */
    it('should handle multiple entries with same key but different versions', async () => {
      const key = 'same-key';
      
      // Store with version 1
      await service.set(key, 'data-v1', 300, 1, 1);
      
      // Store with version 2 (overwrites due to same key)
      await service.set(key, 'data-v2', 300, 1, 2);

      // Only the latest entry should exist
      const cached = await service.get(key);
      expect(cached).not.toBeNull();
      expect(cached?.data).toBe('data-v2');
      expect(cached?.version).toBe(2);
    });

    /**
     * Test: complex data structures
     * Requirements: 7.1
     */
    it('should handle complex data structures', async () => {
      const key = 'complex-key';
      const complexData = {
        string: 'test',
        number: 42,
        boolean: true,
        null: null,
        array: [1, 2, 3],
        nested: {
          deep: {
            value: 'nested'
          }
        }
      };
      const ttl = 300;

      await service.set(key, complexData, ttl);

      const cached = await service.get(key);
      expect(cached).not.toBeNull();
      expect(cached?.data).toEqual(complexData);
    });

    /**
     * Test: timestamp and expiresAt calculation
     * Requirements: 7.4
     */
    it('should correctly calculate timestamp and expiresAt', async () => {
      const key = 'time-key';
      const data = 'time-data';
      const ttl = 300; // 5 minutes
      const beforeStore = Date.now();

      await service.set(key, data, ttl);

      const cached = await service.get(key);
      const afterStore = Date.now();

      expect(cached).not.toBeNull();
      expect(cached?.timestamp).toBeGreaterThanOrEqual(beforeStore);
      expect(cached?.timestamp).toBeLessThanOrEqual(afterStore);
      expect(cached?.expiresAt).toBeGreaterThanOrEqual(beforeStore + (ttl * 1000));
      expect(cached?.expiresAt).toBeLessThanOrEqual(afterStore + (ttl * 1000));
    });
  });
});
