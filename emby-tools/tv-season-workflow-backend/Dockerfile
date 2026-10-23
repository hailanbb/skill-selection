FROM node:24-bookworm-slim
WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev --ignore-scripts
COPY app ./app
COPY vendor ./vendor
COPY reference/clouddrive.proto ./reference/clouddrive.proto
ENV HOST=0.0.0.0 DATA_DIR=/data
EXPOSE 8080
CMD ["node","app/server.cjs"]
