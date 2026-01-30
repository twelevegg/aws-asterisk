# =============================================================================
# Stasis App - Asterisk ARI Client (Node.js)
# =============================================================================
FROM node:18-alpine

WORKDIR /app

# 의존성 파일 복사
COPY package*.json ./

# 의존성 설치
RUN npm ci --only=production

# 애플리케이션 코드 복사
COPY . .

# 비root 사용자로 실행
RUN addgroup -g 1001 -S nodejs && \
    adduser -S nodejs -u 1001 -G nodejs && \
    chown -R nodejs:nodejs /app

USER nodejs

# 실행
CMD ["node", "app.js"]
