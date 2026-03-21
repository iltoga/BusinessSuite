# Sync & Local-Resilience

BusinessSuite supports **local-first operation** for deployments that may lose connectivity to the central server (e.g. a Bali office running a local PostgreSQL replica that periodically syncs with a cloud hub).

## Architecture

```
  Cloud Hub (primary)          Local Node (replica)
  ┌──────────────────┐         ┌──────────────────┐
  │   PostgreSQL     │◄──push──┤   PostgreSQL     │
  │   (source)       │──pull──►│   (replica)      │
  │   Media (S3)     │◄──────►│   Media (local)   │
  └──────────────────┘         └──────────────────┘
         ▲                              ▲
         │ JWT / Bearer                 │ Bearer (LOCAL_SYNC_REMOTE_TOKEN)
         │                              │
      Angular SPA                   Angular SPA / Desktop
```

### Data Flow

1. **Capture** — Django `post_save`/`post_delete` signals write a `SyncChangeLog` row containing the serialised model payload, a SHA-256 checksum, and a `source_node` identifier.
2. **Push** — The local node POSTs its change log entries to the hub's `/api/sync/changes/push/`.
3. **Pull** — The local node GETs new entries from `/api/sync/changes/pull/?after_seq=N`.
4. **Conflict resolution** — Last-write-wins by `source_timestamp`; ties broken by `source_node` string comparison. Conflicts are recorded in `SyncConflict` for manual review.
5. **Media sync** — `/api/sync/media/manifest/` lists files with checksums; `/api/sync/media/fetch/` downloads binary content.

### Re-entrant Guard

`sync_apply_context()` sets a `ContextVar` so signal handlers can detect an ongoing sync apply and skip re-logging that change — preventing infinite replication loops.

## Models

| Model                     | Purpose                                                           |
| ------------------------- | ----------------------------------------------------------------- |
| `LocalResilienceSettings` | Singleton config (enabled, encryption, mode, vault epoch)         |
| `SyncChangeLog`           | Append-only log of upsert/delete operations with sequence numbers |
| `SyncCursor`              | Per-node tracking of last pulled/pushed sequence                  |
| `SyncConflict`            | Records conflicts for manual review (pending/reviewed status)     |
| `MediaManifestEntry`      | Tracks media files with checksums for binary sync                 |

All models are in `core/models/local_resilience.py`.

## API Endpoints

All sync endpoints live under `/api/sync/` and require either:

- An authenticated superuser/admin group user, **or**
- A `Bearer` token matching `LOCAL_SYNC_REMOTE_TOKEN`

| Method | Path                        | Purpose                                                           |
| ------ | --------------------------- | ----------------------------------------------------------------- |
| GET    | `/api/sync/state/`          | Current node ID, last seq, pending conflicts, cursor info         |
| POST   | `/api/sync/changes/push/`   | Ingest remote changes (body: `{sourceNode, changes}`)             |
| GET    | `/api/sync/changes/pull/`   | Pull local changes after a sequence (query: `after_seq`, `limit`) |
| GET    | `/api/sync/media/manifest/` | List media entries (query: `after_updated_at`, `limit`)           |
| POST   | `/api/sync/media/fetch/`    | Download media binary content (body: `{paths, includeContent}`)   |

## Configuration

All settings are in `business_suite/settings/base.py`:

| Env Variable                         | Default    | Description                                |
| ------------------------------------ | ---------- | ------------------------------------------ |
| `LOCAL_SYNC_ENABLED`                 | `False`    | Master toggle for sync feature             |
| `LOCAL_SYNC_NODE_ID`                 | `hostname` | Unique identifier for this deployment node |
| `LOCAL_SYNC_REMOTE_BASE_URL`         | (empty)    | Hub URL for push/pull operations           |
| `LOCAL_SYNC_REMOTE_TOKEN`            | (empty)    | Shared secret for service-to-service auth  |
| `LOCAL_SYNC_PUSH_LIMIT`              | `200`      | Max changes per push batch                 |
| `LOCAL_SYNC_PULL_LIMIT`              | `200`      | Max changes per pull batch                 |
| `LOCAL_SYNC_REQUEST_TIMEOUT_SECONDS` | `10`       | HTTP timeout for sync requests             |

## Desktop Mode

`LocalResilienceSettings` supports two modes:

- **`local_primary`** — Local node is authoritative; pushes to hub.
- **`remote_primary`** — Hub is authoritative; local node pulls.

The Electron desktop app (`desktop/`) connects to a local backend running these sync services.

## Service Layer

Core logic in `core/services/sync_service.py`:

- `get_local_node_id()` — Returns node identifier.
- `capture_model_upsert(instance)` — Record a model save.
- `capture_model_delete(model_label, object_pk)` — Record a model deletion.
- `pull_changes(after_seq, limit)` — Query local change log.
- `ingest_remote_changes(source_node, changes)` — Apply remote changes with conflict detection.
- `get_media_manifest()` / `refresh_media_manifest()` — Media file tracking.
- `fetch_media_entries(paths, include_content)` — Read media binary content.

## Testing

```bash
cd backend && DJANGO_TESTING=1 uv run pytest core/tests/test_local_resilience_service.py -v
cd backend && DJANGO_TESTING=1 uv run pytest core/tests/test_sync_service_media_manifest.py -v
```
