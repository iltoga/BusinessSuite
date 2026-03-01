# Grafana Cloud Setup Guide

## This is a comprehensive guide to setting up **Grafana Alloy** to ship logs from your Dockerized applications (`bs-core`, `bs-worker`, `bs-frontend`) directly to **Grafana Cloud**

---

### Step 1: Obtain Grafana Cloud Credentials

You must use the **Grafana Cloud Portal** (account management) rather than the Grafana dashboard itself to find your connection strings.

1. Log in to [https://grafana.com/profile/org](https://grafana.com/profile/org).
2. Locate your **Stack** (application, for instance `example`).
3. Inside the stack overview, find the **Loki** card and click the **Details** button.
4. Copy and save the following values for your `.env` file:
   - **URL**: The remote write endpoint (e.g., `https://logs-prod-xxx.grafana.net/loki/api/v1/push`).
   - **User**: The User ID (a 6-7 digit number).
   - **Password/Token**: Click **Generate Token**, name it `alloy-production`, and copy the string immediately.

---

### Step 2: Create the Alloy Configuration

Create a file at `./grafana/alloy/config.alloy`. This configuration tells Alloy to look at the Docker socket, find your specific containers, and send their logs to the cloud.

```alloy
// 1. Discover all Docker containers running on the host
discovery.docker "docker_loader" {
  host = "unix:///var/run/docker.sock"
}

// 2. Filter targets: Only keep bs-core, bs-worker, and bs-frontend
discovery.relabel "bs_services" {
  targets = discovery.docker.docker_loader.targets

  // Filter: Only include containers matching our service names
  rule {
    source_labels = ["__meta_docker_container_name"]
    regex         = "/?(bs-core|bs-worker|bs-frontend)"
    action        = "keep"
  }

  // Labeling: Extract the container name as a clean 'service' label
  rule {
    source_labels = ["__meta_docker_container_name"]
    regex         = "/?(.*)"
    target_label  = "service"
  }
}

// 3. Scrape logs from the filtered Docker containers
loki.source.docker "bs_log_scraper" {
  host       = "unix:///var/run/docker.sock"
  targets    = discovery.relabel.bs_services.output
  forward_to = [loki.write.grafana_cloud.receiver]
}

// 4. Send logs to Grafana Cloud Loki
loki.write "grafana_cloud" {
  endpoint {
    url = sys.env("GRAFANA_CLOUD_LOKI_URL")

    basic_auth {
      username = sys.env("GRAFANA_CLOUD_LOKI_USER")
      password = sys.env("GRAFANA_CLOUD_LOKI_API_KEY")
    }
  }
}
```

---

### Step 3: Update Production `docker-compose.yml`

This version removes the local Loki and Grafana containers, replacing them with a single `bs-alloy` service.

```yaml
services:
  db:
    container_name: postgres-srv
    image: postgres:18
    restart: unless-stopped
    command:
      - "postgres"
      - "-c"
      - "tcp_keepalives_idle=300"
      - "-c"
      - "tcp_keepalives_interval=60"
      - "-c"
      - "tcp_keepalives_count=5"
      - "-c"
      - "idle_in_transaction_session_timeout=300000"
    environment:
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASS}
      POSTGRES_DB: ${DB_NAME}
    networks:
      - dockernet
    volumes:
      - type: bind
        source: ${DB_PATH}
        target: /var/lib/postgresql
        bind:
          propagation: rslave
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER} -d ${DB_NAME} || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    container_name: bs-redis
    image: redis:7-alpine
    restart: unless-stopped
    command:
      - "redis-server"
      - "--save"
      - "300"
      - "10"
      - "--appendonly"
      - "no"
      - "--maxmemory"
      - "200mb"
      - "--maxmemory-policy"
      - "allkeys-lru"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    volumes:
      - redis_data:/data
    networks:
      dockernet:
        ipv4_address: 192.168.2.62

  bs-core:
    container_name: bs-core
    depends_on:
      - redis
      - db
    image: bs-app:web
    build:
      context: ./
      dockerfile: Dockerfile
      target: web
    networks:
      dockernet:
        ipv4_address: 192.168.2.60
    environment:
      DB_HOST: ${DB_HOST}
      DB_PORT: ${DB_PORT}
      DB_NAME: ${DB_NAME}
      DB_USER: ${DB_USER}
      DB_PASS: ${DB_PASS}
    volumes:
      - type: bind
        source: ./
        target: /usr/src/app
        bind:
          propagation: rslave
      - type: bind
        source: ${DATA_PATH}/media
        target: /media
      - type: bind
        source: ${DATA_PATH}/db
        target: /db
      - type: bind
        source: ${DATA_PATH}/logs
        target: /logs
      - type: bind
        source: ${DATA_PATH}/staticfiles
        target: /staticfiles
      - le-certs:/etc/letsencrypt
    restart: unless-stopped

  bs-worker:
    container_name: bs-worker
    depends_on:
      - db
      - bs-core
      - redis
    image: bs-app:web
    networks:
      dockernet:
        ipv4_address: 192.168.2.63
    environment:
      DB_HOST: ${DB_HOST}
      DB_PORT: ${DB_PORT}
      DB_NAME: ${DB_NAME}
      DB_USER: ${DB_USER}
      DB_PASS: ${DB_PASS}
    volumes:
      - type: bind
        source: ./
        target: /usr/src/app
      - type: bind
        source: ${DATA_PATH}/media
        target: /media
      - type: bind
        source: ${DATA_PATH}/db
        target: /db
      - type: bind
        source: ${DATA_PATH}/logs
        target: /logs
      - type: bind
        source: ${DATA_PATH}/staticfiles
        target: /staticfiles
      - le-certs:/etc/letsencrypt
    restart: unless-stopped
    command: pgq run business_suite.pgqueue:factory

  bs-frontend:
    container_name: bs-frontend
    depends_on:
      - bs-core
    image: bs-frontend:web
    build:
      context: ./
      dockerfile: Dockerfile.frontend
    networks:
      dockernet:
        ipv4_address: 192.168.2.61
    environment:
      PORT: 4000
      BACKEND_URL: http://bs-core:8000
      CSP_ENABLED: ${CSP_ENABLED}
      CSP_MODE: ${CSP_MODE}
      LOGO_FILENAME: ${LOGO_FILENAME}
      LOGO_INVERTED_FILENAME: ${LOGO_INVERTED_FILENAME}
    restart: unless-stopped

  bs-alloy:
    container_name: bs-alloy
    image: grafana/alloy:latest
    restart: unless-stopped
    volumes:
      - ./grafana/alloy/config.alloy:/etc/alloy/config.alloy:ro
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - alloy-data:/var/lib/alloy/data
    environment:
      GRAFANA_CLOUD_LOKI_URL: ${GRAFANA_CLOUD_LOKI_URL}
      GRAFANA_CLOUD_LOKI_USER: ${GRAFANA_CLOUD_LOKI_USER}
      GRAFANA_CLOUD_LOKI_API_KEY: ${GRAFANA_CLOUD_LOKI_API_KEY}
    command:
      - run
      - --server.http.listen-addr=0.0.0.0:12345
      - --storage.path=/var/lib/alloy/data
      - /etc/alloy/config.alloy
    ports:
      - "12345:12345"
    networks:
      - dockernet

networks:
  dockernet:
    external: true

volumes:
  le-certs:
    name: le-certs
    external: true
  alloy-data:
    name: alloy-data
  redis_data:
```

---

### Step 3a: Scrape host log files (Django & Angular)

If your services write logs to files (recommended for persistence), mount the host logs directory into the Alloy container and configure a file source to pick them up. In this repository we mount `${DATA_PATH}/logs` into application containers at `/logs` (Django + workers) and into Alloy at `/host_logs`. The front-end has been updated to write its process logs to `/logs/frontend.log` so it will also be picked up.

Example Alloy file source (add to `config-local.alloy` / `config-prod.alloy`):

```alloy
// Scrape host log files (Django & Angular)
loki.source.file "host_logs" {
  paths = ["/host_logs/*.log"]
  forward_to = [loki.write.grafana_cloud.receiver]   # or loki.write.local.receiver for dev
}
```

Example `docker-compose` mounts (bs-frontend and bs-alloy):

```yaml
bs-frontend:
  volumes:
    - type: bind
      source: ${DATA_PATH}/logs
      target: /logs

bs-alloy:
  volumes:
    - type: bind
      source: ${DATA_PATH}/logs
      target: /host_logs:ro
```

Notes:

- Make sure `${DATA_PATH}/logs` exists on the host and is writable by the app containers. Alloy only needs read access so the mount can be `:ro` for extra safety.
- The Alloy config examples in this repo (`grafana/alloy/config-local.alloy` and `grafana/alloy/config-prod.alloy`) already include a `loki.source.file` block that points to `/host_logs/*.log`.

---

### Step 4: Verification and Usage

1. **Configure Environment**: Add the `GRAFANA_CLOUD_...` variables to your `.env` file on the VPS.
2. **Deploy**: Run `docker-compose up -d`.
3. **Check Alloy UI**: Navigate to `http://example.com:12345`.
   - Click on the **Graph** menu. You should see a visual path from `discovery.docker` -> `loki.write.grafana_cloud`.
   - If a block is red, click it to see the error message (usually credential issues).
4. **View Logs in Grafana Cloud**:
   - Log back into your Grafana instance (`revis.grafana.net`).
   - Go to **Explore** (compass icon).
   - Select the **Loki** datasource.
   - Use the query `{service="bs-core"}` to see your Django application logs.

### Dashboard tips & references

- Use templating variables (e.g., `service`, `level`, `logger`, `actor_username`) to make dashboards interactive and filterable. Our provided dashboard JSONs (`grafana/dashboards/`) use `label_values()` to populate these dropdowns.
- For textual logs, use the **Logs** panel and add multiple queries (one for container logs and one for host files) so you can see both sources in one place.
- Useful LogQL snippets:
  - Recent errors for a service: `{service="bs-frontend", level="error"}`
  - Parse JSON lines in the log: `{application="business_suite"} | json`
  - Count errors in the last 5 minutes: `sum(count_over_time({service="bs-core", level="error"}[5m]))`

See Grafana Loki docs for LogQL examples and best practices: <https://grafana.com/docs/loki/latest/queries/>
