FROM node:21-slim

RUN apt update && apt install -y curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . .
RUN rm -rf /app/public/images && ln -s /app/shared/images /app/public/images

RUN npm install

CMD ["npm", "run", "start"]
