#!/bin/bash
set -e

echo "============================================"
echo "  n8n 셀프호스팅 원클릭 설치"
echo "============================================"

# ──────────────────────────────────
# 0. 변수 설정 (비밀번호/키 자동 생성)
# ──────────────────────────────────
N8N_DIR="/opt/n8n"
DOMAIN="n8n.example.com"
ENCRYPTION_KEY=$(openssl rand -hex 32)
DB_PASSWORD=$(openssl rand -hex 16)
ADMIN_PASSWORD=$(openssl rand -base64 18 | tr -dc 'A-Za-z0-9' | head -c 20)

echo ""
echo "[INFO] 생성된 비밀번호들 (반드시 메모하세요!):"
echo "  DB Password      : $DB_PASSWORD"
echo "  Admin Password   : $ADMIN_PASSWORD"
echo "  Encryption Key   : $ENCRYPTION_KEY"
echo ""

# ──────────────────────────────────
# 1. 기존 n8n 정리
# ──────────────────────────────────
echo "[1/8] 기존 n8n 정리..."
(cd $N8N_DIR 2>/dev/null && docker compose down 2>/dev/null) || true
sudo systemctl stop n8n 2>/dev/null || true

# ──────────────────────────────────
# 2. 디렉토리 생성
# ──────────────────────────────────
echo "[2/8] 디렉토리 생성..."
sudo mkdir -p $N8N_DIR/{n8n_data,postgres_data,caddy_data,caddy_config,backups}
sudo chown -R 1000:1000 $N8N_DIR/n8n_data

# ──────────────────────────────────
# 3. .env 파일 생성
# ──────────────────────────────────
echo "[3/8] .env 파일 생성..."
sudo tee $N8N_DIR/.env > /dev/null << ENVEOF
# ============================================
# n8n 기본 설정 (도메인 변경 시 DOMAIN_NAME, WEBHOOK_URL 수정)
# ============================================
DOMAIN_NAME=${DOMAIN}
N8N_HOST=0.0.0.0
N8N_PORT=5678
N8N_PROTOCOL=https
WEBHOOK_URL=https://${DOMAIN}/

# ============================================
# 보안
# ============================================
N8N_BASIC_AUTH_ACTIVE=true
N8N_BASIC_AUTH_USER=admin
N8N_BASIC_AUTH_PASSWORD=${ADMIN_PASSWORD}
N8N_ENCRYPTION_KEY=${ENCRYPTION_KEY}

# ============================================
# PostgreSQL
# ============================================
DB_TYPE=postgresdb
DB_POSTGRESDB_HOST=postgres
DB_POSTGRESDB_PORT=5432
DB_POSTGRESDB_DATABASE=n8n
DB_POSTGRESDB_USER=n8n
DB_POSTGRESDB_PASSWORD=${DB_PASSWORD}
POSTGRES_DB=n8n
POSTGRES_USER=n8n
POSTGRES_PASSWORD=${DB_PASSWORD}
POSTGRES_NON_ROOT_USER=n8n
POSTGRES_NON_ROOT_PASSWORD=${DB_PASSWORD}

# ============================================
# 실행 설정
# ============================================
EXECUTIONS_MODE=regular
EXECUTIONS_DATA_SAVE_ON_ERROR=all
EXECUTIONS_DATA_SAVE_ON_SUCCESS=all
EXECUTIONS_DATA_SAVE_ON_PROGRESS=true
EXECUTIONS_DATA_SAVE_MANUAL_EXECUTIONS=true
EXECUTIONS_DATA_PRUNE=true
EXECUTIONS_DATA_MAX_AGE=720

# ============================================
# 기타
# ============================================
N8N_PAYLOAD_SIZE_MAX=64
N8N_METRICS=true
N8N_DIAGNOSTICS_ENABLED=false
N8N_HIRING_BANNER_ENABLED=false
N8N_COMMUNITY_PACKAGES_ENABLED=true
N8N_RUNNERS_ENABLED=true
GENERIC_TIMEZONE=Asia/Seoul
TZ=Asia/Seoul
ENVEOF

# ──────────────────────────────────
# 4. docker-compose.yml 생성
# ──────────────────────────────────
echo "[4/8] docker-compose.yml 생성..."
sudo tee $N8N_DIR/docker-compose.yml > /dev/null << 'DCEOF'
services:
  postgres:
    image: postgres:16-alpine
    restart: always
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - ./postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - n8n-network

  n8n:
    image: docker.n8n.io/n8nio/n8n:latest
    restart: always
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      - N8N_HOST=${N8N_HOST}
      - N8N_PORT=${N8N_PORT}
      - N8N_PROTOCOL=${N8N_PROTOCOL}
      - WEBHOOK_URL=${WEBHOOK_URL}
      - N8N_BASIC_AUTH_ACTIVE=${N8N_BASIC_AUTH_ACTIVE}
      - N8N_BASIC_AUTH_USER=${N8N_BASIC_AUTH_USER}
      - N8N_BASIC_AUTH_PASSWORD=${N8N_BASIC_AUTH_PASSWORD}
      - N8N_ENCRYPTION_KEY=${N8N_ENCRYPTION_KEY}
      - DB_TYPE=${DB_TYPE}
      - DB_POSTGRESDB_HOST=${DB_POSTGRESDB_HOST}
      - DB_POSTGRESDB_PORT=${DB_POSTGRESDB_PORT}
      - DB_POSTGRESDB_DATABASE=${DB_POSTGRESDB_DATABASE}
      - DB_POSTGRESDB_USER=${DB_POSTGRESDB_USER}
      - DB_POSTGRESDB_PASSWORD=${DB_POSTGRESDB_PASSWORD}
      - EXECUTIONS_MODE=${EXECUTIONS_MODE}
      - EXECUTIONS_DATA_SAVE_ON_ERROR=${EXECUTIONS_DATA_SAVE_ON_ERROR}
      - EXECUTIONS_DATA_SAVE_ON_SUCCESS=${EXECUTIONS_DATA_SAVE_ON_SUCCESS}
      - EXECUTIONS_DATA_SAVE_ON_PROGRESS=${EXECUTIONS_DATA_SAVE_ON_PROGRESS}
      - EXECUTIONS_DATA_SAVE_MANUAL_EXECUTIONS=${EXECUTIONS_DATA_SAVE_MANUAL_EXECUTIONS}
      - EXECUTIONS_DATA_PRUNE=${EXECUTIONS_DATA_PRUNE}
      - EXECUTIONS_DATA_MAX_AGE=${EXECUTIONS_DATA_MAX_AGE}
      - N8N_PAYLOAD_SIZE_MAX=${N8N_PAYLOAD_SIZE_MAX}
      - N8N_METRICS=${N8N_METRICS}
      - N8N_DIAGNOSTICS_ENABLED=${N8N_DIAGNOSTICS_ENABLED}
      - N8N_HIRING_BANNER_ENABLED=${N8N_HIRING_BANNER_ENABLED}
      - N8N_COMMUNITY_PACKAGES_ENABLED=${N8N_COMMUNITY_PACKAGES_ENABLED}
      - N8N_RUNNERS_ENABLED=${N8N_RUNNERS_ENABLED}
      - GENERIC_TIMEZONE=${GENERIC_TIMEZONE}
      - TZ=${TZ}
    ports:
      - "5678:5678"
    volumes:
      - ./n8n_data:/home/node/.n8n
    extra_hosts:
      - "host.docker.internal:host-gateway"
    networks:
      - n8n-network

  caddy:
    image: caddy:2-alpine
    restart: always
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - ./caddy_data:/data
      - ./caddy_config:/config
    networks:
      - n8n-network

networks:
  n8n-network:
    driver: bridge
DCEOF

# ──────────────────────────────────
# 5. Caddyfile 생성
# ──────────────────────────────────
echo "[5/8] Caddyfile 생성..."
sudo tee $N8N_DIR/Caddyfile > /dev/null << CADDYEOF
${DOMAIN} {
    reverse_proxy n8n:5678

    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
    }
}
CADDYEOF

# ──────────────────────────────────
# 6. 백업 스크립트 + cron 등록
# ──────────────────────────────────
echo "[6/8] 백업 스크립트 + cron 등록..."
sudo tee $N8N_DIR/backup.sh > /dev/null << 'BKEOF'
#!/bin/bash
BACKUP_DIR="/opt/n8n/backups"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR
docker compose -f /opt/n8n/docker-compose.yml exec -T postgres pg_dump -U n8n n8n > "$BACKUP_DIR/db_$DATE.sql"
docker compose -f /opt/n8n/docker-compose.yml exec -T n8n n8n export:workflow --all --output="/home/node/.n8n/backups/workflows_$DATE.json" 2>/dev/null || true
docker compose -f /opt/n8n/docker-compose.yml exec -T n8n n8n export:credentials --all --output="/home/node/.n8n/backups/creds_$DATE.json" 2>/dev/null || true
find $BACKUP_DIR -type f -mtime +7 -delete
echo "[$DATE] Backup completed"
BKEOF
sudo chmod +x $N8N_DIR/backup.sh
(crontab -l 2>/dev/null | grep -v "$N8N_DIR/backup.sh"; echo "0 3 * * * $N8N_DIR/backup.sh >> $N8N_DIR/backups/backup.log 2>&1") | crontab -

# ──────────────────────────────────
# 7. IP 폴백 / 도메인 복귀 스크립트
# ──────────────────────────────────
echo "[7/8] 전환 스크립트 생성..."

# IP 모드 전환
sudo tee $N8N_DIR/switch-to-ip.sh > /dev/null << 'IPEOF'
#!/bin/bash
cd /opt/n8n
SERVER_IP=$(hostname -I | awk '{print $1}')
sed -i "s|N8N_PROTOCOL=https|N8N_PROTOCOL=http|" .env
sed -i "s|WEBHOOK_URL=.*|WEBHOOK_URL=http://${SERVER_IP}:5678/|" .env
cat > docker-compose.override.yml << OVEOF
services:
  caddy:
    profiles:
      - disabled
OVEOF
docker compose down
docker compose up -d
echo ""
echo "=== IP 모드로 전환 완료 ==="
echo "접속: http://${SERVER_IP}:5678"
echo ""
IPEOF
sudo chmod +x $N8N_DIR/switch-to-ip.sh

# 도메인 모드 복귀
sudo tee $N8N_DIR/switch-to-domain.sh > /dev/null << 'DMEOF'
#!/bin/bash
cd /opt/n8n
source .env
sed -i "s|N8N_PROTOCOL=http|N8N_PROTOCOL=https|" .env
sed -i "s|WEBHOOK_URL=.*|WEBHOOK_URL=https://${DOMAIN_NAME}/|" .env
rm -f docker-compose.override.yml
docker compose down
docker compose up -d
echo ""
echo "=== 도메인 모드로 복귀 완료 ==="
echo "접속: https://${DOMAIN_NAME}"
echo ""
DMEOF
sudo chmod +x $N8N_DIR/switch-to-domain.sh

# ──────────────────────────────────
# 8. 방화벽 + 실행
# ──────────────────────────────────
echo "[8/8] 방화벽 설정 + n8n 실행..."
sudo ufw allow 80/tcp 2>/dev/null || true
sudo ufw allow 443/tcp 2>/dev/null || true
sudo ufw allow 5678/tcp 2>/dev/null || true

cd $N8N_DIR
docker compose pull
docker compose up -d

# 기동 대기
echo ""
echo "n8n 기동 대기 중..."
sleep 10

# 상태 확인
docker compose ps

# ──────────────────────────────────
# 완료 메시지
# ──────────────────────────────────
SERVER_IP=$(hostname -I | awk '{print $1}')
echo ""
echo "============================================"
echo "  n8n 설치 완료!"
echo "============================================"
echo ""
echo "  도메인 접속  : https://${DOMAIN}"
echo "  IP 폴백 접속 : http://${SERVER_IP}:5678"
echo ""
echo "  Admin User     : admin"
echo "  Admin Pass     : ${ADMIN_PASSWORD}"
echo "  DB Password    : ${DB_PASSWORD}"
echo "  Encryption Key : ${ENCRYPTION_KEY}"
echo ""
echo "  FastAPI 연동   : n8n HTTP Request 노드에서"
echo "                   http://host.docker.internal:8000 사용"
echo ""
echo "  도메인 안 될 때 : sudo bash $N8N_DIR/switch-to-ip.sh"
echo "  도메인 복귀     : sudo bash $N8N_DIR/switch-to-domain.sh"
echo ""
echo "  로그 확인  : cd $N8N_DIR && docker compose logs -f n8n"
echo "  중지       : cd $N8N_DIR && docker compose down"
echo "  재시작     : cd $N8N_DIR && docker compose restart"
echo "  업그레이드 : cd $N8N_DIR && docker compose pull && docker compose up -d"
echo "  수동 백업  : sudo bash $N8N_DIR/backup.sh"
echo ""
echo "  [중요] 위 비밀번호들을 안전한 곳에 저장하세요!"
echo "  [중요] 도메인 사용 시 .env의 DOMAIN_NAME을 실제 도메인으로 변경 후"
echo "         Caddyfile도 함께 수정하고 docker compose restart 하세요"
echo "============================================"
