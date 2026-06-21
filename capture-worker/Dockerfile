# Worker de captura — Node.js + Baileys (Etapa 1)
FROM node:22-alpine

# git: algumas dependências do Baileys são instaladas via URL git.
RUN apk add --no-cache git

WORKDIR /app

# Instala dependências primeiro (cache de build)
COPY package.json ./
RUN npm install

# Código + build TypeScript -> dist/
COPY tsconfig.json ./
COPY src ./src
RUN npm run build

# auth_state e media são montados via volume (ver docker-compose.yml)
CMD ["node", "dist/index.js"]
