# Production Invoice Import Timeout Fix

## Problem
Invoice imports were failing on the production server with `SystemExit: 1` errors. The issue was caused by Gunicorn worker timeouts during long-running OpenAI/OpenRouter API calls (especially for vision/multimodal invoice parsing).

**Error Pattern:**
```
File "/usr/local/lib/python3.13/site-packages/gunicorn/workers/base.py", line 204, in handle_abort
    sys.exit(1)
SystemExit: 1
```

## Root Causes
1. **Gunicorn default timeout**: 30 seconds (too short for LLM API calls)
2. **OpenAI client had no timeout**: Could hang indefinitely
3. **Vision model processing**: Can take 60-120 seconds for complex invoices

## Solutions Applied

### 1. OpenAI Client Timeout Configuration
**File:** `invoices/services/llm_invoice_parser.py`

Added explicit timeout settings to the OpenAI client initialization:

```python
# For OpenRouter
timeout = getattr(settings, "OPENROUTER_TIMEOUT", 120.0)
self.client = OpenAI(
    api_key=self.api_key,
    base_url=base_url,
    timeout=timeout,  # NEW: 120 second timeout
)

# For OpenAI
timeout = getattr(settings, "OPENAI_TIMEOUT", 120.0)
self.client = OpenAI(
    api_key=self.api_key,
    timeout=timeout,  # NEW: 120 second timeout
)
```

### 2. Gunicorn Worker Timeout Increase
**File:** `start.sh`

Updated Gunicorn command with production-ready settings:

```bash
gunicorn business_suite.wsgi:application \
  --bind 0.0.0.0:8000 \
  --timeout 180 \          # NEW: 3 minutes (was 30s default)
  --workers 2 \             # NEW: Multiple workers for better concurrency
  --threads 2 \             # NEW: Multiple threads per worker
  --worker-class sync \     # Sync workers for Django
  --log-file - \
  --access-logfile - \
  --error-logfile - \
  --log-level info
```

### 3. Settings Configuration
**File:** `business_suite/settings/prod.py`

Added configurable timeout settings:

```python
# OpenRouter / OpenAI API Configuration
OPENROUTER_TIMEOUT = float(os.getenv("OPENROUTER_TIMEOUT", "120.0"))
OPENAI_TIMEOUT = float(os.getenv("OPENAI_TIMEOUT", "120.0"))
```

## Configuration Options

### Environment Variables (.env)
You can override the default timeouts:

```bash
# Optional: Adjust LLM API timeouts (default: 120 seconds)
OPENROUTER_TIMEOUT=120.0
OPENAI_TIMEOUT=120.0
```

### Gunicorn Settings Explained

| Setting | Value | Purpose |
|---------|-------|---------|
| `--timeout` | 180s | Max time for a request (covers LLM API + processing) |
| `--workers` | 2 | Number of processes (adjust based on CPU cores) |
| `--threads` | 2 | Threads per worker for I/O-bound tasks |
| `--worker-class` | sync | Standard sync workers (suitable for Django) |

**Worker/Thread Guidelines:**
- Workers: `(2 × CPU_cores) + 1` for CPU-bound workloads
- For this app: 2-4 workers is sufficient (I/O-bound due to LLM API calls)
- Threads: 2-4 per worker for better concurrent request handling

## Testing

### Local Testing
```bash
# Test with default settings
./start.sh

# Test invoice import with timing
curl -X POST http://localhost:8000/invoices/import/batch/ \
  -F "files=@invoice.pdf" \
  -H "Authorization: Token YOUR_TOKEN" \
  -v
```

### Production Deployment
1. **Rebuild Docker image:**
   ```bash
   docker-compose build bs-core
   ```

2. **Restart services:**
   ```bash
   docker-compose down
   docker-compose up -d
   ```

3. **Monitor logs:**
   ```bash
   docker-compose logs -f bs-core
   ```

Look for log messages:
- ✅ `Initialized LLM parser with OpenRouter (model: openai/gpt-5-mini, timeout: 120.0s)`
- ✅ `[INFO] Booting worker with pid: XXX`
- ✅ Successfully processed invoices without `SystemExit` errors

## Monitoring

### Check Worker Health
```bash
# View Gunicorn worker processes
docker exec bs-core ps aux | grep gunicorn

# Check for worker restarts (should be minimal)
docker logs bs-core 2>&1 | grep "Worker"
```

### Performance Metrics
- **Normal invoice import**: 10-30 seconds
- **Complex/vision processing**: 30-90 seconds
- **Timeout threshold**: 180 seconds (3 minutes)

## Troubleshooting

### If imports still timeout:

1. **Increase Gunicorn timeout:**
   ```bash
   # In start.sh, change:
   --timeout 300  # 5 minutes
   ```

2. **Increase LLM API timeout:**
   ```bash
   # In .env, add:
   OPENROUTER_TIMEOUT=180.0
   ```

3. **Check network connectivity:**
   ```bash
   docker exec bs-core curl -I https://openrouter.ai/api/v1
   ```

4. **Review logs for API errors:**
   ```bash
   docker logs bs-core 2>&1 | grep -A 10 "Error parsing invoice"
   ```

### Memory Issues
If workers are killed due to memory:
- Reduce `--workers` count
- Monitor with `docker stats bs-core`
- Consider increasing container memory limits

## Rollback
If issues occur, revert to previous configuration:

```bash
# In start.sh, restore old command:
gunicorn business_suite.wsgi:application --bind 0.0.0.0:8000 --log-file -

# Rebuild and restart
docker-compose build bs-core
docker-compose restart bs-core
```

## Additional Optimizations

### For High-Volume Production:

1. **Use Gunicorn with gevent workers** (async I/O):
   ```bash
   gunicorn business_suite.wsgi:application \
     --bind 0.0.0.0:8000 \
     --timeout 180 \
     --workers 4 \
     --worker-class gevent \
     --worker-connections 1000
   ```

2. **Add Celery for background processing:**
   - Move invoice imports to async Celery tasks
   - Immediate response to user, process in background
   - Better for large batch imports

3. **Enable HTTP keep-alive:**
   ```bash
   --keep-alive 5
   ```

## References
- Gunicorn docs: https://docs.gunicorn.org/en/stable/settings.html
- OpenAI Python SDK: https://github.com/openai/openai-python
- Django deployment: https://docs.djangoproject.com/en/5.2/howto/deployment/
